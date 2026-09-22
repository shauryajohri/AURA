import { useCallback, useEffect, useState } from "react";
import { upgrades, type ProposalRow } from "../../../systemApi";
import ProposalCard from "../../Upgrade/ProposalCard";

/**
 * Build with AURA — the prompt bar under the editor.
 *
 * Say what you want changed in the repo you're in. AURA works out which files
 * that touches, rewrites them, and shows you the diff. Nothing is written
 * until you approve, and anything applied can be rolled back, so you can ask
 * for something big without betting the working tree on it.
 *
 * Whatever file you have open is passed as a hint, so "rename this to
 * something clearer" means the file in front of you rather than a guess.
 */

interface Props {
  /** The repo or folder being worked on. */
  root: string;
  /** What to call it on screen. */
  label?: string;
  /** Paths (absolute) of the open tabs — the hint for "this file". */
  openFiles?: string[];
  /** Fired after an approve, so the editor can re-read what changed. */
  onApplied?: (paths: string[]) => void;
}

/** Absolute path → the repo-relative form the backend speaks in. */
function relativize(root: string, abs: string): string {
  const r = root.replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
  const a = abs.replace(/\\/g, "/");
  return a.toLowerCase().startsWith(r + "/") ? a.slice(r.length + 1) : "";
}

export default function CodePrompt({ root, label, openFiles = [], onApplied }: Props) {
  const [open, setOpen] = useState(false);
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<ProposalRow[]>([]);

  const load = useCallback(async () => {
    if (!root) return;
    try {
      setRows(await upgrades.list("project", root));
    } catch {
      /* the panel is still usable; the list just stays empty */
    }
  }, [root]);

  useEffect(() => { if (open) void load(); }, [open, load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = request.trim();
    if (!text || busy || !root) return;
    setBusy(true);
    setError("");
    setNote("");
    setOpen(true);

    const hint = openFiles.map((f) => relativize(root, f)).filter(Boolean).slice(0, 4);
    const res = await upgrades
      .propose({ request: text, scope: "project", root, files: hint, label: label || "" })
      .catch(() => ({ ok: false, error: "the brain didn't answer — is server.py running?" } as
        Awaited<ReturnType<typeof upgrades.propose>>));

    setBusy(false);
    if (!res.ok) { setError(res.error || "that didn't work"); return; }
    setRequest("");
    setNote("Read the diff before you apply it.");
    void load();
  };

  const pending = rows.filter((r) => r.status === "pending");
  const rest = rows.filter((r) => r.status !== "pending");

  return (
    <div className={"cprompt" + (open ? " cprompt--open" : "")}>
      <form className="cprompt__bar" onSubmit={submit}>
        <span className="cprompt__spark">✦</span>
        <input
          className="cprompt__input"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder={root ? `Change something in ${label || "this project"}…` : "Open a project first"}
          disabled={busy || !root}
          spellCheck={false}
        />
        {rows.length > 0 && (
          <button
            type="button"
            className={"cprompt__count" + (pending.length ? " cprompt__count--live" : "")}
            onClick={() => setOpen((v) => !v)}
            title="Proposed changes"
          >
            {pending.length || rows.length}
          </button>
        )}
        <button className="btn btn--primary cprompt__go" disabled={busy || !request.trim() || !root}>
          {busy ? "Writing…" : "Build"}
        </button>
        {open && (
          <button type="button" className="cprompt__close" onClick={() => setOpen(false)} title="Hide">
            ▾
          </button>
        )}
      </form>

      {open && (
        <div className="cprompt__panel">
          {busy && <p className="cprompt__working">Reading the project and writing the change…</p>}
          {error && <p className="cprompt__err">{error}</p>}
          {note && <p className="cprompt__note">{note}</p>}

          {pending.map((r) => (
            <ProposalCard
              key={r.id}
              row={r}
              onChanged={(n) => {
                if (n) setNote(n);
                onApplied?.(r.files);
                void load();
              }}
            />
          ))}

          {rest.length > 0 && (
            <details className="cprompt__history">
              <summary>Earlier changes ({rest.length})</summary>
              {rest.map((r) => (
                <ProposalCard key={r.id} row={r} onChanged={() => void load()} />
              ))}
            </details>
          )}

          {!rows.length && !busy && !error && (
            <p className="cprompt__empty">
              Ask for a change — "add a dark mode toggle", "split this file",
              "make the tests cover the error path".
            </p>
          )}
        </div>
      )}
    </div>
  );
}
