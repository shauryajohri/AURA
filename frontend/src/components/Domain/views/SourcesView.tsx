import { useCallback, useEffect, useState } from "react";
import { api, type Room } from "../../../api";
import { sources as sourcesApi, type RepoRef, type Source } from "../../../systemApi";
import { useDomainStore } from "../../../stores/domainStore";
import { setWorkspace } from "../useWorkspaceRoot";

/**
 * Sources — the things AURA keeps in step with.
 *
 * Paste a GitHub link once and AURA re-reads it every time it opens: which
 * repos exist, what they're for, what changed. Point it at a folder of PDFs
 * and Word files and the same thing happens to your documents. Put a source
 * in a room and every conversation in that room starts already knowing about
 * it.
 *
 * Open on a repo and AURA pulls the code down so you can prompt it and edit
 * it in Code.
 */

const KIND_META: Record<string, { icon: string; label: string }> = {
  github: { icon: "◧", label: "GitHub" },
  docs: { icon: "≡", label: "Documents" },
  link: { icon: "⚯", label: "Link" },
};

const STATUS_TEXT: Record<string, string> = {
  idle: "not synced yet",
  syncing: "syncing…",
  ok: "",
  error: "",
};

function ago(stamp: string): string {
  if (!stamp) return "never";
  const t = new Date(stamp.replace(" ", "T")).getTime();
  if (isNaN(t)) return stamp;
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function RepoRow({ repo, onOpen, busy }: {
  repo: RepoRef; onOpen: (r: RepoRef) => void; busy: string;
}) {
  const here = !!repo.local;
  return (
    <div className={"srepo" + (here ? " srepo--local" : "")}>
      <span className="srepo__name">{repo.name || repo.full_name}</span>
      {repo.language && <span className="srepo__lang">{repo.language}</span>}
      {repo.private && <span className="srepo__private">private</span>}
      {repo.description
        ? <span className="srepo__desc">{repo.description}</span>
        : <span className="srepo__spacer" />}
      <button
        className="srepo__open"
        disabled={busy === repo.full_name}
        onClick={() => onOpen(repo)}
      >
        {busy === repo.full_name ? "Getting it…" : here ? "Open in Code" : "Work on this"}
      </button>
    </div>
  );
}

function SourceCard({ source, rooms, onChanged, onOpenRepo }: {
  source: Source;
  rooms: Room[];
  onChanged: () => void;
  onOpenRepo: (source: Source, repo: RepoRef) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const meta = KIND_META[source.kind] ?? KIND_META.link;
  const repos = source.meta.repos ?? [];
  const docs = Object.values(source.meta.files ?? {});

  const sync = async () => {
    setBusy("sync");
    await sourcesApi.sync(source.id).catch(() => {});
    setBusy("");
    onChanged();
  };

  const disconnect = async () => {
    setBusy("remove");
    await sourcesApi.remove(source.id).catch(() => {});
    onChanged();
  };

  const setRoom = async (value: string) => {
    await sourcesApi.update(source.id, { room_id: value ? Number(value) : null }).catch(() => {});
    onChanged();
  };

  return (
    <article className={"scard scard--" + source.status}>
      <header className="scard__head">
        <span className="scard__icon">{meta.icon}</span>
        <button className="scard__title" onClick={() => setOpen((v) => !v)}>
          <span className="scard__label">{source.label || source.url}</span>
          <span className="scard__url">{source.url}</span>
        </button>
        <span className={"scard__dot scard__dot--" + source.status} title={source.status} />
      </header>

      <div className="scard__meta">
        <span className="scard__kind">{meta.label}</span>
        <span className="scard__detail">
          {source.status === "error"
            ? source.detail
            : source.detail || STATUS_TEXT[source.status] || ""}
        </span>
        <span className="scard__sync">synced {ago(source.last_sync)}</span>
      </div>

      <div className="scard__row">
        <label className="scard__roomlab">
          Room
          <select
            className="scard__room"
            value={source.room_id ?? ""}
            onChange={(e) => setRoom(e.target.value)}
          >
            <option value="">Not in a room</option>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>{r.icon} {r.name}</option>
            ))}
          </select>
        </label>
        <button className="btn btn--quiet" onClick={sync} disabled={!!busy}>
          {busy === "sync" ? "Syncing…" : "Sync now"}
        </button>
        <button className="btn btn--quiet" onClick={disconnect} disabled={!!busy}>
          Disconnect
        </button>
        {(repos.length > 0 || docs.length > 0) && (
          <button className="btn btn--quiet" onClick={() => setOpen((v) => !v)}>
            {open ? "Hide" : `Show ${repos.length || docs.length}`}
          </button>
        )}
      </div>

      {open && repos.length > 0 && (
        <div className="scard__body">
          {repos.map((r) => (
            <RepoRow
              key={r.full_name}
              repo={r}
              busy={busy}
              onOpen={async (repo) => {
                setBusy(repo.full_name);
                await onOpenRepo(source, repo);
                setBusy("");
              }}
            />
          ))}
        </div>
      )}

      {open && docs.length > 0 && (
        <div className="scard__body">
          {docs.map((d) => (
            <div key={d.name} className="sdoc">
              <span className="sdoc__name">{d.name}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

export default function SourcesView() {
  const [rows, setRows] = useState<Source[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const setSection = useDomainStore((s) => s.setSection);
  const addSource = useDomainStore((s) => s.addSource);

  const load = useCallback(async () => {
    try {
      setRows(await sourcesApi.list());
      setError("");
    } catch {
      setError("Brain offline — start server.py to connect anything.");
    }
  }, []);

  useEffect(() => {
    void load();
    api.getRooms().then((r) => setRooms(r.rooms ?? [])).catch(() => {});
  }, [load]);

  // A sync finishing arrives as a websocket frame, not a reply to anything
  // this component asked for — so the list refreshes itself when one lands.
  useEffect(() => {
    const onFrame = () => void load();
    window.addEventListener("aura:sources", onFrame);
    return () => window.removeEventListener("aura:sources", onFrame);
  }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const raw = input.trim();
    if (!raw || busy) return;
    setBusy(true);
    setError("");
    setNote("");
    const res = await sourcesApi.add(raw).catch(() =>
      ({ ok: false, error: "the brain didn't answer" } as Awaited<ReturnType<typeof sourcesApi.add>>));
    setBusy(false);
    if (!res.ok) { setError(res.error || "couldn't connect that"); return; }
    setInput("");
    setNote("Connected. Reading it now — this page updates when it's done.");
    void load();
  };

  const openRepo = async (source: Source, repo: RepoRef) => {
    const res = await sourcesApi.clone(source.id, repo.full_name).catch(() =>
      ({ ok: false, error: "couldn't reach the brain" } as Awaited<ReturnType<typeof sourcesApi.clone>>));
    if (!res.ok || !res.path) {
      setError(res.error || "couldn't get that repo");
      return;
    }
    // The workspace is what Git and the prompt bar read; the code source is
    // what puts the repo in the explorer tree. Both, or Code opens on a repo
    // it can't show you.
    setWorkspace(res.path, repo.full_name);
    addSource({ path: res.path, name: repo.name || repo.full_name, dir: true });
    setSection("code");
  };

  return (
    <div className="sources">
      <form className="sources__add" onSubmit={add}>
        <input
          className="sources__input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="github.com/you  ·  a folder of PDFs and Word files  ·  any link"
          spellCheck={false}
          disabled={busy}
        />
        <button className="btn btn--primary" disabled={busy || !input.trim()}>
          {busy ? "Connecting…" : "Connect"}
        </button>
      </form>

      <p className="sources__lede">
        Anything you connect here is re-read every time AURA opens. Put a source
        in a room and every conversation in that room knows about it.
      </p>

      {error && <p className="sources__err">{error}</p>}
      {note && <p className="sources__note">{note}</p>}

      <div className="sources__list">
        {rows.map((s) => (
          <SourceCard
            key={s.id}
            source={s}
            rooms={rooms}
            onChanged={load}
            onOpenRepo={openRepo}
          />
        ))}
      </div>

      {!rows.length && !error && (
        <p className="sources__empty">
          Nothing connected yet. Paste your GitHub link above to start.
        </p>
      )}
    </div>
  );
}
