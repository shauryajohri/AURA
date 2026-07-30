import { useEffect, useMemo, useState } from "react";
import { brainApi, whenLabel, type GhRepo } from "../../../brainApi";
import { useBrainStore } from "../../../stores/brainStore";
import { useDomainStore } from "../../../stores/domainStore";
import SourcePicker from "../views/SourcePicker";

// ============================================================================
// Module 1 — Project Creation.
//
// The first screen of an AI Software Development OS is not an editor: it is the
// question "what are we building?". Three ways in — an empty project you talk
// into existence, a local folder AURA reads (code + git history), or a GitHub
// repo it clones for you. All three end in the same place: a knowledge graph.
// ============================================================================

type Mode = "none" | "empty" | "folder" | "github";

export default function ProjectsView() {
  const projects = useBrainStore((s) => s.projects);
  const activeId = useBrainStore((s) => s.activeId);
  const busy = useBrainStore((s) => s.busy);
  const error = useBrainStore((s) => s.error);
  const reachable = useBrainStore((s) => s.reachable);
  const loadProjects = useBrainStore((s) => s.loadProjects);
  const select = useBrainStore((s) => s.select);
  const createProject = useBrainStore((s) => s.createProject);
  const importFolder = useBrainStore((s) => s.importFolder);
  const importRepo = useBrainStore((s) => s.importRepo);
  const deleteProject = useBrainStore((s) => s.deleteProject);
  const clearError = useBrainStore((s) => s.clearError);
  const setSection = useDomainStore((s) => s.setSection);

  const [mode, setMode] = useState<Mode>("none");
  const [name, setName] = useState("");
  const [picking, setPicking] = useState(false);
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  // GitHub
  const [gh, setGh] = useState<{ connected: boolean; account?: string | null } | null>(null);
  const [repos, setRepos] = useState<GhRepo[]>([]);
  const [repoErr, setRepoErr] = useState("");
  const [repoFilter, setRepoFilter] = useState("");
  const [loadingRepos, setLoadingRepos] = useState(false);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  useEffect(() => {
    if (mode !== "github") return;
    let dead = false;
    setRepoErr("");
    brainApi.ghStatus()
      .then((s) => { if (!dead) setGh({ connected: s.connected, account: s.account }); })
      .catch(() => !dead && setRepoErr("brain offline"));
    return () => { dead = true; };
  }, [mode]);

  const pullRepos = async () => {
    setLoadingRepos(true);
    setRepoErr("");
    try {
      const r = await brainApi.ghRepos(100);
      if (!r.ok) setRepoErr(r.error ?? "could not list repos");
      else setRepos(r.repos ?? []);
    } catch {
      setRepoErr("brain offline");
    }
    setLoadingRepos(false);
  };

  const shownRepos = useMemo(() => {
    const f = repoFilter.trim().toLowerCase();
    return f ? repos.filter((r) => r.full_name.toLowerCase().includes(f)) : repos;
  }, [repos, repoFilter]);

  const enter = async (pid: string) => {
    await select(pid);
    setSection("dashboard");
  };

  const submitEmpty = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    const pid = await createProject(n);
    setName("");
    setMode("none");
    if (pid) setSection("research");   // straight into the conversation
  };

  return (
    <div className="brproj">
      <header className="brproj__head">
        <div>
          <h2 className="brproj__title">PROJECTS</h2>
          <p className="brproj__sub">
            Every project is a knowledge graph — ideas, decisions, features, tasks,
            commits and docs, all linked.
          </p>
        </div>
        <div className="brproj__ways">
          <button className={"brbtn" + (mode === "empty" ? " brbtn--on" : "")}
                  onClick={() => setMode(mode === "empty" ? "none" : "empty")}>
            ✧ New project
          </button>
          <button className={"brbtn" + (mode === "folder" ? " brbtn--on" : "")}
                  onClick={() => { setMode("folder"); setPicking(true); }}>
            ▤ Import folder
          </button>
          <button className={"brbtn" + (mode === "github" ? " brbtn--on" : "")}
                  onClick={() => setMode(mode === "github" ? "none" : "github")}>
            ⎇ Import from GitHub
          </button>
        </div>
      </header>

      {!reachable && (
        <div className="brnote brnote--warn">
          The Project Brain isn't answering. Start AURA's server, then reload.
        </div>
      )}
      {error && (
        <div className="brnote brnote--warn">
          {error}
          <button className="brnote__x" onClick={clearError}>✕</button>
        </div>
      )}
      {busy && <div className="brnote brnote--busy">{busy}</div>}

      {mode === "empty" && (
        <form className="brproj__form" onSubmit={submitEmpty}>
          <input
            className="brinput"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name — e.g. AURA Domain"
          />
          <button className="brbtn brbtn--go" type="submit" disabled={!name.trim()}>
            Create · then talk it into shape
          </button>
        </form>
      )}

      {mode === "github" && (
        <div className="brproj__gh">
          {gh && !gh.connected && (
            <div className="brnote">
              GitHub isn't connected yet. Connect it in <b>Domain → Settings → Connectors</b>,
              then come back — AURA will clone the repo and read its whole history.
            </div>
          )}
          {gh?.connected && (
            <>
              <div className="brproj__ghbar">
                <span className="brproj__ghacct">◉ {gh.account ?? "connected"}</span>
                <input
                  className="brinput brinput--sm"
                  value={repoFilter}
                  onChange={(e) => setRepoFilter(e.target.value)}
                  placeholder="Filter repositories…"
                />
                <button className="brbtn" onClick={pullRepos} disabled={loadingRepos}>
                  {loadingRepos ? "Loading…" : repos.length ? "Refresh" : "List my repos"}
                </button>
              </div>
              {repoErr && <div className="brnote brnote--warn">{repoErr}</div>}
              <div className="brproj__repos">
                {shownRepos.map((r) => (
                  <button
                    key={r.full_name}
                    className="brrepo"
                    onClick={() => importRepo(r.full_name, r.clone_url)}
                    title={"Clone and read " + r.full_name}
                  >
                    <span className="brrepo__name">{r.full_name}</span>
                    <span className="brrepo__meta">
                      {r.private ? "private" : "public"}
                      {r.language ? " · " + r.language : ""}
                      {r.updated_at ? " · " + whenLabel(r.updated_at) : ""}
                    </span>
                    {r.description && <span className="brrepo__blurb">{r.description}</span>}
                  </button>
                ))}
                {!loadingRepos && repos.length > 0 && shownRepos.length === 0 && (
                  <div className="brempty">Nothing matches that filter.</div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <div className="brproj__grid">
        {projects.map((p) => {
          const an = (p.meta?.analysis ?? {}) as any;
          const head = (p.meta?.head ?? {}) as any;
          return (
            <article
              key={p.id}
              className={"brpcard" + (activeId === p.id ? " brpcard--on" : "")}
            >
              <button className="brpcard__open" onClick={() => enter(p.id)}>
                <h3 className="brpcard__name">{p.name}</h3>
                <p className="brpcard__path">{p.root || p.repo_url || "no folder linked"}</p>
                <div className="brpcard__facts">
                  {an.primary_language && <span className="brchip">{an.primary_language}</span>}
                  {(an.frameworks ?? []).slice(0, 3).map((f: string) => (
                    <span className="brchip" key={f}>{f}</span>
                  ))}
                  {typeof an.file_count === "number" && (
                    <span className="brchip">{an.file_count} files</span>
                  )}
                </div>
                {(head.branch || head.sha) && (
                  <p className="brpcard__commit">
                    ⎇ {head.branch}{head.sha ? " · " + head.sha : ""}
                  </p>
                )}
                <span className="brpcard__when">updated {whenLabel(p.updated_at)}</span>
              </button>
              <div className="brpcard__row">
                <button className="brlink" onClick={() => enter(p.id)}>Open →</button>
                {confirmDel === p.id ? (
                  <>
                    <button className="brlink brlink--danger"
                            onClick={() => { void deleteProject(p.id); setConfirmDel(null); }}>
                      Delete for good
                    </button>
                    <button className="brlink" onClick={() => setConfirmDel(null)}>Keep</button>
                  </>
                ) : (
                  <button className="brlink brlink--quiet" onClick={() => setConfirmDel(p.id)}>
                    Forget
                  </button>
                )}
              </div>
            </article>
          );
        })}

        {projects.length === 0 && reachable && !busy && (
          <div className="brempty brempty--big">
            <span className="brempty__icon">◈</span>
            <h3>Nothing here yet</h3>
            <p>
              Start with an empty project and talk to AURA about it, or point her at a
              folder you already have — she'll read the code and the git history and
              build the graph herself.
            </p>
          </div>
        )}
      </div>

      {picking && (
        <SourcePicker
          onClose={() => { setPicking(false); setMode("none"); }}
          onAdd={(entries) => {
            const dir = entries.find((e) => e.dir) ?? entries[0];
            if (dir) void importFolder(dir.dir ? dir.path : dir.path, dir.name);
          }}
        />
      )}
    </div>
  );
}
