import { useCallback, useEffect, useRef, useState } from "react";
import { domainApi } from "../../../domainApi";
import { useWorkspaceRoot } from "../useWorkspaceRoot";
import SourcePicker from "./SourcePicker";

// ============================================================================
// Build & Debug console.
//
// Runs your build/test/run commands through the same shell backend the
// Terminal uses, then READS the output: compiler and runtime errors are
// extracted with file:line, so a failed build becomes a clickable list of
// problems instead of a wall of text. That parsed list is the Debug console.
// ============================================================================

interface Problem {
  file: string;
  line: number;
  col?: number;
  severity: "error" | "warning";
  message: string;
  raw: string;
}

interface Run {
  id: number;
  command: string;
  output: string;
  code: number | null;
  ms: number;
  problems: Problem[];
  at: string;
}

/** Command presets, detected from what's actually in the folder. */
const PRESETS: Array<{ label: string; cmd: string; needs: string[] }> = [
  { label: "npm run build", cmd: "npm run build", needs: ["package.json"] },
  { label: "npm run dev", cmd: "npm run dev", needs: ["package.json"] },
  { label: "npm test", cmd: "npm test", needs: ["package.json"] },
  { label: "tsc --noEmit", cmd: "npx tsc --noEmit", needs: ["tsconfig.json"] },
  { label: "pytest", cmd: "python -m pytest -q", needs: ["requirements.txt", "pyproject.toml", "setup.py"] },
  { label: "python server.py", cmd: "python server.py", needs: ["server.py"] },
  { label: "cargo build", cmd: "cargo build", needs: ["Cargo.toml"] },
  { label: "make", cmd: "make", needs: ["Makefile"] },
];

// Matchers for the compilers people actually use. Each returns file/line/msg.
const MATCHERS: Array<{ re: RegExp; map: (m: RegExpExecArray) => Problem }> = [
  // TypeScript / tsc:  src/App.tsx(12,5): error TS2322: message
  {
    re: /^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(\w+):\s*(.*)$/,
    map: (m) => ({ file: m[1], line: +m[2], col: +m[3], severity: m[4] as "error", message: `${m[5]}: ${m[6]}`, raw: m[0] }),
  },
  // gcc/clang/eslint style: path/file.c:12:5: error: message
  {
    re: /^(.+?):(\d+):(\d+):\s+(error|warning|fatal error):\s*(.*)$/,
    map: (m) => ({ file: m[1], line: +m[2], col: +m[3], severity: m[4].includes("error") ? "error" : "warning", message: m[5], raw: m[0] }),
  },
  // Python traceback:  File "server.py", line 42, in <module>
  {
    re: /^\s*File "(.+?)", line (\d+)/,
    map: (m) => ({ file: m[1], line: +m[2], severity: "error", message: "traceback frame", raw: m[0] }),
  },
  // Rust: --> src/main.rs:12:5
  {
    re: /^\s*-->\s+(.+?):(\d+):(\d+)/,
    map: (m) => ({ file: m[1], line: +m[2], col: +m[3], severity: "error", message: "compile error", raw: m[0] }),
  },
];

function parseProblems(output: string): Problem[] {
  const out: Problem[] = [];
  const seen = new Set<string>();
  const lines = output.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    for (const { re, map } of MATCHERS) {
      const m = re.exec(line);
      if (!m) continue;
      const p = map(m as RegExpExecArray);
      // Python tracebacks put the real message on the LAST line of the block;
      // borrow the following non-indented line when we only got a frame.
      if (p.message === "traceback frame") {
        const tail = lines.slice(i + 1).find((l) => l.trim() && !l.startsWith(" "));
        if (tail) p.message = tail.trim();
      }
      const key = p.file + ":" + p.line + ":" + p.message;
      if (!seen.has(key)) { seen.add(key); out.push(p); }
      break;
    }
  }
  return out.slice(0, 200);
}

