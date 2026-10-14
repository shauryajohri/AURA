import { useEffect, useRef, type ReactNode } from "react";
import { initGuard, useGuardStore } from "../../stores/guardStore";
import LockScreen from "./LockScreen";
import "./guard.css";

/**
 * Buddy Lock's front door for the whole UI.
 *
 * At launch the app isn't even mounted until the owner is recognised — so its
 * startup fetches don't run against a locked API and nothing of theirs is on
 * screen behind the lock. Once in, a later lock (owner walked away) overlays
 * the app instead of unmounting it, so their place is kept; the app underneath
 * is made inert so a half-typed message can't be sent from behind the glass.
 *
 * Crossing between owner and guest REMOUNTS the app. Whatever the widgets
 * fetched while the owner sat here (tasks, the chat on screen) would otherwise
 * stay rendered in front of the guest; a fresh mount refetches with guest
 * permissions instead. Locking doesn't remount — the owner keeps their place.
 *
 * The brain enforces all of this on its own (every chat message and REST call
 * is checked) — this is the face of it, not the lock itself.
 */
export default function GuardGate({ children }: { children: ReactNode }) {
  const loaded = useGuardStore((s) => s.loaded);
  const locked = useGuardStore((s) => !!s.status?.active && s.status.role === "locked");
  const guest = useGuardStore((s) => s.status?.role === "guest");
  const everIn = useRef(false);
  const appRef = useRef<HTMLDivElement>(null);

  useEffect(() => { initGuard(); }, []);

  if (loaded && !locked) everIn.current = true;
  // Who the mounted app belongs to. Frozen while locked: remounting behind the
  // lock would fetch against a locked API, so the swap waits for the unlock.
  const owner = useRef<"main" | "guest">("main");
  if (!locked) owner.current = guest ? "guest" : "main";

  useEffect(() => {
    const el = appRef.current;
    if (!el) return;
    if (locked) el.setAttribute("inert", "");
    else el.removeAttribute("inert");
  }, [locked]);

  if (!loaded) return <div className="lock lock--boot" />;
  if (locked && !everIn.current) return <LockScreen />;

  return (
    <>
      <div ref={appRef} key={owner.current} className="guardgate__app">{children}</div>
      {locked && <LockScreen />}
    </>
  );
}
