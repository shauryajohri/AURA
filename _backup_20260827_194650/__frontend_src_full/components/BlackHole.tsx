import { useEffect, useRef, useState } from "react";
import type { AuraState } from "../types";
import { useCoreStore } from "../stores/coreStore";
import { usePlanetStore } from "../stores/planetStore";
import { useSettingsStore } from "../stores/settingsStore";
import { MODELS } from "../data/models";

// ============================================================================
// AURA CORE — Black Hole, built 1:1 from the design spec:
//   Event horizon 240px · 12 orbital guides · Main #7D3CFF · Inner #A76DFF
//   Photon ring #F3D9FF · Disk: purple/pink/blue/orange · 90s/revolution
//   Subtle pulse · 20% soft purple bloom · gravitational lens arcs
// Layer order: bloom → guides → lens → REAR disk → inner glow →
//              event horizon (pure black) → photon ring → FRONT disk
// ============================================================================

// Monochrome violet palette — matched to the reference still: a black void,
// one white-hot ring wrapped in electric purple, and nothing else in the way.
const MAIN = "125,60,255";    // #7D3CFF electric purple
const INNER = "167,109,255";  // #A76DFF inner glow
const PHOTON = "243,217,255"; // #F3D9FF near-white ring light
const SOFT = "196,150,255";   // pale violet wisps
const DEEP = "139,101,255";   // #8B65FF
const WHITE = "255,252,255";  // white-hot sparks / beam core
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
const RINGS = 12;        // orbital guide count, per spec

interface Props {
  state: AuraState;
  size?: number;
  activeModelId?: string | null; // planet of the model that last answered
}

