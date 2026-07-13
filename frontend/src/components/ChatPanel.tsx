import { useEffect, useRef, useState } from "react";
import type { ChatTurn, ConnStatus } from "../types";

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  onSend: (text: string) => void;
}

export default function ChatPanel({ status, turns, onSend }: Props) {
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

  const now = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });

  return (
    <section className="chat">
      <header className="chat__header">
        <span>AURA CHAT</span>
        <span className={"chat__dot chat__dot--" + status} />
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
              <span className="bubble__time">{now}</span>
            </span>
            <p className="bubble__text">
              {t.text}
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
