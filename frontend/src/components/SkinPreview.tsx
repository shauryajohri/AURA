import { useEffect, useRef, useState } from "react";
import type { AuraState } from "../types";
import { CORE_EXTENT, createCore, type OrbState } from "../skins/coreForms";
import { createSky, isSkyKind, SKY_BRIGHT, SKY_TEMPO } from "../skins/backdrops";
import { FILMS, isFilm, type BackdropId, type CoreFormId, type Skin } from "../skins/skins";

interface Props {
  skin: Skin;
  core: CoreFormId;
  backdrop: BackdropId;
  /** What she's doing in the preview — so a design can be seen reacting. */
  state?: AuraState;
  /** Particle density multiplier; previews run light. */
  density?: number;
  className?: string;
}

// Same state language as BlackHole, so a preview behaves like the real core.
const SPIN: Record<string, number> = { idle: 1, listening: 1.6, thinking: 5, speaking: 2.4 };
const GLOW: Record<string, number> = { idle: 0.55, listening: 0.72, thinking: 0.95, speaking: 0.85 };

/** The film a backdrop plays, if any, and what stands in when it can't. */
function filmOf(backdrop: BackdropId): { src: string; still: BackdropId } | null {
  if (backdrop === "video") return { src: "./aura-main.mp4", still: "cosmos" };
  if (isFilm(backdrop)) return { src: FILMS[backdrop].src, still: FILMS[backdrop].fallback };
  return null;
}

/**
 * A miniature of a skin, drawn by the real renderers: the procedural sky
 * from skins/backdrops and the core form from skins/coreForms, at card size.
 * Films can't be painted on a canvas, so they play as a muted <video>
 * underneath, and give way to their procedural stand-in if the file is
 * missing; the constellation web gets a painted stand-in.
 */
export default function SkinPreview({
  skin, core, backdrop, state = "idle", density = 0.45, className = "",
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  const film = filmOf(backdrop);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const playing = film && failedSrc !== film.src ? film.src : null;
  // what the canvas paints behind the core: nothing while a film plays
  const shown: BackdropId = film ? (playing ? backdrop : film.still) : backdrop;

  useEffect(() => {
    const wrap = wrapRef.current!;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const sky = !playing && isSkyKind(shown) ? createSky(shown) : null;
    const N = (base: number) => Math.max(4, Math.round(base * density));
    const renderCore = createCore(core, N);
    let W = 0, H = 0, raf = 0, visible = true;

    const build = () => {
      const r = wrap.getBoundingClientRect();
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      const k = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(W * k);
      canvas.height = Math.round(H * k);
      ctx.setTransform(k, 0, 0, k, 0, 0);
      sky?.resize(W, H, skin.sky, k);
    };

    let rot = 0, glow = 0.55, pulse = 0, tempo = 1, bright = 1;
    const t0 = performance.now();
    let prev = t0;
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      if (!visible) { prev = now; return; }
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      const st = stateRef.current as string;
      const os = (st in SPIN ? st : "idle") as OrbState;
      const w = ((Math.PI * 2) / 90) * SPIN[os];
      rot += w * dt;
      glow += (GLOW[os] - glow) * Math.min(1, dt * 4);
      pulse += dt * (os === "speaking" ? 2.6 : os === "thinking" ? 1.8 : 0.9);
      tempo += ((SKY_TEMPO[os] ?? 1) - tempo) * Math.min(1, dt * 2);
      bright += ((SKY_BRIGHT[os] ?? 1) - bright) * Math.min(1, dt * 2);
      const flicker = 0.84 + 0.12 * Math.sin(pulse * 5.1) + 0.05 * Math.sin(pulse * 12.7 + 1.3) +
        0.04 * Math.sin(pulse * 2.3 + 0.7);

      ctx.clearRect(0, 0, W, H);
      sky?.draw({ ctx, W, H, t: (now - t0) / 1000, dt, tempo, bright, speaking: os === "speaking", sky: skin.sky });

      // fit the whole form: its reach (in horizon radii) spans the shorter side
      const ext = CORE_EXTENT[core];
      const R = Math.min((W * 0.5) / ext, (H * 0.5) / Math.min(ext, 2.3));
      const cx = W / 2, cy = H / 2;
      const backing = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 3.2);
      backing.addColorStop(0, "rgba(0,0,0,0.9)");
      backing.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = backing;
      ctx.fillRect(0, 0, W, H);
      renderCore({
        ctx, cx, cy, R, s: R / 168, D: Math.max(W, H), rot, w, glow, pulse, flicker,
        breathe: 1 + 0.015 * Math.sin(pulse), talk: os === "speaking" ? 0.25 * Math.sin(pulse * 6) : 0,
        dt, now, os, pal: skin.pal,
      });
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
    };

    // previews off-screen (scrolled away in the gallery) cost nothing
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(wrap);
    const ro = new ResizeObserver(build);
    ro.observe(wrap);
    build();
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
    };
  }, [skin, core, shown, playing, density]);

  return (
    <div ref={wrapRef} className={`skinprev skinprev--${shown} ${className}`}>
      {playing && (
        <video
          key={playing}
          className="skinprev__video"
          src={playing}
          muted loop playsInline autoPlay
          onError={() => setFailedSrc(playing)}
        />
      )}
      <canvas ref={canvasRef} className="skinprev__canvas" aria-hidden="true" />
    </div>
  );
}
