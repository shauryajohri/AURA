import { useCallback, useEffect, useState } from "react";
import { api, type Task } from "../api";

/**
 * Tasks — everything that needs doing, now or later.
 *
 * The counterpart to Quests, and the distinction matters: a task is a thing
 * to do, a quest is time you've committed to today with AURA watching. So
 * Tasks is the backlog you think in, and any task can be promoted into a
 * quest the moment you decide today is the day.
 */

const PRIORITIES = ["high", "medium", "low"] as const;

const PRIORITY_DOT: Record<string, string> = {
  high: "tdot--high",
  medium: "tdot--med",
  low: "tdot--low",
};

export default function TasksView() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const [draft, setDraft] = useState("");
  const [draftPriority, setDraftPriority] = useState<string>("medium");
  const [draftBucket, setDraftBucket] = useState<"now" | "later">("now");
  const [editId, setEditId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [promoting, setPromoting] = useState<number | null>(null);
  const [promoteMins, setPromoteMins] = useState(60);
  const [flash, setFlash] = useState("");

  const load = useCallback(() => {
    api
      .getTasks()
      .then((t) => {
        setTasks(t);
        setOffline(false);
        setLoading(false);
      })
      .catch(() => {
        setOffline(true);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = draft.trim();
    if (!title) return;
    setDraft("");
    await api.addTask(title, draftPriority, draftBucket).catch(() => setOffline(true));
    load();
  };

  const saveEdit = async (id: number) => {
    await api.updateTask(id, { title: editText.trim() }).catch(() => setOffline(true));
    setEditId(null);
    load();
  };

  const promote = async (t: Task) => {
    const r = await api.promoteTask(t.id, promoteMins).catch(() => null);
    setPromoting(null);
    if (r?.ok) {
      setFlash(
        `"${r.title}" is a quest now${
          r.target_minutes ? ` — ${r.target_minutes}m` : " — untimed"
        }. AURA will watch for it.`,
      );
      setTimeout(() => setFlash(""), 6000);
    }
    load();
  };

  const now = tasks.filter((t) => t.status !== "done" && t.bucket !== "later");
  const later = tasks.filter((t) => t.status !== "done" && t.bucket === "later");
  const done = tasks.filter((t) => t.status === "done");

  const row = (t: Task) => (
    <li key={t.id} className="trow">
      <button
        className={"trow__check" + (t.status === "done" ? " trow__check--on" : "")}
        title={t.status === "done" ? "Reopen" : "Mark done"}
        onClick={() =>
          (t.status === "done" ? api.uncompleteTask(t.id) : api.completeTask(t.id)).then(load)
        }
      >
        {t.status === "done" ? "✓" : ""}
      </button>

      <span className={"tdot " + (PRIORITY_DOT[t.priority] || "tdot--med")} />

      {editId === t.id ? (
        <input
          className="trow__edit"
          value={editText}
          autoFocus
          onChange={(e) => setEditText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveEdit(t.id);
            if (e.key === "Escape") setEditId(null);
          }}
          onBlur={() => saveEdit(t.id)}
        />
      ) : (
        <span
          className="trow__text"
          title="Double-click to rename"
          onDoubleClick={() => {
            setEditId(t.id);
            setEditText(t.title);
          }}
        >
          {t.title}
        </span>
      )}

      <span className="trow__actions">
        {t.status !== "done" && (
          <>
            <button
              onClick={() =>
                api.setTaskBucket(t.id, t.bucket === "later" ? "now" : "later").then(load)
              }
              title={t.bucket === "later" ? "Move to Now" : "Push to Later"}
            >
              {t.bucket === "later" ? "→ now" : "→ later"}
            </button>
            <button
              onClick={() => {
                setPromoting(promoting === t.id ? null : t.id);
                setPromoteMins(60);
              }}
              title="Track this as a quest today"
            >
              quest
            </button>
          </>
        )}
        <button onClick={() => api.deleteTask(t.id).then(load)}>×</button>
      </span>

      {promoting === t.id && (
        <div className="tpromote">
          <span>Track for</span>
          <input
            type="number"
            min={0}
            value={promoteMins}
            onChange={(e) => setPromoteMins(Number(e.target.value))}
          />
          <span>min — 0 to just monitor</span>
          <button onClick={() => promote(t)}>Make quest</button>
          <button onClick={() => setPromoting(null)}>Cancel</button>
        </div>
      )}
    </li>
  );

  return (
    <div className="view">
      <div className="view__head">
        <h2>Tasks</h2>
        <span className="view__count">
          {now.length} now · {later.length} later
        </span>
      </div>
      <p className="view__hint">
        Everything that needs doing. Move things between Now and Later, and
        promote anything into a tracked quest when today's the day.
      </p>

      <form className="taskadd" onSubmit={add}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="What needs doing?"
        />
        <select value={draftPriority} onChange={(e) => setDraftPriority(e.target.value)}>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          value={draftBucket}
          onChange={(e) => setDraftBucket(e.target.value as "now" | "later")}
        >
          <option value="now">now</option>
          <option value="later">later</option>
        </select>
        <button type="submit">Add</button>
      </form>

      {flash && <p className="tflash">{flash}</p>}

      {loading && <p className="view__empty">Loading...</p>}
      {offline && !loading && (
        <p className="view__empty">Brain offline — start AURA to load tasks.</p>
      )}

      {!loading && !offline && (
        <>
          <div className="intel-sec">
            <h3 className="intel-sec__title">
              Now<span className="intel-sec__count">{now.length}</span>
            </h3>
            {now.length === 0 ? (
              <p className="intel-empty">Nothing queued for today.</p>
            ) : (
              <ul className="tlist">{now.map(row)}</ul>
            )}
          </div>

          <div className="intel-sec">
            <h3 className="intel-sec__title">
              Later<span className="intel-sec__count">{later.length}</span>
            </h3>
            {later.length === 0 ? (
              <p className="intel-empty">Backlog's empty.</p>
            ) : (
              <ul className="tlist">{later.map(row)}</ul>
            )}
          </div>

          {done.length > 0 && (
            <div className="intel-sec">
              <h3 className="intel-sec__title">
                Done<span className="intel-sec__count">{done.length}</span>
              </h3>
              <ul className="tlist tlist--done">{done.slice(0, 25).map(row)}</ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
