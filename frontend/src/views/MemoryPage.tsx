import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Fact, MemoryNote, MemoryRecap, SavedLink } from "../api";
import MemoryView from "./MemoryView";
import PageShell from "./PageShell";
import { useLocalStorage } from "../hooks/useLocalStorage";

// ---- Timeline: everything AURA remembers, grouped by when it happened ----

interface MemItem {
  key: string;
  kind: "fact" | "note" | "recap";
  id: number;
  text: string;
  sub?: string;
  category: string;
  when: Date | null;
}

const parseWhen = (s: string | null): Date | null => {
  if (!s) return null;
  const d = new Date(s.includes("T") ? s : s.replace(" ", "T"));
  return isNaN(d.getTime()) ? null : d;
};

const dayBucket = (d: Date | null): string => {
  if (!d) return "Older";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const that = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((today.getTime() - that.getTime()) / 86400000);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return "This Week";
  return "Older";
};

const BUCKETS = ["Favorites", "Today", "Yesterday", "This Week", "Older"];

function TimelinePane() {
  const [items, setItems] = useState<MemItem[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [pins, setPins] = useLocalStorage<string[]>("aura.memory.pins", []);
  const [cat, setCat] = useState<string>("all");
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const load = useCallback(() => {
    Promise.allSettled([api.getFacts(), api.getNotes(300), api.getRecaps(80)]).then(
      ([f, n, r]) => {
        if (f.status === "rejected" && n.status === "rejected" && r.status === "rejected") {
          setOffline(true);
          return;
        }
        const out: MemItem[] = [];
        if (f.status === "fulfilled")
          for (const x of f.value)
            out.push({ key: "f" + x.id, kind: "fact", id: x.id, text: x.fact, category: x.category || "general", when: parseWhen(x.created_at) });
        if (n.status === "fulfilled")
          for (const x of n.value)
            out.push({ key: "n" + x.id, kind: "note", id: x.id, text: x.title, sub: x.summary, category: "notes", when: parseWhen(x.created_at) });
        if (r.status === "fulfilled")
          for (const x of r.value)
            out.push({ key: "r" + x.id, kind: "recap", id: x.id, text: x.summary, category: x.app || "sessions", when: parseWhen(x.created_at) });
        out.sort((a, b) => (b.when?.getTime() ?? 0) - (a.when?.getTime() ?? 0));
        setItems(out);
        setOffline(false);
      },
    );
  }, []);
  useEffect(() => { load(); }, [load]);

  const cats = useMemo(() => {
    const s = new Set<string>();
    for (const it of items ?? []) s.add(it.category);
    return ["all", ...Array.from(s).sort()];
  }, [items]);

  const pinned = useMemo(() => new Set(pins), [pins]);
  const togglePin = (key: string) =>
    setPins(pinned.has(key) ? pins.filter((p) => p !== key) : [...pins, key]);

  const remove = (it: MemItem) => {
    const call =
      it.kind === "fact" ? api.deleteFact(it.id) :
      it.kind === "note" ? api.deleteNote(it.id) : api.deleteRecap(it.id);
    call.then(load).catch(() => {});
  };

  const saveEdit = (it: MemItem) => {
    if (it.kind === "fact" && editText.trim()) {
      api.updateFact(it.id, editText.trim()).then(() => { setEditKey(null); load(); }).catch(() => {});
    } else {
      setEditKey(null);
    }
  };

  if (offline) return <p className="pane-note">Brain offline — start server.py to browse memory.</p>;
  if (!items) return <p className="pane-note">Gathering memories…</p>;

  const filtered = cat === "all" ? items : items.filter((i) => i.category === cat);
  const groups: Record<string, MemItem[]> = { Favorites: [], Today: [], Yesterday: [], "This Week": [], Older: [] };
  for (const it of filtered) {
    if (pinned.has(it.key)) groups.Favorites.push(it);
    groups[dayBucket(it.when)].push(it);
  }

  const card = (it: MemItem) => (
    <article key={it.key} className={"pane-card memcard" + (pinned.has(it.key) ? " memcard--pinned" : "")}>
      <header>
        <span className={"pane-chip pane-chip--" + it.kind}>{it.kind}</span>
        {it.category !== "general" && <span className="memcard__cat">{it.category}</span>}
        <span className="pane-card__when">
          {it.when ? it.when.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : ""}
        </span>
        <button
          className={"memcard__pin" + (pinned.has(it.key) ? " memcard__pin--on" : "")}
          title={pinned.has(it.key) ? "Unpin" : "Pin to Favorites"}
          onClick={() => togglePin(it.key)}
        >
          {pinned.has(it.key) ? "★" : "☆"}
        </button>
        {it.kind === "fact" && (
          <button className="memcard__edit" title="Edit"
            onClick={() => { setEditKey(it.key); setEditText(it.text); }}>✎</button>
        )}
        <button className="pane-card__del" title="Forget" onClick={() => remove(it)}>✕</button>
      </header>
      {editKey === it.key ? (
        <div className="memcard__editrow">
          <input value={editText} onChange={(e) => setEditText(e.target.value)} autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") saveEdit(it); if (e.key === "Escape") setEditKey(null); }} />
          <button onClick={() => saveEdit(it)}>Save</button>
        </div>
      ) : (
        <p>{it.text}</p>
      )}
      {it.sub && editKey !== it.key && <p className="memcard__sub">{it.sub}</p>}
    </article>
  );

  return (
    <div className="memtl">
      <div className="memtl__cats">
        {cats.map((c) => (
          <button key={c}
            className={"pageshell__tab memtl__cat" + (cat === c ? " pageshell__tab--on" : "")}
            onClick={() => setCat(c)}>
            {c}
          </button>
        ))}
      </div>
      {BUCKETS.map((b) =>
        groups[b].length === 0 ? null : (
          <section key={b} className="memtl__group">
            <h3 className="memtl__title">{b === "Favorites" ? "★ Favorites" : b}</h3>
            <div className="pane-list">{groups[b].map(card)}</div>
          </section>
        ),
      )}
      {filtered.length === 0 && <p className="pane-note">Nothing here yet — talk to AURA and memory grows.</p>}
    </div>
  );
}

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
        { id: "timeline", label: "Timeline", body: <TimelinePane /> },
        { id: "conversations", label: "Conversations", body: <ConversationsPane /> },
        { id: "search", label: "Search", body: <SearchPane /> },
        { id: "bookmarks", label: "Bookmarks", body: <BookmarksPane /> },
        { id: "manage", label: "Manage", body: <MemoryView /> },
      ]}
    />
  );
}
