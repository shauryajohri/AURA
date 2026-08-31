import { useEffect, useRef } from "react";

// Soft drifting motes for the sanctuary — the world must never feel static.
// Cheap: ~90 particles, transform-free canvas, additive blending.

interface Mote { x: number; y: number; vx: number; vy: number; r: number; a: number; tw: number; ph: number; }

export default function FloatingParticles() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0, W = 0, H = 0;
    let motes: Mote[] = [];

    const build = () => {
      const DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      motes = Array.from({ length: 90 }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.12, vy: -0.05 - Math.random() * 0.14,
        r: 0.6 + Math.random() * 1.8,
        a: 0.12 + Math.random() * 0.4,
        tw: 0.4 + Math.random() * 1.4,
        ph: Math.random() * Math.PI * 2,
      }));
    };

    let prev = performance.now();
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(50, t - prev); prev = t;
      const step = dt / 16.7;
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";
      for (const m of motes) {
        m.x += m.vx * step; m.y += m.vy * step;
        if (m.y < -10) { m.y = H + 10; m.x = Math.random() * W; }
        if (m.x < -10) m.x = W + 10; else if (m.x > W + 10) m.x = -10;
        const a = m.a * (0.5 + 0.5 * Math.sin(t * 0.001 * m.tw + m.ph));
        ctx.globalAlpha = a;
        ctx.fillStyle = "rgba(214,196,255,1)";
        ctx.beginPath(); ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    };

    build();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", build); };
  }, []);

  return <canvas ref={ref} className="san-particles" aria-hidden="true" />;
}
