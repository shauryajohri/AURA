import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import { useClock } from "../../hooks/useClock";
import { api, Task, SavedLink, UsageStats, Settings } from "../../api";
import { useDomainStore, DomainSection } from "../../stores/domainStore";
import { Layout, ColId, DEFAULT_LAYOUT, CARD_TITLES } from "./layoutTypes";
import SettingsOverlay, { SettingsCategory, CATEGORY_META } from "./SettingsOverlay";
import FloatingParticles from "./FloatingParticles";

// ============================================================================
// Section 3 — the Sanctuary. The environment arrives first; after a ~300ms
// breath, cards reveal one by one. Domain is the hero card.
// All cards are LIVE against the FastAPI bridge now:
//   Tasks  → /api/tasks (add / complete / edit / delete)
//   Memory → /api/stats (usage graph) + /api/facts (what AURA remembers)
//   Links  → /api/links (favicon vault — rename, open, delete)
//   Settings → /api/settings (blackhole / planets / voice / auto-chat)
// ============================================================================

const USER = "Shaurya";
const PORTFOLIO_URL = "https://shauryajohri.dev"; // ← your portfolio site

const TITLES = CARD_TITLES;

// reveal order per the spec (not render order)
const REVEAL_ORDER = ["tasks", "memory", "music", "links", "portfolio", "settings", "domain"];

const favicon = (url: string) => {
  try {
    const host = new URL(url).hostname;
    return `https://www.google.com/s2/favicons?domain=${host}&sz=64`;
  } catch {
    return "";
  }
};

interface Props {
  entered: boolean; // journey reached the sanctuary
  onEnterDomain?: () => void; // Enter Workspace → cross into the Domain
}

