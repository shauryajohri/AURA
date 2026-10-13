import { create } from "zustand";
import { api, type Settings } from "../api";
import { useCoreStore } from "./coreStore";
import { usePlanetStore } from "./planetStore";
import { SKIN_KEYS } from "../skins/skins";

/**
 * Bridge between the backend `app_settings` table and the visuals.
 *
 * The Sanctuary settings card has been writing blackhole.* / planets.* /
 * voice.* / autochat.* to /api/settings since it was built, but nothing ever
 * read those values back — the black hole and planets took their numbers from
 * coreStore/planetStore, which are localStorage-only. So the sliders saved
 * happily and changed nothing. This store closes that loop.
 *
 * Direction of truth: the backend is authoritative at boot (it's the shared,
 * persisted copy), and any later edit writes through to it immediately so the
 * two never drift.
 *
 * Note on the visual stores: their own `set` actions are gated behind edit
 * mode (the top-bar Core/Planets menus). Applying settings uses `setState`
 * directly, which is the intended escape hatch for programmatic updates.
 */

const DEFAULTS: Settings = {
  "blackhole.glow": 70,
  "blackhole.particles": 60,
  "blackhole.rotation": 50,
  "planets.orbit_speed": 50,
  "planets.rings": true,
  "planets.labels": true,
  "orbits.opacity": 55,
  "orbits.width": 50,
  "orbits.style": "dashed",
  "voice.enabled": true,
  // "" = no explicit choice; the backend picks (see voice_output.resolve_voice).
  "voice.name": "",
  "voice.rate": 55,
  "voice.sensitivity": 55,
  "voice.wake_word": true,
  "voice.noise_suppression": true,
  "autochat.enabled": true,
  "autochat.frequency": 40,
  // Phone report — AURA rings you with a spoken progress report
  "phone.enabled": false,
  "phone.number": "",
  "phone.daily": true,
  "phone.daily_time": "09:00",
  "phone.milestones": true,
  "phone.meeting_alert": false,
  "phone.meeting_lead": 15,
  "phone.quiet_start": "22:00",
  "phone.quiet_end": "08:00",
  // Relationship — who AURA is to you (core/persona.py)
  "persona.mode": "buddy",
  "persona.user_name": "",
  "persona.custom": "",
  // General / Appearance
  "general.start_minimized": false,
  "general.launch_on_boot": false,
  "buddy.enabled": true,
  "anim.enabled": true,
  "anim.intensity": 70,
  "anim.reduced_motion": false,
  "wallpaper.video": true,
  "wallpaper.dim": 30,
  // Privacy & behaviour
  "privacy.screen_reading": true,
  "privacy.store_conversations": true,
  "habits.enabled": true,
  "habits.ignore": [],
  "behavior.proactive": true,
  "behavior.interrupt_work": false,
  "agent.enabled": true,
  "agent.confirm_all": false,
  // Developer / experimental
  "dev.verbose_logs": false,
  "dev.show_intents": false,
  "experimental.plugins": false,
  "experimental.cloud_sync": false,
  // Skins (src/skins). Core/backdrop "" = wear the skin's own choice.
  "skin.id": "aura",
  "skin.core": "",
  "skin.backdrop": "",
};

/** A raw /api/settings response with any key the backend doesn't know yet
 *  filled from DEFAULTS. SettingsOverlay picks each row's control by the
 *  value's type, so a missing boolean would otherwise draw as a slider. */
export const withDefaults = (s: Settings): Settings => ({ ...DEFAULTS, ...s });

// The skin is also cached locally: the backend answers a beat after first
// paint, and without this every launch would flash the default violet world
// before switching to the one the user picked. Works with the brain offline.
const SKIN_CACHE = "aura.skin";

function readSkinCache(): Settings {
  try {
    const raw = JSON.parse(localStorage.getItem(SKIN_CACHE) || "{}") as Settings;
    const out: Settings = {};
    for (const k of SKIN_KEYS) if (typeof raw[k] === "string") out[k] = raw[k];
    return out;
  } catch {
    return {};
  }
}

function writeSkinCache(s: Settings) {
  const out: Settings = {};
  for (const k of SKIN_KEYS) if (k in s) out[k] = s[k];
  try {
    localStorage.setItem(SKIN_CACHE, JSON.stringify(out));
  } catch {
    /* ignore quota errors */
  }
}

const INITIAL: Settings = withDefaults(readSkinCache());

const num = (s: Settings, k: string, fallback: number): number => {
  const v = s[k];
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
};
const bool = (s: Settings, k: string, fallback: boolean): boolean => {
  const v = s[k];
  return typeof v === "boolean" ? v : fallback;
};
const str = (s: Settings, k: string, fallback: string): string => {
  const v = s[k];
  return typeof v === "string" ? v : fallback;
};

