import { useEffect, useState } from "react";
import { NODE_META, whenLabel } from "../../../brainApi";
import { useBrainStore } from "../../../stores/brainStore";
import { useDomainStore } from "../../../stores/domainStore";
import NoProject from "./NoProject";

// ============================================================================
// Modules 8 + 14 — Progress Engine and Project Dashboard.
//
// Not a single percentage. Buckets, per-feature rollup, the one thing that is
// actually blocking the most work, and the recent events that moved the needle.
// Every number here is computed server-side from the graph, never from the UI.
// ============================================================================

export default function BrainDashboard() {
  const activeId = useBrainStore((s) => s.activeId);
  const dash = useBrainStore((s) => s.dashboard);
  const progress = useBrainStore((s) => s.progress);
  const counts = useBrainStore((s) => s.dashboard?.counts ?? {});
  const loading = useBrainStore((s) => s.loading);
  const busy = useBrainStore((s) => s.busy);
  const refresh = useBrainStore((s) => s.refresh);
  const rescan = useBrainStore((s) => s.rescan);
  const openNode = useBrainStore((s) => s.openNode);
  const loadProjects = useBrainStore((s) => s.loadProjects);
  const setSection = useDomainStore((s) => s.setSection);

  const [note, setNote] = useState("");

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  if (!activeId) return <NoProject what="see how it's going" />;

  const p = dash?.project;
  const pct = progress?.percent ?? 0;
  const nextFeature = (progress?.by_feature ?? [])
    .filter((f) => f.percent < 100)
    .sort((a, b) => b.percent - a.percent)[0];

  const doRescan = async () => {
    setNote(await rescan());
    setTimeout(() => setNote(""), 6000);
  };

  return (
    <div className="brdash">
      <header className="brdash__head">
        <div>
          <h2 className="brproj__title">{p?.name ?? "PROJECT"}</h2>
          <p className="brproj__sub">{p?.root || p?.repo_url || "no folder linked"}</p>
        </div>
        <div className="brdash__acts">
          <button className="brbtn" onClick={() => setSection("research")}>✧ Research</button>
          <button className="brbtn" onClick={() => setSection("graph")}>◉ Knowledge graph</button>
          <button className="brbtn" onClick={doRescan} disabled={!!busy}>⎇ Sync git</button>
          <button className="brbtn" onClick={() => refresh()} disabled={loading}>↻</button>
        </div>
      </header>

      {busy && <div className="brnote brnote--busy">{busy}</div>}
      {note && <div className="brnote">{note}</div>}

      <div className="brdash__hero">
        <div className="brdash__ring" style={{ ["--pct" as string]: pct }}>
          <span className="brdash__pct">{pct}%</span>
          <span className="brdash__pctlabel">complete</span>
        </div>
        <div className="brdash__buckets">
          <Bucket n={progress?.completed ?? 0} label="Completed" color="#35e08f" />
          <Bucket n={progress?.in_progress ?? 0} label="Working" color="#38e1ff" />
          <Bucket n={progress?.blocked ?? 0} label="Blocked" color="#ff6b6b" />
          <Bucket n={progress?.remaining ?? 0} label="Remaining" color="#8b8fca" />
        </div>
      </div>

      <p className="brdash__summary">{progress?.summary ?? "Nothing planned yet."}</p>

      <div className="brdash__cols">
        <section className="brpanel">
          <h4 className="brpanel__title">Feature progress</h4>
          {(progress?.by_feature ?? []).length === 0 && (
            <p className="brdim">
              No features yet. Talk about the project in Brainstorm — features and their
              tasks appear here on their own.
            </p>
          )}
          {(progress?.by_feature ?? []).map((f) => (
            <button key={f.feature_id} className="brfeat" onClick={() => openNode(f.feature_id)}>
              <span className="brfeat__name">{f.feature}</span>
              <span className="brfeat__bar">
                <span className="brfeat__fill" style={{ width: f.percent + "%" }} />
              </span>
              <span className="brfeat__pct">
                {f.completed}/{f.total}
              </span>
            </button>
          ))}
        </section>

        <section className="brpanel">
          <h4 className="brpanel__title">Attention</h4>
          {progress?.biggest_blocker ? (
            <button className="brblock" onClick={() => openNode(progress.biggest_blocker!.id)}>
              <span className="brblock__label">Biggest blocker</span>
              <span className="brblock__title">{progress.biggest_blocker.title}</span>
              <span className="brdim">
                {progress.biggest_blocker.dependents} task(s) waiting
                {progress.biggest_blocker.reason ? " · " + progress.biggest_blocker.reason : ""}
              </span>
            </button>
          ) : (
            <p className="brdim">Nothing is blocked.</p>
          )}

          {nextFeature && (
            <div className="brblock brblock--quiet">
              <span className="brblock__label">Next milestone</span>
              <span className="brblock__title">{nextFeature.feature}</span>
              <span className="brdim">{nextFeature.percent}% there</span>
            </div>
          )}

          <div className="brcounts">
            {Object.entries(counts)
              .filter(([t]) => t in NODE_META)
              .map(([t, n]) => (
                <span key={t} className="brchip" title={t}>
                  {NODE_META[t as keyof typeof NODE_META].icon} {n}{" "}
                  {NODE_META[t as keyof typeof NODE_META].label.toLowerCase()}
                </span>
              ))}
          </div>
        </section>

        <section className="brpanel">
          <h4 className="brpanel__title">Recently</h4>
          {(dash?.recent ?? []).length === 0 && <p className="brdim">Nothing has happened yet.</p>}
          {(dash?.recent ?? []).map((e) => (
            <button key={e.id} className="brevent" onClick={() => openNode(e.id)}>
              <span className="brevent__icon" style={{ color: NODE_META[e.type].color }}>
                {NODE_META[e.type].icon}
              </span>
              <span className="brevent__title">{e.title}</span>
              <span className="brevent__when">{whenLabel(e.when)}</span>
            </button>
          ))}
          <button className="brlink" onClick={() => setSection("history")}>
            Full timeline →
          </button>
        </section>
      </div>
    </div>
  );
}

function Bucket({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="brbucket">
      <span className="brbucket__n" style={{ color }}>{n}</span>
      <span className="brbucket__label">{label}</span>
    </div>
  );
}
