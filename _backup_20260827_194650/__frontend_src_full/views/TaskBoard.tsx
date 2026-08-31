import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Task } from "../api";

/**
 * The task manager — Today / Upcoming / Completed with real deadlines,
 * projects and priorities.
 *
 * Sectioning is derived, not stored: a task is "Today" if it's due today (or
 * overdue), or has no due date but sits in the `now` bucket. Everything else
 * pending is "Upcoming". That way the existing now/later buckets keep working
 * for tasks that were created before due dates existed.
 */

const PRIORITIES = ["high", "medium", "low"] as const;
const PRIORITY_DOT: Record<string, string> = { high: "tdot--high", medium: "tdot--med", low: "tdot--low" };

const todayISO = () => new Date().toISOString().slice(0, 10);

const dueLabel = (due: string): { text: string; cls: string } => {
  const d = new Date(due + "T00:00:00");
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff < 0) return { text: `${-diff}d overdue`, cls: "tdue--over" };
  if (diff === 0) return { text: "due today", cls: "tdue--now" };
  if (diff === 1) return { text: "due tomorrow", cls: "tdue--soon" };
  if (diff < 7) return { text: `due in ${diff}d`, cls: "tdue--soon" };
  return { text: "due " + d.toLocaleDateString(undefined, { month: "short", day: "numeric" }), cls: "" };
};

