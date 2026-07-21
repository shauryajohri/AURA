import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { domainApi, type FsEntry } from "../../../domainApi";
import { useActiveProject, useDomainStore } from "../../../stores/domainStore";
import SourcePicker from "./SourcePicker";
import CodeEditor from "../code/CodeEditor";
import FileTree from "../code/FileTree";
import QuickOpen from "../code/QuickOpen";
import { LANG_LABEL } from "../code/highlight";
import { fileIcon } from "../code/icons";
import TerminalView from "./TerminalView";

// ============================================================================
// Code — a VS Code-shaped workspace over your chosen working set.
//
//   activity bar · explorer / search / open editors · tabbed editor
//   · bottom panel (terminal) · status bar
//
// The multi-root idea is VS Code's own: the folders and files you pick are the
// workspace roots, so you still never see your whole drive — you just navigate
// what you added the way you'd expect to.
//
// Shortcuts: Ctrl+S save · Ctrl+P go to file · Ctrl+W close tab
//            Ctrl+B toggle sidebar · Ctrl+` toggle panel · Ctrl+/ comment
// ============================================================================

type SideView = "explorer" | "search" | "open";

interface Tab {
  path: string;
  name: string;
  lang: string;
  content: string;
  saved: string;
}

/**
 * Unsaved edits, held per project for as long as the app is running.
 *
 * Sessions persist file *paths* only, so switching projects re-reads from
 * disk — which would silently throw away work in progress. This cache keeps
 * dirty buffers alive across project switches so you can hop to another
 * project and come back to exactly what you were typing. It is deliberately
 * in-memory: a half-finished edit shouldn't outlive the app.
 */
const dirtyCache = new Map<string, Map<string, string>>();

const baseName = (p: string) => p.split(/[\\/]/).filter(Boolean).pop() ?? p;
const dirName = (p: string) => {
  const parts = p.split(/[\\/]/).filter(Boolean);
  return parts.slice(0, -1);
};

