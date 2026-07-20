import { useEffect, useState } from "react";
import { api, Task } from "../../../api";

// ============================================================================
// Domain Tasks — the full task manager, live against /api/tasks.
// Same store AURA manages by voice; here you get the whole surface:
// add with priority, inline edit, complete/reopen, delete.
// ============================================================================

const PRIORITIES = ["high", "medium", "low"] as const;
const PRIO_COLOR: Record<string, string> = {
  high: "#ff7a7a",
  medium: "#f5a623",
  low: "#35e08f",
};

export default function TasksBoard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [offline, setOffline] = useState(false);
  const [input, setInput] = useState("");
  const [prio, setPrio] = useState<(typeof PRIORITIES)[number]>("medium");
  const [editing, setEditing] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  const refresh = () =>
    api.getTasks().then((t) => { setTasks(t); setOffline(false); }).catch(() => setOffline(true));

  useEffect(() => { refresh(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (!t) return;
    setInput("");
    await api.addTask(t, prio).catch(() => setOffline(true));
    refresh();
  };

  const toggle = async (t: Task) => {
    await (t.status === "done" ? api.uncompleteTask(t.id) : api.completeTask(t.id)).catch(() => {});
    refresh();
  };

  const remove = async (id: number) => {
    await api.deleteTask(id).catch(() => {});
    refresh();
  };

  const commitEdit = async () => {
    if (editing !== null && editText.trim()) {
      await api.updateTask(editing, { title: editText.trim() }).catch(() => {});
      refresh();
    }
    setEditing(null);
  };

  const setPriority = async (t: Task, p: string) => {
    await api.updateTask(t.id, { priority: p }).catch(() => {});
    refresh();
  };

  const pending = tasks.filter((t) => t.status !== "done");
  const done = tasks.filter((t) => t.status === "done");

  const row = (t: Task) => (
    <div key={t.id} className={"dtask" + (t.status === "done" ? " dtask--done" : "")}>
      <button
        className={"dtask__check" + (t.status === "done" ? " dtask__check--on" : "")}
        onClick={() => toggle(t)}
        title={t.status === "done" ? "Reopen" : "Complete"}
      >
        {t.status === "done" ? "✓" : ""}
      </button>

      {editing === t.id ? (
        <input
          className="dtask__edit"
          autoFocus
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit();
            if (e.key === "Escape") setEditing(null);
          }}
        />
      ) : (
        <span
          className="dtask__title"
          title="Double-click to edit"
          onDoubleClick={() => { setEditing(t.id); setEditText(t.title); }}
        >
          {t.title}
        </span>
      )}

      <span className="dtask__prios">
        {PRIORITIES.map((p) => (
          <button
            key={p}
            className={"dtask__prio" + (t.priority === p ? " dtask__prio--on" : "")}
            style={{ ["--pc" as string]: PRIO_COLOR[p] }}
            title={p}
            onClick={() => setPriority(t, p)}
          />
        ))}
      </span>

      <button className="dtask__x" onClick={() => remove(t.id)}>✕</button>
    </div>
  );

  return (
    <div className="dtasks">
      <form className="dtasks__add" onSubmit={add}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What needs doing?"
        />
        <div className="dtasks__prioselect">
          {PRIORITIES.map((p) => (
            <button
              key={p}
              type="button"
              className={"dtask__prio" + (prio === p ? " dtask__prio--on" : "")}
              style={{ ["--pc" as string]: PRIO_COLOR[p] }}
              title={p}
              onClick={() => setPrio(p)}
            />
          ))}
        </div>
        <button type="submit" className="dtasks__addbtn">Add</button>
      </form>

      <div className="dtasks__cols">
        <div className="dtasks__col">
          <div className="dtasks__colhead">
            <span>In flight</span>
            <span className="dtasks__count">{pending.length}</span>
          </div>
          {offline && <div className="dcode__empty">Brain offline — start server.py</div>}
          {!offline && pending.length === 0 && <div className="dcode__empty">Clear skies. Add something.</div>}
          {pending.map(row)}
        </div>
        <div className="dtasks__col">
          <div className="dtasks__colhead">
            <span>Done</span>
            <span className="dtasks__count">{done.length}</span>
          </div>
          {!offline && done.length === 0 && <div className="dcode__empty">Nothing finished yet.</div>}
          {done.map(row)}
        </div>
      </div>
    </div>
  );
}
