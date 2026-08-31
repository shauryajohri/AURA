import { useMemo, useState } from "react";
import { api, Settings } from "../../api";
import { Layout, ColId, Size, CARD_TITLES, DEFAULT_LAYOUT } from "./layoutTypes";
import MicCheck from "../MicCheck";
import VoicePicker from "./VoicePicker";

// ============================================================================
// Focused settings editors. Clicking "Blackhole" in the settings card doesn't
// open a giant tab — it takes you INTO the blackhole area: a full-screen
// focused editor with a live preview. Edit → Save → you're back exactly
// where you were (the sanctuary never unmounts underneath).
//
// Everything edits a DRAFT: Save commits, ✕/Cancel discards.
// ============================================================================

export type SettingsCategory =
  | "general" | "blackhole" | "planets" | "orbits" | "animations" | "wallpaper"
  | "voice" | "autochat" | "privacy" | "behavior" | "keys" | "developer"
  | "experimental" | "layout";

export const CATEGORY_META: Record<SettingsCategory, { icon: string; title: string; desc: string }> = {
  general: { icon: "▣", title: "General", desc: "Startup and window behaviour" },
  blackhole: { icon: "◉", title: "Blackhole", desc: "The core — glow, particles, rotation" },
  planets: { icon: "◍", title: "Planets", desc: "The constellation — orbits, rings, labels" },
  orbits: { icon: "◌", title: "Orbit Lines", desc: "The rings around the core — style, brightness, width" },
  animations: { icon: "≈", title: "Animations", desc: "Motion intensity across the whole OS" },
  wallpaper: { icon: "❖", title: "Wallpaper", desc: "The living cosmos behind everything" },
  voice: { icon: "♪", title: "Voice", desc: "Which voice she speaks with, plus mic and wake word" },
  autochat: { icon: "✦", title: "Auto-chat", desc: "How chatty AURA is on her own" },
  privacy: { icon: "⛨", title: "Privacy", desc: "What AURA may see and store" },
  behavior: { icon: "◎", title: "Behavior", desc: "When she speaks up, when she stays quiet" },
  keys: { icon: "⚿", title: "API Keys", desc: "Which providers are connected" },
  developer: { icon: "⌥", title: "Developer", desc: "Logs, intents, diagnostics" },
  experimental: { icon: "⚗", title: "Experimental", desc: "Unfinished features — here be dragons" },
  layout: { icon: "▦", title: "Layout", desc: "Size & position of your sanctuary cards" },
};

const KEYS: Record<Exclude<SettingsCategory, "layout" | "keys">, string[]> = {
  general: ["general.launch_on_boot", "general.start_minimized"],
  blackhole: ["blackhole.glow", "blackhole.particles", "blackhole.rotation"],
  planets: ["planets.orbit_speed", "planets.rings", "planets.labels"],
  orbits: ["orbits.style", "orbits.opacity", "orbits.width"],
  animations: ["anim.enabled", "anim.intensity", "anim.reduced_motion"],
  wallpaper: ["wallpaper.video", "wallpaper.dim"],
  // voice.name is edited by VoicePicker rather than by the generic control
  // rows, but it must be listed here or save() would never put it in the patch.
  voice: ["voice.enabled", "voice.name", "voice.rate", "voice.sensitivity",
          "voice.wake_word", "voice.noise_suppression"],
  autochat: ["autochat.enabled", "autochat.frequency"],
  privacy: ["privacy.screen_reading", "privacy.store_conversations"],
  behavior: ["behavior.proactive", "behavior.interrupt_work"],
  developer: ["dev.verbose_logs", "dev.show_intents"],
  experimental: ["experimental.plugins", "experimental.cloud_sync"],
};

// Providers AURA can talk to. Keys live in .env on the machine — this panel
// only reports what's wired, it never displays or edits secrets.
const PROVIDERS = [
  { name: "Groq", env: "GROQ_API_KEY", note: "GPT-OSS 120B / 20B — the always-on fallback" },
  { name: "OpenRouter", env: "OPENROUTER_API_KEY", note: "Laguna, Nemotron, Gemma" },
  { name: "OpenAI", env: "OPENAI_API_KEY", note: "GPT-4o" },
  { name: "Anthropic", env: "ANTHROPIC_API_KEY", note: "Claude 3.5" },
  { name: "Google", env: "GOOGLE_API_KEY", note: "Gemini 1.5 Pro" },
  { name: "xAI", env: "XAI_API_KEY", note: "Grok 2" },
];

