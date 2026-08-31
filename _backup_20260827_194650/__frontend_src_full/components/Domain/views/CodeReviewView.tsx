import { useEffect, useMemo, useRef, useState } from "react";
import {
  domainApi,
  type FsEntry,
  type GitPreview,
  type ReviewFinding,
} from "../../../domainApi";
import { api, type ErrorClassification } from "../../../api";
import { useDomainStore } from "../../../stores/domainStore";
import SourcePicker from "./SourcePicker";

// ============================================================================
// CODE REVIEW — AURA's version on the left, yours on the right.
//
// The panel that made the old Qt Workbench worth opening, rebuilt properly:
//
//   · left pane   AURA's proposed file. READ ONLY, always. The model never
//                 touches your working tree; applying is a click you make.
//   · right pane  your file, editable, saved through /api/domain/fs/write.
//   · console     real output from a real shell (/api/domain/shell/run), with
//                 stderr fed to the error engine so a stack trace comes back
//                 explained instead of just red.
//   · permission  Read Only → Sandbox → Merge Review → Write → Push. Each rung
//                 unlocks exactly one more capability, and the buttons for the
//                 rungs above the current one are genuinely disabled, not just
//                 dimmed. Pushing is never one click away from reading.
//
// The ladder is deliberately manual. An AI that can silently escalate its own
// write access is not a tool, it's a liability.
// ============================================================================

