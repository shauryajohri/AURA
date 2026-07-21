import { useEffect, useMemo, useState } from "react";
import { domainApi, type RepoStatus } from "../../../domainApi";
import {
  STATUS_META,
  useDomainStore,
  type Project,
  type ProjectStatus,
} from "../../../stores/domainStore";

// ============================================================================
// Dashboard — every project, filtered by status.
// Tabs: All · In Progress · Completed · Paused · Ideas · On GitHub.
// Cards with a repo URL pull live vitals (last commit, issues, stars).
// ============================================================================

type Tab = ProjectStatus | "all" | "github";

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "progress", label: "In Progress" },
  { id: "completed", label: "Completed" },
  { id: "paused", label: "Paused" },
  { id: "idea", label: "Ideas" },
  { id: "github", label: "On GitHub" },
];

const QUICK: { icon: string; label: string; section?: string }[] = [
  { icon: "✚", label: "New Project" },
  { icon: "⌥", label: "Open Code", section: "code" },
  { icon: "☑", label: "Domain Tasks", section: "tasks" },
  { icon: "≡", label: "Documentation", section: "documents" },
  { icon: "❯", label: "Terminal", section: "terminal" },
];

const ago = (iso?: string) => {
  if (!iso) return "";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  if (d < 2592000) return `${Math.floor(d / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
};

function ProjectCard({ project, active, onOpen }: {
  project: Project; active: boolean; onOpen: () => void;
}) {
  const setStatus = useDomainStore((s) => s.setStatus);
  const openProjectAt = useDomainStore((s) => s.openProjectAt);
  const openInCode = useDomainStore((s) => s.openInCode);
  const [repo, setRepo] = useState<RepoStatus | null>(null);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    if (!project.repoUrl) { setRepo(null); return; }
    let alive = true;
    domainApi.repo(project.repoUrl).then((r) => alive && setRepo(r)).catch(() => {});
    return () => { alive = false; };
  }, [project.repoUrl]);

  const doneTasks = project.tasks.filter((t) => t.done).length;
  const openTasks = project.tasks.length - doneTasks;
  const pct = project.tasks.length
    ? Math.round((doneTasks / project.tasks.length) * 100)
    : (() => {
        const total = project.board.reduce((n, c) => n + c.cards.length, 0);
        const done = project.board.find((c) => c.id === "done")?.cards.length ?? 0;
        return total ? Math.round((done / total) * 100) : 0;
      })();

  const meta = STATUS_META[project.status];

  return (
    <div
      className={"dcard" + (active ? " dcard--on" : "")}
      style={{ ["--accent" as string]: project.accent }}
    >
      <div className="dcard__glow" />

      <div className="dcard__top">
        <button className="dcard__name" onClick={onOpen}>{project.name}</button>
        <div className="dcard__statuswrap">
          <button
            className="dcard__status"
            style={{ color: meta.color, borderColor: meta.color + "55", background: meta.color + "14" }}
            onClick={() => setMenu((v) => !v)}
            title="Change status"
          >
            <span>{meta.icon}</span> {meta.label}
          </button>
          {menu && (
            <div className="dcard__menu" onMouseLeave={() => setMenu(false)}>
              {(Object.keys(STATUS_META) as ProjectStatus[]).map((s) => (
                <button
                  key={s}
                  className={s === project.status ? "on" : ""}
                  onClick={() => { setStatus(project.id, s); setMenu(false); }}
                >
                  <span style={{ color: STATUS_META[s].color }}>{STATUS_META[s].icon}</span>
                  {STATUS_META[s].label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="dcard__blurb">{project.blurb}</div>

      {project.tags.length > 0 && (
        <div className="dcard__tags">
          {project.tags.map((t) => <span key={t}>{t}</span>)}
        </div>
      )}

      {/* live GitHub vitals */}
      {project.repoUrl && (
        <div className="dcard__repo">
          {repo?.ok ? (
            <>
              <div className="dcard__reporow">
                <a href={repo.url} target="_blank" rel="noreferrer" className="dcard__repolink">
                  ⎇ {repo.full_name}
                </a>
                {repo.private && <span className="dcard__badge">private</span>}
                {repo.archived && <span className="dcard__badge">archived</span>}
              </div>
              <div className="dcard__repostats">
                <span title="stars">★ {repo.stars}</span>
                <span title="forks">⑂ {repo.forks}</span>
                <span title="open issues">◉ {repo.open_issues}</span>
                {repo.language && <span>{repo.language}</span>}
                <span className="dcard__pushed">pushed {ago(repo.pushed_at)}</span>
              </div>
              {repo.last_commit && (
                <div className="dcard__commit" title={repo.last_commit.message}>
                  <span className="dcard__commitdot" />
                  {repo.last_commit.message}
                </div>
              )}
            </>
          ) : (
            <div className="dcard__repoerr">
              ⎇ {repo?.error ?? "checking repo…"}
            </div>
          )}
        </div>
      )}

      <div className="dcard__meta">
        <span>{openTasks} open</span>
        <span>{project.docs.length} docs</span>
        <span>{project.notes.length} notes</span>
        <span>{project.sources.length} in code</span>
      </div>

      {/* the working set, straight from the card */}
      {project.sources.length > 0 && (
        <div className="dcard__files">
          {project.sources.slice(0, 4).map((s) => (
            <button
              key={s.path}
              className="dcard__filechip"
              title={s.path}
              onClick={() => {
                openProjectAt(project.id, "code");
                if (!s.dir) openInCode(s.path);
              }}
            >
              {s.dir ? "🗀" : "⌥"} {s.name}
            </button>
          ))}
          {project.sources.length > 4 && (
            <button className="dcard__filechip" onClick={() => openProjectAt(project.id, "code")}>
              +{project.sources.length - 4}
            </button>
          )}
        </div>
      )}

      <div className="dcard__bar"><div style={{ width: `${pct}%` }} /></div>

      <div className="dcard__actions">
        <span className="dcard__pct">{pct}% complete</span>
        <span className="dcode__spacer" />
        <button onClick={() => openProjectAt(project.id, "tasks")}>Tasks</button>
        <button onClick={() => openProjectAt(project.id, "code")}>Code</button>
        <button onClick={onOpen}>Board</button>
      </div>
    </div>
  );
}

export default function DomainDashboard() {
  const projects = useDomainStore((s) => s.projects);
  const activeId = useDomainStore((s) => s.activeId);
  const openProject = useDomainStore((s) => s.openProject);
  const createProject = useDomainStore((s) => s.createProject);
  const setSection = useDomainStore((s) => s.setSection);

  const [tab, setTab] = useState<Tab>("all");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const counts = useMemo(() => {
    const c: Record<string, number> = {
      all: projects.length,
      github: projects.filter((p) => !!p.repoUrl).length,
    };
    (Object.keys(STATUS_META) as ProjectStatus[]).forEach((s) => {
      c[s] = projects.filter((p) => p.status === s).length;
    });
    return c;
  }, [projects]);

  const shown = useMemo(() => {
    if (tab === "all") return projects;
    if (tab === "github") return projects.filter((p) => !!p.repoUrl);
    return projects.filter((p) => p.status === tab);
  }, [projects, tab]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createProject(name.trim());
    setName("");
    setCreating(false);
  };

  return (
    <div className="ddash">
      <div className="ddash__hero">
        <h2>Welcome to your Domain</h2>
        <p>Where ideas evolve into real projects.</p>
      </div>

      <div className="ddash__quick">
        {QUICK.map((q) => (
          <button
            key={q.label}
            className="ddash__qbtn"
            onClick={() =>
              q.label === "New Project" ? setCreating(true) : q.section && setSection(q.section as never)
            }
          >
            <span className="ddash__qicon">{q.icon}</span>
            <span>{q.label}</span>
          </button>
        ))}
      </div>

      {creating && (
        <form className="ddash__create" onSubmit={submit}>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name the project…"
            onKeyDown={(e) => e.key === "Escape" && setCreating(false)}
          />
          <button type="submit">Create</button>
        </form>
      )}

      {/* status tabs */}
      <div className="ddash__tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={"ddash__tab" + (tab === t.id ? " ddash__tab--on" : "")}
            onClick={() => setTab(t.id)}
            style={
              t.id !== "all" && t.id !== "github"
                ? { ["--tabcolor" as string]: STATUS_META[t.id as ProjectStatus].color }
                : undefined
            }
          >
            {t.label}
            <span className="ddash__tabcount">{counts[t.id] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="ddash__grid">
        {shown.map((p) => (
          <ProjectCard
            key={p.id}
            project={p}
            active={p.id === activeId}
            onOpen={() => openProject(p.id)}
          />
        ))}
        {shown.length === 0 && (
          <div className="ddash__none">
            Nothing here yet.{" "}
            {tab === "github"
              ? "Add a repo URL in Settings → Projects to see live commits."
              : "Projects you mark with this status will show up here."}
          </div>
        )}
      </div>
    </div>
  );
}
