import { useCallback, useEffect, useRef, useState } from "react";
import type { AuraState, ChatTurn, ConnStatus } from "../types";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { useLocalStorage } from "../hooks/useLocalStorage";
import MicCheck from "./MicCheck";
import { renderMarkdown } from "./Markdown";

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string) => void;
  onCollapse?: () => void;
  /** Used to mute the mic while AURA is talking so she can't hear herself. */
  auraState?: AuraState;
}

// Message rendering (fenced code, tables, links, lists) lives in Markdown.tsx
// now — DomainChat renders the same replies and was drifting from this copy.

export default function ChatPanel({ status, turns, onSend, onCollapse, auraState }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // The mic check strip is shown once, the first time voice is ever used, then
  // never again unless the user clears storage.
  const [micChecked, setMicChecked] = useLocalStorage<boolean>("aura.micChecked", false);
  const [showCheck, setShowCheck] = useState(false);

  // Voice heard while AURA is mid-sentence is almost always AURA's own output
  // coming back through the speakers — freeze capture until she's done.
  const voice = useVoiceInput({
    onFinal: useCallback((text: string) => onSend(text), [onSend]),
    muted: auraState === "speaking",
  });
  const { toggle: toggleVoice, stop: stopVoice, listening } = voice;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, voice.interim]);

  // A dropped connection makes voice pointless — every sentence would vanish.
  useEffect(() => {
    if (status !== "open" && listening) stopVoice();
  }, [status, listening, stopVoice]);

  const onMicClick = () => {
    if (listening) { stopVoice(); return; }
    if (!micChecked) { setShowCheck(true); return; }
    toggleVoice();
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSend(input);
    setInput("");
  };

  return (
    <section className="chat">
      <header className="chat__header">
        <span>AURA CHAT</span>
        <span className={"chat__dot chat__dot--" + status} />
        {onCollapse && (
          <button className="chat__collapse" onClick={onCollapse} title="Hide chat">
            {"»"}
          </button>
        )}
      </header>

      <div className="chat__log" ref={scrollRef}>
        {turns.length === 0 && (
          <p className="chat__empty">
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
            {/* A div, not a <p>: a <pre> inside a <p> is invalid HTML, so the
                browser silently closed the paragraph early and the code block
                escaped the bubble's layout. */}
            <div className="bubble__text">
              {renderMarkdown(t.text)}
              {t.streaming && <span className="caret" />}
            </div>
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

      <form className={"composer" + (listening ? " composer--voice" : "")} onSubmit={submit}>
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
