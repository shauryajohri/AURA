import { useEffect, useRef } from "react";
import type { AuraState } from "../types";
import { useBootStore } from "../stores/bootStore";

/**
 * Deep space behind everything — the Higgsfield plate (violet nebula at the
 * edges, a quiet dark middle for the core) plus a thin live layer on top:
 * stars that twinkle, a shooting star now and then, and a slow parallax
 * that follows the pointer so the room feels deep.
 *
 * Pauses completely while the window is hidden.
 */

interface Star { x: number; y: number; r: number; a: number; tw: number; ph: number; }
interface Shot { x: number; y: number; vx: number; vy: number; life: number; }

export default function SpaceBackground({ state }: { state: AuraState }) {
  const plateRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phase = useBootStore((s) => s.phase);

  useEffect(() => {
    const plate = plateRef.current!;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let W = 0, H = 0, DPR = 1;
    let stars: Star[] = [];
    const fit = () => {
      W = window.innerWidth; H = window.innerHeight;
      DPR = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = W * DPR; canvas.height = H * DPR;
      const n = Math.round((W * H) / 9000);
      stars = Array.from({ length: n }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        r: Math.random() < 0.08 ? 1.1 + Math.random() * 0.6 : 0.4 + Math.random() * 0.6,
        a: 0.25 + Math.random() * 0.6,
        tw: 0.4 + Math.random() * 1.8,
        ph: Math.random() * Math.PI * 2,
      }));
    };
    fit();
    window.addEventListener("resize", fit);

    const aim = { x: 0, y: 0 };
    const cur = { x: 0, y: 0 };
    const onMove = (e: MouseEvent) => {
      aim.x = e.clientX / W - 0.5;
      aim.y = e.clientY / H - 0.5;
    };
    window.addEventListener("mousemove", onMove);

    const shots: Shot[] = [];
    let nextShot = performance.now() + 8000 + Math.random() * 12000;
    let raf = 0;
    let last = performance.now();
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (document.hidden) return;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      cur.x += (aim.x - cur.x) * Math.min(1, dt * 2);
      cur.y += (aim.y - cur.y) * Math.min(1, dt * 2);
      plate.style.transform = `translate3d(${-cur.x * 18}px, ${-cur.y * 12}px, 0) scale(1.05)`;
      canvas.style.transform = `translate3d(${-cur.x * 30}px, ${-cur.y * 20}px, 0)`;

      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);
      const t = now / 1000;
      for (const s of stars) {
        const tw = reduce ? 1 : 0.55 + 0.45 * Math.sin(t * s.tw + s.ph);
        ctx.fillStyle = `rgba(236,230,255,${s.a * tw})`;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
      }
      if (!reduce && now > nextShot) {
        const fromLeft = Math.random() < 0.5;
        shots.push({
          x: fromLeft ? Math.random() * W * 0.4 : W * (0.6 + Math.random() * 0.4),
          y: Math.random() * H * 0.35,
          vx: (fromLeft ? 1 : -1) * (520 + Math.random() * 300),
          vy: 180 + Math.random() * 140,
          life: 0,
        });
        nextShot = now + 14000 + Math.random() * 22000;
      }
      for (let i = shots.length - 1; i >= 0; i--) {
        const s = shots[i];
        s.life += dt;
        if (s.life > 1.1) { shots.splice(i, 1); continue; }
        s.x += s.vx * dt; s.y += s.vy * dt;
        const a = Math.sin((s.life / 1.1) * Math.PI);
        const g = ctx.createLinearGradient(s.x, s.y, s.x - s.vx * 0.16, s.y - s.vy * 0.16);
        g.addColorStop(0, `rgba(255,250,255,${0.9 * a})`);
        g.addColorStop(1, "rgba(180,150,255,0)");
        ctx.strokeStyle = g;
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(s.x - s.vx * 0.16, s.y - s.vy * 0.16); ctx.stroke();
      }
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", fit);
      window.removeEventListener("mousemove", onMove);
    };
  }, []);

  return (
    <div className={"space space--" + state + (phase === "intro" ? " space--dark" : "")} aria-hidden="true">
      {/* relative to index.html, so it resolves in dev and under file:// */}
      <div ref={plateRef} className="space__plate" style={{ backgroundImage: "url(./cosmos/space.jpg)" }} />
      <canvas ref={canvasRef} className="space__stars" />
    </div>
  );
}
