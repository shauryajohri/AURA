import { useCallback, useEffect, useRef, useState } from "react";
import type { AuraState, ChatTurn, ConnStatus } from "../types";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSettingsStore } from "../stores/settingsStore";
import ChatHistory from "./ChatHistory";
import MicCheck from "./MicCheck";
import { renderMarkdown } from "./Markdown";

/**
 * The chat dock — conversation lives at the BOTTOM of Home now, in one large
 * rounded glass container under the core. No side panel, no floating windows.
 * The composer is intentionally almost identical to the old one (voice, text,
 * send) plus attachments; the log floats above it and can be tucked away so
 * the black hole owns the screen.
 */

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string) => void;
  /** Mute the mic while AURA is talking so she can't hear herself. */
  auraState?: AuraState;
  /** Replace the transcript when a saved chat is reopened. */
  onLoadTurns?: (msgs: { role: string; text: string; created_at: string | null }[]) => void;
  /** Empty the transcript when a new chat is started. */
  onClearTurns?: () => void;
}

const MAX_ATTACH = 200 * 1024; // read text attachments up to 200 KB inline

// How tall the conversation may get, as a share of the viewport. The dock used
// to be pinned at 46vh, which is fine for one-liners and useless for anything
// worth reading — reading the answer matters more than admiring the black hole.
const MIN_DOCK_VH = 24;
const MAX_DOCK_VH = 92;
const DEFAULT_DOCK_VH = 46;

