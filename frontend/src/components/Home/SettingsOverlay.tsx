import { useMemo, useState } from "react";
import { Settings } from "../../api";
import { Layout, ColId, Size, CARD_TITLES, DEFAULT_LAYOUT } from "./layoutTypes";

// ============================================================================
// Focused settings editors. Clicking "Blackhole" in the settings card doesn't
// open a giant tab — it takes you INTO the blackhole area: a full-screen
// focused editor with a live preview. Edit → Save → you're back exactly
// where you were (the sanctuary never unmounts underneath).
//
// Everything edits a DRAFT: Save commits, ✕/Cancel discards.
// ============================================================================

export type SettingsCategory = "blackhole" | "planets" | "voice" | "autochat" | "layout";

export const CATEGORY_META: Record<SettingsCategory, { icon: string; title: string; desc: string }> = {
  blackhole: { icon: "◉", title: "Blackhole", desc: "The core — glow, particles, rotation" },
  planets: { icon: "◍", title: "Planets", desc: "The constellation — orbits, rings, labels" },
  voice: { icon: "♪", title: "Voice", desc: "How AURA speaks" },
  autochat: { icon: "✦", title: "Auto-chat", desc: "How chatty AURA is on her own" },
  layout: { icon: "▦", title: "Layout", desc: "Size & position of your sanctuary cards" },
};

const KEYS: Record<Exclude<SettingsCategory, "layout">, string[]> = {
  blackhole: ["blackhole.glow", "blackhole.particles", "blackhole.rotation"],
  planets: ["planets.orbit_speed", "planets.rings", "planets.labels"],
  voice: ["voice.enabled", "voice.rate"],
  autochat: ["autochat.enabled", "autochat.frequency"],
};

interface Props {
  category: SettingsCategory;
  settings: Settings;
  layout: Layout;
  onSaveSettings: (patch: Settings) => void;
  onSaveLayout: (l: Layout) => void;
  onClose: () => void;
}

