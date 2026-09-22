import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { AuraState, ChatTurn, ConnStatus, TurnAttachment } from "../types";
import type { SendOptions } from "../hooks/useAuraSocket";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { useSavedStore } from "../stores/savedStore";
import { isDocument, uploadToSaved } from "../lib/files";
import InstallCard from "./InstallCard";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSettingsStore } from "../stores/settingsStore";
import ChatHistory from "./ChatHistory";
import RoomPicker from "./RoomPicker";
import MicCheck from "./MicCheck";
import { renderMarkdown } from "./Markdown";
import Icon from "./Icon";
import { coreSignals, emitCore } from "../lib/coreBus";
import { sfx } from "../lib/sfx";

/**
 * The conversation pane — the right-hand side of Home, full height, beside
 * the sky. It never changes size as the conversation grows, so the black hole
 * next to it never moves: a long answer scrolls here instead of pushing the
 * core up. The composer is one box: the message on top, its tools beneath.
 */

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string, opts?: SendOptions) => boolean | void;
  /** Mute the mic while AURA is talking so she can't hear herself. */
  auraState?: AuraState;
  /** Replace the transcript when a saved chat is reopened. */
  onLoadTurns?: (msgs: { role: string; text: string; created_at: string | null }[]) => void;
  /** Empty the transcript when a new chat is started. */
  onClearTurns?: () => void;
  /** The pane's head — the greeting on Home. */
  head?: ReactNode;
}

const MAX_ATTACH = 200 * 1024; // read text attachments up to 200 KB inline

