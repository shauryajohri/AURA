import { useEffect, useRef } from "react";

// ============================================================================
// The scroll journey — one continuous timeline p ∈ [0,1]:
//   0.00 – 0.25  universe, at rest
//   0.25 – 0.45  universe recedes (scale + fade)
//   0.45 – 0.90  transition video, scrubbed BY scroll (not by time)
//   0.90 – 1.00  sanctuary fades in; at p≈1 the cards reveal
//
// PERFORMANCE CONTRACT: this hook never calls setState per frame. It runs a
// single rAF loop and hands p to an imperative callback that mutates DOM
// styles / video.currentTime directly. React only re-renders on phase flips.
// ============================================================================

const WHEEL_GAIN = 0.00045; // scroll distance → journey progress
const EASE = 0.085;         // per-frame approach toward the target

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Progress of p through the [a, b] window, clamped to 0..1. */
export const seg = (p: number, a: number, b: number) => clamp01((p - a) / (b - a));

/** Shared, render-free journey state. Canvases read this to pause themselves. */
export const journey = { p: 0 };

export function useScrollJourney(onFrame: (p: number) => void) {
  const cbRef = useRef(onFrame);
  cbRef.current = onFrame;

  useEffect(() => {
    let target = 0;
    let p = 0;
    let raf = 0;
    let running = false;

    const tick = () => {
      const next = p + (target - p) * EASE;
      if (Math.abs(next - target) < 0.0006) {
        p = target;
        journey.p = p;
        cbRef.current(p);
        running = false;
        return;
      }
      p = next;
      journey.p = p;
      cbRef.current(p);
      raf = requestAnimationFrame(tick);
    };

    const kick = () => {
      if (!running) {
        running = true;
        raf = requestAnimationFrame(tick);
      }
    };

    const onWheel = (e: WheelEvent) => {
      const el = e.target as HTMLElement | null;
      // let scrollable UI regions scroll themselves
      if (el?.closest(".chat__log, .view, .nav, .coremenu, .sancard")) return;
      // free scroll: you go where you push, you stop where you stop —
      // no snapping, no auto-settle. The journey is yours.
      target = clamp01(target + e.deltaY * WHEEL_GAIN);
      kick();
    };

    window.addEventListener("wheel", onWheel, { passive: true });
    cbRef.current(0); // paint initial state

    return () => {
      window.removeEventListener("wheel", onWheel);
      cancelAnimationFrame(raf);
    };
  }, []);
}
