import { create } from "zustand";

/**
 * Notification center — a persistent history of what happened while you
 * weren't looking: routing decisions, memory writes, quest completions,
 * serious V3 events, task activity. Fed by useAuraSocket (which can call
 * getState().add from outside React) and rendered by the bell in the TopBar.
 */

export interface Notice {
  id: string;
  ts: number;
  kind: string; // route | memory | task | quest | build | info | done
  text: string;
  read: boolean;
}

const KEY = "aura.notices";
const MAX = 80;

function load(): Notice[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.slice(0, MAX) : [];
  } catch {
    return [];
  }
}

function persist(list: Notice[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch { /* full */ }
}

interface NotifyStore {
  notices: Notice[];
  open: boolean;
  setOpen: (v: boolean) => void;
  add: (kind: string, text: string) => void;
  markAllRead: () => void;
  clear: () => void;
}

export const useNotifyStore = create<NotifyStore>((set, get) => ({
  notices: load(),
  open: false,
  setOpen: (v) => {
    set({ open: v });
    if (!v) get().markAllRead();
  },
  add: (kind, text) => {
    if (!text) return;
    const list = get().notices;
    // collapse exact repeats arriving back-to-back (routing retries etc.)
    if (list[0] && list[0].text === text && Date.now() - list[0].ts < 5000) return;
    const next: Notice[] = [
      { id: Math.random().toString(36).slice(2), ts: Date.now(), kind, text, read: false },
      ...list,
    ].slice(0, MAX);
    persist(next);
    set({ notices: next });
  },
  markAllRead: () => {
    const next = get().notices.map((n) => (n.read ? n : { ...n, read: true }));
    persist(next);
    set({ notices: next });
  },
  clear: () => {
    persist([]);
    set({ notices: [] });
  },
}));
