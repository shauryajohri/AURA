import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { SavedItem, SavedKind } from "../types";
import { useSavedStore } from "../stores/savedStore";
import { openUrl } from "../components/Markdown";
import { uploadToSaved } from "../lib/files";

/**
 * Saved Info — every link, PDF and file you've shared with AURA, already
 * read. The list on the left is the vault; the reader on the right is what
 * AURA took from the selected item. Open goes to the original, Ask AURA
 * sends it to the chat so she explains it (out loud, if voice is on).
 */

const KIND_LABEL: Record<SavedKind, string> = {
  link: "Web page", github: "GitHub", video: "Video", pdf: "PDF",
  doc: "Document", image: "Image", file: "File",
};
const FILTERS: { id: "all" | SavedKind; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "link", label: "Web pages" },
  { id: "pdf", label: "PDFs" },
  { id: "github", label: "GitHub" },
  { id: "video", label: "Videos" },
  { id: "doc", label: "Documents" },
  { id: "image", label: "Images" },
  { id: "file", label: "Other files" },
];

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days <= 0) return `today, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined });
}

function sourceOf(it: SavedItem): string {
  if (it.url) return it.source || it.url;
  return it.file_name || "uploaded file";
}

interface Props {
  /** Send the item to the chat on Home and let AURA explain it. */
  onAsk: (item: SavedItem) => void;
}

export default function SavedInfoPage({ onAsk }: Props) {
  const items = useSavedStore((s) => s.items);
  const loaded = useSavedStore((s) => s.loaded);
  const offline = useSavedStore((s) => s.offline);
  const load = useSavedStore((s) => s.load);
  const upsert = useSavedStore((s) => s.upsert);
  const remove = useSavedStore((s) => s.remove);

  const [filter, setFilter] = useState<"all" | SavedKind>("all");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [full, setFull] = useState<SavedItem | null>(null);
  const [link, setLink] = useState("");
  const [intakeErr, setIntakeErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { void load(); }, [load]);

  const kinds = useMemo(() => {
    const have = new Set(items.map((i) => i.kind));
    return FILTERS.filter((f) => f.id === "all" || have.has(f.id as SavedKind));
  }, [items]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items.filter((it) => {
      if (filter !== "all" && it.kind !== filter) return false;
      if (!needle) return true;
      const hay = [it.title, it.summary, it.source, it.file_name, it.url, it.tags.join(" "),
                   it.key_points.join(" "), it.excerpt].join(" ").toLowerCase();
      return needle.split(/\s+/).every((w) => hay.includes(w.replace(/^#/, "")));
    });
  }, [items, filter, q]);

  // Keep a selection whenever there's something to select.
  useEffect(() => {
    if (sel !== null && shown.some((x) => x.id === sel)) return;
    setSel(shown[0]?.id ?? null);
  }, [shown, sel]);

  const current = items.find((x) => x.id === sel) ?? null;

  // The reader needs the full text; the list only carries an excerpt. Refetch
  // when the selection changes or its scan finishes.
  useEffect(() => {
    setConfirmDel(false);
    if (!current) { setFull(null); return; }
    let live = true;
    api.getSavedItem(current.id).then((it) => { if (live) setFull(it); }).catch(() => {});
    return () => { live = false; };
  }, [current?.id, current?.status, current?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const addLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!link.trim()) return;
    setBusy(true);
    setIntakeErr("");
    try {
      const res = await api.saveLink(link.trim());
      if (!res.ok || !res.item) throw new Error(res.error || "couldn't save that link");
      upsert(res.item);
      setSel(res.item.id);
      setFilter("all");
      setQ("");
      setLink("");
    } catch (err) {
      setIntakeErr(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const addFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setIntakeErr("");
    for (const f of Array.from(files).slice(0, 5)) {
      try {
        const it = await uploadToSaved(f, "page");
        upsert(it);
        setSel(it.id);
        setFilter("all");
      } catch (err) {
        setIntakeErr(err instanceof Error ? err.message : String(err));
      }
    }
  };

  const open = (it: SavedItem, copy = false) => {
    void api.markSavedOpened(it.id);
    if (it.url && !copy) openUrl(it.url);
    else openUrl(api.savedFileUrl(it.id));
  };

  const togglePin = async (it: SavedItem) => {
    const res = await api.updateSaved(it.id, { pinned: !it.pinned });
    if (res.item) upsert(res.item);
  };

  const rescan = async (it: SavedItem) => {
    const res = await api.rescanSaved(it.id);
    if (res.item) upsert(res.item);
  };

  const del = async (it: SavedItem) => {
    const res = await api.deleteSaved(it.id);
    if (res.ok) remove(it.id);
  };

  const reader = full && current && full.id === current.id ? { ...current, content: full.content } : current;

  return (
    <div className="saved">
      <header className="saved__head">
        <div className="saved__intro">
          <h2>Saved info</h2>
        </div>
        <form className="saved__intake" onSubmit={addLink}
              onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
              onDrop={(e) => { e.preventDefault(); void addFiles(e.dataTransfer.files); }}>
          <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Paste a link to save it"
                 aria-label="Link to save" spellCheck={false} />
          <button type="submit" className="saved__btn saved__btn--go" disabled={busy || !link.trim()}>
            {busy ? "Saving…" : "Save link"}
          </button>
          <button type="button" className="saved__btn" onClick={() => fileRef.current?.click()}>Add a file</button>
          <input ref={fileRef} type="file" hidden multiple accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp,.gif"
                 onChange={(e) => { void addFiles(e.target.files); e.target.value = ""; }} />
        </form>
        {intakeErr && <p className="saved__err" role="alert">{intakeErr}</p>}
      </header>

      {offline && <p className="pane-note">AURA's brain is offline — start server.py to open Saved Info.</p>}
      {!offline && loaded && items.length === 0 && (
        <div className="saved__empty">
          <span className="kindring kindring--link kindring--big" aria-hidden><i /></span>
          <p>Nothing saved yet. Paste a link above, drop a PDF here, or share one in the chat —
            AURA reads it and it lands on this page.</p>
        </div>
      )}

      {items.length > 0 && (
        <>
          <div className="saved__tools">
            <input className="saved__search" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Search titles, summaries, tags and text" aria-label="Search Saved Info" />
            <div className="saved__filters" role="tablist" aria-label="Show">
              {kinds.map((f) => (
                <button key={f.id} role="tab" aria-selected={filter === f.id}
                        className={"saved__filter" + (filter === f.id ? " is-on" : "")}
                        onClick={() => setFilter(f.id)}>
                  {f.label}
                  <span className="saved__count">
                    {f.id === "all" ? items.length : items.filter((i) => i.kind === f.id).length}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="saved__split">
            <ul className="vault" aria-label="Saved items">
              {shown.length === 0 && <li className="pane-note">Nothing matches “{q.trim()}”.</li>}
              {shown.map((it) => (
                <li key={it.id}>
                  <button className={"vault__row" + (it.id === sel ? " is-sel" : "")}
                          aria-current={it.id === sel} onClick={() => setSel(it.id)}>
                    <span className={`kindring kindring--${it.kind}` + (it.status === "scanning" ? " is-scanning" : "")
                      + (it.status === "error" ? " is-error" : "")} aria-hidden><i /></span>
                    <span className="vault__main">
                      <span className="vault__title">{it.title}</span>
                      <span className="vault__src">
                        {sourceOf(it)}
                        {it.created_at && <span className="vault__when">{when(it.created_at)}</span>}
                      </span>
                      <span className="vault__sum">
                        {it.status === "scanning" ? "Reading it now…" : it.status === "error" ? it.error : it.summary}
                      </span>
                    </span>
                    {it.pinned && <span className="vault__pin" title="Pinned">★</span>}
                  </button>
                </li>
              ))}
            </ul>

            {reader ? (
              <article className="reader" key={reader.id}>
                <p className="reader__kind">
                  <span className={`kindring kindring--${reader.kind}` + (reader.status === "scanning" ? " is-scanning" : "")}
                        aria-hidden><i /></span>
                  {KIND_LABEL[reader.kind]} from {sourceOf(reader)}
                </p>
                <h3 className="reader__title">{reader.title}</h3>

                <div className="reader__actions">
                  <button className="saved__btn saved__btn--go" onClick={() => open(reader)}>
                    {reader.url ? "Open original" : "Open file"}
                  </button>
                  <button className="saved__btn saved__btn--ask" onClick={() => onAsk(reader)}
                          disabled={reader.status === "scanning"}>
                    Ask AURA about it
                  </button>
                  {reader.url && reader.has_file && (
                    <button className="saved__btn" onClick={() => open(reader, true)}>Open saved copy</button>
                  )}
                  <span className="reader__spacer" />
                  <button className="saved__icon" onClick={() => togglePin(reader)}
                          aria-pressed={reader.pinned} title={reader.pinned ? "Unpin" : "Pin to the top"}>
                    {reader.pinned ? "★" : "☆"}
                  </button>
                  <button className="saved__icon" onClick={() => rescan(reader)} title="Read it again"
                          disabled={reader.status === "scanning"}>↻</button>
                  {confirmDel ? (
                    <button className="saved__btn saved__btn--del" onClick={() => del(reader)}>Delete for good</button>
                  ) : (
                    <button className="saved__icon" onClick={() => setConfirmDel(true)} title="Delete">✕</button>
                  )}
                </div>

                {reader.status === "scanning" && (
                  <p className="reader__status">AURA is reading this. The summary appears here when she's done.</p>
                )}
                {reader.status === "error" && (
                  <p className="reader__status reader__status--err">
                    She couldn't read it: {reader.error}. The {reader.url ? "link" : "file"} is still saved —
                    Open works, and ↻ tries again.
                  </p>
                )}

                {reader.summary && <p className="reader__summary">{reader.summary}</p>}

                {reader.key_points.length > 0 && (
                  <section className="reader__points">
                    <h4>Worth remembering</h4>
                    <ul>{reader.key_points.map((k, i) => <li key={i}>{k}</li>)}</ul>
                  </section>
                )}

                {reader.tags.length > 0 && (
                  <div className="reader__tags" aria-label="Tags">
                    {reader.tags.map((t) => (
                      <button key={t} onClick={() => { setQ("#" + t); setFilter("all"); }}
                              title={`Show everything tagged ${t}`}>#{t}</button>
                    ))}
                  </div>
                )}

                {reader.content_chars > 0 && (
                  <details className="reader__text">
                    <summary>What AURA read ({reader.content_chars.toLocaleString()} characters)</summary>
                    <div className="reader__raw">{reader.content ?? reader.excerpt}</div>
                  </details>
                )}

                <p className="reader__foot">
                  Saved {when(reader.created_at)}
                  {reader.origin === "chat" ? " from the chat" : ""}
                  {reader.opened_at ? `, last opened ${when(reader.opened_at)}` : ""}
                </p>
              </article>
            ) : (
              <div className="reader reader--blank"><p className="pane-note">Pick something on the left.</p></div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