const ORBIT_STYLES = ["dashed", "solid", "dotted", "hidden"] as const;

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

  const set = (k: string, v: number | boolean | string) => {
    setDraft((d) => ({ ...d, [k]: v }));
    setDirty(true);
  };

  const save = () => {
    if (category === "layout") {
      onSaveLayout({ ...layoutDraft, preset: "custom" });
    } else if (category !== "keys") {
      // "keys" is read-only (secrets live in .env) — nothing to persist.
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
      case "orbits": {
        const style = String(draft["orbits.style"] ?? "dashed");
        const op = n("orbits.opacity", 55) / 100;
        const wd = 0.4 + (n("orbits.width", 50) / 100) * 2.1;
        const dash =
          style === "dashed" ? "6, 9" : style === "dotted" ? "1.5, 7" : "none";
        return (
          <div className="setov__stage">
            <svg viewBox="0 0 260 200" className="setov__orbitsvg" aria-hidden="true">
              <circle cx="130" cy="100" r="20" fill="#000" stroke="rgba(243,217,255,0.9)" strokeWidth="1.6" />
              {style !== "hidden" &&
                [38, 58, 78, 96].map((r, i) => (
                  <circle
                    key={r}
                    cx="130" cy="100" r={r}
                    fill="none"
                    stroke={`rgba(167,109,255,${Math.max(0.05, (0.5 - i * 0.08) * op * 1.8)})`}
                    strokeWidth={wd}
                    strokeDasharray={dash === "none" ? undefined : dash}
                  />
                ))}
              {style === "hidden" && (
                <text x="130" y="165" textAnchor="middle" fill="rgba(139,143,202,0.9)" fontSize="10">
                  orbit lines hidden — planets still orbit
                </text>
              )}
              <circle cx="188" cy="100" r="5" fill="#6C6BFF" />
              <circle cx="130" cy="42" r="4" fill="#38E1FF" />
            </svg>
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
      case "keys":
        return (
          <div className="setov__stage setov__stage--short">
            <div className="keys">
              {PROVIDERS.map((p) => (
                <div key={p.env} className="keys__row">
                  <span className="keys__name">{p.name}</span>
                  <code className="keys__env">{p.env}</code>
                  <span className="keys__note">{p.note}</span>
                </div>
              ))}
            </div>
            <p className="setov__hint">
              Keys are read from <code>.env</code> next to server.py — AURA never
              shows or stores them in the interface. Add a key there and restart
              the brain to light up that provider.
            </p>
          </div>
        );
      case "general":
      case "animations":
      case "wallpaper":
      case "privacy":
      case "behavior":
      case "developer":
      case "experimental":
        return (
          <div className="setov__stage setov__stage--short">
            <div className="setov__genicon">{meta.icon}</div>
            <p className="setov__hint">{meta.desc}</p>
          </div>
        );
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
    if (category === "keys") return null;
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
        {KEYS[category].filter((k) => k !== "voice.name").map((k) => {
          const v = draft[k];
          return (
            <div key={k} className="setov__row">
              <span className="setov__label">{label(k)}</span>
              {k === "orbits.style" ? (
                <span className="setov__stylepick">
                  {ORBIT_STYLES.map((st) => (
                    <button
                      key={st}
                      className={"setov__stylebtn" + (String(v ?? "dashed") === st ? " setov__stylebtn--on" : "")}
                      onClick={() => set(k, st)}
                    >
                      {st}
                    </button>
                  ))}
                </span>
              ) : typeof v === "boolean" ? (
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
        {category === "voice" && (
          <VoicePicker
            value={String(draft["voice.name"] ?? "")}
            onChange={(id) => set("voice.name", id)}
          />
        )}
        {controls()}
        {/* Privacy is also where you wipe the record. It's an action, not a
            setting, so it lives outside the draft/save flow. */}
        {category === "privacy" && <ClearHistory />}
        {/* Output above (how AURA speaks), input below (how she hears you).
            Not part of the draft — it touches hardware, not settings. */}
        {category === "voice" && <MicCheck />}

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

// ── Clear chat history ──────────────────────────────────────────────────────
// Deletes every chat and message across every room. Rooms themselves stay —
// they hold the briefs you set up, and an empty room is still a place to
// begin again. Two-step (button → confirm) because it can't be undone, then a
// reload so nothing in the app is left holding a chat id that no longer exists.
function ClearHistory() {
  const [phase, setPhase] = useState<"idle" | "confirm" | "working" | "done" | "error">("idle");
  const [removed, setRemoved] = useState<{ messages: number; chats: number } | null>(null);

  const run = async () => {
    setPhase("working");
    try {
      const r = await api.clearAllChats();
      setRemoved(r.removed);
      setPhase("done");
      window.setTimeout(() => window.location.reload(), 1400);
    } catch {
      setPhase("error");
    }
  };

  return (
    <div className="setov__danger">
      <div className="setov__dangerinfo">
        <span className="setov__label">Clear chat history</span>
        <p className="setov__hint">
          Permanently deletes every chat and message in every room. The rooms
          stay, just empty. This cannot be undone.
        </p>
      </div>

      {phase === "idle" && (
        <button className="setov__dangerbtn" onClick={() => setPhase("confirm")}>
          Clear history…
        </button>
      )}
      {phase === "confirm" && (
        <div className="setov__dangerrow">
          <span className="setov__hint">Delete everything?</span>
          <button className="setov__cancel" onClick={() => setPhase("idle")}>Keep it</button>
          <button className="setov__dangerbtn" onClick={run}>Delete all</button>
        </div>
      )}
      {phase === "working" && <span className="setov__hint">Clearing…</span>}
      {phase === "done" && (
        <span className="setov__hint">
          Cleared {removed?.messages ?? 0} messages across {removed?.chats ?? 0} chats. Reloading…
        </span>
      )}
      {phase === "error" && (
        <div className="setov__dangerrow">
          <span className="setov__hint">Couldn't reach the brain — is server.py running?</span>
          <button className="setov__cancel" onClick={() => setPhase("idle")}>Back</button>
        </div>
      )}
    </div>
  );
}
