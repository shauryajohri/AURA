/**
 * The core bus — how the rest of the app reaches the black hole.
 *
 * The scene is a canvas that owns its own animation loop, so instead of
 * threading props through React, anything that wants the core to react (a
 * keystroke, a sent message, a click on the void) emits here and the canvas
 * picks it up on its next frame. Coordinates are viewport pixels.
 */

export type CoreEvent =
  /** One spark of light, pulled from (x, y) into the core — a keystroke. */
  | { kind: "spark"; x: number; y: number }
  /** A burst of light streaming in from a rectangle — a sent message. */
  | { kind: "feed"; x: number; y: number; w: number; h: number }
  /** A ring of light leaving the horizon — a reply arriving. */
  | { kind: "pulse" }
  /** A shockwave from a point — a click on the core. */
  | { kind: "shock"; x: number; y: number };

type Listener = (e: CoreEvent) => void;
const listeners = new Set<Listener>();

export function emitCore(e: CoreEvent) {
  for (const l of listeners) l(e);
}

export function onCore(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/**
 * Where the core sits on screen right now (viewport px), published by the
 * scene every frame. The cursor reads it to feel the black hole's pull.
 * `hot`: the pointer is over a planet or the core, so the cursor should
 * treat it as clickable. `pointer`: the pointer is inside the window.
 */
export const coreGeom = { x: -1e4, y: -1e4, r: 0, hot: false, pointer: false };

/** Live signals the scene reads each frame. `mic`: voice input is listening. */
export const coreSignals = { mic: false };
