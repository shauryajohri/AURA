import { create } from "zustand";
import { defaultSkin } from "../data/planetSkins";

// Which planet design each model wears. Saved on every pick — there is no
// draft/save step here, choosing a planet is the whole action.
const KEY = "aura.skins";

const load = (): Record<string, string> => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch {
    return {};
  }
};

interface SkinStore {
  picks: Record<string, string>;
  /** The model the Planets page opens on (clicking a planet in orbit sets it). */
  focus: string | null;
  setFocus: (modelId: string | null) => void;
  pick: (modelId: string, skinId: string) => void;
  reset: (modelId: string) => void;
}

export const useSkinStore = create<SkinStore>((set, get) => ({
  picks: load(),
  focus: null,
  setFocus: (focus) => set({ focus }),
  pick: (modelId, skinId) => {
    const picks = { ...get().picks, [modelId]: skinId };
    try { localStorage.setItem(KEY, JSON.stringify(picks)); } catch { /* quota */ }
    set({ picks });
  },
  reset: (modelId) => {
    const picks = { ...get().picks };
    delete picks[modelId];
    try { localStorage.setItem(KEY, JSON.stringify(picks)); } catch { /* quota */ }
    set({ picks });
  },
}));

export const skinFor = (picks: Record<string, string>, modelId: string, index: number) =>
  picks[modelId] ?? defaultSkin(modelId, index);
