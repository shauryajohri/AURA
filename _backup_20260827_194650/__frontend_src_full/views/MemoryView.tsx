import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Fact, type MemoryNote, type MemoryRecap } from "../api";

// ============================================================================
// Memory — everything AURA remembers, in one place, editable.
//
// Three kinds of memory, and the difference matters:
//   facts   — what she knows about you. You own these: add, edit, delete.
//   notes   — knowledge she extracted from conversations. Read + delete.
//   recaps  — session snapshots (what you were doing in which app). Read + delete.
//
// Refreshes every 6s so the panel tracks a live session, but a refresh never
// clobbers a row you're mid-edit — that was the old Qt panel's worst habit.
// ============================================================================

type Tab = "facts" | "notes" | "recaps";

const REFRESH_MS = 6000;

function when(s: string | null): string {
  if (!s) return "";
  const d = new Date(s.includes("T") ? s : s.replace(" ", "T"));
  if (isNaN(d.getTime())) return s;
  const diff = Date.now() - d.getTime();
  if (diff < 60000) return "just now";
  if (diff < 3600000) return Math.floor(diff / 60000) + "m ago";
  if (diff < 86400000) return Math.floor(diff / 3600000) + "h ago";
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + "d ago";
  return d.toLocaleDateString();
}

export default function MemoryView() {
  const [tab, setTab] = useState<Tab>("facts");
  const [facts, setFacts] = useState<Fact[]>([]);
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  const [recaps, setRecaps] = useState<MemoryRecap[]>([]);
  const [newFact, setNewFact] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [open, setOpen] = useState<Record<number, boolean>>({});

  // the poll reads this instead of `editId` so it doesn't need to be a dep
  const editing = useRef<number | null>(null);
  editing.current = editId;

  const load = useCallback(async () => {
    try {
      const [f, n, r] = await Promise.all([
        api.getFacts(),
        api.getNotes(),
        api.getRecaps(),
      ]);
      // never yank the list out from under an open editor
      if (editing.current === null) setFacts(f);
      else setFacts((prev) => prev.map((p) => f.find((x) => x.id === p.id) ?? p));
      setNotes(n);
      setRecaps(r);
      setOffline(false);
    } catch {
      setOffline(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFact.trim()) return;
    await api.addFact(newFact.trim());
    setNewFact("");
    void load();
  };

  const saveEdit = async (id: number) => {
    const text = editText.trim();
    setEditId(null);
    editing.current = null;
    if (text) await api.updateFact(id, text);
    void load();
  };

  const counts: Record<Tab, number> = {
    facts: facts.length,
    notes: notes.length,
    recaps: recaps.length,
  };

  const HINT: Record<Tab, string> = {
    facts: "What AURA knows about you. Edit or delete anything.",
    notes: "Knowledge she pulled out of your conversations. She writes these; you can prune them.",
    recaps: "Session snapshots — what you were working on, and where.",
  };

  return (
    <div className="view">
      <div className="view__head">
        <h2>Memory</h2>
        <span className="view__count">
          {counts[tab]} {tab}
          {offline && <span className="mem__offline"> · offline</span>}
        </span>
      </div>

      <div className="mem__tabs">
        {(["facts", "notes", "recaps"] as Tab[]).map((t) => (
          <button
            key={t}
            className={"mem__tab" + (tab === t ? " mem__tab--on" : "")}
            onClick={() => setTab(t)}
          >
            {t === "facts" ? "About you" : t === "notes" ? "Saved notes" : "Session history"}
            <span className="mem__tabn">{counts[t]}</span>
          </button>
        ))}
      </div>

      <p className="view__hint">{HINT[tab]}</p>

      {loading && <p className="view__empty">Loading…</p>}
      {offline && !loading && (
        <p className="view__empty">Can't reach AURA's server — memory is unreadable right now.</p>
      )}

      {/* ---- facts: yours to curate ------------------------------------- */}
      {tab === "facts" && (
        <>
          <form className="taskadd" onSubmit={add}>
            <input
              value={newFact}
              onChange={(e) => setNewFact(e.target.value)}
              placeholder="Teach AURA a fact about you…"
            />
            <button type="submit">Save</button>
          </form>

          {!loading && facts.length === 0 && !offline && (
            <p className="view__empty">No facts stored yet.</p>
          )}

          <ul className="factlist">
            {facts.map((f) => (
              <li key={f.id} className="factrow">
                {editId === f.id ? (
                  <>
                    <input
                      className="factrow__edit"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void saveEdit(f.id);
                        if (e.key === "Escape") setEditId(null);
                      }}
                      autoFocus
                    />
                    <button className="factrow__btn" onClick={() => saveEdit(f.id)}>Save</button>
                    <button className="factrow__btn" onClick={() => setEditId(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <span className="factrow__text">{f.fact}</span>
                    <span className="factrow__cat">{f.category}</span>
                    <span className="mem__when">{when(f.created_at)}</span>
                    <button
                      className="factrow__btn"
                      onClick={() => { setEditId(f.id); setEditText(f.fact); }}
                    >
                      Edit
                    </button>
                    <button
                      className="factrow__btn"
                      onClick={() => api.deleteFact(f.id).then(load)}
                    >
                      ×
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {/* ---- notes: hers, prunable -------------------------------------- */}
      {tab === "notes" && (
        <>
          {!loading && notes.length === 0 && !offline && (
            <p className="view__empty">
              Nothing saved yet. Notes appear when a conversation contains something
              worth keeping.
            </p>
          )}
          <ul className="memlist">
            {notes.map((n) => (
              <li key={n.id} className="memrow">
                <button
                  className="memrow__main"
                  onClick={() => setOpen((o) => ({ ...o, [n.id]: !o[n.id] }))}
                >
                  <span className="memrow__title">{n.title || "Untitled note"}</span>
                  <span className={"memrow__summary" + (open[n.id] ? " memrow__summary--open" : "")}>
                    {n.summary}
                  </span>
                </button>
                <span className="mem__when">{when(n.created_at)}</span>
                <button className="factrow__btn" onClick={() => api.deleteNote(n.id).then(load)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* ---- recaps: session history ------------------------------------ */}
      {tab === "recaps" && (
        <>
          {!loading && recaps.length === 0 && !offline && (
            <p className="view__empty">No session history yet.</p>
          )}
          <ul className="memlist">
            {recaps.map((r) => (
              <li key={r.id} className="memrow">
                <button
                  className="memrow__main"
                  onClick={() => setOpen((o) => ({ ...o, [r.id]: !o[r.id] }))}
                >
                  <span className="memrow__title">{r.app || "unknown app"}</span>
                  <span className={"memrow__summary" + (open[r.id] ? " memrow__summary--open" : "")}>
                    {r.summary}
                  </span>
                </button>
                <span className="mem__when">{when(r.created_at)}</span>
                <button className="factrow__btn" onClick={() => api.deleteRecap(r.id).then(load)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