export default function ChatDock({ status, turns, onSend, auraState, onLoadTurns, onClearTurns, head }: Props) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const measureRef = useRef<CanvasRenderingContext2D | null>(null);

  // Where the caret is on screen — each keystroke throws a spark from there
  // into the core.
  const caretPoint = () => {
    const el = inputRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (!measureRef.current) measureRef.current = document.createElement("canvas").getContext("2d");
    const m = measureRef.current;
    if (!m) return null;
    m.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const upto = el.value.slice(0, el.selectionStart ?? el.value.length);
    const w = m.measureText(upto).width - el.scrollLeft;
    return { x: r.left + parseFloat(cs.paddingLeft) + Math.max(0, Math.min(w, r.width - 24)), y: r.top + r.height / 2 };
  };

  // ── Speak on/off ──────────────────────────────────────────────────────
  // Backed by the same `voice.enabled` app-setting the Sanctuary slider
  // writes, so the switch here and the panel there can never disagree.
  const speakOn = useSettingsStore((s) => s.settings["voice.enabled"] !== false);
  const applySettings = useSettingsStore((s) => s.apply);
  const toggleSpeak = () => { void applySettings({ "voice.enabled": !speakOn }); };

  const [micChecked, setMicChecked] = useLocalStorage<boolean>("aura.micChecked", false);
  const [showCheck, setShowCheck] = useState(false);

  const voice = useVoiceInput({
    onFinal: useCallback((text: string) => onSend(text), [onSend]),
    muted: auraState === "speaking",
  });
  const { toggle: toggleVoice, stop: stopVoice, listening } = voice;
  // The floating orb turns cyan while the mic is live.
  useEffect(() => {
    window.aura?.orbListening?.(listening);
    coreSignals.mic = listening;
  }, [listening]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, voice.interim]);

  useEffect(() => {
    if (status !== "open" && listening) stopVoice();
  }, [status, listening, stopVoice]);

  const onMicClick = () => {
    if (listening) { stopVoice(); return; }
    if (!micChecked) { setShowCheck(true); return; }
    toggleVoice();
  };

  // ── Files for Saved Info ─────────────────────────────────────────────
  // PDFs, Word files and images upload straight away and wait as chips above
  // the composer; AURA reads them while you type, and they go with the next
  // message. Text and code files still go inline, as they always have.
  const [pending, setPending] = useState<TurnAttachment[]>([]);
  const [uploading, setUploading] = useState(0);
  const [attachErr, setAttachErr] = useState("");
  const [dropping, setDropping] = useState(false);
  const saved = useSavedStore((s) => s.items);
  const upsertSaved = useSavedStore((s) => s.upsert);
  const statusOf = (id: number) => saved.find((x) => x.id === id)?.status ?? "scanning";

  const upload = async (f: File) => {
    setAttachErr("");
    setUploading((n) => n + 1);
    try {
      const item = await uploadToSaved(f, "chat");
      upsertSaved(item);
      setPending((cur) => [...cur, { id: item.id, name: f.name, kind: item.kind }]);
    } catch (e) {
      setAttachErr(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading((n) => n - 1);
    }
  };

  const takeFiles = (files: FileList | File[]) => {
    for (const f of Array.from(files).slice(0, 5)) {
      if (isDocument(f)) void upload(f);
      else attach(f);
    }
  };

  const attach = (f: File) => {
    const isText =
      f.type.startsWith("text/") ||
      /\.(txt|md|py|js|ts|tsx|jsx|json|css|html|yml|yaml|toml|csv|log)$/i.test(f.name);
    if (isText && f.size <= MAX_ATTACH) {
      f.text().then((body) => {
        setInput((cur) =>
          (cur ? cur + "\n\n" : "") + "Attached `" + f.name + "`:\n```\n" + body + "\n```");
      });
    } else {
      setInput((cur) => (cur ? cur + " " : "") + "[attached file: " + f.name + "]");
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && pending.length === 0) return;
    const text = input.trim() || `Shared ${pending.map((p) => p.name).join(", ")}`;
    const sent = onSend(text, pending.length ? { attachments: pending } : undefined);
    if (sent === false) return;     // socket down — keep what they typed
    // the message streams into the core
    const r = inputRef.current?.getBoundingClientRect();
    if (r) emitCore({ kind: "feed", x: r.left, y: r.top, w: Math.min(r.width, 18 + input.length * 7.5), h: r.height });
    sfx.send();
    setInput("");
    setPending([]);
  };

  return (
    <section
      className={"dock" + (dropping ? " dock--drop" : "")}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("Files") || status !== "open") return;
        e.preventDefault();
        setDropping(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropping(false);
      }}
      onDrop={(e) => {
        if (!e.dataTransfer.files.length) return;
        e.preventDefault();
        setDropping(false);
        takeFiles(e.dataTransfer.files);
      }}
    >
      {dropping && <div className="dock__dropzone">Drop to share it with AURA — she'll read it and keep it in Saved Info</div>}
      {head}

      <ChatHistory
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onOpenChat={(msgs) => onLoadTurns?.(msgs)}
        onNewChat={() => onClearTurns?.()}
      />

      <div className="dock__log" ref={scrollRef}>
        {turns.length === 0 && (
          <p className="dock__empty">
            {status === "open"
              ? "Type below, or press the mic and talk."
              : "Waiting for AURA's brain. Start server.py if it isn't running."}
          </p>
        )}
        {turns.map((t) => (
          <div key={t.id} className={"bubble bubble--" + t.role}>
            <span className="bubble__who">
              {t.role === "user" ? "You" : "AURA"}
              {t.source && t.source !== "greeting" && (
                <span className={"bubble__src bubble__src--" + t.source}>{t.source}</span>
              )}
              {t.ts && <span className="bubble__time">{t.ts}</span>}
            </span>
            <div className="bubble__text">
              {renderMarkdown(t.text)}
              {t.streaming && <span className="caret" />}
            </div>
            {t.attachments && t.attachments.length > 0 && (
              <div className="bubble__files">
                {t.attachments.map((a) => (
                  <span key={a.id} className={"filechip filechip--" + a.kind}>
                    <span className="filechip__ring" aria-hidden />{a.name}
                  </span>
                ))}
              </div>
            )}
            {t.card && <InstallCard proposal={t.card} inChat />}
          </div>
        ))}
      </div>

      {showCheck && (
        <MicCheck
          variant="compact"
          onReady={() => { setMicChecked(true); setShowCheck(false); toggleVoice(); }}
          onDismiss={() => { setMicChecked(true); setShowCheck(false); }}
        />
      )}

      {listening && (
        <div className="voicebar">
          <span className="voicebar__pip" />
          <span className="voicebar__state">
            {auraState === "speaking"
              ? "Paused — AURA is speaking"
              : voice.transcribing
                ? "Transcribing…"
                : voice.interim
                  ? "Hearing you…"
                  : "Listening"}
          </span>
          <span className="voicebar__meter">
            {Array.from({ length: 14 }, (_, i) => (
              <span
                key={i}
                className={"voicebar__bar" + (voice.level >= (i + 1) / 14 * 0.9 ? " is-on" : "")}
              />
            ))}
          </span>
          <span className="voicebar__engine" title={
            voice.engine === "webspeech"
              ? "Using the browser's built-in recognizer"
              : "Using AURA's Python recognizer"
          }>
            {voice.engine === "webspeech" ? "browser" : "brain"}
          </span>
        </div>
      )}

      {voice.error && <div className="voicebar__err">{voice.error}</div>}

      {(pending.length > 0 || uploading > 0 || attachErr) && (
        <div className="dock__files" aria-live="polite">
          {pending.map((a) => {
            const st = statusOf(a.id);
            return (
              <span key={a.id} className={"filechip filechip--" + a.kind + " is-" + st}>
                <span className="filechip__ring" aria-hidden />
                {a.name}
                <span className="filechip__state">
                  {st === "scanning" ? "reading…" : st === "error" ? "couldn't read" : "read"}
                </span>
                <button type="button" className="filechip__x" aria-label={`Don't send ${a.name}`}
                        onClick={() => setPending((cur) => cur.filter((x) => x.id !== a.id))}>✕</button>
              </span>
            );
          })}
          {uploading > 0 && <span className="filechip is-scanning"><span className="filechip__ring" aria-hidden />uploading…</span>}
          {attachErr && <span className="dock__fileerr" role="alert">{attachErr}</span>}
        </div>
      )}

      <form className={"composer composer--dock" + (listening ? " composer--voice" : "")} onSubmit={submit}>
        <div className="composer__field">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => {
              const grew = e.target.value.length > input.length;
              setInput(e.target.value);
              if (grew) {
                sfx.key();
                requestAnimationFrame(() => {
                  const pt = caretPoint();
                  if (pt) emitCore({ kind: "spark", x: pt.x, y: pt.y });
                });
              }
            }}
            placeholder={
              listening
                ? "Speak, or type to interrupt"
                : status === "open"
                  ? "Ask AURA anything"
                  : "Waiting for AURA's brain to connect"
            }
            disabled={status !== "open"}
            autoFocus
          />
          {listening && voice.interim && !input && (
            <span className="composer__interim">{voice.interim}</span>
          )}
        </div>

        <div className="composer__tools">
          <button
            type="button"
            className={"composer__hist" + (historyOpen ? " composer__hist--on" : "")}
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label="Chats"
            title="Chats — open an old one and AURA picks up its context"
            aria-expanded={historyOpen}
          >
            <Icon name="history" />
          </button>

          <button
            type="button"
            className="composer__attach"
            onClick={() => fileRef.current?.click()}
            disabled={status !== "open"}
            aria-label="Attach a file"
            title="Attach a file — PDFs, Word files and images are saved to Saved Info"
          >
            <Icon name="attach" />
          </button>
          <input
            ref={fileRef}
            type="file"
            hidden
            multiple
            onChange={(e) => {
              if (e.target.files?.length) takeFiles(e.target.files);
              e.target.value = "";
            }}
          />

          {/* Pick the room AURA works in — loads that room's brief so the reply
              comes back in its style (Coding → DSA, Japanese Study → tutor). */}
          <RoomPicker
            onLoad={(msgs) => onLoadTurns?.(msgs)}
            onClear={() => onClearTurns?.()}
          />

          <span className="composer__spacer" />

          {/* Speak on/off. When off AURA still answers in the chat, she just
              doesn't say it out loud. */}
          <button
            type="button"
            className={"speakswitch" + (speakOn ? " speakswitch--on" : "")}
            onClick={toggleSpeak}
            role="switch"
            aria-checked={speakOn}
            aria-label={speakOn ? "Voice on — AURA speaks her replies" : "Voice off — replies are text only"}
            title={speakOn ? "Voice on — click for text only" : "Text only — click to let AURA speak"}
          >
            <Icon name={speakOn ? "speaker" : "mute"} />
          </button>

          <button
            type="button"
            className={"composer__mic" + (listening ? " composer__mic--live" : "")}
            onClick={onMicClick}
            disabled={status !== "open"}
            aria-label={listening ? "Stop listening" : "Talk to AURA"}
            title={listening ? "Stop listening" : "Start always-on voice"}
            aria-pressed={listening}
          >
            <Icon name="mic" />
          </button>
          <button type="submit" className="composer__send"
                  disabled={status !== "open" || (!input.trim() && pending.length === 0)}
                  aria-label="Send">
            <Icon name="send" />
          </button>
        </div>
      </form>
    </section>
  );
}
