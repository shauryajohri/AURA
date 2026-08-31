import { useCallback, useEffect, useState } from "react";
import { domainApi, type GitBranches, type GitCommit, type GitPreview } from "../../../domainApi";
import { useWorkspaceRoot } from "../useWorkspaceRoot";
import SourcePicker from "./SourcePicker";

// ============================================================================
// Git — the repository panel.
//
// Everything destructive is explicit: staging is a click, committing needs a
// message, pushing to a protected branch needs a second confirmation, and pull
// is fast-forward only. The panel never runs anything on its own.
// ============================================================================

const STATE_ICON: Record<string, string> = {
  modified: "±", added: "+", deleted: "−", renamed: "→", untracked: "?",
};

export default function GitView() {
  const { root, setRoot } = useWorkspaceRoot();
  const [pre, setPre] = useState<GitPreview | null>(null);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [branches, setBranches] = useState<GitBranches | null>(null);
  const [diff, setDiff] = useState<{ path: string; body: string } | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [picking, setPicking] = useState(false);
  const [newBranch, setNewBranch] = useState("");

  const refresh = useCallback(async () => {
    if (!root) return;
    setErr("");
    const [p, l, b] = await Promise.all([
      domainApi.gitPreview(root).catch(() => null),
      domainApi.gitLog(root, 40).catch(() => null),
      domainApi.gitBranches(root).catch(() => null),
    ]);
    setPre(p);
    setCommits(l?.commits ?? []);
    setBranches(b);
    if (p && !p.ok) setErr(p.error ?? "");
  }, [root]);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (label: string, fn: () => Promise<{ ok: boolean; error?: string; output?: string; hint?: string }>) => {
    setBusy(label); setErr(""); setNote("");
    try {
      const r = await fn();
      if (!r.ok) setErr(r.error || r.hint || (label + " failed"));
      else setNote(r.output?.trim() || label + " ✓");
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy("");
    }
  };

  const openDiff = async (path: string, staged: boolean) => {
    const r = await domainApi.gitDiff(root, path, staged).catch(() => null);
    setDiff({ path, body: r?.diff || "(no changes to show)" });
  };

  if (!root) {
    return (
      <div className="dgit">
        <p className="pane-note">Pick the project folder to work with.</p>
        <button className="dgit__btn dgit__btn--primary" onClick={() => setPicking(true)}>Choose folder…</button>
        {picking && (
          <SourcePicker
            onAdd={(entries) => { if (entries[0]) setRoot(entries[0].path); setPicking(false); }}
            onClose={() => setPicking(false)}
          />
        )}
      </div>
    );
  }

  const files = pre?.files ?? [];
  const staged = files.filter((f) => f.staged);
  const unstaged = files.filter((f) => !f.staged);
  const isRepo = pre?.is_repo !== false;

  return (
    <div className="dgit">
      <header className="dgit__head">
        <div className="dgit__where">
          <span className="dgit__branch" title={pre?.upstream || ""}>
            {"⑂ "}{pre?.branch || "—"}
            {pre?.protected && <em className="dgit__prot">protected</em>}
          </span>
          <span className="dgit__root" title={root}>{root}</span>
        </div>
        <div className="dgit__counts">
          {(pre?.ahead ?? 0) > 0 && <span title="commits to push">↑{pre?.ahead}</span>}
          {(pre?.behind ?? 0) > 0 && <span title="commits to pull">↓{pre?.behind}</span>}
          <button className="dgit__btn" onClick={() => setPicking(true)}>Change folder</button>
          <button className="dgit__btn" onClick={refresh} disabled={!!busy}>Refresh</button>
        </div>
      </header>

      {err && <div className="dgit__err">{err}</div>}
      {note && <div className="dgit__note">{note}</div>}

      {!isRepo ? (
        <p className="pane-note">This folder isn't a git repository.</p>
      ) : (
        <div className="dgit__grid">
          {/* ---- changes + commit ---- */}
          <section className="dgit__col">
            <h4 className="dgit__title">Changes · {files.length}</h4>

            {files.length === 0 && <p className="pane-note">Working tree clean.</p>}

            {staged.length > 0 && (
              <>
                <div className="dgit__sub">
                  <span>Staged · {staged.length}</span>
                  <button className="dgit__mini" disabled={!!busy}
                    onClick={() => run("unstage", () => domainApi.gitStage(root, undefined, true))}>
                    unstage all
                  </button>
                </div>
                {staged.map((f) => (
                  <div key={"s" + f.path} className="dgit__file">
                    <span className={"dgit__st dgit__st--" + f.state}>{STATE_ICON[f.state] ?? "±"}</span>
                    <button className="dgit__path" onClick={() => openDiff(f.path, true)} title={f.path}>{f.path}</button>
                    <button className="dgit__mini" disabled={!!busy}
                      onClick={() => run("unstage", () => domainApi.gitStage(root, [f.path], true))}>−</button>
                  </div>
                ))}
              </>
            )}

            {unstaged.length > 0 && (
              <>
                <div className="dgit__sub">
                  <span>Unstaged · {unstaged.length}</span>
                  <button className="dgit__mini" disabled={!!busy}
                    onClick={() => run("stage", () => domainApi.gitStage(root))}>stage all</button>
                </div>
                {unstaged.map((f) => (
                  <div key={"u" + f.path} className="dgit__file">
                    <span className={"dgit__st dgit__st--" + f.state}>{STATE_ICON[f.state] ?? "±"}</span>
                    <button className="dgit__path" onClick={() => openDiff(f.path, false)} title={f.path}>{f.path}</button>
                    <button className="dgit__mini" disabled={!!busy}
                      onClick={() => run("stage", () => domainApi.gitStage(root, [f.path]))}>+</button>
                  </div>
                ))}
              </>
            )}

            <textarea
              className="dgit__msg"
              placeholder="Commit message…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={2}
            />
            <div className="dgit__actions">
              <button
                className="dgit__btn dgit__btn--primary"
                disabled={!!busy || !message.trim() || files.length === 0}
                onClick={() =>
                  run("commit", () => domainApi.gitCommit(root, message).then((r) => { if (r.ok) setMessage(""); return r; }))
                }
              >
                {busy === "commit" ? "Committing…" : "Commit"}
              </button>
              <button className="dgit__btn" disabled={!!busy}
                onClick={() => run("pull", () => domainApi.gitPull(root))}>
                {busy === "pull" ? "Pulling…" : "Pull"}
              </button>
              <button
                className="dgit__btn"
                disabled={!!busy || !pre?.can_push}
                onClick={() => {
                  if (pre?.protected && !window.confirm(`Push directly to ${pre.branch}? It's a protected branch.`)) return;
                  run("push", () => domainApi.gitPush(root, { allow_protected: true }));
                }}
              >
                {busy === "push" ? "Pushing…" : "Push"}
              </button>
            </div>
          </section>

          {/* ---- branches + history ---- */}
          <section className="dgit__col">
            <h4 className="dgit__title">Branches</h4>
            <div className="dgit__branches">
              {(branches?.branches ?? []).map((b) => (
                <button
                  key={b}
                  className={"dgit__branchbtn" + (b === branches?.current ? " dgit__branchbtn--on" : "")}
                  disabled={!!busy || b === branches?.current}
                  onClick={() => run("checkout", () => domainApi.gitCheckout(root, b))}
                >
                  {b}
                </button>
              ))}
            </div>
            <div className="dgit__newbranch">
              <input
                placeholder="new-branch-name"
                value={newBranch}
                onChange={(e) => setNewBranch(e.target.value)}
              />
              <button className="dgit__mini" disabled={!!busy || !newBranch.trim()}
                onClick={() => run("checkout", () =>
                  domainApi.gitCheckout(root, newBranch.trim(), true).then((r) => { if (r.ok) setNewBranch(""); return r; }))}>
                create
              </button>
            </div>

            <h4 className="dgit__title">History</h4>
            <div className="dgit__log">
              {commits.length === 0 && <p className="pane-note">No commits yet.</p>}
              {commits.map((c) => (
                <div key={c.sha} className="dgit__commit">
                  <code>{c.sha}</code>
                  <span className="dgit__subject" title={c.subject}>{c.subject}</span>
                  <span className="dgit__meta">{c.author} · {c.when}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {diff && (
        <div className="dgit__diffwrap" onClick={(e) => { if (e.target === e.currentTarget) setDiff(null); }}>
          <div className="dgit__diff">
            <header>
              <span>{diff.path}</span>
              <button onClick={() => setDiff(null)}>✕</button>
            </header>
            <pre>
              {diff.body.split("\n").map((line, i) => (
                <div
                  key={i}
                  className={
                    line.startsWith("+") && !line.startsWith("+++") ? "dl dl--add"
                    : line.startsWith("-") && !line.startsWith("---") ? "dl dl--del"
                    : line.startsWith("@@") ? "dl dl--hunk" : "dl"
                  }
                >
                  {line || " "}
                </div>
              ))}
            </pre>
          </div>
        </div>
      )}

      {picking && (
        <SourcePicker
          startPath={root}
          onAdd={(entries) => { if (entries[0]) setRoot(entries[0].path); setPicking(false); }}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  );
}
