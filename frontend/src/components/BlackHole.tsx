import { useEffect, useRef, useState } from "react";
import type { AuraState } from "../types";
import { useCoreStore } from "../stores/coreStore";

// ============================================================================
// AURA CORE — Black Hole, built 1:1 from the design spec:
//   Event horizon 240px · 12 orbital guides · Main #7D3CFF · Inner #A76DFF
//   Photon ring #F3D9FF · Disk: purple/pink/blue/orange · 90s/revolution
//   Subtle pulse · 20% soft purple bloom · gravitational lens arcs
// Layer order: bloom → guides → lens → REAR disk → inner glow →
//              event horizon (pure black) → photon ring → FRONT disk
// ============================================================================

const MAIN = "125,60,255";    // #7D3CFF electric purple
const INNER = "167,109,255";  // #A76DFF inner glow
const PHOTON = "243,217,255"; // #F3D9FF photon ring
const SOFT = "231,168,255";   // #E7A8FF
const DEEP = "139,101,255";   // #8B65FF
const BLUE = "77,155,255";    // #4D9BFF
const PINK = "255,107,157";   // #FF6B9D
const ORANGE = "255,158,77";  // #FF9E4D
const AMBER = "255,180,92";   // #FFB45C
const MAGENTA = "255,64,224"; // hot magenta — vivid disk accents
const HOT = "196,92,255";     // saturated violet
const WHITE = "255,244,255";  // near-white sparks
const CYAN = "56,225,255";

const rgba = (c: string, a: number) => `rgba(${c},${a < 0 ? 0 : a > 1 ? 1 : a})`;

type OrbState = "idle" | "listening" | "thinking" | "speaking" | "focus" | "alert";
const SPIN: Record<OrbState, number> = { idle: 1, listening: 1.6, thinking: 5, speaking: 2.4, focus: 0.7, alert: 7 };
const GLOW: Record<OrbState, number> = { idle: 0.55, listening: 0.72, thinking: 0.95, speaking: 0.85, focus: 0.45, alert: 1 };

const REF = 680;         // reference composition size (px)
const MAX = 420;         // on-screen cap — keeps the core compact in the stage
const HORIZON = 120;     // event-horizon radius at REF → 240px diameter, per spec
const SQUASH = 0.3;      // accretion-disk tilt
const RINGS = 12;        // orbital guide count, per spec

interface Props {
  state: AuraState;
  size?: number;
}

interface DiskP { a: number; r: number; sp: number; sz: number; c: string; al: number; }
interface Strand { r: number; w: number; c: string; a0: number; len: number; al: number; sp: number; }
interface Infall { a: number; r: number; sp: number; }
interface Node { ring: number; a: number; tw: number; big: boolean; }

