import { useEffect, useState } from "react";
import { api, type Task } from "../api";

export default function TasksView() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => api.getTasks().then((t) => { setTasks(t); setLoading(false); }).catch(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    await api.addTask(title.trim());
    setTitle("");
    load();
  };

  const toggle = async (t: Task) => {
    if (t.status === "done") await api.uncompleteTask(t.id);
    else await api.completeTask(t.id);
    load();
  };

  const pending = tasks.filter((t) => t.status !== "done");
  const done = tasks.filter((t) => t.status === "done");

  return (
    <div className="view">
      <div className="view__head">
        <h2>Tasks</h2>
        <span className="view__count">{pending.length} pending</span>
      </div>

      <form className="taskadd" onSubmit={add}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a task..." />
        <button type="submit">Add</button>
      </form>

      {loading && <p className="view__empty">Loading...</p>}
      {!loading && tasks.length === 0 && <p className="view__empty">No tasks yet. Add one above.</p>}

      <ul className="tasklist">
        {pending.map((t) => (
          <li key={t.id} className="taskrow">
            <button className="taskrow__check" onClick={() => toggle(t)} title="Complete" />
            <span className="taskrow__title">{t.title}</span>
            <span className={"taskrow__pri taskrow__pri--" + t.priority}>{t.priority}</span>
            <button className="taskrow__del" onClick={() => api.deleteTask(t.id).then(load)} title="Delete">{"×"}</button>
          </li>
        ))}
        {done.map((t) => (
          <li key={t.id} className="taskrow taskrow--done">
            <button className="taskrow__check taskrow__check--on" onClick={() => toggle(t)} title="Undo">{"✓"}</button>
            <span className="taskrow__title">{t.title}</span>
            <button className="taskrow__del" onClick={() => api.deleteTask(t.id).then(load)} title="Delete">{"×"}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