/** One crackling electric wisp swirling around the void. */
interface Filament {
  r: number; a0: number; len: number; w: number; c: string;
  al: number; sp: number; ph: number; amp: number;
}
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

  // Sanctuary settings (backend app_settings, synced by settingsStore).
  // `density` sizes the particle arrays, so it has to be a real dependency of
  // the setup effect — changing it rebuilds the scene. Rotation and labels are
  // read per-frame through refs, so those apply instantly without a rebuild.
  const density = useSettingsStore((st) => st.density);
  const rotationMul = useSettingsStore((st) => st.rotationMul);
  const showLabels = useSettingsStore((st) => st.showLabels);
  const rotationMulRef = useRef(rotationMul);
  rotationMulRef.current = rotationMul;
  const showLabelsRef = useRef(showLabels);
  showLabelsRef.current = showLabels;
  // Orbit-line settings (Settings → Orbit Lines) — read per-frame via ref so
  // the sliders act live without a scene rebuild.
  const orbitMul = useSettingsStore((st) => st.orbitMul);
  const orbitWidthMul = useSettingsStore((st) => st.orbitWidthMul);
  const orbitStyle = useSettingsStore((st) => st.orbitStyle);
  const orbitCfgRef = useRef({ mul: 1, wmul: 1, style: "dashed" as string });
  orbitCfgRef.current = { mul: orbitMul, wmul: orbitWidthMul, style: orbitStyle };
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

    // Particle counts scale with the Sanctuary "particles" setting — this is
    // also the performance dial on a weaker GPU, so it's clamped rather than
    // trusted blindly.
    const dens = Math.max(0.1, Math.min(1.8, density));
    const N = (base: number) => Math.max(4, Math.round(base * dens));

    // ---- Electric filaments — the crackling violet wisps of the reference.
    // No accretion disk, no rainbow: just lightning-like plasma threads
    // hugging the ring, thinning out with distance. Each one is a curved arc
    // whose radius wobbles with two sine frequencies, so it reads as a
    // living electric tendril rather than a clean circle.
    const filaments: Filament[] = [];
    for (let i = 0; i < N(110); i++) {
      const rn = 1.05 + Math.pow(Math.random(), 1.8) * 0.95; // 1.05–2.0 R, dense near the ring
      const roll = Math.random();
      filaments.push({
        r: rn,
        a0: Math.random() * Math.PI * 2,
        len: 0.5 + Math.random() * 2.3,
        w: roll > 0.85 ? 0.4 + Math.random() * 0.5 : 0.6 + Math.random() * 1.3,
        c: roll > 0.92 ? WHITE : roll > 0.62 ? INNER : roll > 0.28 ? MAIN : SOFT,
        al: (0.08 + Math.random() * 0.26) + Math.max(0, 1.55 - rn) * 0.22,
        sp: 0.22 / rn + 0.07,
        ph: Math.random() * Math.PI * 2,
        amp: 0.015 + Math.random() * 0.05,
      });
    }

    // Faint concentric swirl echoes — the ghost circles around the still.
    const echoes = Array.from({ length: 6 }, (_, i) => ({
      r: 1.28 + i * 0.17 + Math.random() * 0.05,
      al: 0.055 - i * 0.007,
    }));

    // ---- Planet system: AI models orbiting AURA in harmonic synchrony ------
    // Per the design sheet: equal angular spacing, own orbit + color + nature,
    // slow orbits (60–120s), rim lit by the core, shadow side away, dashed
    // orbit guides. The ACTIVE model (last answered) orbits faster + glows.
    const hexRgb = (h: string) => {
      const n = parseInt(h.slice(1), 16);
      return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
    };
    // Pre-rendered surface texture per planet — the new card design: dark
    // volcanic rock threaded with glowing energy veins in the planet's own
    // color, a few white-hot nodes where the cracks meet, soft energy
    // patches underneath. Rotated live for the self-spin motion.
    const makeTexture = (rgb: string) => {
      const T = 160;
      const tc = document.createElement("canvas");
      tc.width = T; tc.height = T;
      const t = tc.getContext("2d")!;
      const c0 = T / 2;
      // dark rocky base, faintly lit from the upper-left in its own color
      const base = t.createRadialGradient(c0 - T * 0.14, c0 - T * 0.14, T * 0.06, c0, c0, T / 2);
      base.addColorStop(0, `rgba(${rgb},0.34)`);
      base.addColorStop(0.4, "rgba(18,16,30,1)");
      base.addColorStop(1, "rgba(5,4,12,1)");
      t.fillStyle = base;
      t.beginPath(); t.arc(c0, c0, T / 2, 0, Math.PI * 2); t.fill();
      t.save();
      t.beginPath(); t.arc(c0, c0, T / 2, 0, Math.PI * 2); t.clip();
      // rock mottling — dark craters and plates
      for (let i = 0; i < 34; i++) {
        const a = Math.random() * Math.PI * 2, rr = Math.random() * T * 0.48;
        const x = c0 + Math.cos(a) * rr, y = c0 + Math.sin(a) * rr;
        const sr = T * (0.04 + Math.random() * 0.13);
        const sg = t.createRadialGradient(x, y, 0, x, y, sr);
        sg.addColorStop(0, "rgba(0,0,8,0.4)");
        sg.addColorStop(1, "rgba(0,0,0,0)");
        t.fillStyle = sg;
        t.beginPath(); t.arc(x, y, sr, 0, Math.PI * 2); t.fill();
      }
      // soft molten patches glowing under the crust
      for (let i = 0; i < 5; i++) {
        const a = Math.random() * Math.PI * 2, rr = Math.random() * T * 0.4;
        const x = c0 + Math.cos(a) * rr, y = c0 + Math.sin(a) * rr;
        const sr = T * (0.1 + Math.random() * 0.16);
        const sg = t.createRadialGradient(x, y, 0, x, y, sr);
        sg.addColorStop(0, `rgba(${rgb},0.3)`);
        sg.addColorStop(1, "rgba(0,0,0,0)");
        t.fillStyle = sg;
        t.beginPath(); t.arc(x, y, sr, 0, Math.PI * 2); t.fill();
      }
      // glowing energy veins — jagged branching cracks of pure color
      t.lineCap = "round";
      t.shadowColor = `rgba(${rgb},1)`;
      for (let i = 0; i < 16; i++) {
        t.shadowBlur = 4 + Math.random() * 6;
        t.strokeStyle = `rgba(${rgb},${0.35 + Math.random() * 0.5})`;
        t.lineWidth = 0.6 + Math.random() * 1.5;
        t.beginPath();
        const a = Math.random() * Math.PI * 2, rr = Math.random() * T * 0.42;
        let x = c0 + Math.cos(a) * rr, y = c0 + Math.sin(a) * rr;
        t.moveTo(x, y);
        const segs = 4 + Math.floor(Math.random() * 5);
        for (let k = 0; k < segs; k++) {
          x += (Math.random() - 0.5) * T * 0.2;
          y += (Math.random() - 0.5) * T * 0.2;
          t.lineTo(x, y);
        }
        t.stroke();
      }
      // white-hot nodes where the cracks meet
      for (let i = 0; i < 9; i++) {
        const a = Math.random() * Math.PI * 2, rr = Math.random() * T * 0.4;
        t.shadowBlur = 5;
        t.shadowColor = "rgba(255,255,255,1)";
        t.fillStyle = `rgba(255,255,255,${0.4 + Math.random() * 0.5})`;
        t.beginPath();
        t.arc(c0 + Math.cos(a) * rr, c0 + Math.sin(a) * rr, 0.7 + Math.random() * 0.9, 0, Math.PI * 2);
        t.fill();
      }
      t.shadowBlur = 0;
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
      // card-design extras: faint local orbit circles + tiny travelling dots,
      // and one small grey moon of its own
      loc: number[];
      locDots: Array<{ ri: number; a: number; w: number }>;
      moonA: number; moonW: number; moonD: number; moonS: number;
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
      loc: [1.55, 1.95, 2.35].slice(0, 2 + (i % 2)),
      locDots: Array.from({ length: 3 + (i % 3) }, () => ({
        ri: Math.floor(Math.random() * 3),
        a: Math.random() * Math.PI * 2,
        w: 0.25 + Math.random() * 0.4,
      })),
      moonA: Math.random() * Math.PI * 2,
      moonW: (Math.PI * 2) / (16 + (i % 5) * 6),     // one lap in 16–40s
      moonD: 1.65 + (i % 3) * 0.32,
      moonS: 0.14 + (i % 3) * 0.04,
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

    let rot = 0, glow = 0.55, pulse = 0, raf = 0;
    let last = performance.now();

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const os: OrbState = (stateRef.current as OrbState) in SPIN ? (stateRef.current as OrbState) : "idle";
      const baseW = (Math.PI * 2) / 90; // spec: 90 s per revolution
      const w = baseW * SPIN[os] * rotationMulRef.current;
      rot = (rot + w * dt) % (Math.PI * 2);
      glow += (GLOW[os] * glowMulRef.current - glow) * Math.min(1, dt * 4);
      pulse += dt * (os === "speaking" ? 2.6 : os === "thinking" ? 1.8 : 0.9);
      const breathe = 1 + 0.015 * Math.sin(pulse); // spec: subtle pulse
      // The life signal — layered sines at odd frequencies make a natural
      // electric flicker that everything (ring, beam, hotspots, filaments)
      // drinks from, so the whole core visibly LIVES instead of idling.
      const flicker =
        0.84 +
        0.12 * Math.sin(pulse * 5.1) +
        0.05 * Math.sin(pulse * 12.7 + 1.3) +
        0.04 * Math.sin(pulse * 2.3 + 0.7);

      for (const f of filaments) f.a0 = (f.a0 + w * dt * f.sp * 6) % (Math.PI * 2);

      ctx.clearRect(0, 0, D, D);

      // Deep black backing — the core lives in true darkness, like the still.
      // This buries the busy universe video around the ring so the flare and
      // filaments are the only light sources near the void.
      const backing = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 3.6);
      backing.addColorStop(0, "rgba(0,0,0,0.97)");
      backing.addColorStop(0.5, "rgba(0,0,3,0.82)");
      backing.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = backing;
      ctx.beginPath(); ctx.arc(cx, cy, R * 3.6, 0, Math.PI * 2); ctx.fill();

      // Orbital guides — styled by Settings → Orbit Lines: brightness,
      // width and dash style are the user's, "hidden" removes them entirely.
      const ocfg = orbitCfgRef.current;
      const orbitsOn = ocfg.style !== "hidden" && ocfg.mul > 0.01;
      const orbitDash: number[] =
        ocfg.style === "solid" ? [] :
        ocfg.style === "dotted" ? [1.5 * s, 7 * s] : [5 * s, 9 * s];
      if (orbitsOn) {
        ctx.setLineDash(ocfg.style === "dashed" ? [] : orbitDash); // guides stay calm
        for (let i = 0; i < RINGS; i++) {
          ctx.beginPath();
          ctx.arc(cx, cy, guideR[i], 0, Math.PI * 2);
          ctx.strokeStyle = rgba(INNER, (0.035 + (i % 4 === 0 ? 0.02 : 0)) * ocfg.mul);
          ctx.lineWidth = 1 * ocfg.wmul;
          ctx.stroke();
        }
        ctx.setLineDash([]);
      }
      if (orbitsOn) for (const n of nodes) {
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

      ctx.globalCompositeOperation = "lighter";

      // ---- Faint concentric swirl echoes — breathing, not frozen: each one
      // slowly swells and dims on its own phase.
      for (let ei = 0; ei < echoes.length; ei++) {
        const e = echoes[ei];
        const er = R * e.r * (1 + 0.025 * Math.sin(pulse * 0.7 + ei * 1.9));
        ctx.beginPath();
        ctx.arc(cx, cy, er, 0, Math.PI * 2);
        ctx.strokeStyle = rgba(
          MAIN,
          Math.max(0, e.al) * (0.5 + 0.6 * glow) * (0.6 + 0.5 * Math.sin(pulse * 1.1 + ei)),
        );
        ctx.lineWidth = 1 * s;
        ctx.stroke();
      }

      // ---- Electric filaments — crackling violet plasma threads swirling
      // the void. Radius wobbles on two frequencies so each thread reads as
      // living lightning, not a clean circle. They rotate with the core.
      ctx.lineCap = "round";
      for (const f of filaments) {
        ctx.beginPath();
        const STEPS = 16;
        for (let k = 0; k <= STEPS; k++) {
          const t = k / STEPS;
          const ang = f.a0 + rot * 0.4 + f.len * t;
          const wob =
            1 +
            f.amp * Math.sin(ang * 7 + f.ph + pulse * 0.7) +
            f.amp * 0.6 * Math.sin(ang * 17 + f.ph * 2.3);
          const rr = f.r * wob * R;
          const px = cx + rr * Math.cos(ang);
          const py = cy + rr * Math.sin(ang);
          if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        // twinkle: every filament surges and fades on its own rhythm, so the
        // swirl constantly crackles instead of holding one exposure
        const tw = 0.55 + 0.45 * Math.sin(pulse * (1.3 + f.sp * 5) + f.ph * 3.1);
        ctx.strokeStyle = rgba(f.c, f.al * (0.4 + 0.7 * glow) * (0.5 + tw));
        ctx.lineWidth = f.w * s * (0.85 + 0.3 * tw);
        ctx.stroke();
      }

      // ---- Soft violet bloom breathing around the whole core
      const bloom = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, R * 2.7);
      bloom.addColorStop(0, rgba(MAIN, 0.15 * glow + 0.04));
      bloom.addColorStop(0.5, rgba(MAIN, 0.05 * glow));
      bloom.addColorStop(1, rgba(MAIN, 0));
      ctx.fillStyle = bloom;
      ctx.beginPath(); ctx.arc(cx, cy, R * 2.7, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";

      // ---- Event horizon: pure, textureless black that absorbs everything
      const edge = ctx.createRadialGradient(cx, cy, R * 0.9 * breathe, cx, cy, R * 1.1 * breathe);
      edge.addColorStop(0, "rgba(0,0,0,1)");
      edge.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = edge;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.1 * breathe, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#000";
      ctx.beginPath(); ctx.arc(cx, cy, R * breathe, 0, Math.PI * 2); ctx.fill();

      // ---- THE ring — matched to the reference: a white-hot filament
      // wrapped in electric violet, hugging the void tightly.
      const ringR = R * 1.03 * breathe;
      ctx.globalCompositeOperation = "lighter";
      ctx.save();
      // wide outer violet halo
      ctx.shadowColor = rgba(MAIN, 1);
      ctx.shadowBlur = 34 * s;
      ctx.strokeStyle = rgba(MAIN, 0.45 * glow + 0.18);
      ctx.lineWidth = 9 * s;
      ctx.beginPath(); ctx.arc(cx, cy, ringR * 1.06, 0, Math.PI * 2); ctx.stroke();
      // bright violet band
      ctx.shadowColor = rgba(INNER, 1);
      ctx.shadowBlur = 24 * s;
      ctx.strokeStyle = rgba(INNER, 0.7 * glow + 0.22);
      ctx.lineWidth = 4.5 * s;
      ctx.beginPath(); ctx.arc(cx, cy, ringR, 0, Math.PI * 2); ctx.stroke();
      // white-hot inner filament — brightness rides the flicker
      ctx.shadowColor = rgba(PHOTON, 1);
      ctx.shadowBlur = 15 * s;
      ctx.strokeStyle = rgba(PHOTON, (0.72 + 0.28 * glow) * flicker);
      ctx.lineWidth = 2.1 * s;
      ctx.beginPath(); ctx.arc(cx, cy, ringR * 0.985, 0, Math.PI * 2); ctx.stroke();
      // shimmer arcs — three hot segments racing around the ring at
      // different speeds/directions, so the ring is never the same twice.
      // Thinking spins the core fast, and these whip around with it.
      for (let si2 = 0; si2 < 3; si2++) {
        const dir2 = si2 % 2 ? -1 : 1;
        const sa = rot * (1.6 + si2 * 0.7) * dir2 + si2 * 2.3;
        const alen = 0.7 + 0.35 * Math.sin(pulse * 1.7 + si2 * 2.1);
        ctx.shadowBlur = 20 * s;
        ctx.strokeStyle = rgba(PHOTON, (0.2 + 0.22 * Math.sin(pulse * 2.4 + si2 * 1.4)) * glow + 0.05);
        ctx.lineWidth = 2.6 * s;
        ctx.beginPath(); ctx.arc(cx, cy, ringR, sa, sa + alen); ctx.stroke();
      }
      if (os === "speaking") {
        ctx.shadowBlur = 0;
        ctx.strokeStyle = rgba(CYAN, 0.18 + 0.18 * Math.sin(pulse * 2));
        ctx.lineWidth = 1.8 * s;
        ctx.beginPath(); ctx.arc(cx, cy, ringR * 1.12, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();

      // ---- Twin hotspots — the two blinding points where the beam pierces
      // the ring at the horizontal, exactly like the reference.
      for (const side of [-1, 1] as const) {
        const hx = cx + side * ringR;
        // real flicker: two incommensurate sines + the global life signal
        const flick =
          (1 + 0.13 * Math.sin(pulse * 3.2 + side * 1.7) + 0.07 * Math.sin(pulse * 8.9 + side * 0.6)) *
          (0.75 + 0.35 * flicker);
        const hr = R * 0.6 * flick;
        const g1 = ctx.createRadialGradient(hx, cy, 0, hx, cy, hr);
        g1.addColorStop(0, rgba(WHITE, (0.9 * glow + 0.1) * flicker));
        g1.addColorStop(0.16, rgba(PHOTON, (0.55 * glow + 0.1) * flicker));
        g1.addColorStop(0.45, rgba(INNER, 0.22 * glow + 0.03));
        g1.addColorStop(1, rgba(MAIN, 0));
        ctx.fillStyle = g1;
        ctx.beginPath(); ctx.arc(hx, cy, hr, 0, Math.PI * 2); ctx.fill();
      }

      // ---- The horizontal lens-flare beam — a razor of light across space,
      // layered from a wide violet haze down to a 1px white core.
      // The beam breathes: length swells slowly, brightness rides the
      // flicker, and while she SPEAKS it visibly pulses with her voice.
      const talk = os === "speaking" ? 0.25 * Math.sin(pulse * 6) : 0;
      const beamLen =
        Math.min(D * 0.46, R * 6.5) * (0.9 + 0.12 * Math.sin(pulse * 0.8) + talk * 0.3);
      const beam = (h: number, a0: number, cStr: string) => {
        const aa = a0 * flicker * (1 + talk);
        for (const side of [-1, 1] as const) {
          const hx = cx + side * ringR * 0.88;
          const g = ctx.createLinearGradient(hx, 0, hx + side * beamLen, 0);
          g.addColorStop(0, rgba(cStr, aa * (0.55 + 0.55 * glow)));
          g.addColorStop(0.3, rgba(cStr, aa * 0.4 * (0.55 + 0.55 * glow)));
          g.addColorStop(1, rgba(cStr, 0));
          ctx.fillStyle = g;
          ctx.fillRect(side === -1 ? hx - beamLen : hx, cy - h / 2, beamLen, h);
        }
      };
      const bh = 1 + 0.18 * (flicker - 0.84) + talk; // thickness lives too
      beam(30 * s * bh, 0.09, MAIN);    // wide violet haze
      beam(11 * s * bh, 0.26, INNER);   // mid glow
      beam(3.4 * s * bh, 0.85, PHOTON); // bright blade
      beam(1.4 * s, 1.0, WHITE);        // razor core stays razor

      // ---- Occasional gravitational pulse — every ~9s one luminous wave
      // rolls outward from the horizon and dissolves. Subtle, not a siren.
      {
        const period = 9;
        const gp = ((now / 1000) % period) / period; // 0..1
        if (gp < 0.55) {
          const t = gp / 0.55;
          const rr = R * (1.15 + t * 3.2);
          const a = 0.2 * (1 - t) * (1 - t) * (0.5 + 0.5 * glow);
          ctx.strokeStyle = rgba(INNER, a);
          ctx.lineWidth = (3 - 2 * t) * s;
          ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
          ctx.strokeStyle = rgba(PHOTON, a * 0.5);
          ctx.lineWidth = 1.2 * s;
          ctx.beginPath(); ctx.arc(cx, cy, rr * 0.94, 0, Math.PI * 2); ctx.stroke();
        }
      }
      ctx.globalCompositeOperation = "source-over";

      // ---- Planet system ------------------------------------------------
      const activeId = activeRef.current;
      const pcfg = planetCfgRef.current;
      const editMode = pEditingRef.current;
      const slotR = (si: number) =>
        Math.min(D / 2 - 28 * s, rMax * SLOT_FRACS[si] * pcfg.orbit);

      // visible orbit rings — one slot per planet. Styled by the Orbit Lines
      // settings; edit mode overrides them (you need to SEE where to drop a
      // planet), and the hovered slot lights up cyan during a drag.
      if (orbitsOn || editMode) {
        for (let si = 0; si < SLOT_FRACS.length; si++) {
          const rr = slotR(si);
          const hovered = planetDragRef.current !== null && dragSlotRef.current === si;
          ctx.setLineDash(editMode ? [5 * s, 9 * s] : orbitDash);
          ctx.beginPath();
          ctx.arc(cx, cy, rr, 0, Math.PI * 2);
          ctx.strokeStyle = hovered
            ? rgba(CYAN, 0.65)
            : rgba(INNER, editMode ? 0.45 : Math.min(0.6, 0.22 * ocfg.mul));
          ctx.lineWidth = hovered ? 1.8 : 1.2 * (editMode ? 1 : ocfg.wmul);
          ctx.stroke();
          ctx.setLineDash([]);
        }
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

        // local orbit circles — the card design's faint rings + tiny dots
        // travelling them, all in the planet's own color. They follow the
        // Orbit Lines setting too (dimmed, styled, or gone).
        if (orbitsOn) {
          ctx.setLineDash(orbitDash);
          for (let li = 0; li < pl.loc.length; li++) {
            ctx.strokeStyle = rgba(
              pl.c,
              (0.13 - li * 0.03) * (isAct ? 1.7 : 1) * Math.min(1.6, ocfg.mul),
            );
            ctx.lineWidth = 1 * ocfg.wmul;
            ctx.beginPath(); ctx.arc(x, y, pr * pl.loc[li], 0, Math.PI * 2); ctx.stroke();
          }
          ctx.setLineDash([]);
        }
        for (const ld of pl.locDots) {
          const ang = ld.a + pulse * ld.w;
          const lr = pr * pl.loc[ld.ri % pl.loc.length];
          ctx.fillStyle = rgba(pl.c, 0.35 + 0.3 * Math.sin(pulse * 2 + ld.a));
          ctx.beginPath();
          ctx.arc(x + Math.cos(ang) * lr, y + Math.sin(ang) * lr, 1.1 * s, 0, Math.PI * 2);
          ctx.fill();
        }
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

        // rim glow — the card design's luminous edge: a full colored ring,
        // blazing brightest on the core-facing side (that's the light source)
        const toCore = Math.atan2(cy - y, cx - x);
        ctx.globalCompositeOperation = "lighter";
        ctx.save();
        ctx.shadowColor = rgba(pl.c, 1);
        ctx.shadowBlur = 10 * s;
        ctx.strokeStyle = rgba(pl.c, isAct ? 0.5 : 0.3);
        ctx.lineWidth = 1.6 * s;
        ctx.beginPath(); ctx.arc(x, y, pr * 0.99, 0, Math.PI * 2); ctx.stroke();
        // hot lit arc facing the core
        ctx.shadowBlur = 14 * s;
        ctx.strokeStyle = rgba(pl.c, isAct ? 0.95 : 0.75);
        ctx.lineWidth = 2.2 * s;
        ctx.beginPath(); ctx.arc(x, y, pr * 0.97, toCore - 1.25, toCore + 1.25); ctx.stroke();
        ctx.shadowColor = "rgba(255,255,255,1)";
        ctx.shadowBlur = 8 * s;
        ctx.strokeStyle = "rgba(255,255,255,0.55)";
        ctx.lineWidth = 1 * s;
        ctx.beginPath(); ctx.arc(x, y, pr * 0.96, toCore - 0.8, toCore + 0.8); ctx.stroke();
        ctx.restore();

        // Saturn ring — front half sweeping over the body
        if (pl.ring) {
          ctx.strokeStyle = rgba(DUST_SAND, 0.26);
          ctx.lineWidth = pr * 0.3;
          ctx.beginPath();
          ctx.ellipse(x, y, rgx, rgy, pl.tilt, 0, Math.PI);
          ctx.stroke();
          drawRingDust(true);
        }

        // its own little grey moon, circling on the outer local ring
        pl.moonA += pl.moonW * dt;
        {
          const mr = Math.max(1.4, pr * pl.moonS);
          const md = pr * pl.moonD;
          const mx = x + Math.cos(pl.moonA) * md;
          const my = y + Math.sin(pl.moonA) * md;
          const mg = ctx.createRadialGradient(
            mx - mr * 0.4, my - mr * 0.4, mr * 0.15, mx, my, mr);
          mg.addColorStop(0, "rgba(214,214,228,0.95)");
          mg.addColorStop(0.6, "rgba(120,122,140,0.9)");
          mg.addColorStop(1, "rgba(40,40,56,0.9)");
          ctx.fillStyle = mg;
          ctx.beginPath(); ctx.arc(mx, my, mr, 0, Math.PI * 2); ctx.fill();
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
        // Hidden entirely when the Sanctuary "planet labels" setting is off,
        // except for the ACTIVE marker, which is status rather than decoration.
        if (!showLabelsRef.current) {
          if (isAct) {
            ctx.textAlign = "center";
            ctx.font = `700 ${Math.max(7, 8 * s)}px "Exo 2", sans-serif`;
            ctx.fillStyle = "rgba(70,232,138,0.95)";
            ctx.fillText("● ACTIVE", x, y + pr + 13 * s);
          }
          continue;
        }
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
    // `density` is a real dependency: particle arrays are sized once at setup,
    // so changing it has to rebuild the scene rather than just re-render.
  }, [size, density]);

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
