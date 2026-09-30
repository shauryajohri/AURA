import { useEffect, useState } from "react";
import { system, type ResetScope } from "../systemApi";

/**
 * Reset AURA — a clean slate, chosen piece by piece.
 *
 * Deliberately not one big red button. Wanting to clear the conversations is
 * an ordinary thing to want; losing everything AURA has learned about you
 * because that was the only option on offer is not. Whatever you pick, the
 * database is copied aside first and the path comes back, so a reset you
 * regret is recoverable.
 */

interface Props {
  onClose: () => void;
}

export default function ResetPanel({ onClose }: Props) {
  const [scopes, setScopes] = useState<ResetScope[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ labels: string[]; backup: string } | null>(null);

  useEffect(() => {
    system.resetScopes()
      .then(setScopes)
      .catch(() => setError("Brain offline — start server.py to reset anything."));
  }, []);

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const all = () =>
    setPicked((prev) => (prev.size === scopes.length ? new Set() : new Set(scopes.map((s) => s.id))));

  const run = async () => {
    setBusy(true);
    setError("");
    const res = await system
      .reset([...picked], confirm)
      .catch(() => ({ ok: false, error: "the brain didn't answer" } as
        Awaited<ReturnType<typeof system.reset>>));
    setBusy(false);
    if (!res.ok) { setError(res.error || "that didn't work"); return; }
    setDone({ labels: res.labels ?? [], backup: res.backup ?? "" });
    setPicked(new Set());
    setConfirm("");
  };

  if (done) {
    return (
      <div className="reset">
        <h3 className="reset__title">Done</h3>
        <p className="reset__lede">Cleared: {done.labels.join(", ") || "nothing"}.</p>
        {done.backup && (
          <p className="reset__backup">
            A copy of everything as it was is at <code>{done.backup}</code> — keep it
            until you're sure.
          </p>
        )}
        <p className="reset__lede">Restart AURA so it reloads with the clean slate.</p>
        <div className="reset__actions">
          <button className="btn btn--primary" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  const ready = picked.size > 0 && confirm.trim().toUpperCase() === "RESET";

  return (
    <div className="reset">
      <h3 className="reset__title">Reset AURA</h3>
      <p className="reset__lede">
        Pick what to clear. Everything else is left alone, and the whole database
        is copied aside first so this can be undone.
      </p>

      <button className="reset__all" onClick={all}>
        {picked.size === scopes.length && scopes.length > 0 ? "Clear selection" : "Select everything"}
      </button>

      <div className="reset__list">
        {scopes.map((s) => (
          <button
            key={s.id}
            role="checkbox"
            aria-checked={picked.has(s.id)}
            className={"reset__opt" + (picked.has(s.id) ? " reset__opt--on" : "")}
            onClick={() => toggle(s.id)}
          >
            <span className="reset__box">{picked.has(s.id) ? "✓" : ""}</span>
            <span className="reset__text">
              <span className="reset__name">{s.label}</span>
              <span className="reset__desc">{s.desc}</span>
            </span>
          </button>
        ))}
      </div>

      {picked.size > 0 && (
        <div className="reset__confirm">
          <label htmlFor="reset-confirm">
            This clears {picked.size} thing{picked.size === 1 ? "" : "s"}. Type <b>RESET</b> to go ahead.
          </label>
          <input
            id="reset-confirm"
            className="reset__input"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="RESET"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      )}

      {error && <p className="reset__err">{error}</p>}

      <div className="reset__actions">
        <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn btn--danger" onClick={run} disabled={!ready || busy}>
          {busy ? "Clearing…" : "Reset"}
        </button>
      </div>
    </div>
  );
}