export default function BlackHole({ state, size: sizeProp }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  // All appearance/position comes from the core store (Core menu in the top bar).
  // Editing is gated: drag & sliders only work in edit mode; Save persists.
  const scalePct = useCoreStore((s) => s.scale);
  const glowPct = useCoreStore((s) => s.glow);
  const posX = useCoreStore((s) => s.x);
  const posY = useCoreStore((s) => s.y);
  const editing = useCoreStore((s) => s.editing);
  const setCfg = useCoreStore((s) => s.set);
  const glowMulRef = useRef(1);
  glowMulRef.current = glowPct / 100;

  const [stageMin, setStageMin] = useState<number>(sizeProp ?? MAX);
  const stageDims = useRef({ w: sizeProp ?? MAX, h: sizeProp ?? MAX });

  // Fit inside the stage: never bigger than the stage, never comically small.
  useEffect(() => {
    if (sizeProp) return;
    const el = wrapRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      stageDims.current = { w: r.width, h: r.height };
      const m = Math.floor(Math.min(r.width, r.height));
      if (m > 100) setStageMin(m);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [sizeProp]);

  const fitBase = sizeProp ?? Math.min(MAX, stageMin * 0.86);
  const size = Math.max(160, Math.min(stageMin, Math.round((fitBase * scalePct) / 100)));

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * DPR;
    canvas.height = size * DPR;
    canvas.style.width = size + "px";
    canvas.style.height = size + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    const s = size / REF;
    const cx = size / 2, cy = size / 2;
    const R = HORIZON * s; // event-horizon radius

    // ---- Layer 05: energy particles of the accretion disk -----------------
    const palette: Array<[string, number]> = [
      [MAIN, 0.20], [HOT, 0.13], [INNER, 0.10], [MAGENTA, 0.10],
      [BLUE, 0.10], [PINK, 0.12], [ORANGE, 0.10], [AMBER, 0.05],
      [SOFT, 0.05], [WHITE, 0.05],
    ];
    const pick = () => {
      let x = Math.random(), acc = 0;
      for (const [c, w] of palette) { acc += w; if (x <= acc) return c; }
      return MAIN;
    };
    const disk: DiskP[] = [];
    for (let i = 0; i < 680; i++) {
      const rn = 1.08 + Math.pow(Math.random(), 1.6) * 1.7; // cluster near the core, reach further out
      disk.push({
        a: Math.random() * Math.PI * 2,
        r: rn,
        sp: 0.55 / rn + Math.random() * 0.25, // inner orbits faster (Kepler-ish)
        sz: 0.8 + Math.random() * 1.9,
        c: pick(),
        al: 0.35 + Math.random() * 0.6,
      });
    }

    // ---- Layer 04: flowing accretion strands (dense, like the reference) ---
    const strands: Strand[] = [];
    for (let i = 0; i < 72; i++) {
      const rn = 1.05 + Math.pow(Math.random(), 1.3) * 1.75;
      const roll = Math.random();
      const c =
        roll < 0.18 ? ORANGE :
        roll < 0.32 ? PINK :
        roll < 0.44 ? MAGENTA :
        roll < 0.62 ? MAIN :
        roll < 0.74 ? HOT :
        roll < 0.84 ? BLUE :
        roll < 0.94 ? INNER : WHITE;
      strands.push({
        r: rn,
        w: 0.6 + Math.random() * 1.8,
        c,
        a0: Math.random() * Math.PI * 2,
        len: 0.5 + Math.random() * 2.4,
        al: 0.16 + Math.random() * 0.26,
        sp: 0.5 / rn + 0.15,
      });
    }

    // Information particles spiralling into the core
    const infall: Infall[] = [];
    for (let i = 0; i < 36; i++) {
      infall.push({ a: Math.random() * Math.PI * 2, r: 1.1 + Math.random() * 2.1, sp: 0.3 + Math.random() * 0.5 });
    }

    // ---- Orbital guides + node dots ----------------------------------------
    const rMin = R * 1.4, rMax = size / 2 - 4 * s;
    const guideR: number[] = [];
    for (let i = 0; i < RINGS; i++) guideR.push(rMin + ((rMax - rMin) * i) / (RINGS - 1));
    const nodes: Node[] = [];
    for (let i = 0; i < RINGS; i++) {
      const n = 1 + Math.floor(Math.random() * 3);
      for (let j = 0; j < n; j++) {
        nodes.push({ ring: i, a: Math.random() * Math.PI * 2, tw: Math.random() * Math.PI * 2, big: Math.random() < 0.14 });
      }
    }

    // ---- Disk renderer (drawn twice: rear behind horizon, front over it) ---
    const drawDisk = (front: boolean, glow: number) => {
      ctx.save();
      ctx.beginPath();
      if (front) ctx.rect(0, cy, size, size / 2 + 2);
      else ctx.rect(0, 0, size, cy);
      ctx.clip();
      ctx.globalCompositeOperation = "lighter";

      // luminous disk body — vivid violet/magenta haze filling the whole disk
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(1, SQUASH);
      const haze = ctx.createRadialGradient(0, 0, R * 0.9, 0, 0, R * 3.1);
      haze.addColorStop(0, rgba(HOT, 0.38 * (0.5 + 0.6 * glow)));
      haze.addColorStop(0.35, rgba(MAIN, 0.25 * (0.5 + 0.6 * glow)));
      haze.addColorStop(0.65, rgba(MAGENTA, 0.12 * (0.5 + 0.6 * glow)));
      haze.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = haze;
      ctx.beginPath(); ctx.arc(0, 0, R * 3.1, 0, Math.PI * 2); ctx.fill();
      ctx.restore();

      // bright inner band hugging the photon ring, like the reference
      ctx.beginPath();
      ctx.ellipse(cx, cy, 1.14 * R, 1.14 * R * SQUASH, 0, 0, Math.PI * 2);
      ctx.strokeStyle = rgba(HOT, 0.8 * (0.5 + 0.6 * glow));
      ctx.lineWidth = 5 * s;
      ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(cx, cy, 1.24 * R, 1.24 * R * SQUASH, 0, 0, Math.PI * 2);
      ctx.strokeStyle = rgba(INNER, 0.35 * (0.5 + 0.6 * glow));
      ctx.lineWidth = 6 * s;
      ctx.stroke();

      for (const st of strands) {
        ctx.beginPath();
        ctx.ellipse(cx, cy, st.r * R, st.r * R * SQUASH, 0, st.a0, st.a0 + st.len);
        ctx.strokeStyle = rgba(st.c, st.al * (0.55 + 0.6 * glow));
        ctx.lineWidth = st.w * s;
        ctx.stroke();
      }

      // particles drawn as short tangential streaks — reads as flowing motion
      ctx.lineCap = "round";
      for (const p of disk) {
        const sin = Math.sin(p.a);
        if (front ? sin < -0.02 : sin > 0.02) continue;
        const rr = p.r * R;
        const x1 = cx + rr * Math.cos(p.a);
        const y1 = cy + rr * SQUASH * sin;
        const a2 = p.a + 0.05 + 0.02 / p.r;
        const x2 = cx + rr * Math.cos(a2);
        const y2 = cy + rr * SQUASH * Math.sin(a2);
        const depth = (sin + 1) / 2;                       // 1 = nearest to viewer
        const innerBoost = Math.max(0.4, 1.5 - p.r * 0.45); // hotter near the core
        ctx.strokeStyle = rgba(p.c, p.al * (0.45 + 0.55 * depth) * innerBoost * (0.75 + 0.6 * glow));
        ctx.lineWidth = (p.sz * s) / 1.7;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      for (const f of infall) {
        const sin = Math.sin(f.a);
        if (front ? sin < -0.02 : sin > 0.02) continue;
        const x = cx + f.r * R * Math.cos(f.a);
        const y = cy + f.r * R * SQUASH * sin;
        ctx.fillStyle = rgba(PHOTON, 0.55);
        ctx.beginPath();
        ctx.arc(x, y, 0.9 * s, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
      ctx.globalCompositeOperation = "source-over";
    };

    let rot = 0, glow = 0.55, pulse = 0, raf = 0;
    let last = performance.now();

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const os: OrbState = (stateRef.current as OrbState) in SPIN ? (stateRef.current as OrbState) : "idle";
      const baseW = (Math.PI * 2) / 90; // spec: 90 s per revolution
      const w = baseW * SPIN[os];
      rot = (rot + w * dt) % (Math.PI * 2);
      glow += (GLOW[os] * glowMulRef.current - glow) * Math.min(1, dt * 4);
      pulse += dt * (os === "speaking" ? 2.6 : 0.9);
      const breathe = 1 + 0.015 * Math.sin(pulse); // spec: subtle pulse

      for (const p of disk) p.a = (p.a + w * dt * p.sp * 8) % (Math.PI * 2);
      for (const st of strands) st.a0 = (st.a0 + w * dt * st.sp * 6) % (Math.PI * 2);
      for (const f of infall) {
        f.a += dt * f.sp * 1.6;
        f.r -= dt * (0.1 + (3.4 - f.r) * 0.04);
        if (f.r < 1.03) { f.r = 2.4 + Math.random() * 0.9; f.a = Math.random() * Math.PI * 2; }
      }

      ctx.clearRect(0, 0, size, size);

      // Layer 07 — soft purple bloom (20%)
      ctx.globalCompositeOperation = "lighter";
      const bloom = ctx.createRadialGradient(cx, cy, 0, cx, cy, size / 2);
      bloom.addColorStop(0, rgba(MAIN, 0.2 * glow + 0.06));
      bloom.addColorStop(0.5, rgba(MAIN, 0.08));
      bloom.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = bloom;
      ctx.fillRect(0, 0, size, size);
      ctx.globalCompositeOperation = "source-over";

      // Orbital guides — 12 rings connecting AURA to its systems (more present now)
      for (let i = 0; i < RINGS; i++) {
        ctx.beginPath();
        ctx.arc(cx, cy, guideR[i], 0, Math.PI * 2);
        ctx.strokeStyle = rgba(INNER, 0.09 + (i % 4 === 0 ? 0.05 : 0));
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      // bold border rings framing the whole composition
      ctx.globalCompositeOperation = "lighter";
      ctx.beginPath();
      ctx.arc(cx, cy, rMax, 0, Math.PI * 2);
      ctx.strokeStyle = rgba(MAIN, 0.16 + 0.06 * Math.sin(pulse * 0.7));
      ctx.lineWidth = 2.5 * s;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, rMax - 7 * s, 0, Math.PI * 2);
      ctx.strokeStyle = rgba(INNER, 0.2);
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, rMax * 0.82, 0, Math.PI * 2);
      ctx.strokeStyle = rgba(HOT, 0.12);
      ctx.lineWidth = 1.6 * s;
      ctx.stroke();
      ctx.globalCompositeOperation = "source-over";
      for (const n of nodes) {
        const a = n.a + rot * 0.25;
        const x = cx + guideR[n.ring] * Math.cos(a);
        const y = cy + guideR[n.ring] * Math.sin(a);
        const tw = 0.5 + 0.5 * Math.sin(pulse * 1.4 + n.tw);
        if (n.big) {
          const g = ctx.createRadialGradient(x, y, 0, x, y, 9 * s);
          g.addColorStop(0, rgba(PHOTON, 0.7 * tw));
          g.addColorStop(0.35, rgba(DEEP, 0.35 * tw));
          g.addColorStop(1, rgba(DEEP, 0));
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(x, y, 9 * s, 0, Math.PI * 2); ctx.fill();
        }
        ctx.fillStyle = rgba(PHOTON, 0.18 + 0.22 * tw);
        ctx.beginPath(); ctx.arc(x, y, (n.big ? 1.8 : 1.2) * s, 0, Math.PI * 2); ctx.fill();
      }

      // Layer 06 — gravitational lens: faint curved space-time arcs
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < 3; i++) {
        const lr = R * (1.55 + i * 0.5);
        ctx.beginPath();
        ctx.ellipse(cx, cy, lr, lr * 0.62, 0, Math.PI * 1.08, Math.PI * 1.92);
        ctx.strokeStyle = rgba(INNER, 0.06 - i * 0.015);
        ctx.lineWidth = (2.5 - i * 0.6) * s;
        ctx.stroke();
      }
      ctx.globalCompositeOperation = "source-over";

      // Dark backing — dims the busy universe video behind the core so the
      // black hole reads strong instead of melting into the background.
      const backing = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 2.9);
      backing.addColorStop(0, "rgba(0,0,0,0.85)");
      backing.addColorStop(0.45, "rgba(2,0,8,0.55)");
      backing.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = backing;
      ctx.beginPath(); ctx.arc(cx, cy, R * 2.9, 0, Math.PI * 2); ctx.fill();

      // Back-light emission — radiant corona blazing out from behind the void.
      // This is what makes the core THE center of attraction on screen.
      ctx.globalCompositeOperation = "lighter";
      const corona = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, R * 2.5);
      corona.addColorStop(0, rgba(INNER, 0.55 * glow + 0.12));
      corona.addColorStop(0.3, rgba(HOT, 0.3 * glow + 0.06));
      corona.addColorStop(0.6, rgba(MAIN, 0.14 * glow));
      corona.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = corona;
      ctx.beginPath(); ctx.arc(cx, cy, R * 2.5, 0, Math.PI * 2); ctx.fill();
      // vertical light spill above/below the horizon (polar emission)
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(0.45, 1);
      const polar = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 2.3);
      polar.addColorStop(0, rgba(PHOTON, 0.22 * glow + 0.05));
      polar.addColorStop(0.5, rgba(INNER, 0.09 * glow));
      polar.addColorStop(1, rgba(INNER, 0));
      ctx.fillStyle = polar;
      ctx.beginPath(); ctx.arc(0, 0, R * 2.3, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      ctx.globalCompositeOperation = "source-over";

      // Layers 04/05 — REAR half of the accretion disk (occluded by the core)
      drawDisk(false, glow);

      // Layer 02 — inner aura glow (#A76DFF) leaking from the core
      ctx.globalCompositeOperation = "lighter";
      const ig = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 1.75);
      ig.addColorStop(0, rgba(INNER, 0));
      ig.addColorStop(0.22, rgba(INNER, 0.6 * glow + 0.14));
      ig.addColorStop(0.55, rgba(MAIN, 0.26 * glow));
      ig.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = ig;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.75, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";

      // Layer 01 — event horizon: pure black void, no light escapes
      ctx.fillStyle = "#000";
      ctx.beginPath(); ctx.arc(cx, cy, R * breathe, 0, Math.PI * 2); ctx.fill();

      // Layer 03 — photon ring (#F3D9FF), brightest over the top
      ctx.globalCompositeOperation = "lighter";
      ctx.save();
      ctx.shadowColor = rgba(PHOTON, 1);
      ctx.shadowBlur = 26 * s;
      ctx.strokeStyle = rgba(PHOTON, 0.65 + 0.35 * glow);
      ctx.lineWidth = 2.8 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.02 * breathe, 0, Math.PI * 2); ctx.stroke();
      // violet halo just outside the photon ring
      ctx.shadowBlur = 0;
      ctx.strokeStyle = rgba(MAIN, 0.5 * glow + 0.15);
      ctx.lineWidth = 7 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.08 * breathe, 0, Math.PI * 2); ctx.stroke();
      // extreme-gravity hot arc across the top rim
      ctx.shadowColor = rgba(PHOTON, 1);
      ctx.shadowBlur = 26 * s;
      ctx.strokeStyle = rgba(PHOTON, 0.9 * glow + 0.1);
      ctx.lineWidth = 4.2 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.02 * breathe, Math.PI * 1.05, Math.PI * 1.95); ctx.stroke();
      if (os === "speaking") {
        ctx.strokeStyle = rgba(CYAN, 0.2 + 0.2 * Math.sin(pulse * 2));
        ctx.lineWidth = 2 * s;
        ctx.beginPath(); ctx.arc(cx, cy, R * 1.06, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
      ctx.globalCompositeOperation = "source-over";

      // Layers 04/05 — FRONT half of the disk sweeping across the void
      drawDisk(true, glow);

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  // Dragging the core is only possible in edit mode (Core menu → Edit).
  // Position persists on Save, so AURA is exactly where you left her on relaunch.
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!editing) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = e.clientX - (rect.left + rect.width / 2);
    const dy = e.clientY - (rect.top + rect.height / 2);
    const horizonR = (size / REF) * HORIZON;
    if (Math.hypot(dx, dy) > horizonR * 1.25) return; // only the core itself, not empty space
    e.preventDefault();
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: posX, oy: posY };
  };

  useEffect(() => {
    const move = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
      // keep at least half the core inside the stage
      const limX = Math.max(0, stageDims.current.w / 2 - 40);
      const limY = Math.max(0, stageDims.current.h / 2 - 40);
      setCfg({
        x: Math.max(-limX, Math.min(limX, d.ox + dx)),
        y: Math.max(-limY, Math.min(limY, d.oy + dy)),
      });
    };
    const up = () => { dragRef.current = null; };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [setCfg]);

  return (
    <div
      ref={wrapRef}
      className="bh-wrap"
      style={{ transform: `translate(calc(-50% + ${posX}px), calc(-50% + ${posY}px))` }}
    >
      <canvas
        ref={canvasRef}
        className={"bh-canvas" + (editing ? " bh-canvas--edit" : "")}
        onMouseDown={handleMouseDown}
        title={editing ? "Drag to move AURA core" : undefined}
      />
      {editing && <div className="bh-editbadge">EDIT MODE — drag to move</div>}
    </div>
  );
}
