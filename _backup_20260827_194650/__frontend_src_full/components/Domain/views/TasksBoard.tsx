import { useMemo, useState } from "react";
import { useActiveProject, useDomainStore, type DomainTask } from "../../../stores/domainStore";

// ============================================================================
// Domain Tasks — engineering work, scoped to the open project.
//
// Deliberately NOT the same list as AURA's personal tasks (those live in the
// Python store behind /api/tasks and drive the Sanctuary + voice nagging).
// These are per-project, carry a tag and priority, and never leak into the
// companion's reminders.
// ============================================================================

type Filter = "open" | "done" | "all";

const PRIORITY: Record<DomainTask["priority"], { label: string; color: string }> = {
  high: { label: "High", color: "#ff5a5a" },
  medium: { label: "Med", color: "#ffb648" },
  low: { label: "Low", color: "#8b8fca" },
};

export default function TasksBoard() {
  const project = useActiveProject();
  const addTask = useDomainStore((s) => s.addTask);
  const toggleTask = useDomainStore((s) => s.toggleTask);
  const patchTask = useDomainStore((s) => s.patchTask);
  const removeTask = useDomainStore((s) => s.removeTask);
  const taskToCard = useDomainStore((s) => s.taskToCard);
  const openInCode = useDomainStore((s) => s.openInCode);
  const setSection = useDomainStore((s) => s.setSection);

  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<DomainTask["priority"]>("medium");
  const [tag, setTag] = useState("");
  const [filter, setFilter] = useState<Filter>("open");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const tasks = useMemo(() => project?.tasks ?? [], [project]);

  const shown = useMemo(() => {
    const list = filter === "all" ? tasks : tasks.filter((t) => (filter === "done" ? t.done : !t.done));
    const rank = { high: 0, medium: 1, low: 2 };
    return [...list].sort(
      (a, b) =>
        Number(a.done) - Number(b.done) ||
        rank[a.priority] - rank[b.priority] ||
        b.createdAt - a.createdAt
    );
  }, [tasks, filter]);

  const counts = {
    open: tasks.filter((t) => !t.done).length,
    done: tasks.filter((t) => t.done).length,
    all: tasks.length,
  };

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    addTask(title.trim(), priority, tag.trim() || undefined);
    setTitle("");
    setTag("");
  };

  const commitEdit = (id: string) => {
    if (draft.trim()) patchTask(id, { title: draft.trim() });
    setEditing(null);
  };

  return (
    <div className="dtasks">
      <div className="dtasks__head">
        <div>
          <h3>{project.name} · Tasks</h3>
          <p>Project work only — separate from AURA's personal task list.</p>
        </div>
        <div className="dtasks__filters">
          {(["open", "done", "all"] as Filter[]).map((f) => (
            <button
              key={f}
              className={"dtasks__filter" + (filter === f ? " dtasks__filter--on" : "")}
              onClick={() => setFilter(f)}
            >
              {f}
              <span>{counts[f]}</span>
            </button>
          ))}
        </div>
      </div>

      <form className="dtasks__new" onSubmit={submit}>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs building?"
        />
        <input
          className="dtasks__tagin"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          placeholder="tag"
        />
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value as DomainTask["priority"])}
        >
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <button type="submit" disabled={!title.trim()}>Add</button>
      </form>

      <div className="dtasks__list">
        {shown.length === 0 && (
          <div className="dtasks__empty">
            {filter === "done" ? "Nothing finished yet." : "All clear. Add the next piece of work."}
          </div>
        )}
        {shown.map((t) => (
          <div key={t.id} className={"dtask" + (t.done ? " dtask--done" : "")}>
            <button className="dtask__check" onClick={() => toggleTask(t.id)} title="Toggle">
              {t.done ? "✓" : ""}
            </button>

            {editing === t.id ? (
              <input
                className="dtask__edit"
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => commitEdit(t.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit(t.id);
                  if (e.key === "Escape") setEditing(null);
                }}
              />
            ) : (
              <span
                className="dtask__title"
                onDoubleClick={() => { setEditing(t.id); setDraft(t.title); }}
                title="Double-click to edit"
              >
                {t.title}
              </span>
            )}

            {t.tag && <span className="dtask__tag">{t.tag}</span>}

            {t.file && (
              <button
                className="dtask__file"
                onClick={() => openInCode(t.file!)}
                title={t.file}
              >
                ⌥ {t.file.split(/[\\/]/).filter(Boolean).pop()}
              </button>
            )}

            {t.cardId ? (
              <button className="dtask__card" onClick={() => setSection("projects")} title="On the board">
                ▤
              </button>
            ) : (
              <button
                className="dtask__card dtask__card--add"
                onClick={() => taskToCard(t.id)}
                title="Add to the planning board"
              >
                ▤ +
              </button>
            )}

            <button
              className="dtask__pri"
              style={{
                color: PRIORITY[t.priority].color,
                borderColor: PRIORITY[t.priority].color + "55",
              }}
              onClick={() =>
                patchTask(t.id, {
                  priority:
                    t.priority === "high" ? "low" : t.priority === "medium" ? "high" : "medium",
                })
              }
              title="Cycle priority"
            >
              {PRIORITY[t.priority].label}
            </button>

            <button className="dtask__del" onClick={() => removeTask(t.id)} title="Delete">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}
