import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import { useClock } from "../../hooks/useClock";
import FloatingParticles from "./FloatingParticles";

// ============================================================================
// Section 3 — the Sanctuary. The environment arrives first; after a ~300ms
// breath, cards reveal one by one (Tasks → Memory → Music → Portfolio →
// Settings → Domain). Domain is the hero card. Beam stays visible through
// the center column gap. Drag to swap, presets, hide/resize in Custom.
// ============================================================================

const USER = "Shaurya";
const PORTFOLIO_URL = "https://shauryajohri.dev"; // ← your portfolio site

type ColId = "left" | "center" | "right";
type Preset = "default" | "compact" | "custom";
type Size = "normal" | "tall";

interface Layout {
  cols: Record<ColId, string[]>;
  hidden: string[];
  sizes: Record<string, Size>;
  preset: Preset;
}

const DEFAULT_LAYOUT: Layout = {
  cols: {
    left: ["tasks", "memory", "music"],
    center: ["domain"],
    right: ["portfolio", "settings"],
  },
  hidden: [],
  sizes: {},
  preset: "default",
};

const TITLES: Record<string, string> = {
  tasks: "Tasks", memory: "Memory", music: "Music",
  domain: "AURA Domain", portfolio: "Portfolio", settings: "Settings",
};

// reveal order per the spec (not render order)
const REVEAL_ORDER = ["tasks", "memory", "music", "portfolio", "settings", "domain"];

interface Props {
  entered: boolean; // journey reached the sanctuary
}

export default function SanctuarySection({ entered }: Props) {
  const { greeting } = useClock();
  const [layout, setLayout] = useLocalStorage<Layout>("aura.sanctuary", DEFAULT_LAYOUT);
  const [quickTasks, setQuickTasks] = useLocalStorage<string[]>("aura.sanctuary.tasks", []);
  const [taskInput, setTaskInput] = useState("");
  const [playing, setPlaying] = useState(false);
  const [revealed, setRevealed] = useState(false);

  // arrive → breathe (~300ms) → cards begin
  useEffect(() => {
    if (!entered) { setRevealed(false); return; }
    const t = setTimeout(() => setRevealed(true), 300);
    return () => clearTimeout(t);
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

  const swap = (a: string, b: string) => {
    if (a === b) return;
    captureRects();
    setLayout((l) => {
      const cols: Record<ColId, string[]> = {
        left: [...l.cols.left], center: [...l.cols.center], right: [...l.cols.right],
      };
      let pa: [ColId, number] | null = null, pb: [ColId, number] | null = null;
      (Object.keys(cols) as ColId[]).forEach((c) => {
        const ia = cols[c].indexOf(a), ib = cols[c].indexOf(b);
        if (ia >= 0) pa = [c, ia];
        if (ib >= 0) pb = [c, ib];
      });
      if (!pa || !pb) return l;
      const [ca, ia] = pa as [ColId, number];
      const [cb, ib] = pb as [ColId, number];
      cols[ca][ia] = b;
      cols[cb][ib] = a;
      return { ...l, cols };
    });
  };

  const applyPreset = (p: Preset) => {
    if (p === "custom") setLayout((l) => ({ ...l, preset: "custom" }));
    else setLayout({ ...DEFAULT_LAYOUT, preset: p });
  };
  const resetLayout = () => setLayout({ ...DEFAULT_LAYOUT, preset: layout.preset });

  const hideCard = (id: string) => {
    captureRects();
    setLayout((l) => ({ ...l, hidden: [...l.hidden, id] }));
  };
  const showCard = (id: string) =>
    setLayout((l) => ({ ...l, hidden: l.hidden.filter((h) => h !== id) }));
  const cycleSize = (id: string) => {
    captureRects();
    setLayout((l) => ({
      ...l,
      sizes: { ...l.sizes, [id]: l.sizes[id] === "tall" ? "normal" : "tall" },
    }));
  };

  const addTask = (e: React.FormEvent) => {
    e.preventDefault();
    const t = taskInput.trim();
    if (!t) return;
    setQuickTasks((q) => [...q, t]);
    setTaskInput("");
  };

  // ---- card bodies ---------------------------------------------------------
  const body = (id: string) => {
    switch (id) {
      case "tasks":
        return (
          <>
            <div className="sancard__section">Today</div>
            <ul className="san-list">
              {quickTasks.length === 0 && <li className="san-list__empty">Nothing yet — add one below.</li>}
              {quickTasks.map((t, i) => (
                <li key={i} className="san-list__item">
                  <span className="san-dot" /> {t}
                  <button className="san-x" onClick={() => setQuickTasks((q) => q.filter((_, j) => j !== i))}>
                    {"✕"}
                  </button>
                </li>
              ))}
            </ul>
            <div className="san-progress">
              <div className="san-progress__bar" style={{ width: quickTasks.length ? "38%" : "0%" }} />
            </div>
            <form className="san-quickadd" onSubmit={addTask}>
              <input value={taskInput} onChange={(e) => setTaskInput(e.target.value)} placeholder="Quick add..." />
              <button type="submit">+</button>
            </form>
          </>
        );
      case "memory":
        return (
          <>
            <ul className="san-list">
              <li className="san-list__item"><span className="san-dot" /> Restored memory/store.py</li>
              <li className="san-list__item"><span className="san-dot" /> Built the scroll journey</li>
              <li className="san-list__item"><span className="san-dot" /> Core design locked in</li>
            </ul>
            <div className="san-timeline"><span /><span /><span /><span /><span /></div>
            <button className="san-ghostbtn">Search memories</button>
          </>
        );
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
      case "domain":
        return (
          <>
            <p className="san-muted">Your AI workspace. Everything begins here.</p>
            <button className="san-primarybtn san-domain__enter">Enter Workspace →</button>
            <div className="san-shortcuts">
              {[["⚒", "Build"], ["◎", "Research"], ["⌗", "Debug"], ["✦", "Create"]].map(([ic, lb]) => (
                <button key={lb} className="san-shortcut">
                  <span className="san-shortcut__icon">{ic}</span>
                  <span>{lb}</span>
                </button>
              ))}
            </div>
          </>
        );
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
        return (
          <>
            <div className="san-chips">
              {["General", "Appearance", "Voice", "AI", "Privacy"].map((c) => (
                <span key={c} className="san-chip">{c}</span>
              ))}
            </div>
            <div className="sancard__section">Layout</div>
            <div className="san-presets">
              {(["default", "compact", "custom"] as Preset[]).map((pr) => (
                <button
                  key={pr}
                  className={"san-preset " + (layout.preset === pr ? "san-preset--on" : "")}
                  onClick={() => applyPreset(pr)}
                >
                  {pr[0].toUpperCase() + pr.slice(1)}
                </button>
              ))}
              <button className="san-preset" onClick={resetLayout}>Reset</button>
            </div>
            {custom && layout.hidden.length > 0 && (
              <>
                <div className="sancard__section">Hidden</div>
                <div className="san-chips">
                  {layout.hidden.map((h) => (
                    <button key={h} className="san-chip san-chip--btn" onClick={() => showCard(h)}>
                      {TITLES[h]} +
                    </button>
                  ))}
                </div>
              </>
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
          if (dragId.current) swap(dragId.current, id);
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
          <div className="sanctuary__col">{layout.cols.left.map(card)}</div>
          <div className="sanctuary__col sanctuary__col--center">{layout.cols.center.map(card)}</div>
          <div className="sanctuary__col">{layout.cols.right.map(card)}</div>
        </div>
      ) : (
        <div className="sanctuary__void" />
      )}
    </div>
  );
}
