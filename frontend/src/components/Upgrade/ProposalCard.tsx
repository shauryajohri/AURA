import { useState } from "react";
import { upgrades, type FileChange, type Proposal, type ProposalRow } from "../../systemApi";

/**
 * One proposed change, and the decision about it.
 *
 * Collapsed it is a sentence and a count. Opened it is the actual diff, file
 * by file — because "AURA wants to edit 3 files" is not something anyone can
 * sensibly say yes to. The diff is the whole point of the approval step.
 */

interface Props {
  row: ProposalRow;
  /** Called after approve / reject / rollback so the list can refresh. */
  onChanged: (note?: string) => void;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: "Waiting on you", cls: "pending" },
  applied: { label: "Applied", cls: "applied" },
  rejected: { label: "Rejected", cls: "rejected" },
  rolled_back: { label: "Rolled back", cls: "rejected" },
};

/** A unified diff, coloured. Long runs of unchanged context are folded away —
 *  they are noise when the question is "what changes?". */
function Diff({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: JSX.Element[] = [];
  let skipped = 0;

  const flush = (key: string) => {
    if (!skipped) return;
    out.push(
      <div key={"fold" + key} className="udiff__fold">
        {skipped} unchanged line{skipped === 1 ? "" : "s"}
      </div>,
    );
    skipped = 0;
  };

  lines.forEach((line, i) => {
    if (line.startsWith("+++") || line.startsWith("---")) return;
    if (line.startsWith("@@")) {
      flush(String(i));
      out.push(<div key={i} className="udiff__hunk">{line}</div>);
      return;
    }
    const kind = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "ctx";
    if (kind === "ctx") {
      skipped++;
      return;
    }
    flush(String(i));
    out.push(<div key={i} className={"udiff__line udiff__line--" + kind}>{line || " "}</div>);
  });
  flush("end");

  return <div className="udiff">{out}</div>;
}

function FileBlock({ change }: { change: FileChange }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="upfile">
      <button className="upfile__head" onClick={() => setOpen((v) => !v)}>
        <span className="upfile__caret">{open ? "▾" : "▸"}</span>
        <span className="upfile__path">{change.path}</span>
        {change.new && <span className="upfile__tag">new file</span>}
        <span className="upfile__counts">
          <span className="upfile__add">+{change.added}</span>
          <span className="upfile__del">−{change.removed}</span>
        </span>
      </button>
      {open && <Diff text={change.diff} />}
    </div>
  );
}

export default function ProposalCard({ row, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const status = STATUS[row.status] ?? STATUS.pending;

  const expand = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (!full) {
      const p = await upgrades.get(row.id).catch(() => null);
      if (p) setFull(p);
      else setError("couldn't load the diff");
    }
  };

  const act = async (what: "approve" | "reject" | "rollback" | "remove") => {
    setBusy(what);
    setError("");
    const fn = what === "approve" ? upgrades.approve
      : what === "reject" ? upgrades.reject
        : what === "rollback" ? upgrades.rollback : upgrades.remove;
    const res = await fn(row.id).catch(() => ({ ok: false, error: "the brain didn't answer" }));
    setBusy("");
    if (!res.ok) { setError(res.error || "that didn't work"); return; }
    // Rewriting AURA's own source only takes effect on the next start, and
    // saying so here is the difference between "nothing happened" and "done".
    const restart = "restart" in res && res.restart;
    onChanged(
      what === "approve"
        ? (restart ? "Applied. Restart AURA for it to take effect." : "Applied.")
        : what === "rollback"
          ? (restart ? "Rolled back. Restart AURA to load the old code." : "Rolled back.")
          : undefined,
    );
  };

  return (
    <article className={"upcard upcard--" + status.cls}>
      <header className="upcard__head">
        <button className="upcard__title" onClick={expand}>
          <span className="upcard__caret">{open ? "▾" : "▸"}</span>
          <span className="upcard__request">{row.request}</span>
        </button>
        <span className={"upcard__status upcard__status--" + status.cls}>{status.label}</span>
      </header>

      <div className="upcard__meta">
        {row.scope === "self"
          ? <span className="upcard__scope">AURA's own code</span>
          : <span className="upcard__scope">{row.label}</span>}
        <span className="upcard__files">
          {row.files.length} file{row.files.length === 1 ? "" : "s"}
        </span>
        <span className="upcard__add">+{row.added}</span>
        <span className="upcard__del">−{row.removed}</span>
        <span className="upcard__when">{row.applied_at || row.created_at}</span>
      </div>

      {row.why && <p className="upcard__why">{row.why}</p>}

      {open && (
        <div className="upcard__body">
          {full
            ? full.changes.map((c) => <FileBlock key={c.path} change={c} />)
            : <p className="upcard__loading">Loading the diff…</p>}
        </div>
      )}

      {error && <p className="upcard__err">{error}</p>}

      <footer className="upcard__actions">
        {row.status === "pending" && (
          <>
            <button className="btn btn--primary" disabled={!!busy} onClick={() => act("approve")}>
              {busy === "approve" ? "Applying…" : "Approve & apply"}
            </button>
            <button className="btn" disabled={!!busy} onClick={() => act("reject")}>Reject</button>
          </>
        )}
        {row.status === "applied" && (
          <button className="btn" disabled={!!busy} onClick={() => act("rollback")}>
            {busy === "rollback" ? "Rolling back…" : "Roll it back"}
          </button>
        )}
        {(row.status === "rejected" || row.status === "rolled_back") && (
          <button className="btn btn--quiet" disabled={!!busy} onClick={() => act("remove")}>
            Forget this
          </button>
        )}
        {!open && (
          <button className="btn btn--quiet" onClick={expand}>See the changes</button>
        )}
      </footer>
    </article>
  );
}
