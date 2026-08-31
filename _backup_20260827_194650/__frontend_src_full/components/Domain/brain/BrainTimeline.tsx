import { useMemo, useState } from "react";
import { NODE_META, whenLabel, type NodeType } from "../../../brainApi";
import { useBrainStore } from "../../../stores/brainStore";
import NoProject from "./NoProject";

// ============================================================================
// Module 13 — Timeline.
//
// The project's own history, not the app's activity log: commits, decisions,
// finished tasks and milestones, newest first, grouped by day, searchable.
// Every row opens the node drawer, so "what happened on Tuesday" leads straight
// into "and why did we do that".
// ============================================================================

const KINDS: NodeType[] = ["commit", "decision", "task", "milestone"];

/** Backend `when` is local ISO or a git date — group on the date part only. */
function dayKey(when: string | null): string {
  if (!when) return "unknown";
  const d = new Date(when);
  if (!isNaN(d.getTime())) return d.toDateString();
  return when.slice(0, 10);
}

function dayLabel(key: string): string {
  const d = new Date(key);
  if (isNaN(d.getTime())) return key;
  const today = new Date().toDateString();
  const yest = new Date(Date.now() - 86400000).toDateString();
  if (d.toDateString() === today) return "Today";
  if (d.toDateString() === yest) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function BrainTimeline() {
  const activeId = useBrainStore((s) => s.activeId);
  const timeline = useBrainStore((s) => s.timeline);
  const openNode = useBrainStore((s) => s.openNode);
  const refresh = useBrainStore((s) => s.refresh);

  const [kinds, setKinds] = useState<Set<NodeType>>(new Set(KINDS));
  const [q, setQ] = useState("");

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return timeline.filter(
      (e) => kinds.has(e.type) && (!needle || e.title.toLowerCase().includes(needle))
    );
  }, [timeline, kinds, q]);

  const days = useMemo(() => {
    const map = new Map<string, typeof shown>();
    for (const e of shown) {
      const k = dayKey(e.when);
      map.set(k, [...(map.get(k) ?? []), e]);
    }
    return [...map.entries()];
  }, [shown]);

  if (!activeId) return <NoProject what="read the project's history" />;

  const toggle = (t: NodeType) =>
    setKinds((s) => {
      const n = new Set(s);
      if (n.has(t)) n.delete(t); else n.add(t);
      return n;
    });

  return (
    <div className="brtime">
      <header className="brdash__head">
        <div>
          <h2 className="brproj__title">TIMELINE</h2>
          <p className="brproj__sub">
            Everything that actually happened — {timeline.length} event
            {timeline.length === 1 ? "" : "s"}.
          </p>
        </div>
        <div className="brdash__acts">
          <input
            className="brinput brinput--sm"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search history…"
          />
          <button className="brbtn" onClick={() => refresh()}>↻</button>
        </div>
      </header>

      <div className="brgraph__legend">
        {KINDS.map((t) => (
          <button
            key={t}
            className={"brlegend" + (kinds.has(t) ? "" : " brlegend--off")}
            style={{ borderColor: NODE_META[t].color }}
            onClick={() => toggle(t)}
          >
            <span style={{ color: NODE_META[t].color }}>{NODE_META[t].icon}</span>
            {NODE_META[t].label}
          </button>
        ))}
      </div>

      {days.length === 0 && (
        <p className="brdim">
          Nothing recorded yet. Sync git from the Dashboard, or make a decision in Brainstorm.
        </p>
      )}

      <div className="brtime__log">
        {days.map(([key, events]) => (
          <div key={key} className="brtime__day">
            <div className="brtime__daylabel">{dayLabel(key)}</div>
            {events.map((e) => (
              <button key={e.id} className="brtime__row" onClick={() => openNode(e.id)}>
                <span className="brtime__icon" style={{ color: NODE_META[e.type].color }}>
                  {NODE_META[e.type].icon}
                </span>
                <span className="brtime__title">{e.title}</span>
                {e.type === "task" && <span className="brchip">done</span>}
                <span className="brtime__when">{whenLabel(e.when)}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
