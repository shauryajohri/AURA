import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AuraState,
  ChatTurn,
  ClientMessage,
  ConnStatus,
  Presence,
  ServerMessage,
} from "../types";

const DEFAULT_URL = "ws://127.0.0.1:8760/ws";

function newId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function nowTime(): string {
  return new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

// Map a model id string (e.g. "llama-3.3-70b-versatile") to a constellation
// node id in data/models.ts, so the node that answered lights up ACTIVE.
function modelIdToNode(model: string): string | null {
  const m = model.toLowerCase();
  // Real AURA roster first (core/model_router ids).
  if (m.includes("laguna")) return "laguna";
  if (m.includes("nemotron")) return "nemotron";
  if (m.includes("gemma")) return "gemma";
  if (m.includes("8b") || m.includes("instant")) return "llama8b";
  if (m.includes("llama")) return "llama";
  if (m.includes("gpt")) return "gpt4o";
  if (m.includes("claude")) return "claude";
  if (m.includes("gemini")) return "gemini";
  if (m.includes("grok")) return "grok";
  return null;
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
          break;
        case "chunk":
          appendChunk(msg.payload.text);
          break;
        case "done":
          finishStream(msg.payload.text);
          if (msg.payload.model) setActiveModelId(modelIdToNode(msg.payload.model));
          break;
        case "push":
          pushMessage(msg.payload.text, msg.payload.source);
          break;
        case "presence":
          setPresence(msg.payload.state);
          break;
        case "mode":
          setMode(msg.payload.mode);
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

  const send = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    setTurns((prev) => [...prev, { id: newId(), role: "user", text: trimmed, ts: nowTime() }]);
    const msg: ClientMessage = { type: "message", payload: { text: trimmed } };
    ws.send(JSON.stringify(msg));
  }, []);

  return { status, auraState, presence, mode, activeModelId, turns, send };
}
