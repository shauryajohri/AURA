import { useMemo, useState } from "react";
import {
  useDomainStore,
  type Activity,
  type ActivityKind,
} from "../../../stores/domainStore";

// ============================================================================
// History — everything that changed in the Domain, newest first.
//
// Written by the store itself, so nothing has to remember to log: status
// flips, cards moving, tasks ticked, files saved, docs and notes edited,
// Office files written back. Grouped by day, filterable by kind, and
// scopeable to the open project.
// ============================================================================

const KIND_META: Record<ActivityKind, { label: string; icon: string; color: string }> = {
  project: { label: "Projects", icon: "▣", color: "#8b5cff" },
  task: { label: "Tasks", icon: "☑", color: "#38e1ff" },
  card: { label: "Board", icon: "▤", color: "#b18bff" },
  code: { label: "Code", icon: "⌥", color: "#ffd866" },
  doc: { label: "Docs", icon: "≡", color: "#35e08f" },
  note: { label: "Notes", icon: "✎", color: "#f472b6" },
  roadmap: { label: "Roadmap", icon: "◇", color: "#4cc9ff" },
  source: { label: "Files", icon: "🗀", color: "#ff8c42" },
  office: { label: "Apps", icon: "◈", color: "#2b7cd3" },
  terminal: { label: "Terminal", icon: "❯", color: "#8b8fca" },
};

const time = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const dayLabel = (ts: number) => {
  const d = new Date(ts);
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Today";
  if (same(d, yest)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
};

export default function HistoryView() {
  const activity = useDomainStore((s) => s.activity);
  const activeId = useDomainStore((s) => s.activeId);
  const clearActivity = useDomainStore((s) => s.clearActivity);
  const openInCode = useDomainStore((s) => s.openInCode);

  const [kinds, setKinds] = useState<Set<ActivityKind>>(new Set());
  const [scoped, setScoped] = useState(true);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    return activity.filter((a) => {
      if (scoped && activeId && a.projectId !== activeId) return false;
      if (kinds.size && !kinds.has(a.kind)) return false;
      if (query) {
        const hay = (a.summary + " " + (a.detail ?? "")).toLowerCase();
        if (!hay.includes(query.toLowerCase())) return false;
      }
      return true;
    });
  }, [activity, kinds, scoped, activeId, query]);

  const days = useMemo(() => {
    const out: { label: string; items: Activity[] }[] = [];
    for (const a of filtered) {
      const label = dayLabel(a.ts);
      const last = out[out.length - 1];
      if (last?.label === label) last.items.push(a);
      else out.push({ label, items: [a] });
    }
    return out;
  }, [filtered]);

  const counts = useMemo(() => {
    const c = {} as Record<ActivityKind, number>;
    for (const a of activity) {
      if (scoped && activeId && a.projectId !== activeId) continue;
      c[a.kind] = (c[a.kind] ?? 0) + 1;
    }
    return c;
  }, [activity, scoped, activeId]);

  const toggle = (k: ActivityKind) =>
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <div className="dhist">
      <div className="dhist__head">
        <div>
          <h3>History</h3>
          <p>Every change AURA saw, newest first.</p>
        </div>
        <input
          className="dnotes__search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the log…"
        />
        <button
          className={"dhist__scope" + (scoped ? " dhist__scope--on" : "")}
          onClick={() => setScoped((v) => !v)}
          title="Limit to the open project"
        >
          {scoped ? "this project" : "all projects"}
        </button>
      </div>

      <div className="dhist__filters">
        {(Object.keys(KIND_META) as ActivityKind[]).map((k) => {
          const n = counts[k] ?? 0;
          if (!n && !kinds.has(k)) return null;
          return (
            <button
              key={k}
              className={"dhist__chip" + (kinds.has(k) ? " dhist__chip--on" : "")}
              style={{ ["--kc" as string]: KIND_META[k].color }}
              onClick={() => toggle(k)}
            >
              <span>{KIND_META[k].icon}</span>
              {KIND_META[k].label}
              <em>{n}</em>
            </button>
          );
        })}
        {kinds.size > 0 && (
          <button className="dhist__clearf" onClick={() => setKinds(new Set())}>clear filters</button>
        )}
      </div>

      <div className="dhist__log">
        {days.length === 0 && (
          <div className="dhist__empty">
            {activity.length === 0
              ? "Nothing logged yet. Move a card, tick a task or save a file and it lands here."
              : "No entries match that filter."}
          </div>
        )}

        {days.map((day) => (
          <div key={day.label} className="dhist__day">
            <div className="dhist__daylabel">
              {day.label}
              <span>{day.items.length}</span>
            </div>

            {day.items.map((a) => {
              const meta = KIND_META[a.kind];
              const isPath = a.detail && /[\\/]/.test(a.detail) && a.kind !== "project";
              return (
                <div key={a.id} className="dhist__row" style={{ ["--kc" as string]: meta.color }}>
                  <span className="dhist__time">{time(a.ts)}</span>
                  <span className="dhist__icon" title={meta.label}>{meta.icon}</span>
                  <div className="dhist__body">
                    <div className="dhist__summary">{a.summary}</div>
                    {a.detail && (
                      isPath ? (
                        <button
                          className="dhist__detail dhist__detail--link"
                          onClick={() => openInCode(a.detail!)}
                          title="Open in Code"
                        >
                          {a.detail}
                        </button>
                      ) : (
                        <div className="dhist__detail">{a.detail}</div>
                      )
                    )}
                  </div>
                  {!scoped && <span className="dhist__proj">{a.projectName}</span>}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {activity.length > 0 && (
        <div className="dhist__foot">
          <span>{activity.length} entries · oldest fall off after 500</span>
          <span className="dcode__spacer" />
          <button onClick={() => { if (confirm("Clear the whole history log?")) clearActivity(); }}>
            Clear log
          </button>
        </div>
      )}
    </div>
  );
}