export default function SanctuarySection({ entered, onEnterDomain }: Props) {
  const { greeting } = useClock();
  const [layout, setLayout] = useLocalStorage<Layout>("aura.sanctuary", DEFAULT_LAYOUT);
  const [playing, setPlaying] = useState(false);
  const [revealed, setRevealed] = useState(false);

  // ---- layout migration: cards added in later versions (links) join the
  // saved layout instead of silently not existing.
  useEffect(() => {
    setLayout((l) => {
      const present = new Set([...l.cols.left, ...l.cols.center, ...l.cols.right, ...l.hidden]);
      const missing = Object.keys(TITLES).filter((id) => !present.has(id));
      if (missing.length === 0) return l;
      return { ...l, cols: { ...l.cols, right: [...missing, ...l.cols.right] } };
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // arrive → breathe (~300ms) → cards begin
  useEffect(() => {
    if (!entered) { setRevealed(false); return; }
    const t = setTimeout(() => setRevealed(true), 300);
    return () => clearTimeout(t);
  }, [entered]);

  // ---- live data ----------------------------------------------------------
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskInput, setTaskInput] = useState("");
  const [editingTask, setEditingTask] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  const [links, setLinks] = useState<SavedLink[]>([]);
  const [linkUrl, setLinkUrl] = useState("");
  const [linkName, setLinkName] = useState("");
  const [renamingLink, setRenamingLink] = useState<number | null>(null);
  const [renameText, setRenameText] = useState("");
  const [linksEdit, setLinksEdit] = useState(false);   // hover ✎ toggles this
  const [linkSearch, setLinkSearch] = useState("");

  const [stats, setStats] = useState<UsageStats | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  // Which settings area is open (null = none). The sanctuary stays mounted
  // underneath, so closing the editor puts you exactly where you were.
  const [settingsFocus, setSettingsFocus] = useState<SettingsCategory | null>(null);

  const refreshTasks = () => api.getTasks().then(setTasks).catch(() => setOffline(true));
  const refreshLinks = () => api.getLinks().then(setLinks).catch(() => setOffline(true));

  useEffect(() => {
    if (!entered) return;
    setOffline(false);
    refreshTasks();
    refreshLinks();
    api.getStats().then(setStats).catch(() => setOffline(true));
    api.getSettings().then(setSettings).catch(() => setOffline(true));
  }, [entered]);

  const custom = layout.preset === "custom";

  // ---- drag to swap (FLIP-animated) ---------------------------------------
  const dragId = useRef<string | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const prevRects = useRef<Record<string, DOMRect> | null>(null);

  const captureRects = () => {
    const m: Record<string, DOMRect> = {};
    for (const [id, el] of Object.entries(cardRefs.current)) {
      if (el) m[id] = el.getBoundingClientRect();
    }
    prevRects.current = m;
  };

  useLayoutEffect(() => {
    const prev = prevRects.current;
    if (!prev) return;
    prevRects.current = null;
    for (const [id, el] of Object.entries(cardRefs.current)) {
      if (!el || !prev[id]) continue;
      const now = el.getBoundingClientRect();
      const dx = prev[id].left - now.left, dy = prev[id].top - now.top;
      if (dx || dy) {
        el.animate(
          [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
          { duration: 260, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }
        );
      }
    }
  }, [layout]);

  // Pick up a card and DROP it anywhere: on another card (slides in at that
  // spot) or on a column's empty space (lands at the end). Real placement,
  // not just a swap.
  const placeCard = (dragged: string, target: { card?: string; col?: ColId }) => {
    if (target.card === dragged) return;
    captureRects();
    setLayout((l) => {
      const cols: Record<ColId, string[]> = {
        left: l.cols.left.filter((x) => x !== dragged),
        center: l.cols.center.filter((x) => x !== dragged),
        right: l.cols.right.filter((x) => x !== dragged),
      };
      if (target.card) {
        for (const c of ["left", "center", "right"] as ColId[]) {
          const i = cols[c].indexOf(target.card);
          if (i >= 0) { cols[c].splice(i, 0, dragged); return { ...l, cols }; }
        }
        return l; // target vanished — keep old layout
      }
      if (target.col) cols[target.col].push(dragged);
      return { ...l, cols };
    });
  };

  const hideCard = (id: string) => {
    captureRects();
    setLayout((l) => ({ ...l, hidden: [...l.hidden, id] }));
  };
  const cycleSize = (id: string) => {
    captureRects();
    setLayout((l) => ({
      ...l,
      sizes: { ...l.sizes, [id]: l.sizes[id] === "tall" ? "normal" : "tall" },
    }));
  };

  // ---- task actions -------------------------------------------------------
  const addTask = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = taskInput.trim();
    if (!t) return;
    setTaskInput("");
    await api.addTask(t).catch(() => setOffline(true));
    refreshTasks();
  };
  const toggleTask = async (t: Task) => {
    await (t.status === "done" ? api.uncompleteTask(t.id) : api.completeTask(t.id)).catch(() => {});
    refreshTasks();
  };
  const removeTask = async (id: number) => {
    await api.deleteTask(id).catch(() => {});
    refreshTasks();
  };
  const commitTaskEdit = async () => {
    if (editingTask !== null && editText.trim()) {
      await api.updateTask(editingTask, { title: editText.trim() }).catch(() => {});
      refreshTasks();
    }
    setEditingTask(null);
  };

  // ---- link actions -------------------------------------------------------
  const addLink = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = linkUrl.trim();
    if (!url) return;
    setLinkUrl("");
    setLinkName("");
    await api.addLink(url, linkName.trim() || undefined).catch(() => setOffline(true));
    refreshLinks();
  };
  const commitRename = async () => {
    if (renamingLink !== null && renameText.trim()) {
      await api.updateLink(renamingLink, { name: renameText.trim() }).catch(() => {});
      refreshLinks();
    }
    setRenamingLink(null);
  };
  const removeLink = async (id: number) => {
    await api.deleteLink(id).catch(() => {});
    refreshLinks();
  };

  // ---- domain overview (shared zustand store with the workspace) ----------
  const domProjects = useDomainStore((s) => s.projects);
  const domActiveId = useDomainStore((s) => s.activeId);
  const setDomSection = useDomainStore((s) => s.setSection);
  const domActive = domProjects.find((p) => p.id === domActiveId) ?? null;
  const domInFlight = domProjects.reduce(
    (n, p) => n + (p.board.find((c) => c.id === "progress")?.cards.length ?? 0), 0);
  const domDonePct = (() => {
    if (!domActive) return 0;
    const total = domActive.board.reduce((n, c) => n + c.cards.length, 0);
    const done = domActive.board.find((c) => c.id === "done")?.cards.length ?? 0;
    return total ? Math.round((done / total) * 100) : 0;
  })();
  const jumpInto = (section: DomainSection) => {
    setDomSection(section);
    onEnterDomain?.();
  };

  // ---- card bodies ---------------------------------------------------------
  const doneCount = tasks.filter((t) => t.status === "done").length;

  const body = (id: string) => {
    switch (id) {
      case "tasks":
        return (
          <>
            <div className="sancard__section">Today</div>
            <ul className="san-list">
              {tasks.length === 0 && (
                <li className="san-list__empty">
                  {offline ? "Brain offline — start server.py" : "Nothing yet — add one below."}
                </li>
              )}
              {tasks.map((t) => (
                <li key={t.id} className={"san-list__item" + (t.status === "done" ? " san-list__item--done" : "")}>
                  <button
                    className={"san-check" + (t.status === "done" ? " san-check--on" : "")}
                    onClick={() => toggleTask(t)}
                    title={t.status === "done" ? "Reopen" : "Complete"}
                  >
                    {t.status === "done" ? "✓" : ""}
                  </button>
                  {editingTask === t.id ? (
                    <input
                      className="san-editinput"
                      autoFocus
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onBlur={commitTaskEdit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitTaskEdit();
                        if (e.key === "Escape") setEditingTask(null);
                      }}
                    />
                  ) : (
                    <span
                      className="san-list__text"
                      title="Double-click to edit"
                      onDoubleClick={() => { setEditingTask(t.id); setEditText(t.title); }}
                    >
                      {t.title}
                    </span>
                  )}
                  <button className="san-x" onClick={() => removeTask(t.id)}>{"✕"}</button>
                </li>
              ))}
            </ul>
            <div className="san-progress">
              <div
                className="san-progress__bar"
                style={{ width: tasks.length ? `${(doneCount / tasks.length) * 100}%` : "0%" }}
              />
            </div>
            <form className="san-quickadd" onSubmit={addTask}>
              <input value={taskInput} onChange={(e) => setTaskInput(e.target.value)} placeholder="Quick add..." />
              <button type="submit">+</button>
            </form>
          </>
        );

      case "memory": {
        const days = stats?.days ?? [];
        const max = Math.max(1, ...days.map((d) => Math.max(d.user_msgs, d.facts_saved)));
        return (
          <>
            <div className="sancard__section">You ↔ AURA · last 7 days</div>
            <div className="san-graph">
              {days.length === 0 && (
                <div className="san-list__empty">{offline ? "Brain offline" : "No data yet"}</div>
              )}
              {days.map((d) => (
                <div key={d.date} className="san-graph__day" title={`${d.date}
you: ${d.user_msgs} messages · saved: ${d.facts_saved} memories`}>
                  <div className="san-graph__bars">
                    <div className="san-graph__bar san-graph__bar--you" style={{ height: `${(d.user_msgs / max) * 100}%` }} />
                    <div className="san-graph__bar san-graph__bar--aura" style={{ height: `${(d.facts_saved / max) * 100}%` }} />
                  </div>
                  <span className="san-graph__label">{d.date.slice(8)}</span>
                </div>
              ))}
            </div>
            <div className="san-graph__legend">
              <span><i className="san-graph__dot san-graph__dot--you" /> you talked</span>
              <span><i className="san-graph__dot san-graph__dot--aura" /> AURA saved</span>
            </div>
            {stats && (
              <div className="san-memtotals">
                {stats.totals.user_messages} messages · {stats.totals.facts} memories ·{" "}
                {stats.totals.knowledge} notes · {stats.totals.tasks} tasks
              </div>
            )}
          </>
        );
      }

      case "music":
        return (
          <div className="san-music">
            <div className="san-music__art" />
            <div className="san-music__meta">
              <div className="san-music__song">Night Drive</div>
              <div className="san-music__artist">Lo-fi Chill</div>
              <div className={"san-eq" + (playing ? " san-eq--on" : "")}>
                <span /><span /><span /><span /><span /><span /><span /><span />
              </div>
            </div>
            <div className="san-music__controls">
              <button>{"⏮"}</button>
              <button className="san-music__play" onClick={() => setPlaying((p) => !p)}>
                {playing ? "⏸" : "▶"}
              </button>
              <button>{"⏭"}</button>
            </div>
          </div>
        );

      case "domain": {
        const pendingTasks = tasks.filter((t) => t.status !== "done").length;
        return (
          <>
            <p className="san-muted">Your AI workspace. Everything begins here.</p>

            {/* live pulse of the workspace */}
            <div className="san-domstats">
              <div className="san-domstat">
                <span className="san-domstat__num">{domProjects.length}</span>
                <span className="san-domstat__label">projects</span>
              </div>
              <div className="san-domstat">
                <span className="san-domstat__num">{domInFlight}</span>
                <span className="san-domstat__label">in flight</span>
              </div>
              <div className="san-domstat">
                <span className="san-domstat__num">{pendingTasks}</span>
                <span className="san-domstat__label">tasks open</span>
              </div>
              <div className="san-domstat">
                <span className="san-domstat__num">{stats ? stats.totals.facts : "–"}</span>
                <span className="san-domstat__label">memories</span>
              </div>
            </div>

            <button className="san-primarybtn san-domain__enter" onClick={onEnterDomain}>Enter Workspace →</button>

            {/* continue where you left off */}
            {domActive && (
              <button className="san-domcontinue" onClick={() => jumpInto("projects")}>
                <span className="san-domcontinue__dot" style={{ background: domActive.accent, boxShadow: `0 0 8px ${domActive.accent}` }} />
                <span className="san-domcontinue__text">
                  Continue <b>{domActive.name}</b>
                </span>
                <span className="san-domcontinue__pct">{domDonePct}%</span>
                <span className="san-domcontinue__bar">
                  <i style={{ width: `${domDonePct}%`, background: `linear-gradient(90deg, ${domActive.accent}, var(--cyan))` }} />
                </span>
              </button>
            )}

            <div className="san-shortcuts">
              {([
                ["⚒", "Build", "code"],
                ["◎", "Research", "research"],
                ["☑", "Tasks", "tasks"],
                ["✦", "Create", "images"],
              ] as [string, string, DomainSection][]).map(([ic, lb, sec]) => (
                <button key={lb} className="san-shortcut" onClick={() => jumpInto(sec)}>
                  <span className="san-shortcut__icon">{ic}</span>
                  <span>{lb}</span>
                </button>
              ))}
            </div>
          </>
        );
      }

      case "links": {
        const q = linkSearch.trim().toLowerCase();
        const filtered = q
          ? links.filter((l) => l.name.toLowerCase().includes(q) || l.url.toLowerCase().includes(q))
          : links;
        return (
          <>
            {/* hover the card → the ✎ appears; click → edit mode */}
            <button
              className={"san-linkedit" + (linksEdit ? " san-linkedit--on" : "")}
              title={linksEdit ? "Done editing" : "Edit shortcuts"}
              onClick={() => setLinksEdit((v) => !v)}
            >
              {linksEdit ? "✓" : "✎"}
            </button>

            {links.length > 0 && (
              <div className="san-linksearch">
                <span className="san-linksearch__icon">◌</span>
                <input
                  value={linkSearch}
                  onChange={(e) => setLinkSearch(e.target.value)}
                  placeholder="Search shortcuts…"
                />
                {linkSearch && (
                  <button className="san-linksearch__clear" onClick={() => setLinkSearch("")}>✕</button>
                )}
              </div>
            )}

            {links.length === 0 ? (
              <div className="san-linkempty">
                <span className="san-linkempty__icon">↗</span>
                <p>{offline ? "Brain offline — start server.py" : "Nothing saved yet."}</p>
                {!offline && !linksEdit && (
                  <button className="san-linkempty__add" onClick={() => setLinksEdit(true)}>
                    + Add a shortcut
                  </button>
                )}
              </div>
            ) : filtered.length === 0 ? (
              <div className="san-list__empty">No match for “{linkSearch}”.</div>
            ) : (
              <div className="san-linkgrid">
              {filtered.map((l) => (
                <div key={l.id} className="san-tile" title={l.url}>
                  <button className="san-tile__open" onClick={() => window.open(l.url, "_blank")}>
                    {favicon(l.url) ? (
                      <img className="san-tile__ico" src={favicon(l.url)} alt="" />
                    ) : (
                      <span className="san-tile__ico san-tile__ico--fallback">↗</span>
                    )}
                    {renamingLink === l.id ? (
                      <input
                        className="san-editinput san-tile__rename"
                        autoFocus
                        value={renameText}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setRenameText(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename();
                          if (e.key === "Escape") setRenamingLink(null);
                        }}
                      />
                    ) : (
                      <span className="san-tile__name">{l.name}</span>
                    )}
                  </button>
                  {linksEdit && (
                    <span className="san-tile__tools san-tile__tools--edit">
                      <button
                        title="Rename"
                        onClick={() => { setRenamingLink(l.id); setRenameText(l.name); }}
                      >
                        ✎
                      </button>
                      <button title="Delete" onClick={() => removeLink(l.id)}>✕</button>
                    </span>
                  )}
                </div>
              ))}
            </div>
            )}
            {linksEdit && (
            <form className="san-quickadd san-quickadd--links" onSubmit={addLink}>
              <input
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                placeholder="Paste a URL…"
              />
              <input
                className="san-quickadd__name"
                value={linkName}
                onChange={(e) => setLinkName(e.target.value)}
                placeholder="Name (optional)"
              />
              <button type="submit">+</button>
            </form>
            )}
          </>
        );
      }

      case "portfolio":
        return (
          <>
            <p className="san-muted">Your work. Your story.</p>
            <button className="san-primarybtn" onClick={() => window.open(PORTFOLIO_URL, "_blank")}>
              View Website ↗
            </button>
          </>
        );

      case "settings":
        // A menu, not a wall of sliders. Each row opens its own focused
        // editing area (SettingsOverlay) — edit, save, return.
        return (
          <>
            {(Object.keys(CATEGORY_META) as SettingsCategory[]).map((cat) => (
              <button
                key={cat}
                className="san-setopt"
                onClick={() => setSettingsFocus(cat)}
                disabled={!settings && cat !== "layout"}
              >
                <span className="san-setopt__icon">{CATEGORY_META[cat].icon}</span>
                <span className="san-setopt__meta">
                  <span className="san-setopt__name">{CATEGORY_META[cat].title}</span>
                  <span className="san-setopt__desc">{CATEGORY_META[cat].desc}</span>
                </span>
                <span className="san-setopt__go">→</span>
              </button>
            ))}
            {!settings && offline && (
              <div className="san-list__empty">Brain offline — visual settings need server.py</div>
            )}
          </>
        );

      default:
        return null;
    }
  };

  // ---- card shell ----------------------------------------------------------
  const card = (id: string) => {
    if (layout.hidden.includes(id)) return null;
    const delay = 90 * Math.max(0, REVEAL_ORDER.indexOf(id));
    const tall = layout.sizes[id] === "tall";
    return (
      <div
        key={id}
        ref={(el) => { cardRefs.current[id] = el; }}
        className={
          "sancard" +
          (id === "domain" ? " sancard--domain" : "") +
          (tall ? " sancard--tall" : "") +
          (revealed ? " sancard--enter" : "")
        }
        style={{ animationDelay: `${delay}ms` }}
        draggable
        onDragStart={(e) => {
          dragId.current = id;
          e.dataTransfer.effectAllowed = "move";
          requestAnimationFrame(() => cardRefs.current[id]?.classList.add("sancard--dragging"));
        }}
        onDragEnd={() => {
          cardRefs.current[id]?.classList.remove("sancard--dragging");
          dragId.current = null;
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation(); // don't let the column also claim this drop
          if (dragId.current) placeCard(dragId.current, { card: id });
        }}
      >
        <div className="sancard__head">
          <span className="sancard__title">{TITLES[id]}</span>
          {custom && (
            <span className="sancard__tools">
              <button title="Resize" onClick={() => cycleSize(id)}>{tall ? "▭" : "▯"}</button>
              {id !== "settings" && <button title="Hide" onClick={() => hideCard(id)}>{"✕"}</button>}
            </span>
          )}
        </div>
        {body(id)}
      </div>
    );
  };

  return (
    <div className={"sanctuary" + (layout.preset === "compact" ? " sanctuary--compact" : "")}>
      <FloatingParticles />
      <div className="san-beamglow" aria-hidden="true" />

      <header className="sanctuary__top">
        <div className="sanctuary__brand">
          <span className="brand__mark" />
          <span className="sanctuary__logo">AURA</span>
        </div>
        <div className="sanctuary__greet">
          <h1>{greeting}, {USER}</h1>
          <p>Welcome back to your sanctuary</p>
        </div>
        <div className="sanctuary__actions">
          <button title="Search">{"🔍"}</button>
          <button title="Notifications">{"🔔"}</button>
          <button className="sanctuary__profile" title="Profile">S</button>
        </div>
      </header>

      {revealed ? (
        <div className="sanctuary__grid">
          {(["left", "center", "right"] as ColId[]).map((c) => (
            <div
              key={c}
              className={"sanctuary__col" + (c === "center" ? " sanctuary__col--center" : "")}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (dragId.current) placeCard(dragId.current, { col: c });
              }}
            >
              {layout.cols[c].map(card)}
            </div>
          ))}
        </div>
      ) : (
        <div className="sanctuary__void" />
      )}

      {/* focused settings editor — edit, save, and you're back right here */}
      {settingsFocus && settings && (
        <SettingsOverlay
          category={settingsFocus}
          settings={settings}
          layout={layout}
          onSaveSettings={(patch) => {
            setSettings((s) => (s ? { ...s, ...patch } : s));
            api.saveSettings(patch).catch(() => setOffline(true));
          }}
          onSaveLayout={(l) => setLayout(l)}
          onClose={() => setSettingsFocus(null)}
        />
      )}
      {settingsFocus === "layout" && !settings && (
        <SettingsOverlay
          category="layout"
          settings={{}}
          layout={layout}
          onSaveSettings={() => {}}
          onSaveLayout={(l) => setLayout(l)}
          onClose={() => setSettingsFocus(null)}
        />
      )}
    </div>
  );
}