export default function SettingsOverlay({
  category, settings, layout, onSaveSettings, onSaveLayout, onClose,
}: Props) {
  const meta = CATEGORY_META[category];

  // ---- drafts --------------------------------------------------------------
  const [draft, setDraft] = useState<Settings>(() => ({ ...settings }));
  const [layoutDraft, setLayoutDraft] = useState<Layout>(() => ({
    cols: { left: [...layout.cols.left], center: [...layout.cols.center], right: [...layout.cols.right] },
    hidden: [...layout.hidden],
    sizes: { ...layout.sizes },
    preset: layout.preset,
  }));
  const [dirty, setDirty] = useState(false);

  const set = (k: string, v: number | boolean) => {
    setDraft((d) => ({ ...d, [k]: v }));
    setDirty(true);
  };

  const save = () => {
    if (category === "layout") {
      onSaveLayout({ ...layoutDraft, preset: "custom" });
    } else {
      const patch: Settings = {};
      for (const k of KEYS[category]) {
        if (draft[k] !== settings[k]) patch[k] = draft[k];
      }
      if (Object.keys(patch).length) onSaveSettings(patch);
    }
    onClose();
  };

  // ---- layout draft helpers ------------------------------------------------
  const allCards = Object.keys(CARD_TITLES);
  const colOf = (id: string): ColId | null => {
    for (const c of ["left", "center", "right"] as ColId[]) {
      if (layoutDraft.cols[c].includes(id)) return c;
    }
    return null;
  };
  const moveToCol = (id: string, col: ColId) => {
    setLayoutDraft((l) => {
      const cols: Record<ColId, string[]> = {
        left: l.cols.left.filter((x) => x !== id),
        center: l.cols.center.filter((x) => x !== id),
        right: l.cols.right.filter((x) => x !== id),
      };
      cols[col] = [...cols[col], id];
      return { ...l, cols, hidden: l.hidden.filter((h) => h !== id) };
    });
    setDirty(true);
  };
  const nudge = (id: string, dir: -1 | 1) => {
    setLayoutDraft((l) => {
      const col = (["left", "center", "right"] as ColId[]).find((c) => l.cols[c].includes(id));
      if (!col) return l;
      const arr = [...l.cols[col]];
      const i = arr.indexOf(id);
      const j = i + dir;
      if (j < 0 || j >= arr.length) return l;
      [arr[i], arr[j]] = [arr[j], arr[i]];
      return { ...l, cols: { ...l.cols, [col]: arr } };
    });
    setDirty(true);
  };
  const cycleSize = (id: string) => {
    setLayoutDraft((l) => ({
      ...l,
      sizes: { ...l.sizes, [id]: (l.sizes[id] === "tall" ? "normal" : "tall") as Size },
    }));
    setDirty(true);
  };
  const toggleHidden = (id: string) => {
    setLayoutDraft((l) =>
      l.hidden.includes(id)
        ? { ...l, hidden: l.hidden.filter((h) => h !== id), cols: { ...l.cols, right: [...l.cols.right, id] } }
        : {
            ...l,
            hidden: [...l.hidden, id],
            cols: {
              left: l.cols.left.filter((x) => x !== id),
              center: l.cols.center.filter((x) => x !== id),
              right: l.cols.right.filter((x) => x !== id),
            },
          }
    );
    setDirty(true);
  };

  // ---- previews ------------------------------------------------------------
  const n = (k: string, fallback = 50) => Number(draft[k] ?? fallback);
  const b = (k: string) => Boolean(draft[k]);

  const particleDots = useMemo(
    () => Array.from({ length: 14 }, () => ({
      angle: Math.random() * 360,
      dist: 46 + Math.random() * 34,
      size: 1.5 + Math.random() * 2.5,
      dur: 5 + Math.random() * 6,
    })),
    []
  );

  const preview = () => {
    switch (category) {
      case "blackhole": {
        const glow = n("blackhole.glow") / 100;
        const density = Math.round((n("blackhole.particles") / 100) * particleDots.length);
        const spin = 24 - (n("blackhole.rotation") / 100) * 21; // 24s slow → 3s fast
        return (
          <div className="setov__stage">
            <div
              className="setov__bh"
              style={{
                boxShadow: `0 0 ${30 + glow * 90}px rgba(139,92,255,${0.25 + glow * 0.65}), 0 0 ${10 + glow * 30}px rgba(56,225,255,${0.1 + glow * 0.3})`,
              }}
            >
              <div className="setov__bhdisk" style={{ animationDuration: `${spin}s`, opacity: 0.5 + glow * 0.5 }} />
              <div className="setov__bhcore" />
            </div>
            {particleDots.slice(0, density).map((p, i) => (
              <span
                key={i}
                className="setov__bhparticle"
                style={{
                  ["--angle" as string]: `${p.angle}deg`,
                  ["--dist" as string]: `${p.dist}px`,
                  width: p.size, height: p.size,
                  animationDuration: `${p.dur}s`,
                }}
              />
            ))}
          </div>
        );
      }
      case "planets": {
        const dur = 26 - (n("planets.orbit_speed") / 100) * 22; // 26s → 4s
        const planets = [
          { name: "Laguna", color: "#6C6BFF", r: 52, ring: false },
          { name: "Claude", color: "#B18BFF", r: 78, ring: true },
          { name: "Nemotron", color: "#38E1FF", r: 104, ring: false },
        ];
        return (
          <div className="setov__stage">
            <div className="setov__sun" />
            {planets.map((p, i) => (
              <div
                key={p.name}
                className="setov__orbit"
                style={{ width: p.r * 2, height: p.r * 2, animationDuration: `${dur + i * 3}s` }}
              >
                <div className="setov__planetwrap">
                  <span className="setov__planet" style={{ background: p.color, boxShadow: `0 0 12px ${p.color}` }}>
                    {p.ring && b("planets.rings") && <i className="setov__ring" />}
                  </span>
                  {b("planets.labels") && <span className="setov__planetlabel">{p.name}</span>}
                </div>
              </div>
            ))}
          </div>
        );
      }
      case "voice": {
        const rate = n("voice.rate");
        return (
          <div className="setov__stage setov__stage--short">
            <div className={"setov__eq" + (b("voice.enabled") ? " setov__eq--on" : "")}
                 style={{ ["--eqdur" as string]: `${1.6 - (rate / 100) * 1.1}s` }}>
              {Array.from({ length: 12 }, (_, i) => <span key={i} style={{ animationDelay: `${i * 0.07}s` }} />)}
            </div>
            <p className="setov__hint">{b("voice.enabled") ? "AURA speaks at this pace." : "Voice is off — text only."}</p>
          </div>
        );
      }
      case "autochat": {
        const freq = n("autochat.frequency");
        return (
          <div className="setov__stage setov__stage--short">
            <div className={"setov__pulse" + (b("autochat.enabled") ? " setov__pulse--on" : "")}
                 style={{ ["--pulsedur" as string]: `${4.5 - (freq / 100) * 3.5}s` }} />
            <p className="setov__hint">
              {b("autochat.enabled")
                ? freq > 66 ? "AURA will speak up often." : freq > 33 ? "AURA chimes in now and then." : "AURA mostly stays quiet."
                : "AURA only speaks when spoken to."}
            </p>
          </div>
        );
      }
      case "layout":
        return (
          <div className="setov__minimap">
            {(["left", "center", "right"] as ColId[]).map((c) => (
              <div key={c} className="setov__minicol">
                {layoutDraft.cols[c].map((id) => (
                  <div
                    key={id}
                    className={"setov__minicard" + (layoutDraft.sizes[id] === "tall" ? " setov__minicard--tall" : "") + (id === "domain" ? " setov__minicard--hero" : "")}
                  >
                    {CARD_TITLES[id]}
                  </div>
                ))}
              </div>
            ))}
          </div>
        );
    }
  };

  // ---- controls ------------------------------------------------------------
  const label = (k: string) => k.split(".")[1].replace(/_/g, " ");

  const controls = () => {
    if (category === "layout") {
      return (
        <div className="setov__cards">
          {allCards.map((id) => {
            const hidden = layoutDraft.hidden.includes(id);
            const col = colOf(id);
            return (
              <div key={id} className={"setov__cardrow" + (hidden ? " setov__cardrow--hidden" : "")}>
                <span className="setov__cardname">{CARD_TITLES[id]}</span>
                {!hidden && col && (
                  <>
                    <span className="setov__colpick">
                      {(["left", "center", "right"] as ColId[]).map((c) => (
                        <button
                          key={c}
                          className={"setov__colbtn" + (col === c ? " setov__colbtn--on" : "")}
                          onClick={() => moveToCol(id, c)}
                          title={c}
                        >
                          {c === "left" ? "◧" : c === "center" ? "◫" : "◨"}
                        </button>
                      ))}
                    </span>
                    <button className="setov__mini" onClick={() => nudge(id, -1)} title="Move up">↑</button>
                    <button className="setov__mini" onClick={() => nudge(id, 1)} title="Move down">↓</button>
                    <button className="setov__mini" onClick={() => cycleSize(id)} title="Size">
                      {layoutDraft.sizes[id] === "tall" ? "▭" : "▯"}
                    </button>
                  </>
                )}
                {id !== "settings" && (
                  <button className="setov__mini" onClick={() => toggleHidden(id)} title={hidden ? "Show" : "Hide"}>
                    {hidden ? "＋" : "✕"}
                  </button>
                )}
              </div>
            );
          })}
          <button
            className="setov__resetbtn"
            onClick={() => { setLayoutDraft({ ...DEFAULT_LAYOUT }); setDirty(true); }}
          >
            Reset to default
          </button>
        </div>
      );
    }
    return (
      <div className="setov__controls">
        {KEYS[category].map((k) => {
          const v = draft[k];
          return (
            <div key={k} className="setov__row">
              <span className="setov__label">{label(k)}</span>
              {typeof v === "boolean" ? (
                <button className={"san-toggle" + (v ? " san-toggle--on" : "")} onClick={() => set(k, !v)}>
                  <span className="san-toggle__knob" />
                </button>
              ) : (
                <>
                  <input
                    className="san-slider setov__slider"
                    type="range" min={0} max={100}
                    value={Number(v) || 0}
                    onChange={(e) => set(k, Number(e.target.value))}
                  />
                  <span className="setov__val">{Number(v) || 0}</span>
                </>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="setov" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="setov__panel">
        <header className="setov__head">
          <span className="setov__icon">{meta.icon}</span>
          <div className="setov__titles">
            <h2>{meta.title}</h2>
            <p>{meta.desc}</p>
          </div>
          <button className="setov__close" onClick={onClose} title="Back without saving">✕</button>
        </header>

        {preview()}
        {controls()}

        <footer className="setov__foot">
          <button className="setov__cancel" onClick={onClose}>Cancel</button>
          <button className={"setov__save" + (dirty ? "" : " setov__save--idle")} onClick={save}>
            Save & return
          </button>
        </footer>
      </div>
    </div>
  );
}