export default function CodePane() {
  const project = useActiveProject();
  const activeId = useDomainStore((s) => s.activeId);
  const addSource = useDomainStore((s) => s.addSource);
  const removeSource = useDomainStore((s) => s.removeSource);
  const saveSession = useDomainStore((s) => s.saveSession);
  const pendingFile = useDomainStore((s) => s.pendingFile);
  const consumePendingFile = useDomainStore((s) => s.consumePendingFile);
  const log = useDomainStore((s) => s.log);

  const [tabs, setTabs] = useState<Tab[]>([]);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [side, setSide] = useState<SideView>("explorer");
  const [sideOpen, setSideOpen] = useState(true);
  const [sideW, setSideW] = useState(232);
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelH, setPanelH] = useState(200);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [refreshToken, setRefreshToken] = useState(0);
  const [picking, setPicking] = useState(false);
  const [quickOpen, setQuickOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [cursor, setCursor] = useState({ line: 1, col: 1, sel: 0 });
  const [wrap, setWrap] = useState(false);
  const [restoring, setRestoring] = useState(false);

  // which project's editors are currently on screen
  const loadedFor = useRef<string | null>(null);
  const tabsRef = useRef<Tab[]>([]);
  const openRef = useRef<string | null>(null);
  const expandedRef = useRef<Set<string>>(new Set());
  tabsRef.current = tabs;
  openRef.current = openPath;
  expandedRef.current = expanded;
  const [menu, setMenu] = useState<{ x: number; y: number; entry: { path: string; name: string; dir: boolean } } | null>(null);

  // search view
  const [needle, setNeedle] = useState("");
  const [results, setResults] = useState<FsEntry[]>([]);
  const [searching, setSearching] = useState(false);

  const sources = useMemo(() => project?.sources ?? [], [project]);
  const active = tabs.find((t) => t.path === openPath) ?? null;
  const dirty = active ? active.content !== active.saved : false;
  const dirtyCount = tabs.filter((t) => t.content !== t.saved).length;

  // ---- opening / saving ---------------------------------------------------
  const openFile = useCallback(
    async (e: { path: string; name: string }) => {
      setOpenPath(e.path);
      if (tabs.some((t) => t.path === e.path)) return;
      const r = await domainApi.read(e.path);
      if (!r.ok) { setErr(r.error ?? "could not open that file"); setOpenPath(null); return; }
      setErr("");
      setTabs((prev) => [
        ...prev,
        { path: r.path!, name: r.name!, lang: r.lang ?? "txt", content: r.content ?? "", saved: r.content ?? "" },
      ]);
    },
    [tabs]
  );

  const save = useCallback(async () => {
    const t = tabs.find((x) => x.path === openPath);
    if (!t || t.content === t.saved) return;
    setSaving(true);
    const r = await domainApi.write(t.path, t.content);
    setSaving(false);
    if (!r.ok) { setErr(r.error ?? "save failed"); return; }
    const delta = t.content.split("\n").length - t.saved.split("\n").length;
    setTabs((prev) => prev.map((x) => (x.path === t.path ? { ...x, saved: x.content } : x)));
    log("code", `Saved ${t.name}`, t.path + (delta ? ` (${delta > 0 ? "+" : ""}${delta} lines)` : ""));
    setStatus("Saved " + t.name);
    setTimeout(() => setStatus(""), 1800);
  }, [tabs, openPath, log]);

  const closeTab = useCallback(
    (path: string) => {
      const t = tabs.find((x) => x.path === path);
      if (t && t.content !== t.saved && !confirm(`${t.name} has unsaved changes. Close anyway?`)) return;
      const rest = tabs.filter((x) => x.path !== path);
      setTabs(rest);
      if (openPath === path) setOpenPath(rest[rest.length - 1]?.path ?? null);
    },
    [tabs, openPath]
  );

  // ---- per-project editor sessions ----------------------------------------
  // Opening a project restores the files it had open last time; switching to
  // another project closes those editors and opens that project's own set.
  useEffect(() => {
    if (!activeId) return;
    if (loadedFor.current === activeId) return;

    const outgoing = loadedFor.current;
    if (outgoing) {
      // park the outgoing project: remember its layout, keep dirty buffers
      saveSession(outgoing, {
        tabs: tabsRef.current.map((t) => t.path),
        active: openRef.current,
        expanded: [...expandedRef.current],
      });
      const dirty = new Map<string, string>();
      tabsRef.current.forEach((t) => { if (t.content !== t.saved) dirty.set(t.path, t.content); });
      if (dirty.size) dirtyCache.set(outgoing, dirty);
      else dirtyCache.delete(outgoing);
    }

    loadedFor.current = activeId;

    const incoming = useDomainStore.getState().projects.find((p) => p.id === activeId);
    const session = incoming?.session ?? { tabs: [], active: null, expanded: [] };

    // clear the old project's editors immediately — nothing bleeds across
    setTabs([]);
    setOpenPath(null);
    setErr("");
    setExpanded(new Set(session.expanded));

    if (session.tabs.length === 0) return;

    let cancelled = false;
    setRestoring(true);
    (async () => {
      const held = dirtyCache.get(activeId);
      const loaded: Tab[] = [];
      for (const path of session.tabs) {
        const r = await domainApi.read(path);
        if (cancelled) return;
        if (!r.ok) continue;              // deleted or moved since last time
        const onDisk = r.content ?? "";
        loaded.push({
          path: r.path!,
          name: r.name!,
          lang: r.lang ?? "txt",
          content: held?.get(path) ?? onDisk,
          saved: onDisk,
        });
      }
      if (cancelled) return;
      setTabs(loaded);
      setOpenPath(
        loaded.find((t) => t.path === session.active)?.path ?? loaded[0]?.path ?? null
      );
      setRestoring(false);
      const missing = session.tabs.length - loaded.length;
      if (missing > 0) setStatus(`${missing} file${missing > 1 ? "s" : ""} no longer on disk`);
    })();

    return () => { cancelled = true; };
  }, [activeId, saveSession]);

  // Keep the session current as you work, so leaving Code (or closing AURA)
  // and coming back lands you where you were.
  useEffect(() => {
    if (!activeId || loadedFor.current !== activeId || restoring) return;
    const next = {
      tabs: tabs.map((t) => t.path),
      active: openPath,
      expanded: [...expanded],
    };
    const prev = useDomainStore.getState().projects.find((p) => p.id === activeId)?.session;
    if (
      prev &&
      prev.active === next.active &&
      prev.tabs.length === next.tabs.length &&
      prev.tabs.every((t, i) => t === next.tabs[i]) &&
      prev.expanded.length === next.expanded.length &&
      prev.expanded.every((e, i) => e === next.expanded[i])
    ) return;                                    // nothing moved — don't write
    saveSession(activeId, next);
  }, [tabs, openPath, expanded, activeId, restoring, saveSession]);

  // a file opened from the board / tasks / history
  useEffect(() => {
    if (!pendingFile) return;
    const path = pendingFile;
    consumePendingFile();
    const name = baseName(path);
    if (!sources.some((s) => path === s.path || path.startsWith(s.path)))
      addSource({ path, name, dir: false, lang: null });
    openFile({ path, name });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFile]);

  // ---- shortcuts ----------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      const k = e.key.toLowerCase();
      if (k === "s") { e.preventDefault(); save(); }
      else if (k === "p") { e.preventDefault(); setQuickOpen(true); }
      else if (k === "b") { e.preventDefault(); setSideOpen((v) => !v); }
      else if (k === "w" && openPath) { e.preventDefault(); closeTab(openPath); }
      else if (e.key === "`") { e.preventDefault(); setPanelOpen((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save, closeTab, openPath]);

  // ---- search across the working set ---------------------------------------
  useEffect(() => {
    const term = needle.trim();
    if (side !== "search" || term.length < 2) { setResults([]); return; }
    let alive = true;
    setSearching(true);
    const t = setTimeout(async () => {
      const folders = sources.filter((s) => s.dir);
      const all = await Promise.all(
        folders.map((f) => domainApi.searchFiles(f.path, term).catch(() => ({ hits: [] as FsEntry[] })))
      );
      if (!alive) return;
      const seen = new Set<string>();
      const merged: FsEntry[] = [];
      for (const r of all)
        for (const h of (r as { hits?: FsEntry[] }).hits ?? [])
          if (!seen.has(h.path)) { seen.add(h.path); merged.push(h); }
      setResults(merged);
      setSearching(false);
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [needle, side, sources]);

  // ---- resizers -----------------------------------------------------------
  const dragSide = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sideW;
    const move = (ev: MouseEvent) =>
      setSideW(Math.max(150, Math.min(460, startW + ev.clientX - startX)));
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
    };
    document.body.style.cursor = "col-resize";
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const dragPanel = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = panelH;
    const move = (ev: MouseEvent) =>
      setPanelH(Math.max(90, Math.min(520, startH - (ev.clientY - startY))));
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
    };
    document.body.style.cursor = "row-resize";
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  // ---- explorer actions ---------------------------------------------------
  const toggleExpand = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const targetDir = (entry?: { path: string; dir: boolean }) => {
    if (entry?.dir) return entry.path;
    if (entry) return dirName(entry.path).join(entry.path.includes("\\") ? "\\" : "/") ||
      (entry.path.includes("\\") ? entry.path.slice(0, 3) : "/");
    const firstDir = sources.find((s) => s.dir);
    return firstDir?.path ?? "";
  };

  const newEntry = async (dir: boolean, at?: { path: string; dir: boolean }) => {
    const base = targetDir(at);
    if (!base) { setErr("Add a folder to the workspace first."); return; }
    const name = prompt(dir ? "New folder name" : "New file name", dir ? "new-folder" : "untitled.ts");
    if (!name) return;
    const sep = base.includes("\\") ? "\\" : "/";
    const r = await domainApi.create(base + sep + name, dir);
    if (!r.ok) { setErr(r.error ?? "could not create"); return; }
    setExpanded((p) => new Set(p).add(base));
    setRefreshToken((n) => n + 1);
    log("code", `Created ${dir ? "folder" : "file"} ${name}`, base + sep + name);
    if (!dir) openFile({ path: base + sep + name, name });
  };

  const renameEntry = async (entry: { path: string; name: string }) => {
    const next = prompt("Rename", entry.name);
    if (!next || next === entry.name) return;
    const r = await domainApi.rename(entry.path, next);
    if (!r.ok) { setErr(r.error ?? "could not rename"); return; }
    setTabs((prev) => prev.filter((t) => t.path !== entry.path));
    if (openPath === entry.path) setOpenPath(null);
    setRefreshToken((n) => n + 1);
    log("code", `Renamed ${entry.name} → ${next}`, r.path);
  };

  const deleteEntry = async (entry: { path: string; name: string; dir: boolean }) => {
    if (!confirm(`Delete ${entry.name}${entry.dir ? " and everything in it" : ""}?`)) return;
    const r = await domainApi.remove(entry.path);
    if (!r.ok) { setErr(r.error ?? "could not delete"); return; }
    setTabs((prev) => prev.filter((t) => !t.path.startsWith(entry.path)));
    if (openPath?.startsWith(entry.path)) setOpenPath(null);
    setRefreshToken((n) => n + 1);
    log("code", `Deleted ${entry.name}`, entry.path);
  };

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const crumbs = active ? [...dirName(active.path).slice(-2), active.name] : [];

  return (
    <div className="vsc">
      {/* ---------- activity bar ---------- */}
      <div className="vsc-act">
        {([
          ["explorer", "🗀", "Explorer"],
          ["search", "⌕", "Search"],
          ["open", "❒", "Open editors"],
        ] as [SideView, string, string][]).map(([id, ico, label]) => (
          <button
            key={id}
            className={"vsc-act__btn" + (sideOpen && side === id ? " vsc-act__btn--on" : "")}
            onClick={() => {
              if (side === id && sideOpen) setSideOpen(false);
              else { setSide(id); setSideOpen(true); }
            }}
            title={label}
          >
            {ico}
            {id === "open" && dirtyCount > 0 && <span className="vsc-act__dot" />}
          </button>
        ))}
        <span className="vsc-act__spacer" />
        <button className="vsc-act__btn" onClick={() => setPicking(true)} title="Add folder or file to workspace">
          ✚
        </button>
        <button
          className={"vsc-act__btn" + (panelOpen ? " vsc-act__btn--on" : "")}
          onClick={() => setPanelOpen((v) => !v)}
          title="Terminal panel (Ctrl+`)"
        >
          ❯
        </button>
      </div>

      {/* ---------- sidebar ---------- */}
      {sideOpen && (
        <>
          <aside className="vsc-side" style={{ width: sideW }}>
            {side === "explorer" && (
              <>
                <div className="vsc-side__head">
                  <span>EXPLORER</span>
                  <div className="vsc-side__acts">
                    <button onClick={() => newEntry(false)} title="New file">✚</button>
                    <button onClick={() => newEntry(true)} title="New folder">🗀</button>
                    <button onClick={() => setRefreshToken((n) => n + 1)} title="Refresh">↻</button>
                    <button onClick={() => setExpanded(new Set())} title="Collapse all">⌃</button>
                  </div>
                </div>

                <div className="vsc-side__body">
                  {sources.length === 0 && (
                    <div className="vsc-side__empty">
                      <p>No folders in the workspace.</p>
                      <button onClick={() => setPicking(true)}>Add folder…</button>
                      <span>Only what you add appears here, and it stays with the project.</span>
                    </div>
                  )}
                  {sources.map((s) => (
                    <FileTree
                      key={s.path}
                      root={{ path: s.path, name: s.name, dir: s.dir }}
                      activePath={openPath}
                      expanded={expanded}
                      onToggleExpand={toggleExpand}
                      onOpenFile={openFile}
                      onContext={(e, entry) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setMenu({ x: e.clientX, y: e.clientY, entry });
                      }}
                      refreshToken={refreshToken}
                    />
                  ))}
                </div>
              </>
            )}

            {side === "search" && (
              <>
                <div className="vsc-side__head"><span>SEARCH</span></div>
                <div className="vsc-side__searchbox">
                  <input
                    autoFocus
                    value={needle}
                    onChange={(e) => setNeedle(e.target.value)}
                    placeholder="Find file by name…"
                  />
                </div>
                <div className="vsc-side__body">
                  {searching && <div className="vsc-tree__hint">searching…</div>}
                  {!searching && needle.trim().length >= 2 && results.length === 0 && (
                    <div className="vsc-tree__hint">No match in the workspace.</div>
                  )}
                  {results.map((r) => (
                    <button
                      key={r.path}
                      className={"vsc-tree__row" + (openPath === r.path ? " vsc-tree__row--on" : "")}
                      onClick={() => openFile(r)}
                      title={r.path}
                    >
                      <span className="vsc-tree__ico">{fileIcon(r.name)}</span>
                      <span className="vsc-tree__name">{r.name}</span>
                      <span className="vsc-tree__sub">{dirName(r.path).slice(-1)[0]}</span>
                    </button>
                  ))}
                </div>
              </>
            )}

            {side === "open" && (
              <>
                <div className="vsc-side__head">
                  <span>OPEN EDITORS</span>
                  <div className="vsc-side__acts">
                    <button
                      onClick={() => { tabs.forEach((t) => t.content === t.saved && closeTab(t.path)); }}
                      title="Close saved editors"
                    >
                      ⊘
                    </button>
                  </div>
                </div>
                <div className="vsc-side__body">
                  {tabs.length === 0 && <div className="vsc-tree__hint">Nothing open.</div>}
                  {tabs.map((t) => (
                    <div key={t.path} className="vsc-open__row">
                      <button
                        className={"vsc-tree__row" + (openPath === t.path ? " vsc-tree__row--on" : "")}
                        onClick={() => setOpenPath(t.path)}
                        title={t.path}
                      >
                        <span className="vsc-tree__ico">{fileIcon(t.name)}</span>
                        <span className="vsc-tree__name">{t.name}</span>
                        {t.content !== t.saved && <span className="vsc-tab__dot" />}
                      </button>
                      <button className="vsc-open__x" onClick={() => closeTab(t.path)} title="Close">✕</button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
          <div className="vsc-resize vsc-resize--x" onMouseDown={dragSide} />
        </>
      )}

      {/* ---------- editor column ---------- */}
      <div className="vsc-main">
        <div className="vsc-tabs">
          <span className="vsc-tabs__proj" title="Editors belong to this project">
            {project.name}
          </span>
          {tabs.map((t) => (
            <div
              key={t.path}
              className={"vsc-tab" + (t.path === openPath ? " vsc-tab--on" : "")}
              onClick={() => setOpenPath(t.path)}
              onAuxClick={(e) => e.button === 1 && closeTab(t.path)}
              title={t.path}
            >
              <span className="vsc-tab__ico">{fileIcon(t.name)}</span>
              <span className="vsc-tab__name">{t.name}</span>
              <button
                className="vsc-tab__close"
                onClick={(e) => { e.stopPropagation(); closeTab(t.path); }}
              >
                {t.content !== t.saved ? <span className="vsc-tab__dot" /> : "✕"}
              </button>
            </div>
          ))}
          {tabs.length > 0 && (
            <>
              <button className="vsc-tabs__qo" onClick={() => setQuickOpen(true)} title="Go to file (Ctrl+P)">
                ⌕
              </button>
              <button
                className="vsc-tabs__qo"
                onClick={() => {
                  const unsaved = tabs.filter((t) => t.content !== t.saved);
                  if (unsaved.length && !confirm(`${unsaved.length} file(s) have unsaved changes. Close all anyway?`)) return;
                  setTabs([]);
                  setOpenPath(null);
                }}
                title="Close all editors"
              >
                ⊘
              </button>
            </>
          )}
        </div>

        {active && (
          <div className="vsc-crumbs">
            {crumbs.map((c, i) => (
              <span key={i}>
                {i > 0 && <span className="vsc-crumbs__sep">›</span>}
                {c}
              </span>
            ))}
          </div>
        )}

        {err && (
          <div className="vsc-err">
            {err}
            <button onClick={() => setErr("")}>✕</button>
          </div>
        )}

        <div className="vsc-stage">
          {restoring ? (
            <div className="vsc-welcome">
              <div className="vsc-welcome__mark vsc-welcome__mark--spin">⌥</div>
              <h3>Reopening {project.name}</h3>
              <p className="vsc-welcome__sub">Restoring the files you had open.</p>
            </div>
          ) : active ? (
            <CodeEditor
              key={active.path}
              value={active.content}
              lang={active.lang}
              wrap={wrap}
              onCursor={setCursor}
              onSave={save}
              onChange={(next) =>
                setTabs((prev) =>
                  prev.map((t) => (t.path === active.path ? { ...t, content: next } : t))
                )
              }
            />
          ) : (
            <div className="vsc-welcome">
              <div className="vsc-welcome__mark">⌥</div>
              <h3>{sources.length ? "Open a file" : "Add a folder to get started"}</h3>
              <ul>
                <li><kbd>Ctrl</kbd><kbd>P</kbd> go to file</li>
                <li><kbd>Ctrl</kbd><kbd>B</kbd> toggle sidebar</li>
                <li><kbd>Ctrl</kbd><kbd>`</kbd> terminal</li>
                <li><kbd>Ctrl</kbd><kbd>S</kbd> save</li>
              </ul>
              {sources.length === 0 && (
                <button className="vsc-welcome__add" onClick={() => setPicking(true)}>
                  Add folder to workspace
                </button>
              )}
            </div>
          )}
        </div>

        {panelOpen && (
          <>
            <div className="vsc-resize vsc-resize--y" onMouseDown={dragPanel} />
            <div className="vsc-panel" style={{ height: panelH }}>
              <div className="vsc-panel__head">
                <span className="vsc-panel__tab">TERMINAL</span>
                <span className="vsc-act__spacer" />
                <button onClick={() => setPanelOpen(false)} title="Close panel">✕</button>
              </div>
              <div className="vsc-panel__body">
                <TerminalView embedded />
              </div>
            </div>
          </>
        )}

        {/* ---------- status bar ---------- */}
        <div className="vsc-status">
          <span className="vsc-status__seg">{project.name}</span>
          {active ? (
            <>
              <span className="vsc-status__seg">
                Ln {cursor.line}, Col {cursor.col}
                {cursor.sel > 0 && ` (${cursor.sel} selected)`}
              </span>
              <span className="vsc-status__seg">Spaces: 2</span>
              <span className="vsc-status__seg">{LANG_LABEL[active.lang] ?? active.lang}</span>
              <button className="vsc-status__seg vsc-status__btn" onClick={() => setWrap((w) => !w)}>
                Wrap: {wrap ? "on" : "off"}
              </button>
            </>
          ) : (
            <span className="vsc-status__seg">{sources.length} in workspace</span>
          )}
          <span className="vsc-act__spacer" />
          {status && <span className="vsc-status__ok">{status}</span>}
          {dirty && <span className="vsc-status__dirty">● unsaved</span>}
          <button
            className="vsc-status__seg vsc-status__btn"
            onClick={save}
            disabled={!dirty || saving}
          >
            {saving ? "saving…" : "Save"}
          </button>
        </div>
      </div>

      {/* ---------- overlays ---------- */}
      {menu && (
        <div className="vsc-menu" style={{ left: menu.x, top: menu.y }}>
          {menu.entry.dir && (
            <>
              <button onClick={() => newEntry(false, menu.entry)}>New file</button>
              <button onClick={() => newEntry(true, menu.entry)}>New folder</button>
              <div className="vsc-menu__sep" />
            </>
          )}
          <button onClick={() => renameEntry(menu.entry)}>Rename…</button>
          <button onClick={() => deleteEntry(menu.entry)}>Delete</button>
          {sources.some((s) => s.path === menu.entry.path) && (
            <>
              <div className="vsc-menu__sep" />
              <button onClick={() => removeSource(menu.entry.path)}>Remove from workspace</button>
            </>
          )}
        </div>
      )}

      {quickOpen && (
        <QuickOpen
          roots={sources.map((s) => ({ path: s.path, name: s.name, dir: s.dir }))}
          openTabs={tabs.map((t) => ({ path: t.path, name: t.name }))}
          onPick={openFile}
          onClose={() => setQuickOpen(false)}
        />
      )}

      {picking && (
        <SourcePicker
          startPath={sources[0]?.path}
          onClose={() => setPicking(false)}
          onAdd={(entries) =>
            entries.forEach((e) => addSource({ path: e.path, name: e.name, dir: e.dir, lang: e.lang }))
          }
        />
      )}
    </div>
  );
}
