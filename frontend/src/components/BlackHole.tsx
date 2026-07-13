import { useEffect, useRef } from "react";
import type { AuraState } from "../types";

interface Props {
  state: AuraState;
  size?: number;
}

// Port of the old PySide orb (ui/orb.py) — a tilted black-hole accretion disk.
// Palette + state language copied 1:1 so it reads exactly like the old orb.
const EVENT_VIOLET = "61,43,122";     // #3D2B7A
const NEBULA_PURPLE = "26,16,51";     // #1A1033
const ACCRETION_BLUE = "91,127,255";  // #5B7FFF
const ION_CYAN = "127,232,255";       // #7FE8FF
const STARLIGHT = "245,243,255";      // #F5F3FF
const FOCUS_GREEN = "61,220,151";     // #3DDC97
const ALERT_ORANGE = "255,122,61";    // #FF7A3D

type OrbState = "idle" | "listening" | "thinking" | "speaking" | "focus" | "alert";

const ACCENT: Record<OrbState, string> = {
  idle: EVENT_VIOLET,
  listening: ACCRETION_BLUE,
  thinking: STARLIGHT,      // white hole = "I'm working"
  speaking: ION_CYAN,
  focus: FOCUS_GREEN,
  alert: ALERT_ORANGE,
};
const TARGET_GLOW: Record<OrbState, number> = {
  idle: 0.55, listening: 0.75, thinking: 0.85, speaking: 1.0, focus: 0.42, alert: 1.0,
};
const SPIN: Record<OrbState, number> = {
  idle: 0.35, listening: 0.6, thinking: 1.6, speaking: 0.9, focus: 0.2, alert: 2.4,
};
const BREATHE_AMP: Record<OrbState, number> = {
  idle: 0.035, listening: 0.09, thinking: 0.035, speaking: 0.06, focus: 0.035, alert: 0.035,
};

const rgba = (c: string, a: number) => `rgba(${c},${a})`;

interface Particle { angle: number; radius: number; speed: number; size: number; bright: number; }

export default function BlackHole({ state, size = 360 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * DPR;
    canvas.height = size * DPR;
    canvas.style.width = size + "px";
    canvas.style.height = size + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    const cx = size / 2, cy = size / 2;
    const base = size;
    const scale = base / 120; // orb's reference diameter

    // 9 disk sparks at three radii (like orb.py: [28,34,40] * 3)
    const particles: Particle[] = [];
    for (const r of [28, 34, 40, 28, 34, 40, 28, 34, 40]) {
      particles.push({
        angle: Math.random() * 360,
        radius: r,
        speed: 0.4 + Math.random() * 0.8,
        size: 1.2 + Math.random() * 1.6,
        bright: 0.5 + Math.random() * 0.5,
      });
    }

    let rot = 0, pulse = 0, glow = 0.55;
    let raf = 0;

    const draw = () => {
      const os = (stateRef.current as OrbState) in ACCENT ? (stateRef.current as OrbState) : "idle";
      const accent = ACCENT[os];
      const spin = SPIN[os];
      const amp = BREATHE_AMP[os];

      rot = (rot + spin) % 360;
      pulse += os === "thinking" ? 0.09 : 0.05;
      glow += (TARGET_GLOW[os] - glow) * 0.08; // eased approach
      for (const p of particles) p.angle = (p.angle + p.speed * spin) % 360;

      const breathe = 1 + amp * Math.sin(pulse);
      const coreR = base * 0.17 * breathe;

      ctx.clearRect(0, 0, size, size);

      // Outer glow
      const glowR = coreR * 3.2;
      const gg = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR);
      gg.addColorStop(0.25, rgba(accent, 0.22 * (0.6 + 0.4 * glow)));
      gg.addColorStop(1, rgba(accent, 0));
      ctx.fillStyle = gg;
      ctx.beginPath(); ctx.arc(cx, cy, glowR, 0, Math.PI * 2); ctx.fill();

      // Disk sparks (tilted 0.42)
      for (const p of particles) {
        const rad = (p.angle * Math.PI) / 180;
        const x = cx + p.radius * scale * Math.cos(rad);
        const y = cy + p.radius * scale * 0.42 * Math.sin(rad);
        ctx.fillStyle = rgba(accent, Math.min(1, p.bright * (0.5 + 0.5 * glow)));
        const s = p.size * scale;
        ctx.beginPath(); ctx.arc(x, y, s / 2, 0, Math.PI * 2); ctx.fill();
      }

      // Accretion ring — rotating conical gradient, squashed to a tilted disk
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(1, 0.42);
      const cone = ctx.createConicGradient((rot * Math.PI) / 180, 0, 0);
      cone.addColorStop(0.0, rgba(accent, 0.95));
      cone.addColorStop(0.25, rgba(EVENT_VIOLET, 0.55));
      cone.addColorStop(0.5, rgba(NEBULA_PURPLE, 0.25));
      cone.addColorStop(0.75, rgba(EVENT_VIOLET, 0.55));
      cone.addColorStop(1.0, rgba(accent, 0.95));
      const ringR = coreR * 2;
      ctx.strokeStyle = cone;
      ctx.lineWidth = coreR * 0.36;
      ctx.beginPath(); ctx.arc(0, 0, ringR, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();

      // Event horizon — truly black core with a thin bright rim
      const r = coreR * 1.15;
      const hole = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      hole.addColorStop(0, "rgba(0,0,0,1)");
      hole.addColorStop(0.86, "rgba(0,0,0,1)");
      hole.addColorStop(0.97, rgba(accent, Math.min(1, 0.7 + 0.3 * glow)));
      hole.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = hole;
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return <canvas ref={canvasRef} className="bh-canvas" />;
}
