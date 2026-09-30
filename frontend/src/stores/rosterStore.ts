import { useMemo } from "react";
import { create } from "zustand";
import { api } from "../api";
import { MODELS, type ModelNode } from "../data/models";

/**
 * The live planet roster: the built-in models (data/models.ts) plus every
 * planet installed from a pasted key or link (core/integrations). `born`
 * marks planets that appeared while the app was open — the black hole plays
 * their birth once.
 */
interface RosterState {
  installed: ModelNode[];
  /** planet id → Date.now() when it first appeared */
  born: Record<string, number>;
  loaded: boolean;
  load: () => Promise<void>;
}

// A planet installed this recently is still "new" when the app first loads,
// so installing from the Models page and then going Home still shows it.
const FRESH_MS = 30_000;

export const useRosterStore = create<RosterState>((set, get) => ({
  installed: [],
  born: {},
  loaded: false,
  load: async () => {
    try {
      const planets = await api.getPlanets();
      const { installed, loaded } = get();
      const had = new Set(installed.map((p) => p.id));
      const born = { ...get().born };
      const now = Date.now();
      for (const p of planets) {
        if (had.has(p.id)) continue;
        const created = p.created_at ? Date.parse(p.created_at) : NaN;
        if (loaded || (Number.isFinite(created) && now - created < FRESH_MS)) born[p.id] = now;
      }
      set({ installed: planets, born, loaded: true });
    } catch {
      set({ loaded: true });
    }
  },
}));

/** Built-in + installed planets, stable between renders. */
export function useRoster(): ModelNode[] {
  const installed = useRosterStore((s) => s.installed);
  return useMemo(() => [...MODELS, ...installed], [installed]);
}

/** Non-hook lookup for event handlers (the socket maps model ids with it). */
export function rosterNow(): ModelNode[] {
  return [...MODELS, ...useRosterStore.getState().installed];
}
