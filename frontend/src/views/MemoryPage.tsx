import { useEffect, useMemo, useState } from "react";
import { api, Fact, MemoryNote, MemoryRecap, SavedLink } from "../api";
import MemoryView from "./MemoryView";
import PageShell from "./PageShell";

/**
 * Memory — the full recall surface behind the ❋ sidebar item.
 * Timeline (facts / notes / recaps, editable) · Conversations (session
 * recaps) · Search (one box across everything AURA remembers) · Bookmarks
 * (the links vault, moved here from the old Village screen).
 */

function ConversationsPane() {
  const [recaps, setRecaps] = useState<MemoryRecap[] | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    api.getRecaps(80).then(setRecaps).catch(() => setOffline(true));
  }, []);
  if (offline) return <p className="pane-note">Brain offline — start server.py to load conversations.</p>;
  if (!recaps) return <p className="pane-note">Loading conversations…</p>;
  if (recaps.length === 0) return <p className="pane-note">No conversation recaps yet — talk to AURA and they'll gather here.</p>;
  return (
    <div className="pane-list">
      {recaps.map((r) => (
        <article key={r.id} className="pane-card">
          <header>
            {r.app && <span className="pane-chip pane-chip--recap">{r.app}</span>}
            <span className="pane-card__when">{r.created_at ?? ""}</span>
            <button className="pane-card__del" title="Forget this recap"
              onClick={() => api.deleteRecap(r.id).then(() => setRecaps((cur) => cur?.filter((x) => x.id !== r.id) ?? null))}>
              ✕
            </button>
          </header>
          <p>{r.summary}</p>
        </article>
      ))}
    </div>
  );
}

function SearchPane() {
  const [q, setQ] = useState("");
  const [facts, setFacts] = useState<Fact[]>([]);
  const [notes, setNotes] = useState<MemoryNote[]>([]);
  const [recaps, setRecaps] = useState<MemoryRecap[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.allSettled([api.getFacts(), api.getNotes(400), api.getRecaps(120)]).then(
      ([f, n, r]) => {
        if (f.status === "fulfilled") setFacts(f.value);
        if (n.status === "fulfilled") setNotes(n.value);
        if (r.status === "fulfilled") setRecaps(r.value);
        setReady(true);
      },
    );
  }, []);

  const hits = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (needle.length < 2) return [];
    const rows: Array<{ kind: string; text: string; when: string | null; key: string }> = [];
    for (const f of facts)
      if (f.fact.toLowerCase().includes(needle))
        rows.push({ kind: "fact", text: f.fact, when: f.created_at, key: "f" + f.id });
    for (const n of notes) {
      const body = n.title + " — " + n.summary;
      if (body.toLowerCase().includes(needle))
        rows.push({ kind: "note", text: body, when: n.created_at ?? null, key: "n" + n.id });
    }
    for (const r of recaps)
      if (r.summary.toLowerCase().includes(needle))
        rows.push({ kind: "recap", text: r.summary, when: r.created_at ?? null, key: "r" + r.id });
    return rows.slice(0, 60);
  }, [q, facts, notes, recaps]);

  return (
    <div className="pane-search">
      <input
        className="pane-search__box"
        placeholder="Search everything AURA remembers…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoFocus
      />
      {!ready && <p className="pane-note">Indexing memory…</p>}
      {ready && q.trim().length >= 2 && hits.length === 0 && (
        <p className="pane-note">Nothing in memory matches "{q.trim()}".</p>
      )}
      <div className="pane-list">
        {hits.map((h) => (
          <article key={h.key} className="pane-card">
            <header>
              <span className={"pane-chip pane-chip--" + h.kind}>{h.kind}</span>
              <span className="pane-card__when">{h.when ?? ""}</span>
            </header>
            <p>{h.text}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function BookmarksPane() {
  const [links, setLinks] = useState<SavedLink[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");

  const load = () => api.getLinks().then(setLinks).catch(() => setOffline(true));
  useEffect(() => { load(); }, []);

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    api.addLink(url.trim(), name.trim() || undefined).then(() => { setUrl(""); setName(""); load(); });
  };

  if (offline) return <p className="pane-note">Brain offline — the links vault needs server.py.</p>;
  return (
    <div className="pane-links">
      <form className="pane-links__add" onSubmit={add}>
        <input placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        <input placeholder="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" disabled={!url.trim()}>Save</button>
      </form>
      {!links && <p className="pane-note">Loading vault…</p>}
      {links && links.length === 0 && <p className="pane-note">The vault is empty — save the links you never want to lose.</p>}
      <div className="pane-list">
        {(links ?? []).map((l) => (
          <article key={l.id} className="pane-card pane-card--link">
            <a href={l.url} target="_blank" rel="noreferrer">{l.name || l.url}</a>
            <span className="pane-card__when">{l.url}</span>
            <button className="pane-card__del" title="Remove"
              onClick={() => api.deleteLink(l.id).then(load)}>✕</button>
          </article>
        ))}
      </div>
    </div>
  );
}

export default function MemoryPage() {
  return (
    <PageShell
      title="Memory"
      tagline="Everything AURA holds for you — living, searchable, yours to edit."
      storeKey="aura.page.memory"
      tabs={[
        { id: "timeline", label: "Timeline", body: <MemoryView /> },
        { id: "conversations", label: "Conversations", body: <ConversationsPane /> },
        { id: "search", label: "Search", body: <SearchPane /> },
        { id: "bookmarks", label: "Bookmarks", body: <BookmarksPane /> },
      ]}
    />
  );
}
