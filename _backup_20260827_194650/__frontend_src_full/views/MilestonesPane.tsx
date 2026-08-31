import { useEffect, useMemo, useState } from "react";
import { api, type Task } from "../api";

/**
 * Milestones — one card per project, showing how far it's come.
 *
 * A project's milestone IS its completion: tasks done vs. total, the next
 * deadline, and whether anything is overdue. Deliberately derived from tasks
 * rather than a separate table, so a project exists the moment you tag a task
 * with it and nothing can drift out of sync.
 */

interface Group {
  name: string;
  total: number;
  done: number;
  overdue: number;
  next: string | null;
  latest: string | null;
}

export default function MilestonesPane() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api.getTasks().then(setTasks).catch(() => setOffline(true));
  }, []);

  const groups = useMemo<Group[]>(() => {
    if (!tasks) return [];
    const today = new Date().toISOString().slice(0, 10);
    const map = new Map<string, Group>();
    for (const t of tasks) {
      const name = t.project || "Unassigned";
      let g = map.get(name);
      if (!g) { g = { name, total: 0, done: 0, overdue: 0, next: null, latest: null }; map.set(name, g); }
      g.total += 1;
      if (t.done_at) {
        g.done += 1;
        if (!g.latest || t.done_at > g.latest) g.latest = t.done_at;
      } else if (t.due) {
        if (t.due < today) g.overdue += 1;
        if (!g.next || t.due < g.next) g.next = t.due;
      }
    }
    return Array.from(map.values()).sort((a, b) => b.total - a.total);
  }, [tasks]);

  if (offline) return <p className="pane-note">Brain offline — milestones need server.py.</p>;
  if (!tasks) return <p className="pane-note">Measuring progress…</p>;
  if (groups.length === 0)
    return <p className="pane-note">No projects yet — tag a task with a project and it appears here.</p>;

  return (
    <div className="milestones">
      {groups.map((g) => {
        const pct = g.total ? Math.round((g.done / g.total) * 100) : 0;
        const complete = pct === 100;
        return (
          <article key={g.name} className={"milecard" + (complete ? " milecard--done" : "")}>
            <header>
              <h4>{g.name}</h4>
              <strong>{pct}%</strong>
            </header>
            <div className="taskboard__track"><span style={{ width: pct + "%" }} /></div>
            <div className="milecard__meta">
              <span>{g.done}/{g.total} tasks</span>
              {g.overdue > 0 && <span className="milecard__over">{g.overdue} overdue</span>}
              {g.next && !complete && (
                <span>next {new Date(g.next + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
              )}
              {complete && <span className="milecard__win">✦ milestone reached</span>}
            </div>
          </article>
        );
      })}
    </div>
  );
}
