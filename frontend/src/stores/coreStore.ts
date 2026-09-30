import { create } from "zustand";

// AURA core (black hole) appearance + position.
// Values are only written to disk on Save — live edits are drafts.
const KEY = "aura.core";

// Bumped whenever the sky changes shape. The offset below is stored in pixels
// from the centre of the sky, so a position nudged when the conversation sat
// along the bottom puts the core a hundred pixels off-centre now that the
// conversation is a right-hand pane. Size and glow still mean what they meant,
// so only the position is dropped on an upgrade.
const VERSION = 2;

interface CoreCfg {
  scale: number; // %
  glow: number;  // %
  x: number;     // px offset from stage center
  y: number;
}

const DEFAULTS: CoreCfg = { scale: 100, glow: 100, x: 0, y: 0 };

const load = (): CoreCfg => {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}") as Partial<CoreCfg> & { v?: number };
    const cfg = { ...DEFAULTS, ...saved };
    if (saved.v !== VERSION) {
      cfg.x = 0;
      cfg.y = 0;
    }
    return { scale: cfg.scale, glow: cfg.glow, x: cfg.x, y: cfg.y };
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
      localStorage.setItem(KEY, JSON.stringify({ scale, glow, x, y, v: VERSION }));
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
