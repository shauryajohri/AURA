// The brain's launch token (local_auth.py). Every /api/* call carries it as a
// header and the socket offers it as a subprotocol; without it the brain
// refuses, which is what stops other web pages on this laptop from driving
// AURA through 127.0.0.1:8760.
//
// Where it comes from:
//   · Electron (dev and packaged): the main process, over the preload bridge.
//   · A plain browser on the Vite dev server: the dev server's own
//     /__aura/token route (vite.config.ts), same-origin only.
// It changes every time the brain restarts, so a refusal re-asks once.

const HEADER = "X-Aura-Token";

let cached = "";
let inflight: Promise<string> | null = null;

async function load(): Promise<string> {
  if (window.aura?.getToken) {
    try {
      return (await window.aura.getToken()) || "";
    } catch {
      return "";
    }
  }
  try {
    const r = await fetch("/__aura/token", { cache: "no-store" });
    return r.ok ? (await r.text()).trim() : "";
  } catch {
    return "";
  }
}

/** The current token; `fresh` re-asks instead of using the cached one. */
export function getToken(fresh = false): Promise<string> {
  if (!fresh && cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = load().then((t) => {
      cached = t;
      inflight = null;
      return t;
    });
  }
  return inflight;
}

/** Thrown when the brain still refuses after a fresh token: the window and
 *  the brain belong to different launches. Callers treat it like offline. */
export class AuthRefused extends Error {}

/** fetch() for the brain's private API. Bodies must be re-sendable (strings),
 *  which every caller's JSON body is. */
export async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const send = async (fresh: boolean) => {
    const headers = new Headers(init.headers);
    const token = await getToken(fresh);
    if (token) headers.set(HEADER, token);
    return fetch(url, { ...init, headers });
  };
  let res = await send(false);
  if (res.status === 401) res = await send(true); // the brain restarted
  if (res.status === 401) throw new AuthRefused("AURA's brain didn't recognise this window — restart AURA");
  return res;
}

/** Subprotocols for the /ws socket. Always re-asks: a reconnect usually
 *  means the brain restarted, and with it the token. */
export async function socketProtocols(): Promise<string[]> {
  const token = await getToken(true);
  return token ? ["aura", `aura-token.${token}`] : ["aura"];
}