const LEVELS = ["read", "sandbox", "merge", "write", "push"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_META: Record<Level, { label: string; blurb: string }> = {
  read:    { label: "Read Only",    blurb: "AURA can read and suggest. Nothing can change." },
  sandbox: { label: "Sandbox",      blurb: "You can run the file and see output." },
  merge:   { label: "Merge Review", blurb: "You can diff her version against yours." },
  write:   { label: "Write",        blurb: "Saving to disk is unlocked." },
  push:    { label: "Push",         blurb: "Commit and push to the remote is unlocked." },
};

const rank = (l: Level) => LEVELS.indexOf(l);

type ConsoleTab = "output" | "problems" | "diff";

interface Line {
  kind: "cmd" | "out" | "err" | "sys";
  text: string;
}

/** Cheap line-level diff: enough to see what moved, no dependency. */
function diffLines(a: string, b: string): { sign: " " | "-" | "+"; text: string }[] {
  const A = a.split("\n");
  const B = b.split("\n");
  const out: { sign: " " | "-" | "+"; text: string }[] = [];
  // longest-common-subsequence table on lines, capped so a huge file can't hang the UI
  const CAP = 1200;
  if (A.length > CAP || B.length > CAP) {
    return [{ sign: " ", text: `(file too large to diff inline — ${A.length} vs ${B.length} lines)` }];
  }
  const m = Array.from({ length: A.length + 1 }, () => new Uint16Array(B.length + 1));
  for (let i = A.length - 1; i >= 0; i--)
    for (let j = B.length - 1; j >= 0; j--)
      m[i][j] = A[i] === B[j] ? m[i + 1][j + 1] + 1 : Math.max(m[i + 1][j], m[i][j + 1]);
  let i = 0;
  let j = 0;
  while (i < A.length && j < B.length) {
    if (A[i] === B[j]) { out.push({ sign: " ", text: A[i] }); i++; j++; }
    else if (m[i + 1][j] >= m[i][j + 1]) { out.push({ sign: "-", text: A[i] }); i++; }
    else { out.push({ sign: "+", text: B[j] }); j++; }
  }
  while (i < A.length) out.push({ sign: "-", text: A[i++] });
  while (j < B.length) out.push({ sign: "+", text: B[j++] });
  return out;
}

const RUN_CMD: Record<string, (p: string) => string> = {
  py: (p) => `python "${p}"`,
  js: (p) => `node "${p}"`,
  mjs: (p) => `node "${p}"`,
  ts: (p) => `npx tsx "${p}"`,
  tsx: (p) => `npx tsx "${p}"`,
  sh: (p) => `bash "${p}"`,
};

export default function CodeReviewView() {
  const setSection = useDomainStore((s) => s.setSection);

  const [level, setLevel] = useState<Level>("read");
  const [picking, setPicking] = useState(false);

  const [path, setPath] = useState("");
  const [lang, setLang] = useState("");
  const [mine, setMine] = useState("");
  const [onDisk, setOnDisk] = useState("");        // last known saved content
  const [theirs, setTheirs] = useState("");        // AURA's suggestion
  const [findings, setFindings] = useState<ReviewFinding[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [instruction, setInstruction] = useState("");

  const [tab, setTab] = useState<ConsoleTab>("output");
  const [lines, setLines] = useState<Line[]>([]);
  const [explained, setExplained] = useState<ErrorClassification | null>(null);

  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [git, setGit] = useState<GitPreview | null>(null);
  const [commitMsg, setCommitMsg] = useState("");
  const shellId = useRef<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const dirty = mine !== onDisk;
  const can = (l: Level) => rank(level) >= rank(l);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines, tab]);

  const say = (kind: Line["kind"], text: string) =>
    setLines((ls) => [...ls, { kind, text }].slice(-400));

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 5000); };

  /** The folder a path sits in — what git commands need as their root. */
  const folder = useMemo(() => {
    if (!path) return "";
    const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
    return i > 0 ? path.slice(0, i) : path;
  }, [path]);

  const openFile = async (entry: FsEntry) => {
    const r = await domainApi.read(entry.path);
    if (!r.ok || r.content === undefined) { flash(r.error ?? "could not read that file"); return; }
    setPath(r.path ?? entry.path);
    setLang(r.lang ?? entry.lang ?? "");
    setMine(r.content);
    setOnDisk(r.content);
    setTheirs("");
    setFindings([]);
    setExplained(null);
    setLines([{ kind: "sys", text: `opened ${entry.name}` }]);
    setTab("output");
  };

  const askReview = async () => {
    if (!path) return;
    setBusy("AURA is reading it…");
    const r = await domainApi.review({ path, content: mine, lang, instruction });
    setBusy("");
    if (!r.ok) { flash(r.error ?? "review failed"); return; }
    setTheirs(r.suggestion ?? "");
    setFindings(r.findings ?? []);
    setTruncated(!!r.truncated);
    if (r.source === "unstructured") flash("Model replied in prose — shown under Problems.");
    setTab(r.findings?.length ? "problems" : "diff");
  };

  const save = async () => {
    if (!can("write") || !path) return;
    setBusy("saving…");
    const r = await domainApi.write(path, mine);
    setBusy("");
    if (!r.ok) { flash(r.error ?? "could not write"); return; }
    setOnDisk(mine);
    say("sys", `saved ${path}`);
    flash("Saved.");
  };

  /** Merge = copy her version into the editor. Still needs a Save after. */
  const applyTheirs = () => {
    if (!can("merge") || !theirs) return;
    setMine(theirs);
    setTab("diff");
    flash(can("write")
      ? "Applied to the editor — Save writes it to disk."
      : "Applied to the editor. Raise permission to Write to save it.");
  };

  const run = async () => {
    if (!can("sandbox") || !path) return;
    const ext = (path.split(".").pop() ?? "").toLowerCase();
    const build = RUN_CMD[ext];
    if (!build) { flash(`I don't know how to run .${ext} files.`); return; }
    const cmd = build(path);
    setTab("output");
    say("cmd", cmd);
    setBusy("running…");
    const r = await domainApi.shellRun(shellId.current, cmd, folder, 60);
    setBusy("");
    shellId.current = r.id ?? shellId.current;
    const text = (r.output ?? "").trimEnd();
    if (text) say(r.code === 0 ? "out" : "err", text);
    say("sys", `exit ${r.code}${r.ms ? ` · ${r.ms}ms` : ""}`);

    // a failure is worth explaining, and worth telling the session engine about
    void api.reportBuild(r.code === 0).catch(() => {});
    if (r.code !== 0 && text) {
      const cls = await api.explainError(text, true).catch(() => null);
      if (cls?.matched) { setExplained(cls); setTab("problems"); }
    } else {
      setExplained(null);
    }
  };

  const loadGit = async () => {
    if (!folder) return;
    const p = await domainApi.gitPreview(folder);
    setGit(p);
    if (!p.ok) flash(p.error ?? "not a git repo");
  };

  const publish = async () => {
    if (!can("push") || !folder) return;
    const message = commitMsg.trim();
    if (!message) { flash("A commit message is required."); return; }
    setBusy("committing and pushing…");
    const r = await domainApi.gitPublish(folder, message, { allow_protected: false });
    setBusy("");
    if (!r.ok) {
      say("err", r.error ?? "push refused");
      flash(r.error ?? "push refused");
      if (r.preview) setGit(r.preview);
      return;
    }
    say("sys", `pushed ${r.sha ?? ""} to ${r.branch ?? ""}`.trim());
    if (r.output) say("out", r.output);
    setCommitMsg("");
    flash("Pushed.");
    void loadGit();
  };

  const diff = useMemo(
    () => (theirs ? diffLines(onDisk || mine, theirs) : []),
    [theirs, onDisk, mine]
  );

  const gutter = useMemo(() => mine.split("\n").length, [mine]);

  return (
    <div className="dcr">
      {/* ---- permission ladder ------------------------------------------- */}
      <div className="dcr__perm">
        <span className="dcr__permlabel">PERMISSION</span>
        <div className="dcr__rungs">
          {LEVELS.map((l, i) => (
            <button
              key={l}
              className={
                "dcr__rung" +
                (level === l ? " dcr__rung--on" : "") +
                (can(l) ? " dcr__rung--reached" : "")
              }
              title={LEVEL_META[l].blurb}
              // one rung at a time, in both directions — no jumping to Push
              disabled={i > rank(level) + 1}
              onClick={() => setLevel(l)}
            >
              {LEVEL_META[l].label}
            </button>
          ))}
        </div>
        <span className="dcr__permblurb">{LEVEL_META[level].blurb}</span>
      </div>

      {/* ---- file bar ---------------------------------------------------- */}
      <div className="dcr__bar">
        <button className="brbtn" onClick={() => setPicking(true)}>▤ Open file</button>
        <span className="dcr__path" title={path}>{path || "no file open"}</span>
        {dirty && <span className="dcr__dirty">unsaved</span>}
        {lang && <span className="brchip">{lang}</span>}
        <input
          className="brinput brinput--sm"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="What should she look for? (optional)"
        />
        <button className="brbtn brbtn--go" onClick={askReview} disabled={!path || !!busy}>
          ✧ Review
        </button>
        <button className="brbtn" onClick={run} disabled={!can("sandbox") || !path || !!busy}>
          ▷ Run
        </button>
        <button className="brbtn" onClick={save} disabled={!can("write") || !dirty || !!busy}>
          Save
        </button>
      </div>

      {busy && <div className="brnote brnote--busy">{busy}</div>}
      {msg && <div className="brnote">{msg}</div>}

      {/* ---- the two panes ---------------------------------------------- */}
      <div className="dcr__panes">
        <section className="dcr__pane">
          <header className="dcr__panehead">
            <span>AURA'S VERSION</span>
            {truncated && <span className="brchip">head of file only</span>}
            <button
              className="brlink"
              onClick={applyTheirs}
              disabled={!can("merge") || !theirs}
              title={can("merge") ? "Copy into your editor" : "Raise permission to Merge Review"}
            >
              Merge into my file →
            </button>
          </header>
          {theirs ? (
            <pre className="dcr__code dcr__code--ro">{theirs}</pre>
          ) : (
            <div className="dcr__blank">
              {path
                ? "Press Review and she'll read this file and propose a version."
                : "Open a file to start."}
            </div>
          )}
        </section>

        <section className="dcr__pane">
          <header className="dcr__panehead">
            <span>MY VERSION</span>
            <span className="brdim brdim--sm">{gutter} lines</span>
          </header>
          <textarea
            className="dcr__code"
            value={mine}
            spellCheck={false}
            onChange={(e) => setMine(e.target.value)}
            placeholder={path ? "" : "No file open."}
          />
        </section>
      </div>

      {/* ---- console ---------------------------------------------------- */}
      <div className="dcr__console">
        <div className="dcr__tabs">
          {(["output", "problems", "diff"] as ConsoleTab[]).map((t) => (
            <button
              key={t}
              className={"dcr__tab" + (tab === t ? " dcr__tab--on" : "")}
              onClick={() => setTab(t)}
            >
              {t === "output" ? "Output" : t === "problems" ? "Problems" : "Diff"}
              {t === "problems" && findings.length > 0 && (
                <span className="dcr__tabn">{findings.length}</span>
              )}
            </button>
          ))}
          <span className="dcr__spacer" />
          {can("push") && (
            <>
              <button className="brlink brlink--quiet" onClick={loadGit}>git status</button>
              <input
                className="brinput brinput--sm"
                value={commitMsg}
                onChange={(e) => setCommitMsg(e.target.value)}
                placeholder="Commit message…"
              />
              <button className="brbtn" onClick={publish} disabled={!!busy || !commitMsg.trim()}>
                Commit &amp; push
              </button>
            </>
          )}
        </div>

        <div className="dcr__log" ref={logRef}>
          {tab === "output" && (
            <>
              {lines.length === 0 && <p className="brdim brdim--sm">Nothing has run yet.</p>}
              {lines.map((l, i) => (
                <div key={i} className={"dcr__line dcr__line--" + l.kind}>
                  {l.kind === "cmd" ? "❯ " : ""}{l.text}
                </div>
              ))}
              {git && git.ok && (
                <div className="dcr__git">
                  <span className={"brchip" + (git.protected ? " dcr__chip--warn" : "")}>
                    {git.branch}{git.protected ? " (protected)" : ""}
                  </span>
                  <span className="brchip">{git.file_count} changed</span>
                  {git.ahead ? <span className="brchip">{git.ahead} ahead</span> : null}
                  {git.behind ? <span className="brchip">{git.behind} behind</span> : null}
                  {(git.files ?? []).slice(0, 12).map((f) => (
                    <span key={f.path} className="dcr__gitfile">{f.state} · {f.path}</span>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "problems" && (
            <>
              {findings.length === 0 && !explained && (
                <p className="brdim brdim--sm">Nothing flagged.</p>
              )}
              {findings.map((f, i) => (
                <div key={i} className={"dcr__finding dcr__finding--" + f.severity}>
                  <span className="dcr__sev">{f.severity}</span>
                  {f.line !== null && <span className="dcr__fline">line {f.line}</span>}
                  <span className="dcr__fnote">{f.note}</span>
                </div>
              ))}
              {explained && (
                <div className="dcr__explain">
                  <span className="dcr__sev">{explained.level}</span>
                  <strong>{explained.label}</strong>
                  <p>{explained.explanation}</p>
                  {explained.text && <pre className="dcr__errtext">{explained.text}</pre>}
                </div>
              )}
            </>
          )}

          {tab === "diff" && (
            <>
              {diff.length === 0 && (
                <p className="brdim brdim--sm">No suggestion to compare yet.</p>
              )}
              {diff.map((d, i) => (
                <div key={i} className={"dcr__dline dcr__dline--" + (d.sign === "+" ? "add" : d.sign === "-" ? "del" : "same")}>
                  <span className="dcr__dsign">{d.sign}</span>{d.text}
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      <div className="dcr__foot">
        <button className="brlink brlink--quiet" onClick={() => setSection("code")}>
          Full editor →
        </button>
        <button className="brlink brlink--quiet" onClick={() => setSection("terminal")}>
          Terminal →
        </button>
      </div>

      {picking && (
        <SourcePicker
          onClose={() => setPicking(false)}
          onAdd={(entries) => {
            const file = entries.find((e) => !e.dir);
            if (file) void openFile(file);
            else flash("Pick a file, not a folder.");
          }}
        />
      )}
    </div>
  );
}
