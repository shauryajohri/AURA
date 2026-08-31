import { useCallback, useEffect, useState } from "react";
import { domainApi, type FsEntry, type FsRoot } from "../../../domainApi";

// ============================================================================
// Source picker — the only place the full filesystem is ever shown.
//
// You browse here to CHOOSE what enters the Code pane; once picked, the pane
// shows nothing but your selection. Multi-select, then Add.
// ============================================================================

interface Props {
  onAdd: (entries: FsEntry[]) => void;
  onClose: () => void;
  startPath?: string;
}

export default function SourcePicker({ onAdd, onClose, startPath }: Props) {
  const [roots, setRoots] = useState<FsRoot[]>([]);
  const [cwd, setCwd] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [picked, setPicked] = useState<Record<string, FsEntry>>({});
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const browse = useCallback(async (path: string) => {
    setBusy(true);
    setErr("");
    const r = await domainApi.list(path, false);
    setBusy(false);
    if (!r.ok) { setErr(r.error ?? "could not open that folder"); return; }
    setCwd(r.path);
    setParent(r.parent);
    setEntries(r.entries);
    setFilter("");
  }, []);

  useEffect(() => {
    domainApi
      .roots()
      .then((r) => {
        setRoots(r.roots);
        browse(startPath || r.roots[0]?.path || "");
      })
      .catch(() => setErr("bridge offline — is server.py running?"));
  }, [browse, startPath]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (e: FsEntry) =>
    setPicked((p) => {
      const next = { ...p };
      if (next[e.path]) delete next[e.path];
      else next[e.path] = e;
      return next;
    });

  const chosen = Object.values(picked);
  const visible = filter
    ? entries.filter((e) => e.name.toLowerCase().includes(filter.toLowerCase()))
    : entries;

  const crumbs = (() => {
    if (!cwd) return [];
    const sep = cwd.includes("\\") ? "\\" : "/";
    const parts = cwd.split(sep).filter(Boolean);
    return parts.map((part, i) => ({
      label: part,
      path: parts.slice(0, i + 1).join(sep) + (sep === "\\" && i === 0 ? "\\" : ""),
    }));
  })();

  return (
    <div className="dpick__backdrop" onClick={onClose}>
      <div className="dpick" onClick={(e) => e.stopPropagation()}>
        <div className="dpick__head">
          <span className="dpick__title">CHOOSE WHAT TO WORK ON</span>
          <button className="dpick__x" onClick={onClose}>✕</button>
        </div>

        <div className="dpick__roots">
          {roots.map((r) => (
            <button key={r.path} onClick={() => browse(r.path)} title={r.path}>{r.label}</button>
          ))}
        </div>

        <div className="dpick__crumbs">
          {parent && <button className="dcode__up" onClick={() => browse(parent)} title="Up">↑</button>}
          {crumbs.slice(-4).map((c) => (
            <button key={c.path} onClick={() => browse(c.path)}>{c.label}</button>
          ))}
        </div>

        <input
          className="dpick__filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter…"
          autoFocus
        />

        {err && <div className="dpick__err">{err}</div>}

        <div className="dpick__list">
          {busy && <div className="dcode__empty">loading…</div>}
          {!busy && visible.length === 0 && <div className="dcode__empty">Empty folder.</div>}
          {visible.map((e) => (
            <div key={e.path} className={"dpick__row" + (picked[e.path] ? " dpick__row--on" : "")}>
              <button className="dpick__box" onClick={() => toggle(e)} title="Select">
                {picked[e.path] ? "✓" : ""}
              </button>
              <button
                className="dpick__entry"
                onClick={() => (e.dir ? browse(e.path) : toggle(e))}
                onDoubleClick={() => e.dir && browse(e.path)}
                title={e.path}
              >
                <span className={"dcode__lang dcode__lang--" + (e.dir ? "dir" : e.lang)}>
                  {e.dir ? "▸" : e.lang}
                </span>
                <span className="dcode__fname">{e.name}</span>
              </button>
            </div>
          ))}
        </div>

        <div className="dpick__foot">
          <span className="dpick__count">
            {chosen.length ? `${chosen.length} selected` : "Nothing selected"}
          </span>
          <button className="dpick__cancel" onClick={onClose}>Cancel</button>
          <button
            className="dpick__add"
            disabled={chosen.length === 0}
            onClick={() => { onAdd(chosen); onClose(); }}
          >
            Add to project
          </button>
        </div>
      </div>
    </div>
  );
}
