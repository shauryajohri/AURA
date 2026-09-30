import { useEffect, useRef, useState } from "react";
import type { ChatTurn, ConnStatus } from "../../types";
import { renderMarkdown } from "../Markdown";

// ============================================================================
// AURA Chat — the right rail of the Domain. It's the same conversation as
// Home (the socket is App's, passed down), so a skill run here, or "open X",
// is part of one history rather than a second one on its own connection.
// ============================================================================

interface Props {
  status: ConnStatus;
  turns: ChatTurn[];
  send: (text: string) => void;
}

export default function DomainChat({ status, turns, send }: Props) {
  const [input, setInput] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    send(input);
    setInput("");
  };

  return (
    <aside className="dchat">
      <div className="dchat__head">
        <span className="dchat__title">AURA</span>
        <span className={"dchat__dot dchat__dot--" + status} title={status} />
      </div>

      <div className="dchat__log" ref={logRef}>
        {turns.length === 0 && (
          <p className="dchat__empty">
            {status === "open"
              ? "Ask about anything in your Domain, or say “open …” / “run …”."
              : "Reaching the brain…"}
          </p>
        )}
        {turns.map((t) => (
          <div key={t.id} className={"dchat__turn dchat__turn--" + t.role}>
            <span className="dchat__who">
              {t.role === "user" ? "You" : "AURA"}
              {t.ts && <span className="dchat__time">{t.ts}</span>}
            </span>
            {/* A div, not a <p>: block elements (pre, table, ul) inside a
                paragraph are invalid HTML and the browser closes the <p>
                early, dropping them out of the turn's layout. */}
            <div className="dchat__text">
              {renderMarkdown(t.text)}
              {t.streaming && <span className="dchat__caret" />}
            </div>
          </div>
        ))}
      </div>

      <form className="dchat__composer" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={status === "open" ? "Say anything…" : "Connecting…"}
          disabled={status !== "open"}
        />
        <button type="submit" disabled={status !== "open" || !input.trim()}>
          ➤
        </button>
      </form>
    </aside>
  );
}
