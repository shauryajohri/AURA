import { create } from "zustand";
import { guardApi, type GuardStatus, type Seen } from "../guardApi";
import {
  cameraState, grabFrame, onCameraState, startCamera, stopCamera, type CameraState,
} from "../guard/camera";

/**
 * Buddy Lock, renderer side: what the brain says about who's here, plus the
 * presence loop that keeps it current.
 *
 * The loop sends a camera frame every few seconds while the lock is active
 * and AURA is on screen — faster while locked, so the owner sitting down
 * unlocks her within a second or two. The brain does all the deciding; this
 * only reports what the camera sees and renders the answer.
 */

// Unlocked cadence also bounds how fast a takeover is noticed (policy needs
// two stranger frames), so ~5 s from someone else sitting down to the lock.
const PRESENCE_MS_UNLOCKED = 2500;
const PRESENCE_MS_LOCKED = 1500;
const OFFLINE_RETRY_MS = 2000;

interface GuardStore {
  status: GuardStatus | null;
  /** First status has arrived (or the brain is known to be offline). */
  loaded: boolean;
  offline: boolean;
  seen: Seen | null;
  camera: CameraState;
  /** Things (the setup panel) that need the camera even while the lock is off. */
  holds: number;
  refresh: () => Promise<GuardStatus | null>;
  apply: (status?: GuardStatus | null, seen?: Seen | null) => void;
  /** Keep the camera on until the returned release() is called. */
  holdCamera: () => () => void;
}

export const useGuardStore = create<GuardStore>((set, get) => ({
  status: null,
  loaded: false,
  offline: false,
  seen: null,
  camera: cameraState(),
  holds: 0,

  refresh: async () => {
    try {
      const s = await guardApi.status();
      get().apply(s);
      set({ offline: false });
      return s;
    } catch {
      set({ offline: true, loaded: true });
      return null;
    }
  },

  apply: (status, seen) => {
    if (status) set({ status, loaded: true });
    if (seen !== undefined) set({ seen });
    syncCamera();
  },

  holdCamera: () => {
    set((s) => ({ holds: s.holds + 1 }));
    syncCamera();
    let released = false;
    return () => {
      if (released) return;
      released = true;
      set((s) => ({ holds: Math.max(0, s.holds - 1) }));
      syncCamera();
    };
  },
}));

/** Is Buddy Lock enforcing right now? Read outside React (socket send). */
export function guardActive(): boolean {
  return !!useGuardStore.getState().status?.active;
}

// ── camera on/off ──────────────────────────────────────────────────────────
function wantCamera(): boolean {
  const { status, holds } = useGuardStore.getState();
  return (!!status?.active || holds > 0) && document.visibilityState === "visible";
}

function syncCamera(): void {
  if (wantCamera()) {
    void startCamera().then((ok) => { if (ok) void presenceTick(true); });
  } else if (cameraState() === "on" || cameraState() === "starting") {
    stopCamera();
  }
}

// ── presence loop ──────────────────────────────────────────────────────────
let inFlight = false;
let lastSent = 0;

async function presenceTick(force = false): Promise<void> {
  const { status } = useGuardStore.getState();
  if (!status?.active || inFlight || document.visibilityState !== "visible") return;
  const every = status.role === "locked" ? PRESENCE_MS_LOCKED : PRESENCE_MS_UNLOCKED;
  if (!force && Date.now() - lastSent < every) return;
  const frame = grabFrame();
  if (!frame) return;
  inFlight = true;
  lastSent = Date.now();
  try {
    const r = await guardApi.frame(frame);
    useGuardStore.getState().apply(r.status, r.seen);
    useGuardStore.setState({ offline: false });
  } catch {
    useGuardStore.setState({ offline: true });
  } finally {
    inFlight = false;
  }
}

let started = false;

/** Boot the loop once. Safe to call repeatedly (StrictMode double-mount). */
export function initGuard(): void {
  if (started) return;
  started = true;

  onCameraState((camera) => useGuardStore.setState({ camera }));
  document.addEventListener("visibilitychange", () => {
    syncCamera();
    // Coming back to AURA: check who's there right away rather than waiting
    // for the next tick (startCamera's .then also forces one).
    if (document.visibilityState === "visible") void useGuardStore.getState().refresh();
  });

  const boot = async () => {
    const s = await useGuardStore.getState().refresh();
    if (!s) setTimeout(boot, OFFLINE_RETRY_MS);
  };
  void boot();

  setInterval(() => {
    const st = useGuardStore.getState();
    if (st.offline && !st.status) return; // boot() is retrying
    void presenceTick();
  }, 500);
}
