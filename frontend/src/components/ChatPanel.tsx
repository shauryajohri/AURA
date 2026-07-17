import { useEffect, useRef, useState } from "react";
import type { ChatTurn, ConnStatus } from "../types";

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string) => void;
  onCollapse?: () => void;
}

/** Split a message into plain-text and fenced ```code``` segments. */
function renderMessage(text: string) {
  const parts = text.split(/```(\w*)\n?([\s\S]*?)```/g);
  const out: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) out.push(<span key={i}>{parts[i]}</span>);
    if (i + 2 < parts.length) {
      out.push(
        <pre className="bubble__code" key={i + 2}>
          {parts[i + 1] && <span className="bubble__lang">{parts[i + 1]}</span>}
          <code>{parts[i + 2]}</code>
        </pre>
      );
    }
  }
  return out;
}

export default function ChatPanel({ status, turns, onSend, onCollapse }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

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
            <p className="bubble__text">
              {renderMessage(t.text)}
              {t.streaming && <span className="caret" />}
            </p>
          </div>
        ))}
      </div>

      <form className="composer" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={status === "open" ? "Talk or type a message..." : "Connecting to brain..."}
          disabled={status !== "open"}
          autoFocus
        />
        <button type="button" className="composer__mic" title="Voice">{"🎙"}</button>
        <button type="submit" className="composer__send" disabled={status !== "open" || !input.trim()}>
          {"➤"}
        </button>
      </form>
    </section>
  );
}
