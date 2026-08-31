import { useCallback, useEffect, useMemo, useState } from "react";
import { domainApi, type GitHubRepo, type PullRequest, type RepoStatus } from "../../../domainApi";

// ============================================================================
// GitHub — your repositories, inside AURA.
//
// Pick a repo to see its vitals, its open pull requests, and to clone it
// locally (which also builds its project graph, so the Brain knows about it).
// Everything is read-only except Import: merging and reviewing stay on GitHub
// where the checks live.
// ============================================================================

const when = (iso: string): string => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 60) return mins + "m ago";
  const h = Math.round(mins / 60);
  if (h < 24) return h + "h ago";
  const days = Math.round(h / 24);
  if (days < 30) return days + "d ago";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};

export default function GitHubView() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [account, setAccount] = useState("");
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<GitHubRepo | null>(null);
  const [stats, setStats] = useState<RepoStatus | null>(null);
  const [pulls, setPulls] = useState<PullRequest[] | null>(null);
  const [prState, setPrState] = useState<"open" | "all">("open");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");

  // ---- account + repo list ------------------------------------------------
  const load = useCallback(async () => {
    setBusy("repos"); setErr("");
    try {
      const s = await domainApi.ghStatus();
      setConnected(!!s.connected);
      setAccount(s.account || "");
      if (!s.connected) { setBusy(""); return; }
      const r = await domainApi.ghRepos(100);
      if (!r.ok) setErr(r.error || "couldn't list repositories");
      setRepos(r.repos ?? []);
    } catch {
      setErr("Brain offline — GitHub needs server.py running.");
      setConnected(false);
    } finally {
      setBusy("");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ---- selected repo detail ----------------------------------------------
  useEffect(() => {
    if (!selected) { setStats(null); setPulls(null); return; }
    let cancelled = false;
    setStats(null); setPulls(null);
    domainApi.repo(selected.html_url).then((s) => { if (!cancelled) setStats(s); }).catch(() => {});
    domainApi.ghPulls(selected.full_name, prState)
      .then((p) => !cancelled && setPulls(p.pulls ?? []))
      .catch(() => !cancelled && setPulls([]));
    return () => { cancelled = true; };
  }, [selected, prState]);

  const doImport = async () => {
    if (!selected) return;
    setBusy("import"); setErr(""); setNote("");
    try {
      const r = await domainApi.ghImport(selected.full_name, selected.clone_url, selected.default_branch);
      if (!r.ok) setErr(r.error || "import failed");
      else setNote(`${r.updated ? "Updated" : "Cloned"} to ${r.cloned_to} — project graph built.`);
    } catch {
      setErr("Import failed — check the terminal for details.");
    } finally {
      setBusy("");
    }
  };

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return repos;
    return repos.filter((r) =>
      r.full_name.toLowerCase().includes(f) || (r.description || "").toLowerCase().includes(f));
  }, [repos, filter]);

  if (connected === false) {
    return (
      <div className="dgh">
        <div className="dgh__empty">
          <span className="dgh__emptyicon">◧</span>
          <h3>GitHub isn't connected</h3>
          <p className="pane-note">
            {err || "Authorise GitHub in Settings → Connectors to browse your repositories, see pull requests, and clone projects straight into AURA."}
          </p>
          <button className="dgit__btn dgit__btn--primary" onClick={load}>Check again</button>
        </div>
      </div>
    );
  }

  return (
    <div className="dgh">
      <header className="dgit__head">
        <div className="dgit__where">
          <span className="dgit__branch">{"◧ GitHub"}</span>
          <span className="dgit__root">
            {connected === null ? "checking…" : account ? "@" + account : ""}
            {repos.length > 0 && ` · ${repos.length} repositories`}
          </span>
        </div>
        <div className="dgit__counts">
          <input
            className="dgh__filter"
            placeholder="Filter repositories…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <button className="dgit__btn" onClick={load} disabled={!!busy}>
            {busy === "repos" ? "Loading…" : "Refresh"}
          </button>
        </div>
      </header>

      {err && <div className="dgit__err">{err}</div>}
      {note && <div className="dgit__note">{note}</div>}

      <div className="dgh__grid">
        {/* ---- repository list ---- */}
        <section className="dgit__col dgh__list">
          {busy === "repos" && repos.length === 0 && <p className="pane-note">Fetching repositories…</p>}
          {shown.map((r) => (
            <button
              key={r.full_name}
              className={"dgh__repo" + (selected?.full_name === r.full_name ? " dgh__repo--on" : "")}
              onClick={() => setSelected(r)}
            >
              <span className="dgh__reponame">
                {r.name}
                {r.private && <em className="dgh__private">private</em>}
              </span>
              {r.description && <span className="dgh__repodesc">{r.description}</span>}
              <span className="dgh__repometa">
                {r.language && <span className="dgh__lang">{r.language}</span>}
                <span>{when(r.updated_at)}</span>
              </span>
            </button>
          ))}
          {!busy && shown.length === 0 && <p className="pane-note">No repositories match that filter.</p>}
        </section>

        {/* ---- detail ---- */}
        <section className="dgit__col">
          {!selected ? (
            <p className="pane-note">Pick a repository to see its stats and pull requests.</p>
          ) : (
            <>
              <div className="dgh__dethead">
                <div>
                  <h4 className="dgh__dettitle">{selected.full_name}</h4>
                  <p className="dgh__detdesc">{selected.description || "No description."}</p>
                </div>
                <div className="dgh__detactions">
                  <a className="dgit__btn" href={selected.html_url} target="_blank" rel="noreferrer">Open ↗</a>
                  <button className="dgit__btn dgit__btn--primary" disabled={!!busy} onClick={doImport}>
                    {busy === "import" ? "Cloning…" : "Import to AURA"}
                  </button>
                </div>
              </div>

              <div className="dgh__stats">
                <div><dt>Stars</dt><dd>{stats?.stars ?? "—"}</dd></div>
                <div><dt>Forks</dt><dd>{stats?.forks ?? "—"}</dd></div>
                <div><dt>Issues</dt><dd>{stats?.open_issues ?? "—"}</dd></div>
                <div><dt>Branch</dt><dd>{selected.default_branch}</dd></div>
                <div><dt>Language</dt><dd>{selected.language || "—"}</dd></div>
                <div><dt>Pushed</dt><dd>{when(stats?.pushed_at || selected.updated_at) || "—"}</dd></div>
              </div>

              {stats?.last_commit && (
                <div className="dgh__lastcommit">
                  <span className="dgit__title">Latest commit</span>
                  <p>{stats.last_commit.message}</p>
                  <span className="dgit__meta">
                    {stats.last_commit.author} · {when(stats.last_commit.date || "")}
                  </span>
                </div>
              )}

              <div className="dgh__prhead">
                <span className="dgit__title">Pull requests</span>
                <span className="dgh__prtabs">
                  <button className={"dgit__mini" + (prState === "open" ? " dgh__on" : "")}
                    onClick={() => setPrState("open")}>open</button>
                  <button className={"dgit__mini" + (prState === "all" ? " dgh__on" : "")}
                    onClick={() => setPrState("all")}>all</button>
                </span>
              </div>

              {pulls === null && <p className="pane-note">Loading pull requests…</p>}
              {pulls?.length === 0 && (
                <p className="pane-note">
                  {prState === "open" ? "No open pull requests." : "No pull requests yet."}
                </p>
              )}
              {(pulls ?? []).map((p) => (
                <a key={p.number} className="dgh__pr" href={p.url} target="_blank" rel="noreferrer">
                  <span className={"dgh__prstate dgh__prstate--" + (p.draft ? "draft" : p.state)}>
                    {p.draft ? "draft" : p.state}
                  </span>
                  <span className="dgh__prtitle">
                    <em>#{p.number}</em> {p.title}
                  </span>
                  <span className="dgit__meta">
                    {p.author} · {p.head} → {p.base} · {when(p.updated_at)}
                  </span>
                </a>
              ))}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
