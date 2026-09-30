import { useCallback, useEffect, useState } from "react";
import { api, type Integration, type InstalledModel } from "../api";
import type { Job } from "../types";
import InstallCard from "../components/InstallCard";
import { useRosterStore } from "../stores/rosterStore";

/**
 * Models → Installed: everything added by pasting a key or a link. Each
 * planet's jobs can be changed here after the fact, which is how you correct
 * AURA's guess about what a model is best at.
 */

const JOBS: Job[] = ["Coding", "Research", "Chat", "Vision", "Background"];

export default function InstalledView() {
  const [list, setList] = useState<Integration[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [note, setNote] = useState<Record<number, string>>({});
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const installedCount = useRosterStore((s) => s.installed.length);
  const reloadRoster = useRosterStore((s) => s.load);

  const load = useCallback(() => {
    api.getIntegrations()
      .then((r) => { setList(r.integrations); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  // Reload when a planet is installed or removed anywhere (socket → roster).
  useEffect(() => { load(); }, [load, installedCount]);

  const setJobs = async (m: InstalledModel, job: Job) => {
    const jobs = m.jobs.includes(job) ? m.jobs.filter((j) => j !== job) : JOBS.filter((j) => j === job || m.jobs.includes(j));
    if (!jobs.length) return;
    const res = await api.updatePlanet(m.row_id, { jobs });
    if (!res.ok) return;
    load();
    void reloadRoster();
  };

  const setPosition = async (m: InstalledModel, position: "first" | "backup") => {
    await api.updatePlanet(m.row_id, { position });
    load();
  };

  const retest = async (it: Integration) => {
    setNote((n) => ({ ...n, [it.id]: "Testing…" }));
    const res = await api.retestIntegration(it.id);
    const bad = res.results.filter((r) => !r.ok);
    setNote((n) => ({
      ...n,
      [it.id]: bad.length
        ? `${bad.map((b) => `${b.name}: ${b.why}`).join("; ")}. Failed planets are skipped until they pass again.`
        : `All ${res.results.length} answered.`,
    }));
    load();
  };

  const uninstall = async (it: Integration) => {
    await api.uninstall(it.id);
    setConfirmId(null);
    load();
    void reloadRoster();
  };

  if (offline) return <p className="pane-note">AURA's brain is offline — start server.py to manage installed planets.</p>;
  if (!list) return <p className="pane-note">Loading…</p>;

  const installed = list.filter((i) => i.status === "installed");
  const pending = list.filter((i) => i.status === "pending" && i.proposal && i.proposal.stage !== "not_installable");

  return (
    <div className="installed">
      <p className="installed__how">
        To add one, paste an API key or a link in the chat — “install this” plus a GitHub, docs or model
        page works too. AURA checks it, suggests what it's good for, and asks before anything is installed.
      </p>

      {installed.length === 0 && pending.length === 0 && (
        <p className="pane-note">Nothing installed yet. The built-in planets are on the Planet management tab.</p>
      )}

      {installed.map((it) => (
        <section key={it.id} className="installed__group">
          <header className="installed__head">
            <div>
              <h3>{it.label}</h3>
              <p>
                {it.kind === "search" ? "Web search" : `${it.models.length} planet${it.models.length === 1 ? "" : "s"}`}
                {it.key_from ? `, key from ${it.key_from} in .env` : it.key_masked ? `, key ${it.key_masked}` : ""}
                {it.cost ? `, ${it.cost}` : ""}
              </p>
            </div>
            <div className="installed__acts">
              {it.kind === "llm" && <button className="saved__btn" onClick={() => retest(it)}>Test again</button>}
              {confirmId === it.id ? (
                <button className="saved__btn saved__btn--del" onClick={() => uninstall(it)}>Remove {it.label}</button>
              ) : (
                <button className="saved__btn" onClick={() => setConfirmId(it.id)}>Uninstall</button>
              )}
            </div>
          </header>
          {note[it.id] && <p className="installed__note">{note[it.id]}</p>}

          {it.kind === "search" && (
            <p className="installed__search">Used when you ask research or look-up questions.</p>
          )}

          <ul className="installed__planets">
            {it.models.map((m) => (
              <li key={m.row_id} className={m.status === "failed" ? "is-failed" : ""}>
                <span className="installed__orb" style={{ background: m.color, boxShadow: `0 0 12px ${m.color}` }} aria-hidden />
                <div className="installed__who">
                  <strong>{m.name}</strong>
                  <span>
                    {m.wire}
                    {m.status === "failed" ? ` — failed its last test: ${m.error}` : m.latency_ms ? `, answered in ${(m.latency_ms / 1000).toFixed(1)}s` : ""}
                  </span>
                </div>
                <div className="icard__jobs" role="group" aria-label={`Jobs for ${m.name}`}>
                  {JOBS.map((j) => (
                    <button key={j} type="button" aria-pressed={m.jobs.includes(j)}
                            className={"icard__job" + (m.jobs.includes(j) ? " is-on" : "") + (m.best_for.includes(j) ? " is-best" : "")}
                            title={m.best_for.includes(j) ? `${j} — AURA thinks it's good at this` : j}
                            onClick={() => setJobs(m, j)}>
                      {j}
                    </button>
                  ))}
                </div>
                <select className="installed__pos" value={m.position} aria-label={`When to use ${m.name}`}
                        onChange={(e) => setPosition(m, e.target.value as "first" | "backup")}>
                  <option value="backup">Backup</option>
                  <option value="first">First pick</option>
                </select>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {pending.length > 0 && (
        <section className="installed__group">
          <header className="installed__head"><div><h3>Waiting for you</h3>
            <p>Installs you started but didn't finish. They expire after a week.</p></div></header>
          {pending.map((it) => <InstallCard key={it.uid} proposal={it.proposal!} />)}
        </section>
      )}
    </div>
  );
}