export default function ChatDock({ status, turns, onSend, auraState, onLoadTurns, onClearTurns }: Props) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const [logOpen, setLogOpen] = useLocalStorage<boolean>("aura.dockLog", true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Speak on/off ──────────────────────────────────────────────────────
  // Backed by the same `voice.enabled` app-setting the Sanctuary slider
  // writes, so the switch here and the panel there can never disagree.
  const speakOn = useSettingsStore((s) => s.settings["voice.enabled"] !== false);
  const applySettings = useSettingsStore((s) => s.apply);
  const toggleSpeak = () => { void applySettings({ "voice.enabled": !speakOn }); };

  // ── Resizable dock ────────────────────────────────────────────────────
  // Drag the grip at the top edge; the height persists across restarts.
  const [storedVh, setDockVh] = useLocalStorage<number>("aura.dockVh", DEFAULT_DOCK_VH);
  const [dragging, setDragging] = useState(false);
  const clampVh = (v: number) => Math.min(MAX_DOCK_VH, Math.max(MIN_DOCK_VH, v));
  // Guard the persisted value: a stale or hand-edited localStorage entry
  // shouldn't be able to collapse the dock to nothing.
  const dockVh = Number.isFinite(storedVh) ? clampVh(storedVh) : DEFAULT_DOCK_VH;

  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!logOpen) setLogOpen(true);
    e.preventDefault();
    const startY = e.clientY;
    const startVh = dockVh;
    setDragging(true);
    const onMove = (ev: PointerEvent) => {
      // Dragging UP (smaller clientY) makes the dock taller.
      const deltaVh = ((startY - ev.clientY) / window.innerHeight) * 100;
      setDockVh(clampVh(startVh + deltaVh));
    };
    const onUp = () => {
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  // Double-clicking the grip snaps between "tall as it goes" and the default.
  const toggleMaximize = () => {
    if (!logOpen) setLogOpen(true);
    setDockVh(dockVh >= MAX_DOCK_VH - 1 ? DEFAULT_DOCK_VH : MAX_DOCK_VH);
  };

  const [micChecked, setMicChecked] = useLocalStorage<boolean>("aura.micChecked", false);
  const [showCheck, setShowCheck] = useState(false);

  const voice = useVoiceInput({
    onFinal: useCallback((text: string) => onSend(text), [onSend]),
    muted: auraState === "speaking",
  });
  const { toggle: toggleVoice, stop: stopVoice, listening } = voice;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, voice.interim, logOpen]);

  useEffect(() => {
    if (status !== "open" && listening) stopVoice();
  }, [status, listening, stopVoice]);

  const onMicClick = () => {
    if (listening) { stopVoice(); return; }
    if (!micChecked) { setShowCheck(true); return; }
    toggleVoice();
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
    if (!input.trim()) return;
    onSend(input);
    setInput("");
  };

  const last = turns[turns.length - 1];

  return (
    <section
      className={"dock" + (logOpen ? " dock--open" : "") + (dragging ? " dock--dragging" : "")}
      style={{ "--dock-vh": `${dockVh}vh` } as React.CSSProperties}
    >
      {/* Drag the top edge to resize; double-click to snap tall. */}
      <div
        className="dock__grip"
        onPointerDown={startResize}
        onDoubleClick={toggleMaximize}
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize conversation — drag up for more room, double-click to maximise"
        title="Drag to resize · double-click to maximise"
      >
        <span className="dock__gripbar" />
      </div>

      <ChatHistory
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onOpenChat={(msgs) => onLoadTurns?.(msgs)}
        onNewChat={() => onClearTurns?.()}
      />

      {/* conversation log — floats above the composer inside the same glass */}
      {logOpen ? (
        <div className="dock__log" ref={scrollRef}>
          {turns.length === 0 && (
            <p className="dock__empty">
              {status === "open" ? "AURA is here. Say something to begin." : "Connecting to AURA..."}
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
            </div>
          ))}
        </div>
      ) : (
        last && (
          <button className="dock__peek" onClick={() => setLogOpen(true)} title="Show conversation">
            <span className="dock__peekwho">{last.role === "user" ? "You" : "AURA"}</span>
            <span className="dock__peektext">{last.text.slice(0, 120) || "…"}</span>
          </button>
        )
      )}

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

      <form className={"composer composer--dock" + (listening ? " composer--voice" : "")} onSubmit={submit}>
        <button
          type="button"
          className="composer__collapse"
          onClick={() => setLogOpen(!logOpen)}
          title={logOpen ? "Tuck conversation away" : "Show conversation"}
        >
          {logOpen ? "▾" : "▴"}
        </button>

        <button
          type="button"
          className={"composer__hist" + (historyOpen ? " composer__hist--on" : "")}
          onClick={() => setHistoryOpen((v) => !v)}
          title="Chats — open an old one and AURA picks up its context"
          aria-expanded={historyOpen}
        >
          {"\u2630"}
        </button>

        <button
          type="button"
          className="composer__attach"
          onClick={() => fileRef.current?.click()}
          disabled={status !== "open"}
          title="Attach a file"
        >
          {"📎"}
        </button>
        <input
          ref={fileRef}
          type="file"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) attach(f);
            e.target.value = "";
          }}
        />

        <div className="composer__field">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              listening
                ? "Speak — or type to interrupt"
                : status === "open"
                  ? "Talk or type a message..."
                  : "Connecting to brain..."
            }
            disabled={status !== "open"}
            autoFocus
          />
          {listening && voice.interim && !input && (
            <span className="composer__interim">{voice.interim}</span>
          )}
        </div>
        {/* Speak on/off — right is on, left is off. When off AURA still
            answers in the chat, she just doesn't say it out loud. */}
        <button
          type="button"
          className={"speakswitch" + (speakOn ? " speakswitch--on" : "")}
          onClick={toggleSpeak}
          role="switch"
          aria-checked={speakOn}
          aria-label={speakOn ? "Voice on — AURA speaks her replies" : "Voice off — replies are text only"}
          title={speakOn ? "Voice on — click for text only" : "Text only — click to let AURA speak"}
        >
          <span className="speakswitch__icon">{speakOn ? "🔊" : "🔇"}</span>
          <span className="speakswitch__track"><span className="speakswitch__knob" /></span>
        </button>

        <button
          type="button"
          className={"composer__mic" + (listening ? " composer__mic--live" : "")}
          onClick={onMicClick}
          disabled={status !== "open"}
          title={listening ? "Stop listening" : "Start always-on voice"}
          aria-pressed={listening}
        >
          {"🎙"}
        </button>
        <button type="submit" className="composer__send" disabled={status !== "open" || !input.trim()}>
          {"➤"}
        </button>
      </form>
    </section>
  );
}
