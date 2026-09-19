import { create } from "zustand";
import { usePrefs } from "./prefsStore";

/**
 * The startup sequence.
 *
 *   intro  — a point of light becomes the black hole; everything else waits
 *   reveal — space fades in, planets are born from the horizon, the UI arrives
 *   done   — normal app
 *
 * Plays once per launch. Off switch: Settings → This device → "Startup
 * animation". Reduced motion skips it.
 */
export type BootPhase = "intro" | "reveal" | "done";

const reduced = typeof window !== "undefined" &&
  (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
// Vite's hot reload re-runs modules but keeps the page; don't replay the intro
// for every saved file during development.
const played = typeof sessionStorage !== "undefined" && sessionStorage.getItem("aura.introPlayed") === "1";
const start: BootPhase = usePrefs.getState().intro && !reduced && !played ? "intro" : "done";

interface BootStore {
  phase: BootPhase;
  /** performance.now() when the reveal began — the scene times births from it. */
  revealAt: number;
  reveal: () => void;
  finish: () => void;
}

export const useBootStore = create<BootStore>((set, get) => ({
  phase: start,
  revealAt: 0,
  reveal: () => {
    if (get().phase !== "intro") return;
    try { sessionStorage.setItem("aura.introPlayed", "1"); } catch { /* ignore */ }
    set({ phase: "reveal", revealAt: performance.now() });
  },
  finish: () => set({ phase: "done" }),
}));
