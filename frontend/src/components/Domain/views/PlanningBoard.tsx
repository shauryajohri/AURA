import { useRef, useState } from "react";
import { MODELS } from "../../../data/models";
import { useActiveProject, useDomainStore } from "../../../stores/domainStore";

// AI planning board — the default surface when a project is open.
// Drag cards between columns; agents glow on the cards they own.

export default function PlanningBoard() {
  const project = useActiveProject();
  const addCard = useDomainStore((s) => s.addCard);
  const moveCard = useDomainStore((s) => s.moveCard);
  const removeCard = useDomainStore((s) => s.removeCard);

  const dragId = useRef<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [text, setText] = useState("");

  if (!project) return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const submit = (colId: string) => (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) addCard(colId, text.trim());
    setText("");
    setAdding(null);
  };

  return (
    <div className="dboard">
      {project.board.map((col) => (
        <div
          key={col.id}
          className="dboard__col"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (dragId.current) moveCard(dragId.current, col.id);
            dragId.current = null;
          }}
        >
          <div className="dboard__colhead">
            <span className="dboard__coltitle">{col.title}</span>
            <span className="dboard__count">{col.cards.length}</span>
          </div>

          <div className="dboard__cards">
            {col.cards.map((c) => {
              const agent = MODELS.find((m) => m.id === c.agent);
              return (
                <div
                  key={c.id}
                  className="dboard__card"
                  draggable
                  onDragStart={() => { dragId.current = c.id; }}
                >
                  <div className="dboard__cardtitle">{c.title}</div>
                  <div className="dboard__cardfoot">
                    {c.tag && <span className="dboard__tag">{c.tag}</span>}
                    {agent && (
                      <span
                        className="dboard__agent"
                        title={`${agent.name} is on this`}
                        style={{ background: agent.color, boxShadow: `0 0 8px ${agent.color}` }}
                      />
                    )}
                    <button className="dboard__x" onClick={() => removeCard(c.id)}>✕</button>
                  </div>
                </div>
              );
            })}
          </div>

          {adding === col.id ? (
            <form className="dboard__add" onSubmit={submit(col.id)}>
              <input
                autoFocus
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Task…"
                onBlur={() => setAdding(null)}
                onKeyDown={(e) => e.key === "Escape" && setAdding(null)}
              />
            </form>
          ) : (
            <button className="dboard__addbtn" onClick={() => { setAdding(col.id); setText(""); }}>
              + Add
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
