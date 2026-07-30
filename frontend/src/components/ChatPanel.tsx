import { useCallback, useEffect, useRef, useState } from "react";
import type { AuraState, ChatTurn, ConnStatus } from "../types";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { useLocalStorage } from "../hooks/useLocalStorage";
import MicCheck from "./MicCheck";

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string) => void;
  onCollapse?: () => void;
  /** Used to mute the mic while AURA is talking so she can't hear herself. */
  auraState?: AuraState;
}

/** One fenced block, with its language label and a copy button. */
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      },
      () => {},
    );
  };
  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span className="codeblock__lang">{lang || "code"}</span>
        <button className="codeblock__copy" onClick={copy} title="Copy code">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="codeblock__pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Split a message into prose and fenced ```code``` segments.
 *
 * Handles an UNTERMINATED fence, which the previous version didn't: while a
 * reply is still streaming the closing ``` hasn't arrived yet, so the regex
 * failed to match and the half-written code rendered as flat prose — the
 * fence, the language tag and all the source on one running line.
 */
function renderMessage(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const fence = /```([\w+#-]*)[ \t]*\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;

  while ((m = fence.exec(text)) !== null) {
    if (m.index > last) {
      out.push(<span key={key++}>{text.slice(last, m.index)}</span>);
    }
    out.push(<CodeBlock key={key++} lang={m[1]} code={m[2].replace(/\n$/, "")} />);
    last = m.index + m[0].length;
  }

  const tail = text.slice(last);
  const open = tail.indexOf("```");
  if (open !== -1) {
    // Still streaming: render what's arrived as code so it never flashes as
    // a wall of unformatted text mid-answer.
    if (open > 0) out.push(<span key={key++}>{tail.slice(0, open)}</span>);
    const rest = tail.slice(open + 3);
    const nl = rest.indexOf("\n");
    const lang = nl === -1 ? rest.trim() : rest.slice(0, nl).trim();
    const body = nl === -1 ? "" : rest.slice(nl + 1);
    out.push(<CodeBlock key={key++} lang={lang} code={body} />);
  } else if (tail) {
    out.push(<span key={key++}>{tail}</span>);
  }
  return out;
}

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
              {renderMessage(t.text)}
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
