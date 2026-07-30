import { useMemo, useState } from "react";
import { TASK_META, type BrainNode, type TaskState } from "../../../brainApi";
import { taskFeatureMap, useBrainStore } from "../../../stores/brainStore";
import NoProject from "./NoProject";

// ============================================================================
// Module 4 (+ 7) — the generated task board.
//
// These tasks are not typed in by hand: they come out of features, out of task
// expansion, and they close themselves when a commit mentions them. The board's
// only job is to make that visible and let you move one column over.
//
// Grouping by feature is the default because a flat list of forty generated
// tasks tells you nothing about what you're actually building.
// ============================================================================

const COLUMNS: TaskState[] = ["todo", "in_progress", "blocked", "done"];

export default function BrainTasks() {
  const activeId = useBrainStore((s) => s.activeId);
  const nodes = useBrainStore((s) => s.nodes);
  const edges = useBrainStore((s) => s.edges);
  const setTaskStatus = useBrainStore((s) => s.setTaskStatus);
  const openNode = useBrainStore((s) => s.openNode);
  const capture = useBrainStore((s) => s.capture);
  const busy = useBrainStore((s) => s.busy);

  const [group, setGroup] = useState(true);
  const [text, setText] = useState("");

  const tasks = useMemo(() => nodes.filter((n) => n.type === "task"), [nodes]);
  const features = useMemo(() => nodes.filter((n) => n.type === "feature"), [nodes]);

  /** belongs_to points task→feature, but subtasks point task→task. Follow the
   *  chain so a subtask still lands under the feature it ultimately serves. */
  const belongs = useMemo(() => {
    const raw = taskFeatureMap(edges);
    const featureIds = new Set(features.map((f) => f.id));
    const resolved: Record<string, string> = {};
    for (const tid of Object.keys(raw)) {
      let cur: string | undefined = raw[tid];
      const seen = new Set<string>([tid]);
      while (cur && !featureIds.has(cur) && !seen.has(cur)) {
        seen.add(cur);
        cur = raw[cur];
      }
      if (cur && featureIds.has(cur)) resolved[tid] = cur;
    }
    return resolved;
  }, [edges, features]);

  /** tasks a commit closed itself (Module 7) — shown so auto-progress is visible. */
  const autoClosed = useMemo(() => {
    const s = new Set<string>();
    for (const e of edges) if (e.type === "completes") s.add(e.dst);
    return s;
  }, [edges]);

  if (!activeId) return <NoProject what="see the task board" />;

  const byStatus = (list: BrainNode[], s: TaskState) =>
    list.filter((t) => (t.status || "todo") === s);

  const addByTalking = async () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    await capture(t);
  };

  const card = (t: BrainNode) => {
    const st = (t.status || "todo") as TaskState;
    const i = COLUMNS.indexOf(st);
    const next = i >= 0 && i < COLUMNS.length - 1 ? COLUMNS[i + 1] : null;
    const auto = autoClosed.has(t.id);
    return (
      <div key={t.id} className={"brtask brtask--" + st}>
        <button className="brtask__title" onClick={() => openNode(t.id)}>{t.title}</button>
        <div className="brtask__foot">
          {auto && <span className="brchip brchip--auto">closed by commit</span>}
          {t.meta?.parent_task && <span className="brchip">subtask</span>}
          {next && (
            <button className="brlink brlink--quiet" onClick={() => setTaskStatus(t.id, next)}>
              → {TASK_META[next].label}
            </button>
          )}
          {st !== "todo" && (
            <button className="brlink brlink--quiet" onClick={() => setTaskStatus(t.id, "todo")}>
              reset
            </button>
          )}
        </div>
      </div>
    );
  };

  const columns = (list: BrainNode[]) => (
    <div className="brboard">
      {COLUMNS.map((s) => (
        <div key={s} className="brcol">
          <div className="brcol__head">
            <span style={{ color: TASK_META[s].color }}>{TASK_META[s].label}</span>
            <span className="brcol__n">{byStatus(list, s).length}</span>
          </div>
          <div className="brcol__cards">
            {byStatus(list, s).map(card)}
            {byStatus(list, s).length === 0 && <p className="brdim brdim--sm">—</p>}
          </div>
        </div>
      ))}
    </div>
  );

  const orphans = tasks.filter((t) => !belongs[t.id] || !features.some((f) => f.id === belongs[t.id]));

  return (
    <div className="brtasks">
      <header className="brdash__head">
        <div>
          <h2 className="brproj__title">TASKS</h2>
          <p className="brproj__sub">
            {tasks.length} task{tasks.length === 1 ? "" : "s"} generated from{" "}
            {features.length} feature{features.length === 1 ? "" : "s"}. Commits close them
            automatically.
          </p>
        </div>
        <label className="brtoggle">
          <input type="checkbox" checked={group} onChange={(e) => setGroup(e.target.checked)} />
          <span>group by feature</span>
        </label>
      </header>

      <div className="brtasks__add">
        <input
          className="brinput brinput--sm"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addByTalking()}
          placeholder="Describe work in a sentence — AURA turns it into a feature and its tasks…"
        />
        <button className="brbtn" onClick={addByTalking} disabled={!text.trim() || !!busy}>
          {busy ? "…" : "Add"}
        </button>
      </div>

      {tasks.length === 0 && (
        <p className="brdim">
          Nothing yet. Say what you want to build — in Brainstorm or in the box above.
        </p>
      )}

      {!group && tasks.length > 0 && columns(tasks)}

      {group &&
        features.map((f) => {
          const mine = tasks.filter((t) => belongs[t.id] === f.id);
          if (mine.length === 0) return null;
          const done = mine.filter((t) => t.status === "done").length;
          return (
            <section key={f.id} className="brgroup">
              <button className="brgroup__head" onClick={() => openNode(f.id)}>
                <span className="brgroup__name">◆ {f.title}</span>
                <span className="brdim">
                  {done}/{mine.length}
                  {f.meta?.priority ? " · " + f.meta.priority : ""}
                </span>
              </button>
              {columns(mine)}
            </section>
          );
        })}

      {group && orphans.length > 0 && (
        <section className="brgroup">
          <div className="brgroup__head">
            <span className="brgroup__name">Unassigned</span>
            <span className="brdim">{orphans.length}</span>
          </div>
          {columns(orphans)}
        </section>
      )}
    </div>
  );
}
