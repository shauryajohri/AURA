import { useEffect, useRef } from "react";
import { journey, seg } from "./ScrollController";

// Warp streaks over the transition video — descending pulls light upward past
// you (you're falling), ascending reverses the flow. Additive, cheap, alive.

interface Streak { x: number; y: number; v: number; len: number; w: number; a: number; c: string; }

const COLORS = ["214,196,255", "168,130,255", "56,225,255", "255,255,255", "255,160,220"];

export default function TransitionParticles() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0, W = 0, H = 0;
    let streaks: Streak[] = [];

    const build = () => {
      const DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      streaks = Array.from({ length: 130 }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        v: 3 + Math.random() * 9,
        len: 30 + Math.random() * 90,
        w: 0.6 + Math.random() * 1.6,
        a: 0.15 + Math.random() * 0.5,
        c: COLORS[(Math.random() * COLORS.length) | 0],
      }));
    };

    let prev = performance.now();
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(50, t - prev); prev = t;
      const p = journey.p;
      const vis = seg(p, 0.32, 0.48) * (1 - seg(p, 0.9, 0.99));
      if (vis <= 0) { ctx.clearRect(0, 0, W, H); return; }

      const step = dt / 16.7;
      const dir = journey.dir; // 1 = descending → streaks rush upward
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";

      for (const s of streaks) {
        s.y -= dir * s.v * step;
        if (dir > 0 && s.y < -s.len) { s.y = H + s.len; s.x = Math.random() * W; }
        if (dir < 0 && s.y > H + s.len) { s.y = -s.len; s.x = Math.random() * W; }
        const g = ctx.createLinearGradient(s.x, s.y, s.x, s.y + dir * s.len);
        g.addColorStop(0, `rgba(${s.c},${s.a * vis})`);
        g.addColorStop(1, `rgba(${s.c},0)`);
        ctx.strokeStyle = g;
        ctx.lineWidth = s.w;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(s.x, s.y + dir * s.len);
        ctx.stroke();
      }

      ctx.globalCompositeOperation = "source-over";
    };

    build();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", build); };
  }, []);

  return <canvas ref={ref} className="trans-particles" aria-hidden="true" />;
}
