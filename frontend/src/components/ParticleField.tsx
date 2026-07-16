import { useEffect, useRef } from "react";
import type { AuraState } from "../types";

interface Props {
  state: AuraState;
}

/* ------------------------------------------------------------------ */
/* Layer 5 — living particles above the universe video.                */
/*                                                                      */
/* Thousands of particles that react to:                                */
/*   • black-hole gravity  — slow orbital pull toward the center;       */
/*     anything falling into the protected core is re-emitted at the    */
/*     rim, so the video's empty center stays clean                     */
/*   • mouse movement      — a soft repulsion bubble around the cursor  */
/*   • AI state            — tempo/brightness follow idle/thinking/     */
/*     speaking; speaking also emits expanding light rings              */
/*                                                                      */
/* rAF pauses entirely while the window is hidden/minimized.            */
/* ------------------------------------------------------------------ */

interface P {
  x: number; y: number;
  vx: number; vy: number;
  r: number;
  color: string;
  base: number;      // base alpha
  tw: number;        // twinkle speed
  phase: number;
}
interface Ring { r: number; v: number; alpha: number; }

const COLORS = [
  "#6a8cff", "#8b5cff", "#b06bff", "#ff5bd0",
  "#38e1ff", "#ffffff", "#ffd27a", "#7aa8ff",
];

const TEMPO: Record<string, number> = { idle: 1, listening: 1.2, thinking: 2.2, speaking: 1.5 };
const BRIGHT: Record<string, number> = { idle: 1, listening: 1.15, thinking: 1.3, speaking: 1.2 };

const rand = (a: number, b: number) => a + Math.random() * (b - a);

export default function ParticleField({ state }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let W = 0, H = 0;
    let ps: P[] = [];
    let rings: Ring[] = [];
    let lastRing = 0;
    const mouse = { x: -9999, y: -9999 };

    const spawn = (edge = false): P => {
      let x: number, y: number;
      if (edge) {
        // re-emit on a wide circle around the center (escaped the black hole)
        const a = Math.random() * Math.PI * 2;
        const rr = rand(Math.min(W, H) * 0.35, Math.max(W, H) * 0.6);
        x = W / 2 + Math.cos(a) * rr;
        y = H / 2 + Math.sin(a) * rr;
      } else {
        x = Math.random() * W;
        y = Math.random() * H;
      }
      return {
        x, y,
        vx: rand(-0.05, 0.05), vy: rand(-0.05, 0.05),
        r: Math.random() > 0.94 ? rand(1.3, 2.1) : rand(0.4, 1.1),
        color: COLORS[(Math.random() * COLORS.length) | 0],
        base: rand(0.2, 0.8),
        tw: rand(0.5, 2.0),
        phase: Math.random() * Math.PI * 2,
      };
    };

    const build = () => {
      const DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      const n = Math.min(2400, Math.round((W * H) / 900));
      ps = Array.from({ length: n }, () => spawn(false));
      rings = [];
    };

    let prev = performance.now();
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(50, t - prev); prev = t;

      const st = stateRef.current as string;
      const tempo = TEMPO[st] ?? 1;
      const bright = BRIGHT[st] ?? 1;
      const cx = W / 2, cy = H / 2;
      const core = Math.min(W, H) * 0.06;         // protected center
      const step = (dt / 16.7) * tempo;

      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      /* speaking → expanding light rings from the core */
      if (st === "speaking" && t - lastRing > 900) {
        lastRing = t;
        rings.push({ r: core * 1.4, v: 2.2, alpha: 0.5 });
      }
      for (let i = rings.length - 1; i >= 0; i--) {
        const rg = rings[i];
        rg.r += rg.v * step;
        rg.alpha *= Math.pow(0.985, step);
        if (rg.alpha < 0.01) { rings.splice(i, 1); continue; }
        ctx.globalAlpha = rg.alpha;
        ctx.strokeStyle = "rgba(160,190,255,1)";
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(cx, cy, rg.r, 0, Math.PI * 2); ctx.stroke();
      }

      for (const p of ps) {
        /* black-hole gravity: gentle radial pull + tangential swirl */
        const dx = cx - p.x, dy = cy - p.y;
        const d2 = dx * dx + dy * dy;
        const d = Math.sqrt(d2) || 1;
        const g = Math.min(0.05, 2600 / d2) * 0.004 * tempo;
        p.vx += (dx / d) * g * dt;
        p.vy += (dy / d) * g * dt;
        // swirl (perpendicular), stronger nearer the hole
        const s = Math.min(0.03, 1200 / d2) * 0.004 * tempo;
        p.vx += (-dy / d) * s * dt;
        p.vy += (dx / d) * s * dt;

        /* mouse: soft repulsion bubble */
        const mx = p.x - mouse.x, my = p.y - mouse.y;
        const md2 = mx * mx + my * my;
        if (md2 < 160 * 160) {
          const md = Math.sqrt(md2) || 1;
          const f = (1 - md / 160) * 0.06;
          p.vx += (mx / md) * f * dt;
          p.vy += (my / md) * f * dt;
        }

        /* integrate + drag */
        p.x += p.vx * step; p.y += p.vy * step;
        p.vx *= 0.985; p.vy *= 0.985;

        /* fell into the black hole, or drifted off-screen → re-emit */
        if (d < core || p.x < -40 || p.x > W + 40 || p.y < -40 || p.y > H + 40) {
          Object.assign(p, spawn(true));
          continue;
        }

        const a = p.base * (0.55 + 0.45 * Math.sin(t * 0.001 * p.tw * tempo + p.phase)) * bright;
        ctx.globalAlpha = Math.min(1, Math.max(0, a));
        ctx.fillStyle = p.color;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    };

    const onMouse = (e: MouseEvent) => { mouse.x = e.clientX; mouse.y = e.clientY; };
    const onLeave = () => { mouse.x = -9999; mouse.y = -9999; };
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) { prev = performance.now(); raf = requestAnimationFrame(draw); }
    };

    build();
    prev = performance.now();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    window.addEventListener("mousemove", onMouse);
    window.addEventListener("mouseout", onLeave);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", build);
      window.removeEventListener("mousemove", onMouse);
      window.removeEventListener("mouseout", onLeave);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return <canvas ref={canvasRef} className="particle-field" aria-hidden="true" />;
}