export type OrbitStyle = "dashed" | "solid" | "dotted" | "hidden";
const ORBIT_STYLES: OrbitStyle[] = ["dashed", "solid", "dotted", "hidden"];

interface SettingsStore {
  settings: Settings;
  loaded: boolean;
  offline: boolean;

  /** Particle-density multiplier for the accretion disk (0.15–1.6). */
  density: number;
  /** Disk rotation multiplier (0.2–2.0). */
  rotationMul: number;
  /** Whether planets show their name/role labels. */
  showLabels: boolean;
  /** Orbit-line brightness multiplier (0–2.5; 1 at the default slider). */
  orbitMul: number;
  /** Orbit-line width multiplier (0.4–2.5). */
  orbitWidthMul: number;
  /** How orbit lines are drawn. "hidden" removes them (edit mode still shows slots). */
  orbitStyle: OrbitStyle;
  /**
   * Unsaved skin keys being tried on (the skin gallery). Visuals render
   * `{...settings, ...skinPreview}`; null when nothing is being previewed.
   */
  skinPreview: Settings | null;

  load: () => Promise<void>;
  /** Save a partial change AND apply it to the visuals immediately. */
  apply: (patch: Settings) => Promise<void>;
  setSkinPreview: (p: Settings | null) => void;
}

// 0–100 slider → a multiplier centred on 1.0 at the default value.
const toMul = (pct: number, min: number, max: number, mid: number) =>
  pct <= mid
    ? min + ((pct - 0) / (mid - 0)) * (1 - min)
    : 1 + ((pct - mid) / (100 - mid)) * (max - 1);

function derive(s: Settings) {
  const style = str(s, "orbits.style", "dashed") as OrbitStyle;
  return {
    density: toMul(num(s, "blackhole.particles", 60), 0.15, 1.6, 60),
    rotationMul: toMul(num(s, "blackhole.rotation", 50), 0.2, 2.0, 50),
    showLabels: bool(s, "planets.labels", true),
    orbitMul: toMul(num(s, "orbits.opacity", 55), 0, 2.5, 55),
    orbitWidthMul: toMul(num(s, "orbits.width", 50), 0.4, 2.5, 50),
    orbitStyle: ORBIT_STYLES.includes(style) ? style : "dashed",
  };
}

/** Push the settings that the existing visual stores already understand. */
function pushToVisualStores(s: Settings) {
  // Glow: backend 0–100 maps straight onto coreStore's glow percentage.
  useCoreStore.setState({ glow: num(s, "blackhole.glow", 70) });

  // Orbit speed: planetStore.speed is a percentage where 100 = spec speed and
  // the slider allows 25–300. The backend's 0–100 is a friendlier scale, so
  // 50 (its default) should land on 100 (unchanged).
  usePlanetStore.setState({ speed: Math.round(num(s, "planets.orbit_speed", 50) * 2) });

  // Rings off = collapse ring size to zero rather than branching the renderer.
  usePlanetStore.setState({ rings: bool(s, "planets.rings", true) ? 100 : 0 });
}

/** Tell Electron whether the desktop buddy may appear (a no-op in a browser).
 *  Only sent for a value the user really holds — a successful load or an
 *  edit — never the defaults an offline boot falls back to, so main.cjs's own
 *  copy of the last choice stands until the brain answers. */
function pushToBuddy(s: Settings) {
  window.aura?.buddy?.setEnabled(bool(s, "buddy.enabled", true));
}

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  settings: INITIAL,
  loaded: false,
  offline: false,
  skinPreview: null,
  ...derive(INITIAL),

  load: async () => {
    try {
      const s = await api.getSettings();
      // A skin chosen while the brain was offline only exists in the cache;
      // the backend copy wins only for keys it has actually stored.
      const merged = withDefaults({ ...readSkinCache(), ...s });
      pushToVisualStores(merged);
      pushToBuddy(merged);
      writeSkinCache(merged);
      set({ settings: merged, loaded: true, offline: false, ...derive(merged) });
    } catch {
      // Brain offline — keep the defaults so the visuals still render.
      set({ loaded: true, offline: true });
    }
  },

  apply: async (patch) => {
    const merged = { ...get().settings, ...patch };
    // Apply first so the UI responds instantly, then persist.
    pushToVisualStores(merged);
    if ("buddy.enabled" in patch) pushToBuddy(merged);
    writeSkinCache(merged);
    set({ settings: merged, ...derive(merged) });
    try {
      await api.saveSettings(patch);
    } catch {
      set({ offline: true });
    }
  },

  setSkinPreview: (p) => set({ skinPreview: p }),
}));
