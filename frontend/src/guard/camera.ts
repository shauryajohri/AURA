/**
 * Buddy Lock's eyes — one shared webcam stream for the whole renderer.
 *
 * The browser owns the camera the same way it owns the mic: frames are
 * grabbed here and posted to the brain, which does the recognising (and the
 * enforcing). Nothing is kept: a frame is a JPEG string that lives for one
 * request.
 *
 * The camera runs while Buddy Lock needs it (lock active, or setup) — and
 * that includes while AURA is minimised: the presence check is how she knows
 * her buddy is still at the desk, and her proactive help is muted the moment
 * she can't tell. Switch the lock off and the light goes off.
 */

export type CameraState = "off" | "starting" | "on" | "denied" | "error";

const MAX_SIDE = 640;
const JPEG_QUALITY = 0.82;

let stream: MediaStream | null = null;
let video: HTMLVideoElement | null = null;
let canvas: HTMLCanvasElement | null = null;
let capture: any = null; // ImageCapture on the live track (see grabFrameFresh)
let starting: Promise<boolean> | null = null;
let state: CameraState = "off";
let lastError = "";
// After a failure (no camera, permission denied, busy) wait before asking
// again. Without this every state change re-triggered getUserMedia and a
// missing camera spun hundreds of attempts a second.
const RETRY_AFTER_MS = 8000;
let failedAt = 0;
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

/** Start the camera. After a failure this is a no-op for RETRY_AFTER_MS
 *  unless `force` (an explicit "try again" from the user). */
export function startCamera(force = false): Promise<boolean> {
  if (stream) return Promise.resolve(true);
  if (starting) return starting;
  if (!force && failedAt && Date.now() - failedAt < RETRY_AFTER_MS) return Promise.resolve(false);
  // A retry keeps showing the error rather than flashing "starting".
  if (state !== "denied" && state !== "error") setState("starting");
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
      failedAt = 0;
      setState("on");
      return true;
    } catch (e: any) {
      const name = e?.name || "";
      lastError = name === "NotAllowedError" ? "Camera access is blocked."
        : name === "NotFoundError" ? "No camera found."
        : name === "NotReadableError" ? "The camera is busy in another app."
        : String(e?.message || e);
      failedAt = Date.now();
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
  capture = null;
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

/** Scale a drawable to MAX_SIDE and encode it as base64 JPEG (no prefix). */
function encode(src: CanvasImageSource, w: number, h: number): string | null {
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
  const url = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  return url.slice(url.indexOf(",") + 1);
}

/**
 * A frame taken straight from the camera track, for the presence loop. While
 * the window is minimised the <video> element can stop painting, and drawing
 * it would post the same stale picture over and over — ImageCapture reads the
 * track itself. Falls back to the <video> where ImageCapture is missing.
 */
export async function grabFrameFresh(): Promise<string | null> {
  const track = stream?.getVideoTracks()[0];
  const IC = (window as any).ImageCapture;
  if (track && IC && track.readyState === "live") {
    try {
      if (!capture || capture.track !== track) capture = new IC(track);
      const bmp: ImageBitmap = await capture.grabFrame();
      try {
        return encode(bmp, bmp.width, bmp.height);
      } finally {
        bmp.close();
      }
    } catch {
      /* a busy or just-restarted track — fall back below */
    }
  }
  return grabFrame();
}

/**
 * The current frame as base64 JPEG (no data: prefix), or null if the camera
 * isn't running. Synchronous on purpose — a typed message grabs its frame in
 * the same tick it's sent, so the frame is of whoever pressed Enter.
 */
export function grabFrame(): string | null {
  if (!stream || !video || video.readyState < 2 || !video.videoWidth) return null;
  return encode(video, video.videoWidth, video.videoHeight);
}
