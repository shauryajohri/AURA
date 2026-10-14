/**
 * Buddy Lock's eyes — one shared webcam stream for the whole renderer.
 *
 * The browser owns the camera the same way it owns the mic: frames are
 * grabbed here and posted to the brain, which does the recognising (and the
 * enforcing). Nothing is kept: a frame is a JPEG string that lives for one
 * request.
 *
 * The camera only runs while Buddy Lock needs it (lock active, or setup) AND
 * the window is visible. Minimise AURA and the light goes off.
 */

export type CameraState = "off" | "starting" | "on" | "denied" | "error";

const MAX_SIDE = 640;
const JPEG_QUALITY = 0.82;

let stream: MediaStream | null = null;
let video: HTMLVideoElement | null = null;
let canvas: HTMLCanvasElement | null = null;
let starting: Promise<boolean> | null = null;
let state: CameraState = "off";
let lastError = "";
const listeners = new Set<(s: CameraState) => void>();

function setState(s: CameraState) {
  state = s;
  listeners.forEach((fn) => fn(s));
}

export function cameraState(): CameraState {
  return state;
}

export function cameraError(): string {
  return lastError;
}

export function onCameraState(fn: (s: CameraState) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The live stream, for a visible preview <video>. Null when off. */
export function cameraStream(): MediaStream | null {
  return stream;
}

export function startCamera(): Promise<boolean> {
  if (stream) return Promise.resolve(true);
  if (starting) return starting;
  setState("starting");
  starting = (async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });
      stream = s;
      if (!video) {
        // Kept in the DOM (invisibly) rather than detached: a detached or
        // hidden <video> may stop decoding, and then every frame is stale.
        video = document.createElement("video");
        video.muted = true;
        video.playsInline = true;
        video.setAttribute("aria-hidden", "true");
        Object.assign(video.style, {
          position: "fixed", left: "0", top: "0", width: "2px", height: "2px",
          opacity: "0.01", pointerEvents: "none", zIndex: "-1",
        });
        document.body.appendChild(video);
      }
      video.srcObject = s;
      await video.play().catch(() => undefined);
      lastError = "";
      setState("on");
      return true;
    } catch (e: any) {
      const name = e?.name || "";
      lastError = name === "NotAllowedError" ? "Camera access is blocked."
        : name === "NotFoundError" ? "No camera found."
        : name === "NotReadableError" ? "The camera is busy in another app."
        : String(e?.message || e);
      setState(name === "NotAllowedError" ? "denied" : "error");
      return false;
    } finally {
      starting = null;
    }
  })();
  return starting;
}

export function stopCamera(): void {
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  if (video) video.srcObject = null;
  if (state !== "denied") setState("off");
}

/** Wait until the stream is actually producing frames (exposure settles in
 *  the first few hundred ms — the very first frame is usually too dark). */
export async function cameraReady(timeoutMs = 2500): Promise<boolean> {
  if (!(await startCamera())) return false;
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if (video && video.readyState >= 2 && video.videoWidth > 0) return true;
    await new Promise((r) => setTimeout(r, 80));
  }
  return false;
}

/**
 * The current frame as base64 JPEG (no data: prefix), or null if the camera
 * isn't running. Synchronous on purpose — a typed message grabs its frame in
 * the same tick it's sent, so the frame is of whoever pressed Enter.
 */
export function grabFrame(): string | null {
  if (!stream || !video || video.readyState < 2 || !video.videoWidth) return null;
  const w = video.videoWidth;
  const h = video.videoHeight;
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const url = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  return url.slice(url.indexOf(",") + 1);
}
