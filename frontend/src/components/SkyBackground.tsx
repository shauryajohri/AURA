import { useEffect, useRef } from "react";
import type { AuraState } from "../types";
import { createSky, SKY_BRIGHT, SKY_TEMPO, type SkyKind } from "../skins/backdrops";

interface Props {
  kind: SkyKind;
  /** The skin's sky hues — read live, so a recolour needs no rebuild. */
  sky: readonly string[];
  state: AuraState;
}

/**
 * Layer 1 (procedural) — the full-screen sky a skin wears when it isn't the
 * filmed universe. One canvas, one scene from skins/backdrops; it eases its
 * tempo and brightness toward AURA's state instead of snapping, and stops
 * rendering entirely while the window is hidden.
 */
export default function SkyBackground({ kind, sky, state }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;
  const skyRef = useRef(sky);
  skyRef.current = sky;

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const scene = createSky(kind);
    let W = 0, H = 0, raf = 0;
    let builtFor = skyRef.current;

    const build = () => {
      W = window.innerWidth; H = window.innerHeight;
      const k = Math.min(window.devicePixelRatio || 1, 2) * scene.res;
      canvas.width = Math.max(1, Math.round(W * k));
      canvas.height = Math.max(1, Math.round(H * k));
      ctx.setTransform(k, 0, 0, k, 0, 0);
      builtFor = skyRef.current;
      scene.resize(W, H, builtFor, k);
    };

    let tempo = 1, bright = 1;
    const t0 = performance.now();
    let prev = t0;
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      // cached layers carry colour, so a skin change repaints them once
      if (skyRef.current !== builtFor) build();
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      const st = stateRef.current;
      tempo += ((SKY_TEMPO[st] ?? 1) - tempo) * Math.min(1, dt * 2);
      bright += ((SKY_BRIGHT[st] ?? 1) - bright) * Math.min(1, dt * 2);
      scene.draw({
        ctx, W, H, t: (now - t0) / 1000, dt, tempo, bright,
        speaking: st === "speaking", sky: skyRef.current,
      });
    };
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) { prev = performance.now(); raf = requestAnimationFrame(draw); }
    };

    build();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", build);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [kind]);

  return <canvas ref={ref} className="sky-bg" aria-hidden="true" />;
}
