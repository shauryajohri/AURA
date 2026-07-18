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

const SPEED = 0.25;  // cruise: one scroll → full journey ≈ 4s
const BOOST = 3.2;   // scroll again mid-flight → fast travel

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/** Progress of p through the [a, b] window, clamped to 0..1. */
export const seg = (p: number, a: number, b: number) => clamp01((p - a) / (b - a));

/** Shared, render-free journey state. Canvases read this to pause themselves. */
export const journey = { p: 0, dir: 1 as 1 | -1 };

export function useScrollJourney(onFrame: (p: number) => void) {
  const cbRef = useRef(onFrame);
  cbRef.current = onFrame;

  useEffect(() => {
    let target = 0;
    let p = 0;
    let raf = 0;
    let running = false;
    let last = 0;
    let boost = 1;
    let lastWheel = 0;

    // One scroll → the journey begins at cruise speed (you watch the crossing).
    // Scroll again in the same direction mid-flight → fast travel, skip ahead.
    // Scroll the opposite way anytime → turn around.
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const remain = target - p;
      const dirn = remain >= 0 ? 1 : -1;
      const speed = SPEED * boost * Math.min(1, 0.25 + Math.abs(remain) * 3); // soft landing
      let next = p + dirn * speed * dt;
      if ((dirn > 0 && next >= target) || (dirn < 0 && next <= target)) next = target;
      p = next;
      journey.p = p;
      cbRef.current(p);
      if (p === target) { running = false; boost = 1; return; }
      raf = requestAnimationFrame(tick);
    };

    const kick = () => {
      if (!running) {
        running = true;
        last = performance.now();
        raf = requestAnimationFrame(tick);
      }
    };

    const onWheel = (e: WheelEvent) => {
      const el = e.target as HTMLElement | null;
      // let scrollable UI regions scroll themselves
      if (el?.closest(".chat__log, .view, .nav, .coremenu, .sancard")) return;
      if (Math.abs(e.deltaY) < 4) return;
      // debounce wheel bursts — one physical flick = one intent
      const now = performance.now();
      if (now - lastWheel < 180) return;
      lastWheel = now;

      const dir: 1 | -1 = e.deltaY > 0 ? 1 : -1;
      const wanted = dir === 1 ? 1 : 0;

      if (target !== wanted) {
        // new direction → commit the journey at cruise speed
        target = wanted;
        journey.dir = dir;
        boost = 1;
        kick();
      } else if (p !== target) {
        // same direction again mid-flight → fast travel
        boost = BOOST;
        kick();
      }
    };

    window.addEventListener("wheel", onWheel, { passive: true });
    cbRef.current(0); // paint initial state

    return () => {
      window.removeEventListener("wheel", onWheel);
      cancelAnimationFrame(raf);
    };
  }, []);
}
