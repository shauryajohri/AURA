import { useEffect, useRef, useState } from "react";
import { domainApi } from "../../../domainApi";
import { useActiveProject } from "../../../stores/domainStore";

// ============================================================================
// Terminal — a real shell session on the backend.
//
// Commands run through core/domain_shell.py: cwd and env persist between
// commands, output comes back merged with the exit code. Not a PTY, so
// interactive programs are refused with an explanation rather than hanging.
// ============================================================================

interface Line {
  id: number;
  kind: "cmd" | "out" | "err" | "sys";
  text: string;
  code?: number;
  ms?: number;
}

let seq = 0;

interface Props {
  /** Rendered inside the Code pane's bottom panel — drops its own chrome. */
  embedded?: boolean;
}

export default function TerminalView({ embedded }: Props = {}) {
  const project = useActiveProject();
  const [sid, setSid] = useState<string | null>(null);
  const [cwd, setCwd] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [hIndex, setHIndex] = useState(-1);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const push = (kind: Line["kind"], text: string, extra: Partial<Line> = {}) =>
    setLines((prev) => [...prev.slice(-400), { id: ++seq, kind, text, ...extra }]);

  // open a session, rooted at the project folder when there is one
  useEffect(() => {
    let alive = true;
    domainApi
      .shellOpen(project?.folder || undefined)
      .then((r) => {
        if (!alive) return;
        setSid(r.id);
        setCwd(r.cwd);
        push("sys", `session ready · ${r.cwd}`);
      })
      .catch(() => push("err", "bridge offline — start server.py"));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.folder]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

  const run = async (cmd: string) => {
    const line = cmd.trim();
    if (!line) return;

    push("cmd", line);
    setHistory((h) => [line, ...h.filter((x) => x !== line)].slice(0, 100));
    setHIndex(-1);
    setInput("");
    setRunning(true);

    try {
      const r = await domainApi.shellRun(sid, line, cwd);
      setSid(r.id);
      if (r.clear) {
        setLines([]);
      } else {
        if (r.output) push(r.code === 0 ? "out" : "err", r.output.replace(/\s+$/, ""), {
          code: r.code, ms: r.ms,
        });
        else push("sys", `exit ${r.code}${r.ms ? ` · ${r.ms}ms` : ""}`);
      }
      if (r.cwd) setCwd(r.cwd);
      if (r.closed) {
        setSid(null);
        push("sys", "session closed — type anything to start a new one");
      }
    } catch {
      push("err", "could not reach the bridge");
    } finally {
      setRunning(false);
      inputRef.current?.focus();
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { run(input); return; }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.min(hIndex + 1, history.length - 1);
      if (next >= 0) { setHIndex(next); setInput(history[next]); }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = hIndex - 1;
      setHIndex(next);
      setInput(next < 0 ? "" : history[next]);
      return;
    }
    if (e.key === "l" && e.ctrlKey) { e.preventDefault(); setLines([]); }
  };

  const short = cwd.length > 46 ? "…" + cwd.slice(-45) : cwd;

  return (
    <div
      className={"dterm" + (embedded ? " dterm--embedded" : "")}
      onClick={() => inputRef.current?.focus()}
    >
      <div className="dterm__head">
        {!embedded && <span className="dterm__title">TERMINAL</span>}
        <span className="dterm__cwd" title={cwd}>{short}</span>
        <span className="dterm__spacer" />
        <button onClick={() => setLines([])} title="Clear (Ctrl+L)">clear</button>
        <button
          onClick={async () => {
            if (sid) await domainApi.shellClose(sid);
            const r = await domainApi.shellOpen(project?.folder || undefined);
            setSid(r.id); setCwd(r.cwd); setLines([]);
            push("sys", `new session · ${r.cwd}`);
          }}
          title="Restart session"
        >
          restart
        </button>
      </div>

      <div className="dterm__log" ref={logRef}>
        {lines.map((l) => (
          <div key={l.id} className={"dterm__line dterm__line--" + l.kind}>
            {l.kind === "cmd" && <span className="dterm__prompt">❯</span>}
            <pre>{l.text}</pre>
            {l.kind !== "cmd" && l.code !== undefined && l.code !== 0 && (
              <span className="dterm__code">exit {l.code}</span>
            )}
          </div>
        ))}
        {running && <div className="dterm__line dterm__line--sys"><pre>running…</pre></div>}
      </div>

      <div className="dterm__input">
        <span className="dterm__prompt">❯</span>
        <input
          ref={inputRef}
          value={input}
          autoFocus
          spellCheck={false}
          disabled={running}
          placeholder={running ? "" : "type a command…"}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
        />
      </div>
    </div>
  );
}
