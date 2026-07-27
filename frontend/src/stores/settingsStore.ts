import { create } from "zustand";
import { api, type Settings } from "../api";
import { useCoreStore } from "./coreStore";
import { usePlanetStore } from "./planetStore";

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
  "voice.enabled": true,
  "voice.rate": 55,
  "autochat.enabled": true,
  "autochat.frequency": 40,
};

const num = (s: Settings, k: string, fallback: number): number => {
  const v = s[k];
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
};
const bool = (s: Settings, k: string, fallback: boolean): boolean => {
  const v = s[k];
  return typeof v === "boolean" ? v : fallback;
};

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

  load: () => Promise<void>;
  /** Save a partial change AND apply it to the visuals immediately. */
  apply: (patch: Settings) => Promise<void>;
}

// 0–100 slider → a multiplier centred on 1.0 at the default value.
const toMul = (pct: number, min: number, max: number, mid: number) =>
  pct <= mid
    ? min + ((pct - 0) / (mid - 0)) * (1 - min)
    : 1 + ((pct - mid) / (100 - mid)) * (max - 1);

function derive(s: Settings) {
  return {
    density: toMul(num(s, "blackhole.particles", 60), 0.15, 1.6, 60),
    rotationMul: toMul(num(s, "blackhole.rotation", 50), 0.2, 2.0, 50),
    showLabels: bool(s, "planets.labels", true),
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

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  settings: { ...DEFAULTS },
  loaded: false,
  offline: false,
  ...derive(DEFAULTS),

  load: async () => {
    try {
      const s = await api.getSettings();
      const merged = { ...DEFAULTS, ...s };
      pushToVisualStores(merged);
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
    set({ settings: merged, ...derive(merged) });
    try {
      await api.saveSettings(patch);
    } catch {
      set({ offline: true });
    }
  },
}));