export default function TaskBoard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const [draft, setDraft] = useState("");
  const [draftPriority, setDraftPriority] = useState<string>("medium");
  const [draftDue, setDraftDue] = useState("");
  const [draftProject, setDraftProject] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");

  const load = useCallback(() => {
    api.getTasks()
      .then((t) => { setTasks(t); setOffline(false); })
      .catch(() => setOffline(true))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  // "Polish" — hand a rough title to AURA and take back a clean one. Manual
  // tasks deserve the same treatment as the ones she extracts herself.
  const [polishing, setPolishing] = useState(false);
  const polish = () => {
    const title = draft.trim();
    if (!title) return;
    setPolishing(true);
    api.rewriteTask(title)
      .then((r) => { if (r.ok && r.title) setDraft(r.title); })
      .catch(() => {})
      .finally(() => setPolishing(false));
  };

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const title = draft.trim();
    if (!title) return;
    api.addTask(title, draftPriority, draftDue && draftDue <= todayISO() ? "now" : "now", {
      due: draftDue || null,
      project: draftProject.trim() || null,
    }).then(() => { setDraft(""); setDraftDue(""); load(); }).catch(() => {});
  };

  const patch = (id: number, p: Parameters<typeof api.updateTask>[1]) =>
    api.updateTask(id, p).then(load).catch(() => {});

  const projects = useMemo(() => {
    const s = new Set<string>();
    for (const t of tasks) if (t.project) s.add(t.project);
    return ["all", ...Array.from(s).sort()];
  }, [tasks]);

  const visible = projectFilter === "all" ? tasks : tasks.filter((t) => t.project === projectFilter);
  const done = visible.filter((t) => !!t.done_at);
  const open = visible.filter((t) => !t.done_at);
  const today = open.filter((t) => (t.due ? t.due <= todayISO() : t.bucket === "now"));
  const upcoming = open.filter((t) => !today.includes(t));
  const pct = visible.length ? Math.round((done.length / visible.length) * 100) : 0;

  const row = (t: Task) => {
    const due = t.due ? dueLabel(t.due) : null;
    return (
      <div key={t.id} className={"trow" + (t.done_at ? " trow--done" : "")}>
        <button
          className={"trow__check" + (t.done_at ? " trow__check--on" : "")}
          title={t.done_at ? "Mark unfinished" : "Complete"}
          onClick={() =>
            (t.done_at ? api.uncompleteTask(t.id) : api.completeTask(t.id)).then(load).catch(() => {})
          }
        >
          {t.done_at ? "✓" : ""}
        </button>

        <span className={"tdot " + (PRIORITY_DOT[t.priority] ?? "tdot--med")} title={t.priority} />

        {editId === t.id ? (
          <input
            className="trow__edit"
            value={editText}
            autoFocus
            onChange={(e) => setEditText(e.target.value)}
            onBlur={() => { patch(t.id, { title: editText }); setEditId(null); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") { patch(t.id, { title: editText }); setEditId(null); }
              if (e.key === "Escape") setEditId(null);
            }}
          />
        ) : (
          <span className="trow__title" onDoubleClick={() => { setEditId(t.id); setEditText(t.title); }}>
            {t.title}
          </span>
        )}

        {t.origin === "aura" && <span className="trow__ai" title="Suggested by AURA">✦ AURA</span>}
        {t.project && <span className="trow__proj">{t.project}</span>}
        {due && <span className={"tdue " + due.cls}>{due.text}</span>}

        <span className="trow__tools">
          <select
            className="trow__prio"
            value={t.priority}
            onChange={(e) => patch(t.id, { priority: e.target.value })}
            title="Priority"
          >
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input
            className="trow__due"
            type="date"
            value={t.due ?? ""}
            onChange={(e) => patch(t.id, { due: e.target.value || "" })}
            title="Due date"
          />
          <button className="trow__del" title="Delete"
            onClick={() => api.deleteTask(t.id).then(load).catch(() => {})}>✕</button>
        </span>
      </div>
    );
  };

  if (loading) return <p className="pane-note">Loading tasks…</p>;
  if (offline) return <p className="pane-note">Brain offline — start server.py to manage tasks.</p>;

  return (
    <div className="taskboard">
      <div className="taskboard__bar">
        <div className="taskboard__progress">
          <div className="taskboard__progresshead">
            <span>{done.length} of {visible.length} complete</span>
            <strong>{pct}%</strong>
          </div>
          <div className="taskboard__track"><span style={{ width: pct + "%" }} /></div>
        </div>
        {projects.length > 1 && (
          <div className="taskboard__projects">
            {projects.map((p) => (
              <button key={p}
                className={"pageshell__tab memtl__cat" + (projectFilter === p ? " pageshell__tab--on" : "")}
                onClick={() => setProjectFilter(p)}>
                {p}
              </button>
            ))}
          </div>
        )}
      </div>

      <form className="taskadd" onSubmit={add}>
        <input
          className="taskadd__title"
          placeholder="What needs doing?"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <input
          className="taskadd__proj"
          placeholder="Project"
          value={draftProject}
          onChange={(e) => setDraftProject(e.target.value)}
          list="aura-projects"
        />
        <datalist id="aura-projects">
          {projects.filter((p) => p !== "all").map((p) => <option key={p} value={p} />)}
        </datalist>
        <input className="taskadd__due" type="date" value={draftDue} onChange={(e) => setDraftDue(e.target.value)} />
        <select value={draftPriority} onChange={(e) => setDraftPriority(e.target.value)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <button
          type="button"
          className="taskadd__polish"
          onClick={polish}
          disabled={!draft.trim() || polishing}
          title="Let AURA rewrite this into a proper task title"
        >
          {polishing ? "…" : "✦"}
        </button>
        <button type="submit" disabled={!draft.trim()}>Add</button>
      </form>

      <section className="taskgroup">
        <h3 className="memtl__title">Today · {today.length}</h3>
        {today.length === 0 ? <p className="pane-note">Nothing due today. Enjoy it.</p> : today.map(row)}
      </section>

      <section className="taskgroup">
        <h3 className="memtl__title">Upcoming · {upcoming.length}</h3>
        {upcoming.length === 0 ? <p className="pane-note">Nothing queued.</p> : upcoming.map(row)}
      </section>

      {done.length > 0 && (
        <section className="taskgroup taskgroup--done">
          <h3 className="memtl__title">Completed · {done.length}</h3>
          {done.slice(0, 25).map(row)}
        </section>
      )}
    </div>
  );
}
