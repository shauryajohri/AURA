import { create } from "zustand";

// Planet system settings — same Edit/Save flow as the core (black hole).
// The system has fixed orbit SLOTS (one planet per orbit). Dragging a planet
// onto an occupied orbit swaps the old tenant onto the vacated one.
// Names/roles are editable per planet. Only written to disk on Save.
const KEY = "aura.planets";

export interface PlanetMeta {
  name?: string;
  role?: string;
}

interface PlanetCfg {
  orbit: number; // % — global orbit scale
  size: number;  // % — planet size (50–600, up to 6×)
  speed: number; // % — revolution speed (25–300)
  rings: number; // % — Saturn-ring size around ringed planets (60–300)
  slots: Record<string, number>;     // planetId → orbit slot index
  meta: Record<string, PlanetMeta>;  // planetId → name/role overrides
}

const DEFAULTS: PlanetCfg = { orbit: 100, size: 100, speed: 100, rings: 100, slots: {}, meta: {} };

const load = (): PlanetCfg => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}") as Partial<PlanetCfg>;
    return {
      ...DEFAULTS,
      ...raw,
      slots: raw.slots && typeof raw.slots === "object" ? raw.slots : {},
      meta: raw.meta && typeof raw.meta === "object" ? raw.meta : {},
    };
  } catch {
    return { ...DEFAULTS };
  }
};

interface PlanetStore extends PlanetCfg {
  menuOpen: boolean;
  editing: boolean;
  setMenuOpen: (open: boolean) => void;
  startEdit: () => void;
  set: (patch: Partial<Pick<PlanetCfg, "orbit" | "size" | "speed" | "rings">>) => void;
  setSlots: (slots: Record<string, number>) => void;
  setMeta: (id: string, patch: PlanetMeta) => void;
  save: () => void;
  cancel: () => void;
  resetSpec: () => void;
}

export const usePlanetStore = create<PlanetStore>((set, get) => ({
  ...load(),
  menuOpen: false,
  editing: false,
  setMenuOpen: (open) => set({ menuOpen: open }),
  startEdit: () => set({ editing: true }),
  set: (patch) => {
    if (get().editing) set(patch); // adjustments only in edit mode
  },
  setSlots: (slots) => {
    if (get().editing) set({ slots });
  },
  setMeta: (id, patch) => {
    if (!get().editing) return;
    const meta = { ...get().meta, [id]: { ...get().meta[id], ...patch } };
    set({ meta });
  },
  save: () => {
    const { orbit, size, speed, rings, slots, meta } = get();
    try {
      localStorage.setItem(KEY, JSON.stringify({ orbit, size, speed, rings, slots, meta }));
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
