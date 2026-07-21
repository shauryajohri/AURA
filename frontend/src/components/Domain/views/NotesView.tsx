import { useEffect, useMemo, useState } from "react";
import { useActiveProject, useDomainStore, type Note } from "../../../stores/domainStore";

// ============================================================================
// Notes — sticky notes on a board.
//
// The grid shows small squares with a preview; click one and it opens full
// size for reading and editing. Not Research (sourced material) and not
// Documentation (structured project docs) — this is the thought you'd
// otherwise lose.
// ============================================================================

const COLORS = [
  { id: "violet", tint: "#8b5cff" },
  { id: "amber", tint: "#ffb648" },
  { id: "cyan", tint: "#38e1ff" },
  { id: "green", tint: "#35e08f" },
  { id: "pink", tint: "#f472b6" },
];

const when = (ts: number) => {
  const d = (Date.now() - ts) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  if (d < 604800) return `${Math.floor(d / 86400)}d ago`;
  return new Date(ts).toLocaleDateString();
};

const titleOf = (body: string) => {
  const first = body.split("\n").find((l) => l.trim()) ?? "";
  return first.replace(/^#+\s*/, "").slice(0, 40) || "Empty note";
};

/** Full-size view of one note — read it, edit it, restyle it. */
function NoteModal({ note, onClose }: { note: Note; onClose: () => void }) {
  const updateNote = useDomainStore((s) => s.updateNote);
  const pinNote = useDomainStore((s) => s.pinNote);
  const removeNote = useDomainStore((s) => s.removeNote);
  const patchNoteColor = useDomainStore((s) => s.setNoteColor);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tint = COLORS.find((c) => c.id === note.color)?.tint ?? COLORS[0].tint;

  return (
    <div className="dnote__backdrop" onClick={onClose}>
      <div
        className="dnote__modal"
        style={{ ["--tint" as string]: tint }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dnote__mhead">
          <span className="dnote__mwhen">edited {when(note.updatedAt)}</span>
          <span className="dcode__spacer" />
          <div className="dnote__colors">
            {COLORS.map((c) => (
              <button
                key={c.id}
                className={"dnote__dot" + (note.color === c.id ? " dnote__dot--on" : "")}
                style={{ background: c.tint }}
                onClick={() => patchNoteColor(note.id, c.id)}
                title={c.id}
              />
            ))}
          </div>
          <button onClick={() => pinNote(note.id)} title={note.pinned ? "Unpin" : "Pin"}>
            {note.pinned ? "★" : "☆"}
          </button>
          <button
            onClick={() => { if (confirm("Delete this note?")) { removeNote(note.id); onClose(); } }}
            title="Delete"
          >
            🗑
          </button>
          <button onClick={onClose} title="Close">✕</button>
        </div>

        <textarea
          className="dnote__mbody"
          autoFocus
          value={note.body}
          spellCheck={false}
          placeholder="Write it out…"
          onChange={(e) => updateNote(note.id, e.target.value)}
        />

        <div className="dnote__mfoot">
          <span>{note.body.trim() ? note.body.trim().split(/\s+/).length : 0} words</span>
          <span className="dcode__spacer" />
          <span>Esc to close · saves as you type</span>
        </div>
      </div>
    </div>
  );
}

export default function NotesView() {
  const project = useActiveProject();
  const addNote = useDomainStore((s) => s.addNote);
  const pinNote = useDomainStore((s) => s.pinNote);

  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const notes = useMemo(() => {
    const list = project?.notes ?? [];
    const filtered = query
      ? list.filter((n) => n.body.toLowerCase().includes(query.toLowerCase()))
      : list;
    return [...filtered].sort(
      (a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt
    );
  }, [project, query]);

  const open = project?.notes.find((n) => n.id === openId) ?? null;

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const create = () => {
    addNote("");
    // the store prepends, so the newest note is first
    setTimeout(() => {
      const fresh = useDomainStore.getState().projects.find((p) => p.id === project.id)?.notes[0];
      if (fresh) setOpenId(fresh.id);
    }, 0);
  };

  return (
    <div className="dnotes">
      <div className="dnotes__head">
        <div>
          <h3>Notes</h3>
          <p>Stick a thought down. Click any note to open it full size.</p>
        </div>
        <input
          className="dnotes__search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search notes…"
        />
        <button className="dnotes__add" onClick={create}>✚ New note</button>
      </div>

      <div className="dnotes__board">
        {notes.length === 0 && (
          <div className="dnotes__empty">
            {query ? "No note matches that." : "The board is empty — stick something down."}
          </div>
        )}

        {notes.map((n) => {
          const tint = COLORS.find((c) => c.id === n.color)?.tint ?? COLORS[0].tint;
          return (
            <div
              key={n.id}
              className={"dsticky" + (n.pinned ? " dsticky--pin" : "")}
              style={{ ["--tint" as string]: tint }}
              onClick={() => setOpenId(n.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && setOpenId(n.id)}
            >
              <button
                className="dsticky__pin"
                onClick={(e) => { e.stopPropagation(); pinNote(n.id); }}
                title={n.pinned ? "Unpin" : "Pin"}
              >
                {n.pinned ? "★" : "☆"}
              </button>
              <div className="dsticky__title">{titleOf(n.body)}</div>
              <div className="dsticky__preview">{n.body.trim() || "…"}</div>
              <div className="dsticky__when">{when(n.updatedAt)}</div>
              <div className="dsticky__curl" />
            </div>
          );
        })}
      </div>

      {open && <NoteModal note={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
