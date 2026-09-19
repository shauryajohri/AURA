import { create } from "zustand";
import { api } from "../api";
import type { SavedItem } from "../types";

/**
 * Saved Info — everything AURA saved and read for you. One list shared by the
 * page and the chat dock's attachment chips; the socket's "saved" frames keep
 * it live, so a scan that finishes while you're elsewhere is already there.
 */
interface SavedState {
  items: SavedItem[];
  loaded: boolean;
  offline: boolean;
  load: () => Promise<void>;
  upsert: (item: SavedItem) => void;
  remove: (id: number) => void;
}

export const useSavedStore = create<SavedState>((set, get) => ({
  items: [],
  loaded: false,
  offline: false,
  load: async () => {
    try {
      const items = await api.getSaved();
      set({ items, loaded: true, offline: false });
    } catch {
      set({ loaded: true, offline: true });
    }
  },
  upsert: (item) => {
    const items = get().items;
    const i = items.findIndex((x) => x.id === item.id);
    if (i === -1) set({ items: [item, ...items] });
    else set({ items: items.map((x) => (x.id === item.id ? { ...x, ...item } : x)) });
  },
  remove: (id) => set({ items: get().items.filter((x) => x.id !== id) }),
}));
