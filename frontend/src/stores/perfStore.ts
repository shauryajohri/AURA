import { create } from "zustand";

/**
 * Performance mode — one switch that trades a little visual richness for a
 * smooth UI on weaker GPUs (laptops on integrated graphics, mostly).
 *
 * Kept per machine in localStorage rather than in the brain's app_settings:
 * whether the effects run well is a property of THIS computer, and the switch
 * has to work even while the brain is offline.
 *
 * When on:
 *   - every animated canvas (core, particles) runs at 30 fps instead of 60+
 *   - the core renders at 1x pixel density with no shadow-blur glows
 *   - the particle field carries a quarter of the particles
 *   - the trailing cursor lens is skipped (the OS cursor stays)
 *   - glass panels stop live-blurring the moving background (html.perf in CSS)
 *   - the wallpaper video drops its per-frame colour filter
 */

const KEY = "aura.perf";

const read = (): boolean => {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
};

const reflect = (on: boolean) => document.documentElement.classList.toggle("perf", on);

interface PerfStore {
  perf: boolean;
  setPerf: (on: boolean) => void;
}

export const usePerfStore = create<PerfStore>((set) => {
  const initial = read();
  reflect(initial);
  return {
    perf: initial,
    setPerf: (on) => {
      try {
        localStorage.setItem(KEY, on ? "1" : "0");
      } catch {
        /* storage blocked — still apply for this session */
      }
      reflect(on);
      set({ perf: on });
    },
  };
});

/** Minimum ms between canvas frames in performance mode (~30 fps). */
export const PERF_FRAME_MS = 33;
