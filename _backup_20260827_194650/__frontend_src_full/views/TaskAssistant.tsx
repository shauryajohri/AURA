import { useState } from "react";
import { api, type SuggestedTask } from "../api";

/**
 * AI Task Assistant — turn a conversation into a clean, estimated task list.
 *
 * Two ways in: pull the recent chat with AURA, or paste notes / a meeting
 * transcript. She extracts the real action items, rewrites them into proper
 * task titles, groups related ones and estimates each.
 *
 * Nothing is saved until you press Add — suggestions are suggestions. Accepted
 * tasks are stored with origin="aura" so the board can badge them ✦.
 */

const COMPLEXITY_CLASS: Record<string, string> = {
  low: "sug__cx--low", medium: "sug__cx--med", high: "sug__cx--high",
};

interface Props {
  /** Called after tasks are written so the board can refresh. */
  onAdded?: () => void;
}

export default function TaskAssistant({ onAdded }: Props) {
  const [text, setText] = useState("");
  const [tasks, setTasks] = useState<SuggestedTask[] | null>(null);
  const [picked, setPicked] = useState<Record<number, boolean>>({});
  const [project, setProject] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [added, setAdded] = useState(0);

  const run = async (useChat: boolean) => {
    setBusy(useChat ? "chat" : "text"); setErr(""); setAdded(0);
    try {
      const r = await api.extractTasks(useChat ? "" : text);
      setTasks(r.tasks);
      setSource(r.source);
      // Everything starts checked — reviewing a list is faster than building one.
      setPicked(Object.fromEntries(r.tasks.map((_, i) => [i, true])));
      if (r.tasks.length === 0) {
        setErr(useChat
          ? "Nothing actionable in the recent conversation yet."
          : "No action items found in that text.");
      }
    } catch {
      setErr("Brain offline — the assistant needs server.py running.");
    } finally {
      setBusy("");
    }
  };

  const addSelected = async () => {
    if (!tasks) return;
    const chosen = tasks.filter((_, i) => picked[i]);
    if (chosen.length === 0) return;
    setBusy("add"); setErr("");
    try {
      for (const t of chosen) {
        await api.addTask(t.title, t.priority, "later", {
          project: project.trim() || t.group || null,
          origin: "aura",
        });
      }
      setAdded(chosen.length);
      setTasks(null);
      setText("");
      onAdded?.();
    } catch {
      setErr("Couldn't save the tasks — is the brain still running?");
    } finally {
      setBusy("");
    }
  };

  const selectedCount = tasks ? tasks.filter((_, i) => picked[i]).length : 0;
  const selectedHours = tasks
    ? Math.round(tasks.filter((_, i) => picked[i]).reduce((n, t) => n + t.hours, 0) * 10) / 10
    : 0;

  return (
    <div className="sug">
      <p className="pane-note">
        Talk through an idea with AURA, then let her pull the actual work out of it —
        or paste notes below. She rewrites each item into a proper task and estimates it.
      </p>

      <div className="sug__actions">
        <button className="taskadd-btn taskadd-btn--primary" disabled={!!busy} onClick={() => run(true)}>
          {busy === "chat" ? "Reading the conversation…" : "✦ Extract from recent chat"}
        </button>
      </div>

      <textarea
        className="sug__input"
        placeholder="…or paste notes, a transcript, a brain-dump — anything with work hiding in it."
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
      />
      <div className="sug__actions">
        <button className="taskadd-btn" disabled={!!busy || !text.trim()} onClick={() => run(false)}>
          {busy === "text" ? "Reading…" : "Extract from this text"}
        </button>
      </div>

      {err && <p className="pane-note sug__err">{err}</p>}
      {added > 0 && (
        <p className="pane-note sug__ok">
          Added {added} task{added === 1 ? "" : "s"} to your backlog — they're badged ✦ AURA on the board.
        </p>
      )}

      {tasks && tasks.length > 0 && (
        <div className="sug__result">
          <header className="sug__head">
            <span className="memtl__title">
              {tasks.length} found{source === "heuristic" ? " (offline mode)" : ""}
            </span>
            <span className="sug__summary">
              {selectedCount} selected · ~{selectedHours}h
            </span>
          </header>

          {tasks.map((t, i) => (
            <label key={i} className={"sug__row" + (picked[i] ? " sug__row--on" : "")}>
              <input
                type="checkbox"
                checked={!!picked[i]}
                onChange={(e) => setPicked((p) => ({ ...p, [i]: e.target.checked }))}
              />
              <span className="sug__title">{t.title}</span>
              <span className="trow__proj">{t.group}</span>
              <span className={"sug__cx " + (COMPLEXITY_CLASS[t.complexity] ?? "")}>{t.complexity}</span>
              <span className="sug__hours">~{t.hours}h</span>
            </label>
          ))}

          <div className="sug__actions">
            <input
              className="taskadd__proj sug__proj"
              placeholder="Project (optional — defaults to the group)"
              value={project}
              onChange={(e) => setProject(e.target.value)}
            />
            <button
              className="taskadd-btn taskadd-btn--primary"
              disabled={!!busy || selectedCount === 0}
              onClick={addSelected}
            >
              {busy === "add" ? "Adding…" : `Add ${selectedCount} to backlog`}
            </button>
            <button className="taskadd-btn" disabled={!!busy} onClick={() => setTasks(null)}>
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
