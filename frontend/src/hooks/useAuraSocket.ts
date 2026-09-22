import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ActivityEvent,
  AuraState,
  ChatTurn,
  ClientMessage,
  ConnStatus,
  Presence,
  QuestEvent,
  ServerMessage,
  TurnAttachment,
  V3Event,
} from "../types";
import { useNotifyStore } from "../stores/notifyStore";
import { useSavedStore } from "../stores/savedStore";
import { rosterNow, useRosterStore } from "../stores/rosterStore";
import { maskSecrets } from "../lib/secrets";

// How many live V3 events to keep in memory. The panel also fetches history
// from /api/v3/snapshot on mount, so this is only the live tail.
const V3_BUFFER = 40;

const DEFAULT_URL = "ws://127.0.0.1:8760/ws";

function newId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// Hand AURA's words to the floating orb. The main process drops it unless the
// window is minimized or covered, so this is safe to call on every message.
function tellOrb(text: string | undefined): void {
  const plain = (text || "").replace(/```[\s\S]*?```/g, " ").replace(/\*\*|__|`/g, "").trim();
  if (plain) window.aura?.orbNotify?.(plain);
}

function nowTime(): string {
  return new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

// Map the model id the brain reports (e.g. "openai/gpt-oss-120b") to its
// planet in data/models.ts, so the node that answered lights up ACTIVE. Exact
// ids only: the old substring guesses sent every GPT-OSS answer to a GPT-4o
// planet AURA never routed to. Installed planets report "ext:<n>".
function modelIdToNode(model: string): string | null {
  return rosterNow().find((m) => m.modelId === model)?.id ?? null;
}

export interface SendOptions {
  /** Saved Info ids shared with this message (uploaded files). */
  attachments?: TurnAttachment[];
  /** "Ask AURA" from the Saved Info page pins the explain lane. */
  intent?: "EXPLAIN";
}

/**
 * Single WebSocket to the AURA brain. Handles request/response streaming,
 * unsolicited auto-chat pushes (proactive/curiosity/greeting), presence, the
 * animation state, and which model last answered. Auto-reconnects.
 *
 * State updaters are PURE - the in-progress AURA turn is found by position/flag,
 * never a mutable ref (which breaks under React StrictMode's double-invoke).
 */
export function useAuraSocket(url: string = window.aura?.bridgeUrl ?? DEFAULT_URL) {
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const [auraState, setAuraState] = useState<AuraState>("idle");
  const [presence, setPresence] = useState<Presence>("idle");
  const [mode, setMode] = useState<string>("CHAT");
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [v3Events, setV3Events] = useState<V3Event[]>([]);
  // Only the latest quest event is kept — the Quests tab re-fetches the board
  // when it changes, so a full history here would just be duplicate state.
  const [questEvent, setQuestEvent] = useState<QuestEvent | null>(null);
  // The live "what is AURA doing" line. Cleared automatically when the brain
  // goes back to idle after an answer completes.
  const [activity, setActivity] = useState<ActivityEvent | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const appendChunk = useCallback((text: string) => {
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "aura" && last.streaming) {
        return [...prev.slice(0, -1), { ...last, text: last.text + text }];
      }
      return [...prev, { id: newId(), role: "aura", text, streaming: true, ts: nowTime() }];
    });
  }, []);

  // On "done" the backend sends the REFINED final text (guard-cleaned, with
  // code blocks). Replace the raw streamed text with it so backend context
  // (intent analysis, screen info, etc.) never survives in the chat bubble.
  const finishStream = useCallback((finalText?: string) => {
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "aura" && last.streaming) {
        const text = finalText && finalText.trim() ? finalText : last.text;
        return [...prev.slice(0, -1), { ...last, text, streaming: false }];
      }
      // No streamed chunks arrived (e.g. instant rate-limit / error reply
      // resolved without streaming) - still show the final text.
      if (finalText && finalText.trim()) {
        return [...prev, { id: newId(), role: "aura", text: finalText, streaming: false, ts: nowTime() }];
      }
      return prev;
    });
  }, []);

  // Unsolicited AURA message - always a fresh, complete bubble.
  const pushMessage = useCallback((text: string, source: string) => {
    setTurns((prev) => [...prev, { id: newId(), role: "aura", text, streaming: false, source, ts: nowTime() }]);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => mountedRef.current && setStatus("open");

    ws.onmessage = (ev) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      switch (msg.type) {
        case "state":
          setAuraState(msg.payload.state);
          // Back to idle → the current activity line has played out.
          if (msg.payload.state === "idle") setActivity(null);
          break;
        case "activity":
          setActivity(msg.payload);
          useNotifyStore.getState().add(msg.payload.kind || "info", msg.payload.text);
          break;
        case "chunk":
          appendChunk(msg.payload.text);
          break;
        case "done":
          finishStream(msg.payload.text);
          tellOrb(msg.payload.text);
          if (msg.payload.model) setActiveModelId(modelIdToNode(msg.payload.model));
          break;
        case "push":
          pushMessage(msg.payload.text, msg.payload.source);
          tellOrb(msg.payload.text);
          break;
        case "presence":
          setPresence(msg.payload.state);
          break;
        case "mode":
          setMode(msg.payload.mode);
          break;
        case "v3":
          // Intelligence events feed the Intelligence panel only. They are
          // NOT pushed into chat: the proactive loop already decides whether
          // a V3 line is worth speaking and sends that as a normal "push".
          setV3Events((prev) => [...prev, msg.payload].slice(-V3_BUFFER));
          if (msg.payload.serious || msg.payload.kind === "build") {
            useNotifyStore.getState().add(msg.payload.kind, msg.payload.text);
          }
          break;
        case "quest":
          setQuestEvent(msg.payload);
          if (msg.payload.kind === "complete") {
            useNotifyStore.getState().add("quest", `Quest complete: ${msg.payload.title ?? ""}`.trim());
          }
          break;
        case "install": {
          // AURA's line + the install card. The user's own bubble is swapped
          // for the server's masked copy in case the local mask missed a key.
          const { text, proposal, masked } = msg.payload;
          setTurns((prev) => {
            const out = [...prev];
            for (let i = out.length - 1; i >= 0; i--) {
              if (out[i].role === "user") {
                if (masked) out[i] = { ...out[i], text: masked };
                break;
              }
            }
            out.push({ id: newId(), role: "aura", text, streaming: false, ts: nowTime(),
                       source: "install", card: proposal ?? undefined });
            return out;
          });
          tellOrb(text);
          break;
        }
        case "saved":
          if (msg.payload.kind === "delete") useSavedStore.getState().remove(msg.payload.id);
          else if (msg.payload.item) useSavedStore.getState().upsert(msg.payload.item);
          break;
        case "planets":
          void useRosterStore.getState().load();
          if (msg.payload.kind === "installed") {
            useNotifyStore.getState().add("done", "A new planet joined the orbit");
          }
          break;
        // A source finishing its sync is nobody's reply — it lands whenever
        // the pull or the scan is done. Anything showing sources listens for
        // this rather than polling.
        case "sources":
          window.dispatchEvent(new CustomEvent("aura:sources", { detail: msg.payload }));
          break;
        case "error":
          pushMessage("[error] " + msg.payload.message, "error");
          finishStream();
          break;
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("closed");
      reconnectRef.current = setTimeout(connect, 1500);
    };

    ws.onerror = () => ws.close();
  }, [url, appendChunk, finishStream, pushMessage]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const send = useCallback((text: string, opts: SendOptions = {}) => {
    const trimmed = text.trim();
    if (!trimmed) return false;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;

    const attachments = opts.attachments?.length ? opts.attachments : undefined;
    // A pasted API key never shows in your own bubble.
    setTurns((prev) => [...prev, { id: newId(), role: "user", text: maskSecrets(trimmed), ts: nowTime(),
                                   attachments }]);
    const msg: ClientMessage = {
      type: "message",
      payload: {
        text: trimmed,
        ...(attachments ? { attachments: attachments.map((a) => a.id) } : {}),
        ...(opts.intent ? { intent: opts.intent } : {}),
      },
    };
    ws.send(JSON.stringify(msg));
    return true;
  }, []);

  /** Replace the visible transcript — used when a saved chat is reopened or
   *  a new one is started. The backend has already moved AURA's context; this
   *  just makes the window agree with it. */
  const loadTurns = useCallback(
    (msgs: { role: string; text: string; created_at?: string | null }[]) => {
      setTurns(
        msgs.map((m) => ({
          id: newId(),
          role: m.role === "user" ? "user" : "aura",
          text: m.text,
          ts: m.created_at ? new Date(m.created_at).toLocaleTimeString(
            "en-US", { hour: "numeric", minute: "2-digit", hour12: true }) : undefined,
        })) as ChatTurn[]
      );
    },
    []
  );

  const clearTurns = useCallback(() => setTurns([]), []);

  return { status, auraState, presence, mode, activeModelId, turns, v3Events, questEvent, activity, send, loadTurns, clearTurns };
}
