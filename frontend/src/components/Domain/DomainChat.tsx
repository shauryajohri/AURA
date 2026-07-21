import { useEffect, useRef, useState } from "react";
import { api, type NatureInfo } from "../../api";
import { useAuraSocket } from "../../hooks/useAuraSocket";
import { MODELS } from "../../data/models";

// ============================================================================
// AURA Chat — the right rail of the Domain.
// A real conversation with the brain: natural flow, nature locks (Savage,
// Chill, Focus…) and a Code mode for pure engineering talk. No mock panels.
// ============================================================================

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

/** Split a message into plain-text and fenced ```code``` segments. */
function renderMessage(text: string) {
  const parts = text.split(/```(\w*)\n?([\s\S]*?)```/g);
  const out: React.ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) out.push(<span key={i}>{parts[i]}</span>);
    if (i + 2 < parts.length) {
      out.push(
        <pre className="dchat__code" key={i + 2}>
          {parts[i + 1] && <span className="dchat__lang">{parts[i + 1]}</span>}
          <code>{parts[i + 2]}</code>
        </pre>
      );
    }
  }
  return out;
}

export default function DomainChat({ collapsed, onToggle }: Props) {
  const { status, turns, send, mode, activeModelId } = useAuraSocket();
  const [input, setInput] = useState("");
  const [natures, setNatures] = useState<NatureInfo[]>([]);
  const [nature, setNature] = useState<string>("auto");
  const logRef = useRef<HTMLDivElement>(null);

  const model = MODELS.find((m) => m.id === activeModelId) ?? null;
  const codeMode = mode === "CODE";

  useEffect(() => {
    api
      .getNature()
      .then((r) => {
        setNatures(r.natures);
        setNature(r.current);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const pickNature = (id: string) => {
    setNature(id);
    api.setNature(id).catch(() => setNature(nature));
  };

  const toggleCode = () => send(codeMode ? "/code_end" : "/code");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    send(input);
    setInput("");
  };

  if (collapsed) {
    return (
      <button className="dchat-reveal" onClick={onToggle} title="AURA Chat">
        ✦
      </button>
    );
  }

  return (
    <aside className="dchat">
      <div className="dchat__head">
        <span className="dchat__title">AURA CHAT</span>
        <span className={"dchat__dot dchat__dot--" + status} title={status} />
        <button className="dchat__collapse" onClick={onToggle} title="Collapse">
          »
        </button>
      </div>

      {/* nature locks — how AURA talks */}
      <div className="dchat__natures">
        {natures.map((n) => (
          <button
            key={n.id}
            className={"dchat__nature" + (nature === n.id ? " dchat__nature--on" : "")}
            onClick={() => pickNature(n.id)}
            title={n.label}
          >
            <span className="dchat__natureicon">{n.icon}</span>
            {n.label}
          </button>
        ))}
        <button
          className={"dchat__nature dchat__nature--code" + (codeMode ? " dchat__nature--on" : "")}
          onClick={toggleCode}
          title={codeMode ? "Leave code mode" : "Enter code mode"}
        >
          <span className="dchat__natureicon">⌥</span>
          Code
        </button>
      </div>

      <div className="dchat__log" ref={logRef}>
        {turns.length === 0 && (
          <p className="dchat__empty">
            {status === "open"
              ? "AURA is listening. Talk normally — or hit Code and get to work."
              : "Reaching the brain…"}
          </p>
        )}
        {turns.map((t) => (
          <div key={t.id} className={"dchat__turn dchat__turn--" + t.role}>
            <span className="dchat__who">
              {t.role === "user" ? "You" : "AURA"}
              {t.ts && <span className="dchat__time">{t.ts}</span>}
            </span>
            <p className="dchat__text">
              {renderMessage(t.text)}
              {t.streaming && <span className="dchat__caret" />}
            </p>
          </div>
        ))}
      </div>

      <div className="dchat__foot">
        {model && (
          <span className="dchat__model">
            <span
              className="dchat__orb"
              style={{ background: model.color, boxShadow: `0 0 10px ${model.color}` }}
            />
            {model.name}
          </span>
        )}
        {codeMode && <span className="dchat__badge">CODE MODE</span>}
      </div>

      <form className="dchat__composer" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            status === "open"
              ? codeMode
                ? "Ask about the code…"
                : "Say anything…"
              : "Connecting…"
          }
          disabled={status !== "open"}
        />
        <button type="submit" disabled={status !== "open" || !input.trim()}>
          ➤
        </button>
      </form>
    </aside>
  );
}
