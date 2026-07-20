import { useEffect, useRef, useState } from "react";
import type { AuraState } from "../types";
import { useCoreStore } from "../stores/coreStore";
import { usePlanetStore } from "../stores/planetStore";
import { journey } from "./Home/ScrollController";
import { MODELS } from "../data/models";

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
// Realistic ring dust — neutral space tones (sand, grey ice, white sparkle),
// NOT the planet's color. Like the real thing.
const DUST_SAND = "218,208,186";
const DUST_GREY = "198,200,212";
const DUST_ICE = "255,250,240";

const rgba = (c: string, a: number) => `rgba(${c},${a < 0 ? 0 : a > 1 ? 1 : a})`;

type OrbState = "idle" | "listening" | "thinking" | "speaking" | "focus" | "alert";
const SPIN: Record<OrbState, number> = { idle: 1, listening: 1.6, thinking: 5, speaking: 2.4, focus: 0.7, alert: 7 };
const GLOW: Record<OrbState, number> = { idle: 0.55, listening: 0.72, thinking: 0.95, speaking: 0.85, focus: 0.45, alert: 1 };

const REF = 680;         // reference composition size (px)
// Fixed orbit slots (fractions of the guide radius). One planet per slot;
// dropping a planet on a taken slot swaps the occupant onto the vacated one.
// Pushed outward so the enlarged horizon keeps generous clearance to the
// first orbit even at bigger Core / Planet sizes.
const SLOT_FRACS = [0.74, 0.82, 0.9, 0.98, 1.06, 1.14, 1.22, 1.3, 1.38];
const MAX = 420;         // on-screen cap — keeps the core compact in the stage
const HORIZON = 168;     // event-horizon radius (≈40% larger — cinematic redesign)
const SQUASH = 0.3;      // accretion-disk tilt
const RINGS = 12;        // orbital guide count, per spec

interface Props {
  state: AuraState;
  size?: number;
  activeModelId?: string | null; // planet of the model that last answered
}

interface DiskP { a: number; r: number; sp: number; sz: number; c: string; al: number; }
interface Strand { r: number; w: number; c: string; a0: number; len: number; al: number; sp: number; }
interface Infall { a: number; r: number; sp: number; }
interface Node { ring: number; a: number; tw: number; big: boolean; }

