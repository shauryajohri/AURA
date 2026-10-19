import type { BuddyBridge, BuddyUpdate, BuddyWork } from "../types";
import { WIN_H, WIN_W } from "./win";

/**
 * A stand-in for the Electron bridge so buddy.html runs in a plain browser tab
 * during development: the tab is the desktop, its bottom edge is the taskbar,
 * and chat gets a canned reply. Never shipped — main.tsx only loads it under
 * import.meta.env.DEV. From the console, `buddyDev.emit({...})` fakes a relay
 * message and `buddyDev.command("toggle-nap")` a menu pick.
 */
export function createDevBridge(): BuddyBridge {
  const root = document.getElementById("buddy-root")!;
  root.classList.add("buddy-root--dev");
  const work = (): BuddyWork => ({ x: 0, y: 0, width: window.innerWidth, height: window.innerHeight });
  const updates = new Set<(m: BuddyUpdate) => void>();
  const commands = new Set<(c: string) => void>();
  const emit = (m: BuddyUpdate) => updates.forEach((cb) => cb(m));
  const command = (c: string) => commands.forEach((cb) => cb(c));
  const move = (x: number, y: number) => {
    root.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  };
  (window as unknown as { buddyDev: unknown }).buddyDev = { emit, command };

  return {
    relay: () => {},
    onChat: () => () => {},
    setEnabled: () => {},
    onUpdate: (cb) => {
      updates.add(cb);
      setTimeout(() => cb({ kind: "status", status: "open" }), 0); // like main's replay
      return () => { updates.delete(cb); };
    },
    onCommand: (cb) => { commands.add(cb); return () => { commands.delete(cb); }; },
    chat: (text) => {
      emit({ kind: "state", state: "thinking" });
      setTimeout(() => emit({ kind: "state", state: "speaking" }), 1500);
      setTimeout(() => {
        emit({ kind: "say", id: String(Date.now()), text: `You said "${text}". (Dev bridge: the real brain answers inside Electron.)` });
        emit({ kind: "state", state: "idle" });
      }, 3000);
    },
    move,
    place: async (x, y) => {
      const w = work();
      const cx = Math.round(Math.min(Math.max(x ?? w.width - WIN_W - 40, w.x), w.x + w.width - WIN_W));
      const cy = Math.round(Math.min(Math.max(y ?? w.height - WIN_H, w.y), w.y + w.height - WIN_H));
      move(cx, cy);
      return { x: cx, y: cy, work: w };
    },
    geom: async () => work(),
    setIgnoreMouse: () => {},
    focus: () => {},
    openMain: () => console.info("[buddy dev] open AURA"),
    menu: (o) => console.info("[buddy dev] menu", o, "→ buddyDev.command('chat' | 'toggle-wander' | 'toggle-nap')"),
  };
}
