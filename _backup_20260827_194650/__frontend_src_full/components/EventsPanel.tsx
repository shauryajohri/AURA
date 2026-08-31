import { useEffect, useState } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { api, type Task } from "../api";

// Pulls the real pending tasks from memory/store.py via the bridge.
export default function EventsPanel() {
  const [open, setOpen] = useLocalStorage<boolean>("aura.eventsOpen", true);
  const [hidden, setHidden] = useLocalStorage<boolean>("aura.eventsHidden", false);
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.getTasks().then((t) => alive && setTasks(t.filter((x) => x.status !== "done").slice(0, 4))).catch(() => {});
    load();
    const id = setInterval(load, 15000); // keep fresh; tasks may change elsewhere
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (hidden) {
    return (
      <button className="events-reveal" onClick={() => setHidden(false)} title="Show tasks">
        Upcoming Tasks
      </button>
    );
  }

  return (
    <div className={"events " + (open ? "" : "events--collapsed")}>
      <div className="events__head">
        <span>UPCOMING TASKS</span>
        <span className="events__actions">
          <button className="events__btn" onClick={() => setOpen((o) => !o)} title={open ? "Collapse" : "Expand"}>
            {open ? "–" : "+"}
          </button>
          <button className="events__btn" onClick={() => setHidden(true)} title="Hide">
            {"×"}
          </button>
        </span>
      </div>

      {open && (
        <>
          {tasks.length === 0 ? (
            <p className="events__none">No pending tasks.</p>
          ) : (
            <ul className="events__list">
              {tasks.map((t) => (
                <li key={t.id} className="events__item">
                  <span className="events__icon">{"◷"}</span>
                  <div className="events__body">
                    <span className="events__title">{t.title}</span>
                    <span className="events__eta">{t.priority} priority</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
