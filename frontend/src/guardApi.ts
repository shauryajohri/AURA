// REST client for Buddy Lock (guard_api.py). Every call resolves with the
// server's JSON — including refusals (ok:false + error) — and only throws when
// the brain is unreachable, so callers can show the real reason.
const BASE = "http://127.0.0.1:8760";

export type GuardRole = "open" | "owner" | "guest" | "locked";

export interface GuardStatus {
  /** The lock is enforcing (enabled + an owner is enrolled). */
  active: boolean;
  role: GuardRole;
  owner_name: string;
  vault: {
    enabled: boolean;
    owner_name: string;
    face_samples: number;
    voice_samples: number;
    has_pin: boolean;
    corrupt: boolean;
    updated_at: string | null;
  };
  pin_session: boolean;
  owner_seen_ago: number | null;
  faces_in_frame: number | null;
  frame_ago: number | null;
  camera_error: string;
  guest: { claimed: boolean; expires_in: number } | null;
  lock_after_s: number;
  engines?: {
    face: { ready: boolean; error: string };
    voice: { ready: boolean; error: string };
  };
}

/** What the last camera frame showed. */
export interface Seen {
  faces?: number;
  owner?: boolean;
  error?: string;
}

/** Proof for actions that weaken the lock: a frame with the owner in it, or the PIN. */
export interface Proof {
  frame?: string | null;
  pin?: string;
}

export interface GuardResult {
  ok: boolean;
  error?: string;
  status?: GuardStatus;
  [k: string]: unknown;
}

/**
 * Buddy Lock refuses REST calls with 423 (locked) or 403 (guest). The app's
 * fetch helpers parse any body as data, so without this a refusal like
 * {ok:false, locked:true} reaches code expecting {rooms:[...]} and crashes
 * it. Throwing sends it down each caller's existing "couldn't load" path.
 */
export class GuardRefused extends Error {}

export function assertNotRefused(res: Response): void {
  if (res.status === 423 || res.status === 403) {
    throw new GuardRefused(res.status === 423 ? "AURA is locked" : "Not available to guests");
  }
}

async function call<T = GuardResult>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  try {
    return (await r.json()) as T;
  } catch {
    return { ok: false, error: `HTTP ${r.status}` } as T;
  }
}

export const guardApi = {
  status: () => call<GuardStatus>("GET", "/api/guard/status"),
  /** Load the engines, downloading the models the first time (~80 MB). */
  prepare: () =>
    call<{ ok: boolean; face: { ready: boolean; error: string }; voice: { ready: boolean; error: string } }>(
      "POST", "/api/guard/prepare"),
  frame: (frame: string, preview = false) =>
    call<{ ok: boolean; seen: Seen; status: GuardStatus }>("POST", "/api/guard/frame", { frame, preview }),
  unlockPin: (pin: string) => call("POST", "/api/guard/unlock/pin", { pin }),
  unlockVoice: (audio: string) => call("POST", "/api/guard/unlock/voice", { audio }),
  enrollFace: (frames: string[], ownerName: string, proof: Proof = {}) =>
    call<GuardResult & { accepted?: number; problems?: string[] }>(
      "POST", "/api/guard/enroll/face", { frames, owner_name: ownerName, replace: true, ...proof }),
  enrollVoice: (audio: string[], proof: Proof = {}) =>
    call<GuardResult & { accepted?: number; problems?: string[] }>(
      "POST", "/api/guard/enroll/voice", { audio, ...proof }),
  forgetVoice: (proof: Proof = {}) => call("DELETE", "/api/guard/enroll/voice", proof),
  setPin: (newPin: string, proof: Proof = {}) => call("POST", "/api/guard/pin", { new_pin: newPin, ...proof }),
  enable: (proof: Proof = {}) => call("POST", "/api/guard/enable", proof),
  disable: (proof: Proof = {}) => call("POST", "/api/guard/disable", proof),
  reset: (proof: Proof = {}) => call("POST", "/api/guard/reset", proof),
  grantGuest: (minutes: number, proof: Proof = {}) =>
    call<GuardResult & { message?: string }>("POST", "/api/guard/guest", { minutes, ...proof }),
  revokeGuest: () => call<GuardResult & { message?: string }>("DELETE", "/api/guard/guest"),
  lock: () => call("POST", "/api/guard/lock"),
};
