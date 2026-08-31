import { useRef, useState } from "react";
import { MODELS } from "../../../data/models";
import { useActiveProject, useDomainStore } from "../../../stores/domainStore";

// ============================================================================
// AI planning board — the default surface when a project is open.
//
// Cards are the hinge between Tasks and Code: promote a card into a Domain
// task (they stay in step — dropping into Done ticks the task, ticking the
// task moves the card), or attach a file from the working set so the card
// opens straight into the editor.
// ============================================================================

const fileName = (p: string) => p.split(/[\\/]/).filter(Boolean).pop() ?? p;

export default function PlanningBoard() {
  const project = useActiveProject();
  const addCard = useDomainStore((s) => s.addCard);
  const moveCard = useDomainStore((s) => s.moveCard);
  const removeCard = useDomainStore((s) => s.removeCard);
  const promoteCard = useDomainStore((s) => s.promoteCard);
  const attachFileToCard = useDomainStore((s) => s.attachFileToCard);
  const openInCode = useDomainStore((s) => s.openInCode);
  const setSection = useDomainStore((s) => s.setSection);

  const dragId = useRef<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [attaching, setAttaching] = useState<string | null>(null);

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

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
              const task = project.tasks.find((t) => t.id === c.taskId);
              return (
                <div
                  key={c.id}
                  className="dboard__card"
                  draggable
                  onDragStart={() => { dragId.current = c.id; }}
                >
                  <div className="dboard__cardtitle">{c.title}</div>

                  {/* linked file — one click into the editor */}
                  {c.file && (
                    <button
                      className="dboard__file"
                      onClick={() => openInCode(c.file!)}
                      title={c.file}
                    >
                      ⌥ {fileName(c.file)}
                    </button>
                  )}

                  {/* file attach menu, drawn from the project's working set */}
                  {attaching === c.id && (
                    <div className="dboard__attach" onMouseLeave={() => setAttaching(null)}>
                      {project.sources.filter((s) => !s.dir).length === 0 && (
                        <div className="dboard__attachnone">
                          No files in the working set yet — add some in Code.
                        </div>
                      )}
                      {project.sources
                        .filter((s) => !s.dir)
                        .map((s) => (
                          <button
                            key={s.path}
                            onClick={() => { attachFileToCard(c.id, s.path); setAttaching(null); }}
                          >
                            {s.name}
                          </button>
                        ))}
                      {c.file && (
                        <button
                          className="dboard__attachclear"
                          onClick={() => { attachFileToCard(c.id, undefined); setAttaching(null); }}
                        >
                          detach
                        </button>
                      )}
                    </div>
                  )}

                  <div className="dboard__cardfoot">
                    {c.tag && <span className="dboard__tag">{c.tag}</span>}

                    {task ? (
                      <button
                        className={"dboard__task" + (task.done ? " dboard__task--done" : "")}
                        onClick={() => setSection("tasks")}
                        title="Linked task — open Tasks"
                      >
                        ☑ {task.done ? "done" : "task"}
                      </button>
                    ) : (
                      <button
                        className="dboard__promote"
                        onClick={() => promoteCard(c.id)}
                        title="Make this a Domain task"
                      >
                        ☑ +
                      </button>
                    )}

                    <button
                      className="dboard__clip"
                      onClick={() => setAttaching(attaching === c.id ? null : c.id)}
                      title="Attach a file"
                    >
                      ⌥
                    </button>

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