export default function BlackHole({ state, size: sizeProp, activeModelId = null }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;
  const activeRef = useRef<string | null>(activeModelId);
  activeRef.current = activeModelId;

  // Planet settings (Planets menu in the top bar) — read live via ref so the
  // sliders act instantly without restarting the render loop.
  const pOrbit = usePlanetStore((st) => st.orbit);
  const pSize = usePlanetStore((st) => st.size);
  const pSpeed = usePlanetStore((st) => st.speed);
  const pRings = usePlanetStore((st) => st.rings);
  const pEditing = usePlanetStore((st) => st.editing);
  const slotsMap = usePlanetStore((st) => st.slots);
  const metaMap = usePlanetStore((st) => st.meta);
  const setSlots = usePlanetStore((st) => st.setSlots);
  const planetCfgRef = useRef({ orbit: 1, size: 1, speed: 1, rings: 1 });
  planetCfgRef.current = { orbit: pOrbit / 100, size: pSize / 100, speed: pSpeed / 100, rings: pRings / 100 };
  const pEditingRef = useRef(pEditing);
  pEditingRef.current = pEditing;
  const slotsRef = useRef<Record<string, number>>(slotsMap);
  const metaRef = useRef(metaMap);
  metaRef.current = metaMap;
  const setSlotsRef = useRef(setSlots);
  setSlotsRef.current = setSlots;
  // live geometry + planet objects, for hit-testing and drag
  const planetsRef = useRef<Array<{ id: string; a: number; x: number; y: number; curR: number; def: number }>>([]);
  const geomRef = useRef({ cx: 0, cy: 0, rMax: 1, maxR: 1, minR: 0, mul: 1 });
  const planetDragRef = useRef<string | null>(null);
  const dragSlotRef = useRef<number | null>(null);
  if (!planetDragRef.current) slotsRef.current = slotsMap; // sync unless mid-drag

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
    // The canvas covers the ENTIRE app (viewport diagonal), so planets and
    // orbits are never cut off no matter where the core sits or how far out
    // an orbit goes. DPR is trimmed on huge canvases to keep memory sane.
    const D = Math.ceil(Math.hypot(window.innerWidth, window.innerHeight));
    const DPR = Math.min(window.devicePixelRatio || 1, D > 1700 ? 1.5 : 2);
    canvas.width = D * DPR;
    canvas.height = D * DPR;
    canvas.style.width = D + "px";
    canvas.style.height = D + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    const s = size / REF;
    const cx = D / 2, cy = D / 2;
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

    // ---- Nebula inflow clouds — matter being pulled in, stretched, absorbed
    interface Cloud { a: number; r: number; sz: number; c: string; al: number; wsp: number; }
    const cloudCols = [MAIN, INNER, BLUE, PINK, DEEP];
    const clouds: Cloud[] = Array.from({ length: 14 }, (_, i) => ({
      a: Math.random() * Math.PI * 2,
      r: 1.8 + Math.random() * 2.6,
      sz: 55 + Math.random() * 85,
      c: cloudCols[i % cloudCols.length],
      al: 0.05 + Math.random() * 0.08,
      wsp: 0.05 + Math.random() * 0.06,
    }));

    // ---- Vortex streaks — the whole universe swirling around her ----------
    interface Vort { a: number; r: number; sp: number; sz: number; c: string; al: number; }
    const vortex: Vort[] = Array.from({ length: 260 }, () => ({
      a: Math.random() * Math.PI * 2,
      r: 1.6 + Math.random() * 2.8,
      sp: 0.1 + Math.random() * 0.25,
      sz: 0.6 + Math.random() * 1.6,
      c: pick(),
      al: 0.1 + Math.random() * 0.3,
    }));
    const VSQ = 0.78; // the outer vortex is rounder than the flat disk

    // ---- Planet system: AI models orbiting AURA in harmonic synchrony ------
    // Per the design sheet: equal angular spacing, own orbit + color + nature,
    // slow orbits (60–120s), rim lit by the core, shadow side away, dashed
    // orbit guides. The ACTIVE model (last answered) orbits faster + glows.
    const hexRgb = (h: string) => {
      const n = parseInt(h.slice(1), 16);
      return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
    };
    // Pre-rendered surface texture per planet — cloudy patches, light storms
    // and swirl bands in the planet's own color (like the PLANET DETAILS
    // cards), rotated live for the "rotates on its own axis" motion.
    const makeTexture = (rgb: string) => {
      const T = 128;
      const tc = document.createElement("canvas");
      tc.width = T; tc.height = T;
      const t = tc.getContext("2d")!;
      const c0 = T / 2;
      const base = t.createRadialGradient(c0, c0, T * 0.1, c0, c0, T / 2);
      base.addColorStop(0, `rgba(${rgb},1)`);
      base.addColorStop(0.7, `rgba(${rgb},0.9)`);
      base.addColorStop(1, `rgba(${rgb},0.75)`);
      t.fillStyle = base;
      t.beginPath(); t.arc(c0, c0, T / 2, 0, Math.PI * 2); t.fill();
      t.save();
      t.beginPath(); t.arc(c0, c0, T / 2, 0, Math.PI * 2); t.clip();
      // cloud patches — dark continents + bright storms
      for (let i = 0; i < 30; i++) {
        const a = Math.random() * Math.PI * 2, rr = Math.random() * T * 0.48;
        const x = c0 + Math.cos(a) * rr, y = c0 + Math.sin(a) * rr;
        const sr = T * (0.05 + Math.random() * 0.17);
        const dark = Math.random() < 0.55;
        const sg = t.createRadialGradient(x, y, 0, x, y, sr);
        sg.addColorStop(0, dark ? "rgba(0,0,14,0.4)" : "rgba(255,255,255,0.32)");
        sg.addColorStop(1, "rgba(0,0,0,0)");
        t.fillStyle = sg;
        t.beginPath(); t.arc(x, y, sr, 0, Math.PI * 2); t.fill();
      }
      // faint swirl bands
      for (let i = 0; i < 4; i++) {
        t.strokeStyle = `rgba(255,255,255,${0.05 + Math.random() * 0.07})`;
        t.lineWidth = T * (0.02 + Math.random() * 0.035);
        t.beginPath();
        t.ellipse(c0, c0, T * 0.46, T * (0.12 + Math.random() * 0.24),
                  Math.random() * Math.PI, 0, Math.PI * 2);
        t.stroke();
      }
      t.restore();
      return tc;
    };

    interface Planet {
      id: string; name: string; role: string; c: string;
      a: number; def: number; w: number; pr: number;
      tex: HTMLCanvasElement; rot: number; rw: number;
      x: number; y: number; curR: number;
      ring: boolean; tilt: number;
      ringA: number; ringW: number;
      ringDust: Array<{ ang: number; rf: number; sz: number; al: number; t: string }>;
    }
    const planets: Planet[] = MODELS.map((m, i) => ({
      id: m.id,
      name: m.name,
      role: m.role,
      c: hexRgb(m.color),
      a: (i * Math.PI * 2) / MODELS.length + 0.4, // equal spacing start
      def: i % SLOT_FRACS.length,                  // default orbit slot
      w: (Math.PI * 2) / (70 + (i % 5) * 12),     // 70–118s per revolution
      pr: 11 + (i % 3) * 3,                        // bigger, like the cards
      tex: makeTexture(hexRgb(m.color)),
      rot: Math.random() * Math.PI * 2,
      rw: (Math.PI * 2) / (25 + (i % 4) * 6),      // self-rotation 25–43s
      x: 0, y: 0, curR: 0,                          // live position (hit-testing)
      ring: !!m.ring,                                // paid LLMs wear rings
      tilt: -0.45 + (i % 3) * 0.35,
      ringA: Math.random() * Math.PI * 2,
      ringW: (Math.PI * 2) / (14 + (i % 4) * 4),     // ring revolves in 14–26s
      ringDust: !m.ring ? [] : Array.from({ length: 95 }, () => {
        const roll = Math.random();
        return {
          ang: Math.random() * Math.PI * 2,
          rf: 0.82 + Math.random() * 0.36,           // spread across the band
          sz: roll > 0.93 ? 1.6 + Math.random() : 0.5 + Math.random() * 0.8,
          al: roll > 0.93 ? 0.85 : 0.2 + Math.random() * 0.45, // comets sparkle
          t: roll > 0.93 ? DUST_ICE : roll > 0.5 ? DUST_SAND : DUST_GREY,
        };
      }),
    }));
    planetsRef.current = planets as never[];

    // ---- Orbital guides + node dots ----------------------------------------
    const rMin = R * 1.4, rMax = size / 2 - 4 * s;
    geomRef.current = { cx, cy, rMax, maxR: D / 2 - 28 * s, minR: R * 1.25, mul: 1 };
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
      if (front) ctx.rect(0, cy, D, D / 2 + 2);
      else ctx.rect(0, 0, D, cy);
      ctx.clip();
      ctx.globalCompositeOperation = "lighter";

      // Volumetric plasma — THREE stacked layers at different tilts/radii so
      // the disk reads as a thick 3D torus, not a flat ring. Each layer is a
      // squashed radial haze; together they build depth and body.
      const g0 = 0.5 + 0.6 * glow;
      const layer = (sq: number, rad: number, cols: Array<[string, number]>) => {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(1, sq);
        const hz = ctx.createRadialGradient(0, 0, R * 0.9, 0, 0, R * rad);
        hz.addColorStop(0, rgba(cols[0][0], cols[0][1] * g0));
        hz.addColorStop(0.35, rgba(cols[1][0], cols[1][1] * g0));
        hz.addColorStop(0.65, rgba(cols[2][0], cols[2][1] * g0));
        hz.addColorStop(1, rgba(cols[2][0], 0));
        ctx.fillStyle = hz;
        ctx.beginPath(); ctx.arc(0, 0, R * rad, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      };
      layer(SQUASH * 1.5, 3.4, [[PHOTON, 0.16], [INNER, 0.16], [MAIN, 0.08]]);   // thick upper haze
      layer(SQUASH, 3.1, [[HOT, 0.4], [MAIN, 0.26], [MAGENTA, 0.12]]);            // main body
      layer(SQUASH * 0.7, 2.7, [[PHOTON, 0.22], [HOT, 0.2], [INNER, 0.1]]);       // hot mid-plane

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

      // strands are SPIRALS, not flat rings — every stream visibly bends
      // inward toward the horizon as it sweeps (light curving near her)
      for (const st of strands) {
        ctx.beginPath();
        const STEPS = 14;
        for (let k = 0; k <= STEPS; k++) {
          const t = k / STEPS;
          const ang = st.a0 + st.len * t;
          const rr = st.r * R * (1 - 0.17 * t); // radius shrinks along the arc
          const px = cx + rr * Math.cos(ang);
          const py = cy + rr * SQUASH * Math.sin(ang);
          if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
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
      // off in the descent → the core sleeps until the universe returns
      if (journey.p > 0.55) {
        last = now;
        raf = requestAnimationFrame(draw);
        return;
      }
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

      ctx.clearRect(0, 0, D, D);

      // Layered glow — outer soft purple bloom fading naturally into space,
      // built from the horizon radius so it grows with the Core.
      ctx.globalCompositeOperation = "lighter";
      const bloom = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 5.2);
      bloom.addColorStop(0, rgba(MAIN, 0.16 * glow + 0.05));
      bloom.addColorStop(0.4, rgba(MAIN, 0.07 * glow));
      bloom.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = bloom;
      ctx.beginPath(); ctx.arc(cx, cy, R * 5.2, 0, Math.PI * 2); ctx.fill();

      // Space-time ripples — extremely soft concentric gravity waves, almost
      // invisible, just enough to make space feel warped. Slowly expanding.
      for (let i = 0; i < 4; i++) {
        const phase = (pulse * 0.12 + i * 0.25) % 1;
        const rr = R * (1.9 + phase * 3.4);
        const a = 0.05 * (1 - phase) * glow;
        ctx.strokeStyle = rgba(INNER, a);
        ctx.lineWidth = 1.2 * s;
        ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
      }
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

      // ---- Nebula clouds spiralling IN — stretched tangentially as they
      // fall, fading as the horizon takes them, reborn far outside.
      ctx.globalCompositeOperation = "lighter";
      for (const cl of clouds) {
        cl.a += cl.wsp * dt * (1.8 / cl.r);
        cl.r -= dt * 0.055;
        if (cl.r < 1.3) { cl.r = 4.2 + Math.random() * 0.4; cl.a = Math.random() * Math.PI * 2; }
        const fade = Math.min(1, (cl.r - 1.3) / 0.55) * Math.min(1, (4.5 - cl.r) / 0.6);
        if (fade <= 0) continue;
        const cxx = cx + cl.r * R * Math.cos(cl.a);
        const cyy = cy + cl.r * R * VSQ * Math.sin(cl.a);
        const csz = cl.sz * s * (0.6 + 0.4 * Math.min(1, cl.r / 3));
        ctx.save();
        ctx.translate(cxx, cyy);
        ctx.rotate(cl.a + Math.PI / 2);
        ctx.scale(1.9, 1); // stretched along its fall — visibly bending in
        const cg = ctx.createRadialGradient(0, 0, 0, 0, 0, csz);
        cg.addColorStop(0, rgba(cl.c, cl.al * fade * (0.6 + 0.5 * glow)));
        cg.addColorStop(1, rgba(cl.c, 0));
        ctx.fillStyle = cg;
        ctx.beginPath(); ctx.arc(0, 0, csz, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }

      // ---- Vortex streaks — everything around her is in motion, curving
      // toward the horizon (Kepler-fast inside, slow outside).
      ctx.lineCap = "round";
      for (const v of vortex) {
        v.a += v.sp * dt * (1.5 / v.r);
        v.r -= dt * 0.04;
        if (v.r < 1.5) { v.r = 4.4; v.a = Math.random() * Math.PI * 2; }
        const fade = Math.min(1, (v.r - 1.5) / 0.4);
        if (fade <= 0) continue;
        const rr = v.r * R;
        const x1 = cx + rr * Math.cos(v.a);
        const y1 = cy + rr * VSQ * Math.sin(v.a);
        const a2 = v.a + 0.045 + 0.02 / v.r;
        const x2 = cx + rr * Math.cos(a2) * 0.995; // tiny inward bend per streak
        const y2 = cy + rr * VSQ * Math.sin(a2) * 0.995;
        ctx.strokeStyle = rgba(v.c, v.al * fade * (0.5 + 0.5 * glow));
        ctx.lineWidth = (v.sz * s) / 1.6;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
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

      // Layered inner glow leaking from the core: white-hot rim → vibrant
      // violet → soft purple. Three tiers, additive, sitting just outside R.
      ctx.globalCompositeOperation = "lighter";
      const ig = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.95);
      ig.addColorStop(0, rgba(INNER, 0));
      ig.addColorStop(0.08, rgba(PHOTON, 0.5 * glow + 0.12)); // white-hot inner
      ig.addColorStop(0.24, rgba(INNER, 0.55 * glow + 0.12)); // vibrant violet
      ig.addColorStop(0.55, rgba(MAIN, 0.24 * glow));         // soft purple
      ig.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = ig;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.95, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";

      // Layer 01 — event horizon: pure, textureless black void that absorbs
      // all light. A soft dark falloff just outside sinks the disk's inner
      // edge into it, giving the void real depth against the plasma.
      const edge = ctx.createRadialGradient(cx, cy, R * 0.92 * breathe, cx, cy, R * 1.14 * breathe);
      edge.addColorStop(0, "rgba(0,0,0,1)");
      edge.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = edge;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.14 * breathe, 0, Math.PI * 2); ctx.fill();
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

      // Gravitational lensing — light bending around the void, like the
      // reference: the far side of the disk seen wrapped over the top and
      // under the bottom, forming a luminous ring around the whole horizon.
      ctx.globalCompositeOperation = "lighter";
      const lens = ctx.createRadialGradient(cx, cy, R * 1.02, cx, cy, R * 1.85);
      lens.addColorStop(0, rgba(HOT, 0.85 * glow + 0.16));
      lens.addColorStop(0.3, rgba(INNER, 0.42 * glow + 0.06));
      lens.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = lens;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.85, 0, Math.PI * 2);
      ctx.arc(cx, cy, R * 1.0, 0, Math.PI * 2, true);
      ctx.fill();
      // Einstein ring — thin bright circle where background light wraps fully
      // around the void. Sharp, elegant, not sci-fi loud.
      ctx.strokeStyle = rgba(SOFT, 0.3 * glow + 0.08);
      ctx.lineWidth = 1.4 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.32 * breathe, 0, Math.PI * 2); ctx.stroke();
      // white-hot inner edge wrapping the ENTIRE void
      ctx.strokeStyle = rgba(PHOTON, 0.4 * glow + 0.08);
      ctx.lineWidth = 3.5 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.06 * breathe, 0, Math.PI * 2); ctx.stroke();
      // bent-light arcs blazing over the top and under the bottom
      ctx.shadowColor = rgba(HOT, 1);
      ctx.shadowBlur = 24 * s;
      ctx.strokeStyle = rgba(SOFT, 0.65 * glow + 0.12);
      ctx.lineWidth = 7 * s;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.16, Math.PI * 1.12, Math.PI * 1.88); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.16, Math.PI * 0.12, Math.PI * 0.88); ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.globalCompositeOperation = "source-over";

      // Layers 04/05 — FRONT half of the disk sweeping across the void
      drawDisk(true, glow);

      // ---- Planet system ------------------------------------------------
      const activeId = activeRef.current;
      const pcfg = planetCfgRef.current;
      const editMode = pEditingRef.current;
      const slotR = (si: number) =>
        Math.min(D / 2 - 28 * s, rMax * SLOT_FRACS[si] * pcfg.orbit);

      // visible orbit rings — one slot per planet, brighter while editing,
      // the hovered slot lights up cyan during a drag
      for (let si = 0; si < SLOT_FRACS.length; si++) {
        const rr = slotR(si);
        const hovered = planetDragRef.current !== null && dragSlotRef.current === si;
        ctx.setLineDash([5 * s, 9 * s]);
        ctx.beginPath();
        ctx.arc(cx, cy, rr, 0, Math.PI * 2);
        ctx.strokeStyle = hovered ? rgba(CYAN, 0.65) : rgba(INNER, editMode ? 0.45 : 0.22);
        ctx.lineWidth = hovered ? 1.8 : 1.2;
        ctx.stroke();
        ctx.setLineDash([]);
      }

      for (const pl of planets) {
        const isAct = pl.id === activeId;
        const dragging = planetDragRef.current === pl.id;
        if (!dragging) {
          pl.a = (pl.a + pl.w * pcfg.speed * (isAct ? 3.5 : 1) * dt) % (Math.PI * 2);
        }
        const si = dragging && dragSlotRef.current !== null
          ? dragSlotRef.current
          : (slotsRef.current[pl.id] ?? pl.def);
        const orbitR = slotR(si);
        const x = cx + orbitR * Math.cos(pl.a);
        const y = cy + orbitR * Math.sin(pl.a);
        const pr = pl.pr * s * pcfg.size * (isAct ? 1.25 : 1);
        pl.x = x; pl.y = y; pl.curR = pr; // published for hit-testing

        // atmosphere glow
        ctx.globalCompositeOperation = "lighter";
        const atm = ctx.createRadialGradient(x, y, pr * 0.4, x, y, pr * 3);
        atm.addColorStop(0, rgba(pl.c, isAct ? 0.6 : 0.35));
        atm.addColorStop(1, rgba(pl.c, 0));
        ctx.fillStyle = atm;
        ctx.beginPath(); ctx.arc(x, y, pr * 3, 0, Math.PI * 2); ctx.fill();
        ctx.globalCompositeOperation = "source-over";

        // Saturn ring (paid LLMs) — revolving band of neutral space dust
        // (sand/grey/ice, single-toned like real rings), well outside the
        // body, scaled by the Rings slider. Rear half passes behind.
        const rgMul = Math.max(0.6, pcfg.rings);
        const rgx = pr * 2.2 * rgMul, rgy = pr * 0.66 * rgMul;
        const ringCt = Math.cos(pl.tilt), ringSt = Math.sin(pl.tilt);
        const drawRingDust = (frontHalf: boolean) => {
          for (const dd of pl.ringDust) {
            const th = dd.ang + pl.ringA;
            const sn = Math.sin(th);
            if (frontHalf ? sn < 0 : sn >= 0) continue;
            const ex = Math.cos(th) * rgx * dd.rf;
            const ey = sn * rgy * dd.rf;
            const px = x + ex * ringCt - ey * ringSt;
            const py = y + ex * ringSt + ey * ringCt;
            ctx.fillStyle = rgba(dd.t, dd.al * (frontHalf ? 1 : 0.55));
            ctx.beginPath();
            ctx.arc(px, py, dd.sz * s * Math.max(0.7, Math.min(2, pcfg.size)), 0, Math.PI * 2);
            ctx.fill();
          }
        };
        if (pl.ring) {
          pl.ringA += pl.ringW * dt; // the ring itself revolves
          ctx.globalCompositeOperation = "lighter";
          // faint continuous dust band (rear half)
          ctx.strokeStyle = rgba(DUST_SAND, 0.16);
          ctx.lineWidth = pr * 0.3;
          ctx.beginPath();
          ctx.ellipse(x, y, rgx, rgy, pl.tilt, Math.PI, Math.PI * 2);
          ctx.stroke();
          drawRingDust(false);
          ctx.globalCompositeOperation = "source-over";
        }

        // body — textured surface (clouds/storms/bands), self-rotating
        pl.rot += pl.rw * dt;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(pl.rot);
        ctx.beginPath(); ctx.arc(0, 0, pr, 0, Math.PI * 2); ctx.clip();
        ctx.drawImage(pl.tex, -pr, -pr, pr * 2, pr * 2);
        ctx.restore();

        // shading — lit by the core, shadow side facing away
        const ux = (cx - x) / orbitR, uy = (cy - y) / orbitR;
        const shade = ctx.createLinearGradient(
          x + ux * pr, y + uy * pr, x - ux * pr, y - uy * pr);
        shade.addColorStop(0, "rgba(255,255,255,0.2)");
        shade.addColorStop(0.45, "rgba(0,0,0,0)");
        shade.addColorStop(1, "rgba(3,3,12,0.8)");
        ctx.fillStyle = shade;
        ctx.beginPath(); ctx.arc(x, y, pr, 0, Math.PI * 2); ctx.fill();

        // rim light on the core-facing edge (3D depth)
        const toCore = Math.atan2(cy - y, cx - x);
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = "rgba(255,255,255,0.5)";
        ctx.lineWidth = 1.2 * s;
        ctx.beginPath(); ctx.arc(x, y, pr * 0.96, toCore - 1.1, toCore + 1.1); ctx.stroke();

        // Saturn ring — front half sweeping over the body
        if (pl.ring) {
          ctx.strokeStyle = rgba(DUST_SAND, 0.26);
          ctx.lineWidth = pr * 0.3;
          ctx.beginPath();
          ctx.ellipse(x, y, rgx, rgy, pl.tilt, 0, Math.PI);
          ctx.stroke();
          drawRingDust(true);
        }

        // active halo pulse
        if (isAct) {
          ctx.strokeStyle = rgba(pl.c, 0.35 + 0.25 * Math.sin(pulse * 2));
          ctx.lineWidth = 1.6 * s;
          ctx.beginPath(); ctx.arc(x, y, pr * 1.8, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.globalCompositeOperation = "source-over";

        // label — NAME in the planet's color, archetype under it (card style).
        // User-edited names/roles (Planets menu) take precedence.
        const meta = metaRef.current[pl.id] || {};
        const shownName = meta.name || pl.name;
        const shownRole = meta.role || pl.role;
        ctx.textAlign = "center";
        ctx.font = `700 ${Math.max(9, 10.5 * s)}px "Exo 2", sans-serif`;
        ctx.fillStyle = rgba(pl.c, isAct ? 1 : 0.8);
        ctx.fillText(shownName, x, y + pr + 13 * s);
        ctx.font = `400 ${Math.max(8, 8.5 * s)}px "Exo 2", sans-serif`;
        ctx.fillStyle = rgba("236,234,254", isAct ? 0.85 : 0.5);
        ctx.fillText(shownRole, x, y + pr + 24 * s);
        if (isAct) {
          ctx.font = `700 ${Math.max(7, 8 * s)}px "Exo 2", sans-serif`;
          ctx.fillStyle = "rgba(70,232,138,0.95)";
          ctx.fillText("● ACTIVE", x, y + pr + 35 * s);
        }
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  // Dragging the core is only possible in edit mode (Core menu → Edit).
  // Position persists on Save, so AURA is exactly where you left her on relaunch.
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();

    // Planet edit mode: grab a planet and drop it on ANY orbit.
    if (pEditingRef.current) {
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      for (const pl of planetsRef.current) {
        if (Math.hypot(px - pl.x, py - pl.y) <= (pl.curR || 12) + 10) {
          e.preventDefault();
          planetDragRef.current = pl.id;
          return;
        }
      }
    }

    if (!editing) return;
    const dx = e.clientX - (rect.left + rect.width / 2);
    const dy = e.clientY - (rect.top + rect.height / 2);
    const horizonR = (size / REF) * HORIZON;
    if (Math.hypot(dx, dy) > horizonR * 1.25) return; // only the core itself, not empty space
    e.preventDefault();
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: posX, oy: posY };
  };

  // Planet drag: the pointer picks an orbit SLOT (nearest ring). On release,
  // the planet takes that slot — and if another planet lived there, the two
  // swap, so it's always one planet per orbit. Persisted by Save.
  useEffect(() => {
    const nearestSlot = (r: number) => {
      const g = geomRef.current;
      const mul = planetCfgRef.current.orbit || 1;
      let best = 0, bestD = Infinity;
      for (let si = 0; si < SLOT_FRACS.length; si++) {
        const rr = Math.min(g.maxR, g.rMax * SLOT_FRACS[si] * mul);
        const d = Math.abs(r - rr);
        if (d < bestD) { bestD = d; best = si; }
      }
      return best;
    };

    const move = (e: MouseEvent) => {
      const id = planetDragRef.current;
      if (!id) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const g = geomRef.current;
      const px = e.clientX - rect.left - g.cx;
      const py = e.clientY - rect.top - g.cy;
      const pl = planetsRef.current.find((p) => p.id === id);
      if (!pl) return;
      pl.a = Math.atan2(py, px);
      dragSlotRef.current = nearestSlot(Math.hypot(px, py));
    };

    const up = () => {
      const id = planetDragRef.current;
      if (!id) return;
      const target = dragSlotRef.current;
      planetDragRef.current = null;
      dragSlotRef.current = null;
      if (target === null) return;
      const resolve = (pid: string) =>
        slotsRef.current[pid] ??
        (planetsRef.current.find((p) => p.id === pid)?.def ?? 0);
      const prev = resolve(id);
      if (prev === target) return;
      const next: Record<string, number> = { ...slotsRef.current };
      // whoever held the target slot inherits the vacated one
      const occupant = planetsRef.current.find((p) => p.id !== id && resolve(p.id) === target);
      next[id] = target;
      if (occupant) next[occupant.id] = prev;
      slotsRef.current = next;
      setSlotsRef.current(next);
    };

    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

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
        className={"bh-canvas" + (editing || pEditing ? " bh-canvas--edit" : "")}
        onMouseDown={handleMouseDown}
        title={
          pEditing ? "Drag any planet to a new orbit"
          : editing ? "Drag to move AURA core"
          : undefined
        }
      />
      {editing && <div className="bh-editbadge">EDIT MODE — drag to move</div>}
      {!editing && pEditing && <div className="bh-editbadge">PLANET EDIT — drag planets onto any orbit</div>}
    </div>
  );
}
