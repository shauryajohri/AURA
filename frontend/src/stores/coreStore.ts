import { create } from "zustand";

// AURA core (black hole) appearance + position.
// Values are only written to disk on Save — live edits are drafts.
const KEY = "aura.core";

interface CoreCfg {
  scale: number; // %
  glow: number;  // %
  x: number;     // px offset from stage center
  y: number;
}

const DEFAULTS: CoreCfg = { scale: 100, glow: 100, x: 0, y: 0 };

const load = (): CoreCfg => {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) || "{}") as Partial<CoreCfg>) };
  } catch {
    return { ...DEFAULTS };
  }
};

interface CoreStore extends CoreCfg {
  menuOpen: boolean;
  editing: boolean;
  setMenuOpen: (open: boolean) => void;
  startEdit: () => void;
  set: (patch: Partial<CoreCfg>) => void;
  save: () => void;
  cancel: () => void;
  resetSpec: () => void;
}

export const useCoreStore = create<CoreStore>((set, get) => ({
  ...load(),
  menuOpen: false,
  editing: false,
  setMenuOpen: (open) => set({ menuOpen: open }),
  startEdit: () => set({ editing: true }),
  set: (patch) => {
    if (get().editing) set(patch); // adjustments only allowed in edit mode
  },
  save: () => {
    const { scale, glow, x, y } = get();
    try {
      localStorage.setItem(KEY, JSON.stringify({ scale, glow, x, y }));
    } catch {
      /* ignore quota errors */
    }
    set({ editing: false, menuOpen: false });
  },
  cancel: () => set({ ...load(), editing: false }),
  resetSpec: () => {
    if (get().editing) set({ ...DEFAULTS });
  },
}));
