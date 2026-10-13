import { useCallback, useEffect, useState } from "react";
import { api, Habits } from "../api";

// Habits — what AURA has noticed about how you use your computer: which apps
// and tools, how long, and at what time of day. Everything here is yours to
// pause, hide or forget; only app names (and well-known sites) are ever kept.

const dur = (secs: number): string => {
  const m = Math.round(secs / 60);
  if (m < 60) return `${Math.max(m, 1)}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
};

const hourLabel = (h: number) => `${(h % 12) || 12}${h < 12 ? "am" : "pm"}`;

export default function HabitsPane() {
  const [data, setData] = useState<Habits | null>(null);
  const [offline, setOffline] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);

  const load = useCallback(() => {
    api.getHabits(7).then((d) => { setData(d); setOffline(false); }).catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (offline) return <p className="pane-note">Brain offline — habits need server.py.</p>;
  if (!data) return <p className="pane-note">Loading habits…</p>;

  const setEnabled = (on: boolean) =>
    api.saveSettings({ "habits.enabled": on }).then(load);
  const ignore = (app: string) =>
    api.saveSettings({ "habits.ignore": [...data.ignore, app] })
      .then(() => api.forgetHabits(app)).then(load);
  const unignore = (app: string) =>
    api.saveSettings({ "habits.ignore": data.ignore.filter((a) => a !== app) }).then(load);
  const forgetAll = () => api.forgetHabits().then(() => { setConfirmAll(false); load(); });

  const peak = Math.max(1, ...data.hours);
  const empty = data.top.length === 0 && data.today.length === 0;

  return (
    <div className="habits">
      <div className="habits__bar">
        <span className="habits__status">
          {data.enabled
            ? data.current ? <>Watching — <b>{data.current.app}</b> for {dur(data.current.seconds)}</> : "Watching which apps you use"
            : "Paused — nothing is being tracked"}
        </span>
        <button className={"san-toggle" + (data.enabled ? " san-toggle--on" : "")}
                onClick={() => setEnabled(!data.enabled)} title={data.enabled ? "Pause" : "Resume"}>
          <span className="san-toggle__knob" />
        </button>
      </div>

      {empty && (
        <p className="pane-note">
          {data.enabled
            ? "Nothing yet — AURA learns your routine as you use your computer. Check back in a day."
            : "Turn tracking on and AURA will start learning which apps and tools you use."}
        </p>
      )}

      {data.today.length > 0 && (
        <section className="habits__section">
          <h3 className="memtl__title">Today</h3>
          <div className="habits__chips">
            {data.today.slice(0, 8).map((t) => (
              <span key={t.app} className="habits__chip">{t.app} <b>{dur(t.seconds)}</b></span>
            ))}
          </div>
        </section>
      )}

      {data.top.length > 0 && (
        <section className="habits__section">
          <h3 className="memtl__title">Your usual (last {data.days} days)</h3>
          <div className="pane-list">
            {data.top.map((t) => (
              <article key={t.app} className="pane-card habits__row">
                <span className="habits__app">{t.app}</span>
                <span className="pane-card__when">
                  ~{dur(t.avg_per_day)}/day · {t.days_used} day{t.days_used === 1 ? "" : "s"}
                  {t.part_of_day && ` · mostly ${t.part_of_day}`}
                </span>
                <button className="pane-card__del" title="Stop tracking this app and forget it"
                        onClick={() => ignore(t.app)}>hide</button>
              </article>
            ))}
          </div>
        </section>
      )}

      {!empty && (
        <section className="habits__section">
          <h3 className="memtl__title">When you're on</h3>
          <div className="habits__hours" role="img" aria-label="Computer use by hour of day">
            {data.hours.map((s, h) => (
              <div key={h} className="habits__hour" title={`${hourLabel(h)} — ${dur(s)}`}>
                <i style={{ height: `${Math.round((s / peak) * 100)}%` }} />
              </div>
            ))}
          </div>
          <div className="habits__axis"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span></div>
        </section>
      )}

      {data.ignore.length > 0 && (
        <section className="habits__section">
          <h3 className="memtl__title">Never tracked</h3>
          <div className="habits__chips">
            {data.ignore.map((a) => (
              <button key={a} className="habits__chip habits__chip--off" onClick={() => unignore(a)}
                      title="Track this app again">{a} ✕</button>
            ))}
          </div>
        </section>
      )}

      <footer className="habits__foot">
        <span className="pane-note">Only app names (and well-known sites like YouTube) are kept — never window titles. It all stays on this computer.</span>
        {!empty && (confirmAll ? (
          <span className="habits__confirm">
            Forget all habits?
            <button onClick={forgetAll}>Yes, forget</button>
            <button onClick={() => setConfirmAll(false)}>Cancel</button>
          </span>
        ) : (
          <button className="habits__forget" onClick={() => setConfirmAll(true)}>Forget everything</button>
        ))}
      </footer>
    </div>
  );
}