export default function BuildView() {
  const { root, setRoot } = useWorkspaceRoot();
  const [sid, setSid] = useState<string | null>(null);
  const [command, setCommand] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [running, setRunning] = useState(false);
  const [available, setAvailable] = useState<string[]>([]);
  const [picking, setPicking] = useState(false);
  const [tab, setTab] = useState<"output" | "problems">("output");
  const outRef = useRef<HTMLPreElement>(null);
  const nextId = useRef(1);

  // Which presets make sense here? Ask the filesystem, don't guess.
  useEffect(() => {
    if (!root) return;
    domainApi.list(root, false)
      .then((r) => setAvailable((r.entries ?? []).map((e) => e.name)))
      .catch(() => setAvailable([]));
  }, [root]);

  useEffect(() => {
    if (!root) return;
    domainApi.shellOpen(root).then((r) => setSid(r.id)).catch(() => {});
  }, [root]);

  useEffect(() => {
    outRef.current?.scrollTo({ top: outRef.current.scrollHeight });
  }, [runs]);

  const execute = useCallback(async (cmd: string) => {
    const line = cmd.trim();
    if (!line || running || !root) return;
    setRunning(true);
    const started = performance.now();
    try {
      const r = await domainApi.shellRun(sid, line, root, 300);
      const output = r.output ?? "";
      setRuns((prev) => [
        {
          id: nextId.current++,
          command: line,
          output: output || "(no output)",
          code: r.code ?? null,
          ms: Math.round(performance.now() - started),
          problems: parseProblems(output),
          at: new Date().toLocaleTimeString(),
        },
        ...prev,
      ].slice(0, 12));
    } catch (e) {
      setRuns((prev) => [{
        id: nextId.current++, command: line, output: String(e), code: -1,
        ms: Math.round(performance.now() - started), problems: [], at: new Date().toLocaleTimeString(),
      }, ...prev]);
    } finally {
      setRunning(false);
    }
  }, [sid, root, running]);

  if (!root) {
    return (
      <div className="dbuild">
        <p className="pane-note">Choose the project folder to build.</p>
        <button className="dgit__btn dgit__btn--primary" onClick={() => setPicking(true)}>Choose folder…</button>
        {picking && (
          <SourcePicker onAdd={(e) => { if (e[0]) setRoot(e[0].path); setPicking(false); }} onClose={() => setPicking(false)} />
        )}
      </div>
    );
  }

  const latest = runs[0];
  const presets = PRESETS.filter((p) => p.needs.some((n) => available.includes(n)));

  return (
    <div className="dbuild">
      <header className="dgit__head">
        <div className="dgit__where">
          <span className="dgit__branch">{"⚙ Build"}</span>
          <span className="dgit__root" title={root}>{root}</span>
        </div>
        <div className="dgit__counts">
          <button className="dgit__btn" onClick={() => setPicking(true)}>Change folder</button>
        </div>
      </header>

      <div className="dbuild__presets">
        {presets.map((p) => (
          <button key={p.cmd} className="dgit__btn" disabled={running} onClick={() => execute(p.cmd)}>
            {p.label}
          </button>
        ))}
        {presets.length === 0 && <span className="pane-note">No known build files here — type a command below.</span>}
      </div>

      <form
        className="dbuild__cmd"
        onSubmit={(e) => { e.preventDefault(); execute(command); setCommand(""); }}
      >
        <span className="dbuild__prompt">❯</span>
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Any command — npm run build, pytest, cargo test…"
          disabled={running}
        />
        <button type="submit" className="dgit__btn dgit__btn--primary" disabled={running || !command.trim()}>
          {running ? "Running…" : "Run"}
        </button>
      </form>

      {latest && (
        <>
          <div className="dbuild__tabs">
            <button className={"dgit__btn" + (tab === "output" ? " dgit__btn--primary" : "")} onClick={() => setTab("output")}>
              Output
            </button>
            <button className={"dgit__btn" + (tab === "problems" ? " dgit__btn--primary" : "")} onClick={() => setTab("problems")}>
              Problems {latest.problems.length > 0 && <em className="dbuild__count">{latest.problems.length}</em>}
            </button>
            <span className={"dbuild__result" + (latest.code === 0 ? " dbuild__result--ok" : " dbuild__result--fail")}>
              {latest.code === 0 ? "✓ passed" : `exit ${latest.code}`} · {latest.ms}ms
            </span>
          </div>

          {tab === "output" ? (
            <pre className="dbuild__out" ref={outRef}>
              {runs.map((r) => (
                <div key={r.id} className="dbuild__block">
                  <div className="dbuild__blockhead">
                    <span className="dbuild__prompt">❯</span> {r.command}
                    <em>{r.at}</em>
                  </div>
                  {r.output}
                </div>
              ))}
            </pre>
          ) : (
            <div className="dbuild__problems">
              {latest.problems.length === 0 && (
                <p className="pane-note">
                  {latest.code === 0
                    ? "No problems — clean run."
                    : "The command failed but AURA couldn't parse a file:line from it. Check Output."}
                </p>
              )}
              {latest.problems.map((p, i) => (
                <div key={i} className={"dbuild__prob dbuild__prob--" + p.severity}>
                  <span className="dbuild__sev">{p.severity === "error" ? "✕" : "!"}</span>
                  <span className="dbuild__file">{p.file}<em>:{p.line}{p.col ? ":" + p.col : ""}</em></span>
                  <span className="dbuild__msg">{p.message}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {picking && (
        <SourcePicker startPath={root} onAdd={(e) => { if (e[0]) setRoot(e[0].path); setPicking(false); }} onClose={() => setPicking(false)} />
      )}
    </div>
  );
}
