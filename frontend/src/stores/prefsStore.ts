import { create } from "zustand";

// Per-device preferences that never go to the brain: how the app itself
// behaves on this machine. Each is a localStorage flag, default on.
export type Pref = "intro" | "sfx" | "cursor";

const read = (k: Pref) => {
  try { return localStorage.getItem("aura." + k) !== "false"; } catch { return true; }
};

export const usePrefs = create<Record<Pref, boolean>>(() => ({
  intro: read("intro"),
  sfx: read("sfx"),
  cursor: read("cursor"),
}));

export function setPref(k: Pref, on: boolean) {
  try { localStorage.setItem("aura." + k, on ? "true" : "false"); } catch { /* private mode */ }
  usePrefs.setState({ [k]: on } as Partial<Record<Pref, boolean>>);
}
