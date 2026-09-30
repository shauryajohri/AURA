import { useEffect, useRef } from "react";
import type { AuraState } from "../types";
import { useCoreStore } from "../stores/coreStore";
import { usePlanetStore } from "../stores/planetStore";
import { useSettingsStore } from "../stores/settingsStore";
import { useRoster, useRosterStore } from "../stores/rosterStore";
import { skinFor, useSkinStore } from "../stores/skinStore";
import { skinById, skinUrl } from "../data/planetSkins";
import { useBootStore } from "../stores/bootStore";
import { coreGeom, coreSignals, emitCore, onCore } from "../lib/coreBus";
import { sfx } from "../lib/sfx";

// Shared pointer state for the scene (viewport px).
const pointer = { x: -1e4, y: -1e4, ui: false };

// ============================================================================
// AURA CORE — the black hole and its planets.
//
// The black hole itself is film: a Higgsfield render (Kling 3.0) looped
// seamlessly and encoded as WebM with a luminance alpha channel, so its light
// lays over the space plate like light and the void stays empty. The canvas
// adds everything that has to react live — the planets on a tilted orbital
// plane (in front of and behind the hole), their orbits, gravity waves, and
// the light that falls in when you type or send.
//
// Draw order: backing → rear orbits → planets behind → horizon occluder →
//             the film → waves → front orbits → planets in front → infall
// ============================================================================

const LOOP_SRC = "./cosmos/core-loop.webm";
const BIRTH_SRC = "./cosmos/core-birth.webm";
// Where the photon ring sits inside those clips (1600×650 frames).
const VW = 1600, VH = 650, VCX = 804, VCY = 326, VR = 173;

// The black hole is the hero: it takes the stage, and the planets are small
// worlds on wide orbits around it, clear of the ring.
const TILT = 0.4;        // the orbital plane seen from above: height/width of an orbit
const MAX_R = 178;       // photon-ring radius cap (px)
const INNER = 2.45;      // first orbit, in ring radii
const OUTER = 4.7;       // last orbit, in ring radii (pulled in to stay on the stage)
const BIRTH_MS = 2800;   // a planet's spiral out of the horizon
const BIRTH_WINDOW_MS = 5 * 60_000;
const BIRTHS_PLAYED = new Set<string>();

const PHOTON = "244,238,255";
const VIOLET = "155,123,255";
const SIGNAL = "127,231,255";

const rgba = (c: string, a: number) => `rgba(${c},${a < 0 ? 0 : a > 1 ? 1 : a})`;
const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);
const smooth = (e0: number, e1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};
const hexRgb = (h: string) => {
  const n = parseInt(h.slice(1), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

type CoreState = "idle" | "listening" | "thinking" | "speaking";
const RATE: Record<CoreState, number> = { idle: 0.8, listening: 0.95, thinking: 1.7, speaking: 1.1 };
const GLOW: Record<CoreState, number> = { idle: 1, listening: 1.08, thinking: 1.28, speaking: 1.14 };
const INFALL: Record<CoreState, number> = { idle: 0.5, listening: 0.9, thinking: 6, speaking: 1.6 };

// One slot per model (never fewer than nine), spread evenly from the inner to
// the outer orbit. The roster grows when a planet is installed.
const slotFracsFor = (n: number) => {
  const count = Math.max(9, n);
  return Array.from({ length: count }, (_, i) => i / (count - 1));
};

// ---- planet sprites --------------------------------------------------------
// 512px renders, stepped down by halves into a sprite near the drawn size —
// drawing 512 → 40px every frame would shimmer.
const IMG = new Map<string, HTMLImageElement>();
const SPRITES = new Map<string, HTMLCanvasElement>();
function image(id: string) {
  let im = IMG.get(id);
  if (!im) {
    im = new Image();
    im.decoding = "async";
    im.src = skinUrl(id);
    IMG.set(id, im);
  }
  return im;
}
function sprite(id: string, px: number): HTMLCanvasElement | null {
  const im = image(id);
  if (!im.complete || !im.naturalWidth) return null;
  const size = Math.max(32, Math.min(512, Math.ceil(px / 24) * 24));
  const key = id + ":" + size;
  const hit = SPRITES.get(key);
  if (hit) return hit;
  let src: CanvasImageSource = im;
  let sw = im.naturalWidth;
  while (sw / 2 >= size) {
    const t = document.createElement("canvas");
    t.width = t.height = Math.round(sw / 2);
    const tc = t.getContext("2d")!;
    tc.imageSmoothingQuality = "high";
    tc.drawImage(src, 0, 0, t.width, t.height);
    src = t;
    sw = t.width;
  }
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const cc = c.getContext("2d")!;
  cc.imageSmoothingQuality = "high";
  cc.drawImage(src, 0, 0, size, size);
  SPRITES.set(key, c);
  return c;
}
// Body radius inside a sprite (the rest is atmosphere).
const SPRITE_PAD = 1.18;

// A soft point of light, drawn once and stamped for every particle of infall.
let GLINT: HTMLCanvasElement | null = null;
function glint() {
  if (GLINT) return GLINT;
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  const r = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  r.addColorStop(0, "rgba(255,252,255,1)");
  r.addColorStop(0.18, "rgba(226,212,255,0.85)");
  r.addColorStop(0.45, "rgba(160,126,255,0.28)");
  r.addColorStop(1, "rgba(120,90,255,0)");
  g.fillStyle = r;
  g.fillRect(0, 0, 32, 32);
  GLINT = c;
  return c;
}

function makeVideo(src: string, loop: boolean) {
  const v = document.createElement("video");
  v.src = src;
  v.muted = true;
  v.loop = loop;
  v.playsInline = true;
  v.preload = "auto";
  v.setAttribute("aria-hidden", "true");
  return v;
}

interface Props {
  state: AuraState;
  activeModelId?: string | null; // planet of the model that last answered
}

interface Planet {
  id: string; name: string; role: string; ring: boolean; idx: number;
  a: number;          // angle on its orbit
  w: number;          // angular speed (rad/s)
  def: number;        // default slot
  birthAt: number;    // performance.now() the birth started, 0 = none
  hov: number;        // eased hover 0..1
  kickAt: number;     // last shockwave
  x: number; y: number; z: number; pr: number; rx: number; hidden: boolean;
  seenAt: number;     // when its art was first ready (it fades in from there)
}
interface Mote { x: number; y: number; vx: number; vy: number; delay: number; life: number; c: string; }
interface Wave { at: number; strong: boolean; }

export default function BlackHole({ state, activeModelId = null }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;
  const activeRef = useRef<string | null>(activeModelId);
  activeRef.current = activeModelId;

  // Built-in + installed planets. The scene rebuilds only when the SET of
  // planets changes, not on every roster fetch.
  const roster = useRoster();
  const rosterKey = roster.map((m) => m.id).join("|");
  const rosterRef = useRef(roster);
  rosterRef.current = roster;
  const born = useRosterStore((st) => st.born);
  const bornRef = useRef(born);
  bornRef.current = born;
  const picks = useSkinStore((s) => s.picks);
  const picksRef = useRef(picks);
  picksRef.current = picks;

  // Orbits menu (top-right of the sky) — read live so sliders act instantly.
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
  const slotFracsRef = useRef(slotFracsFor(roster.length));
  slotFracsRef.current = slotFracsFor(roster.length);

  // Settings → Appearance / Orbit lines.
  const density = useSettingsStore((st) => st.density);
  const rotationMul = useSettingsStore((st) => st.rotationMul);
  const showLabels = useSettingsStore((st) => st.showLabels);
  const orbitMul = useSettingsStore((st) => st.orbitMul);
  const orbitWidthMul = useSettingsStore((st) => st.orbitWidthMul);
  const orbitStyle = useSettingsStore((st) => st.orbitStyle);
  const liveCfgRef = useRef({ density: 1, rotation: 1, labels: true, omul: 1, owidth: 1, ostyle: "dashed" });
  liveCfgRef.current = {
    density, rotation: rotationMul, labels: showLabels,
    omul: orbitMul, owidth: orbitWidthMul, ostyle: orbitStyle,
  };

  // Core menu (top-right of the sky): size, glow and position — adjustable in edit mode.
  const scalePct = useCoreStore((s) => s.scale);
  const glowPct = useCoreStore((s) => s.glow);
  const posX = useCoreStore((s) => s.x);
  const posY = useCoreStore((s) => s.y);
  const editing = useCoreStore((s) => s.editing);
  const setCfg = useCoreStore((s) => s.set);
  const coreCfgRef = useRef({ scale: 1, glow: 1, x: 0, y: 0, editing: false });
  coreCfgRef.current = { scale: scalePct / 100, glow: glowPct / 100, x: posX, y: posY, editing };

  const bootPhase = useBootStore((s) => s.phase);
  const bootRef = useRef(bootPhase);
  bootRef.current = bootPhase;

  // live scene objects shared with the pointer handlers
  const planetsRef = useRef<Planet[]>([]);
  const hoverRef = useRef<string | null>(null);
  const planetDragRef = useRef<string | null>(null);
  const dragSlotRef = useRef<number | null>(null);
  const geomRef = useRef({ cx: 0, cy: 0, R: 100, left: 0, top: 0, stageW: 0, stageH: 0, inner: 1, outer: 2 });
  if (!planetDragRef.current) slotsRef.current = slotsMap; // sync unless mid-drag

  // The stage: where the core is centred and what it has to fit inside.
  const stageRef = useRef({ x: window.innerWidth / 2, y: window.innerHeight / 2, w: 800, h: 600 });
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const measure = () => {
      const r = host.getBoundingClientRect();
      stageRef.current = { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(host);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  // ---- the two films: the birth (startup) and the loop --------------------
  const filmsRef = useRef<{ loop: HTMLVideoElement; birth: HTMLVideoElement | null; revealT: number }>();
  useEffect(() => {
    const loop = makeVideo(LOOP_SRC, true);
    const birth = bootRef.current === "intro" ? makeVideo(BIRTH_SRC, false) : null;
    // Kept in the DOM (1px, invisible) so Chromium never parks the decoder.
    const shelf = document.createElement("div");
    shelf.className = "bh-films";
    shelf.append(loop);
    if (birth) shelf.append(birth);
    document.body.append(shelf);
    filmsRef.current = { loop, birth, revealT: 0 };
    void loop.play().catch(() => { /* retried on the first gesture */ });
    const retry = () => { if (loop.paused) void loop.play().catch(() => {}); };
    window.addEventListener("pointerdown", retry);

    let fallback = 0;
    let disposed = false;
    if (birth) {
      // (a pause() from unmounting rejects play() — that isn't a failure)
      const reveal = () => { if (!disposed) useBootStore.getState().reveal(); };
      birth.addEventListener("ended", reveal);
      birth.addEventListener("error", reveal);
      birth.play().catch(reveal);
      // never hold the app hostage to a slow decoder
      fallback = window.setTimeout(reveal, 7000);
    }
    return () => {
      disposed = true;
      window.clearTimeout(fallback);
      window.removeEventListener("pointerdown", retry);
      loop.pause();
      birth?.pause();
      shelf.remove();
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let D = 0, DPR = 1;
    const fit = () => {
      // The canvas spans the viewport diagonal, so no orbit is ever clipped
      // wherever the core sits.
      D = Math.ceil(Math.hypot(window.innerWidth, window.innerHeight));
      DPR = Math.min(window.devicePixelRatio || 1, D > 1700 ? 1.5 : 2);
      canvas.width = Math.round(D * DPR);
      canvas.height = Math.round(D * DPR);
      canvas.style.width = D + "px";
      canvas.style.height = D + "px";
    };
    fit();
    window.addEventListener("resize", fit);

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const list = rosterRef.current;
    const intro = bootRef.current === "intro";
    const planets: Planet[] = list.map((m, i) => ({
      id: m.id, name: m.name, role: m.role, ring: !!m.ring, idx: i,
      a: (i * Math.PI * 2) / list.length + 0.5 + (i % 2) * 0.35,
      w: 0, def: i,
      birthAt: (() => {
        if (intro) return -1; // born when the startup reveal begins
        const t = bornRef.current[m.id];
        if (!t || reduceMotion || BIRTHS_PLAYED.has(m.id) || Date.now() - t > BIRTH_WINDOW_MS) return 0;
        BIRTHS_PLAYED.add(m.id);
        return performance.now();
      })(),
      hov: 0, kickAt: -1e9,
      x: 0, y: 0, z: 0, pr: 0, rx: 1, hidden: false, seenAt: 0,
    }));
    planetsRef.current = planets;
    for (const p of planets) image(skinFor(picksRef.current, p.id, p.idx));

    const motes: Mote[] = [];
    const waves: Wave[] = [];
    let glowBoost = 0;
    let Rc = 0;
    const center = intro
      ? { x: window.innerWidth / 2, y: window.innerHeight / 2 }
      : { x: stageRef.current.x, y: stageRef.current.y };
    let orbitFade = intro ? 0 : 1;
    let birthsQueued = !intro;
    let lastRate = -1;
    let loopShownAt = 0;
    let nextAmbient = 0;
    let nextWave = performance.now() + 6000;
    let last = performance.now();
    let raf = 0;

    const toCanvas = (vx: number, vy: number) => ({
      x: vx - (center.x - D / 2),
      y: vy - (center.y - D / 2),
    });
    const spawn = (x: number, y: number, n: number, spread: number, delayMax: number, up: number) => {
      for (let i = 0; i < n; i++) {
        const p = toCanvas(x + (Math.random() - 0.5) * spread, y + (Math.random() - 0.5) * 8);
        motes.push({
          x: p.x, y: p.y,
          vx: (Math.random() - 0.5) * 120, vy: -up * (0.4 + Math.random() * 0.8),
          delay: Math.random() * delayMax, life: 0,
          c: Math.random() < 0.25 ? SIGNAL : Math.random() < 0.5 ? PHOTON : "205,186,255",
        });
      }
      if (motes.length > 600) motes.splice(0, motes.length - 600);
    };
    const offBus = onCore((e) => {
      if (reduceMotion) return;
      if (e.kind === "spark") spawn(e.x, e.y, 2, 6, 0, 90);
      else if (e.kind === "feed") {
        for (let i = 0; i < 44; i++) spawn(e.x + Math.random() * e.w, e.y + Math.random() * e.h, 1, 0, 0.35, 160);
      } else if (e.kind === "pulse") {
        waves.push({ at: performance.now(), strong: false });
        glowBoost = Math.min(0.5, glowBoost + 0.25);
      } else if (e.kind === "shock") {
        const now = performance.now();
        waves.push({ at: now, strong: true });
        glowBoost = Math.min(0.7, glowBoost + 0.45);
        for (const p of planets) p.kickAt = now;
      }
    });

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const films = filmsRef.current;
      const phase = bootRef.current;
      const live = liveCfgRef.current;
      const core = coreCfgRef.current;
      const pcfg = planetCfgRef.current;
      const raw = stateRef.current as string;
      const st: CoreState =
        raw === "thinking" || raw === "speaking" ? raw : coreSignals.mic ? "listening" : "idle";

      // ---- where, and how big -------------------------------------------
      const stage = stageRef.current;
      // sized by the ring and its glow, not by the planets — outer orbits may
      // pass under the chrome, the black hole never does
      const fitR = Math.min(MAX_R, (stage.h / 2 - 22) / 1.28, stage.w / 7.4);
      const Rt = Math.max(56, fitR * core.scale);
      Rc = Rc ? Rc + (Rt - Rc) * Math.min(1, dt * 5) : Rt;
      // The startup forms the core in the middle of the window (the panes
      // are hidden then); on the reveal it glides over to its place in the sky.
      const home = phase === "intro" ? { x: window.innerWidth / 2, y: window.innerHeight / 2 } : stage;
      // The saved position is a nudge, not a teleport. Clamping it to the sky
      // means the core is centred in the gap by default and can never be
      // dragged — or left by an older layout — half under the sidebar or
      // behind the conversation pane.
      const limX = Math.max(0, stage.w / 2 - Rt);
      const limY = Math.max(0, stage.h / 2 - Rt);
      const tx = home.x + clamp(core.x, -limX, limX);
      const ty = home.y + clamp(core.y, -limY, limY);
      center.x += (tx - center.x) * Math.min(1, dt * (core.editing ? 30 : 6));
      center.y += (ty - center.y) * Math.min(1, dt * (core.editing ? 30 : 6));
      canvas.style.transform = `translate3d(${center.x - D / 2}px, ${center.y - D / 2}px, 0)`;
      const R = Rc;
      const cx = D / 2, cy = D / 2;
      coreGeom.x = center.x; coreGeom.y = center.y; coreGeom.r = R;
      const inner = R * INNER;
      const outer = Math.max(inner + 60, Math.min(R * OUTER, stage.w / 2 - 34));
      geomRef.current = {
        cx, cy, R, left: center.x - D / 2, top: center.y - D / 2,
        stageW: stage.w, stageH: stage.h, inner, outer,
      };

      // ---- the startup: once the reveal begins, planets are born ---------
      if (phase !== "intro" && !birthsQueued) {
        birthsQueued = true;
        planets.forEach((p, i) => { p.birthAt = now + 250 + i * 120; });
        if (films) films.revealT = now;
      }
      if (phase !== "intro") orbitFade = Math.min(1, orbitFade + dt / 1.6);

      // ---- tempo & light --------------------------------------------------
      const rate = Math.max(0.3, Math.min(2.4, RATE[st] * live.rotation));
      if (films && Math.abs(rate - lastRate) > 0.01) { films.loop.playbackRate = rate; lastRate = rate; }
      glowBoost = Math.max(0, glowBoost - dt * 0.45);
      const near = coreGeom.pointer ? smooth(R * 4, R * 1.2, Math.hypot(pointer.x - center.x, pointer.y - center.y)) : 0;
      const talk = st === "speaking" ? 0.1 * Math.sin(now / 1000 * 6.3) + 0.06 * Math.sin(now / 1000 * 9.7) : 0;
      const glow = (GLOW[st] + glowBoost + near * 0.18 + talk) * core.glow;

      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, D, D);

      // soft darkening around the core so its light owns the middle of space
      const back = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 3.4);
      back.addColorStop(0, "rgba(2,1,8,0.75)");
      back.addColorStop(1, "rgba(2,1,8,0)");
      ctx.fillStyle = back;
      ctx.beginPath(); ctx.arc(cx, cy, R * 3.4, 0, Math.PI * 2); ctx.fill();

      // ---- planets: positions first, so both halves can be depth-sorted --
      const fracs = slotFracsRef.current;
      const maxRx = D / 2 - 30;
      const slotRx = (si: number) =>
        Math.min(maxRx, (inner + (outer - inner) * fracs[si % fracs.length]) * pcfg.orbit);
      const activeId = activeRef.current;
      const editMode = pEditingRef.current;
      const vx0 = center.x - D / 2, vy0 = center.y - D / 2;
      let hoverId: string | null = null;
      let hoverZ = -9;
      for (const p of planets) {
        const isAct = p.id === activeId;
        const dragging = planetDragRef.current === p.id;
        const si = dragging && dragSlotRef.current !== null
          ? dragSlotRef.current
          : (slotsRef.current[p.id] ?? p.def);
        const frac = fracs[si % fracs.length];
        // inner orbits run faster, like a real system (40s → 110s a lap)
        p.w = (Math.PI * 2) / (40 + 70 * frac);
        if (!dragging && !reduceMotion) {
          p.a = (p.a + p.w * pcfg.speed * live.rotation * (isAct ? 2.2 : 1) * (1 - p.hov * 0.85) * dt) % (Math.PI * 2);
        }
        let rx = slotRx(si);
        let ang = p.a;
        let grow = 1;
        p.hidden = p.birthAt < 0 || (p.birthAt > 0 && now < p.birthAt);
        if (p.birthAt > 0 && now >= p.birthAt) {
          const bt = Math.min(1, (now - p.birthAt) / BIRTH_MS);
          if (bt >= 1) p.birthAt = 0;
          const e = 1 - Math.pow(1 - bt, 3);
          rx = R * 0.9 + (rx - R * 0.9) * e;
          ang = p.a - (1 - e) * Math.PI * 1.5;
          grow = 0.12 + 0.88 * e;
        }
        // a strike on the core sends a ripple through every orbit
        const since = (now - p.kickAt) / 1000;
        if (since < 2.2) rx *= 1 + 0.05 * Math.sin(since * 11 - p.idx * 0.4) * Math.exp(-since * 2.2);
        p.x = cx + rx * Math.cos(ang);
        p.y = cy + rx * TILT * Math.sin(ang);
        p.z = Math.sin(ang);
        p.rx = rx;
        const base = R * (0.082 + (p.idx % 3) * 0.014);
        p.pr = base * pcfg.size * (1 + 0.16 * p.z) * grow * (1 + 0.5 * p.hov + (isAct ? 0.12 : 0));
        // hover: front-most planet under the pointer
        if (!p.hidden && coreGeom.pointer && !pointer.ui && !editMode) {
          const d = Math.hypot(pointer.x - (vx0 + p.x), pointer.y - (vy0 + p.y));
          const behindHole = p.z < 0 && Math.hypot(p.x - cx, p.y - cy) < R * 0.95;
          if (d < p.pr + 8 && !behindHole && p.z > hoverZ) { hoverId = p.id; hoverZ = p.z; }
        }
      }
      if (hoverId !== hoverRef.current) {
        if (hoverId) sfx.hover();
        hoverRef.current = hoverId;
      }
      for (const p of planets) p.hov += ((p.id === hoverId ? 1 : 0) - p.hov) * Math.min(1, dt * 9);
      const overCore = coreGeom.pointer && !pointer.ui &&
        Math.hypot(pointer.x - center.x, pointer.y - center.y) < R * 1.1;
      coreGeom.hot = !!hoverId || overCore;

      // ---- orbits -----------------------------------------------------------
      const ostyle = live.ostyle;
      const orbitsOn = (ostyle !== "hidden" && live.omul > 0.01) || editMode;
      const dash: number[] = editMode ? [5, 8] : ostyle === "solid" ? [] : ostyle === "dotted" ? [1.2, 7] : [3, 10];
      const drawOrbits = (front: boolean) => {
        if (!orbitsOn || orbitFade <= 0) return;
        ctx.save();
        ctx.setLineDash(dash);
        ctx.lineDashOffset = -now / 220;
        const used = new Set<number>();
        for (const p of planets) used.add(slotsRef.current[p.id] ?? p.def);
        for (let si = 0; si < fracs.length; si++) {
          if (!editMode && !used.has(si)) continue;
          const rx = slotRx(si);
          const owner = planets.find((p) => (slotsRef.current[p.id] ?? p.def) === si);
          const lit = owner && (owner.id === activeId || owner.hov > 0.05);
          const targeted = planetDragRef.current !== null && dragSlotRef.current === si;
          let a = (front ? 0.17 : 0.08) * Math.min(2, live.omul);
          if (lit) a += (front ? 0.22 : 0.1) * (owner!.id === activeId ? 1 : owner!.hov);
          if (editMode) a = front ? 0.4 : 0.22;
          ctx.strokeStyle = targeted ? rgba(SIGNAL, 0.8) : rgba("190,172,255", a * orbitFade);
          ctx.lineWidth = (targeted ? 1.6 : 1) * (editMode ? 1 : live.owidth);
          ctx.beginPath();
          ctx.ellipse(cx, cy, rx, rx * TILT, 0, front ? 0 : Math.PI, front ? Math.PI : Math.PI * 2);
          ctx.stroke();
        }
        ctx.restore();
      };

      // ---- a planet ---------------------------------------------------------
      const drawPlanet = (p: Planet) => {
        if (p.hidden) return;
        const skinId = skinFor(picksRef.current, p.id, p.idx);
        const skin = skinById(skinId);
        const gc = hexRgb(skin?.glow ?? "#9b7bff");
        const isAct = p.id === activeId;
        const { x, y, pr } = p;
        // no flat placeholder: a planet appears once its art is decoded
        const spr = sprite(skinId, pr * 2 * SPRITE_PAD * DPR);
        if (!spr) return;
        if (!p.seenAt) p.seenAt = now;
        const birthing = p.birthAt > 0;
        ctx.save();
        ctx.globalAlpha = Math.min(1, (now - p.seenAt) / 600) *
          (birthing ? Math.min(1, (now - p.birthAt) / 500) : 1);

        // the comet trail it leaves along its orbit
        if (orbitFade > 0 && !reduceMotion) {
          const rx = p.rx;
          const at = Math.atan2((p.y - cy) / TILT, p.x - cx);
          const step = Math.min(0.06, (pr * 0.9) / rx);
          ctx.lineCap = "round";
          for (let k = 1; k <= 7; k++) {
            const a0 = at - k * step;
            ctx.strokeStyle = rgba(gc, (0.1 - k * 0.012) * orbitFade * (1 + 1.5 * p.hov));
            ctx.lineWidth = Math.max(0.6, pr * 0.22 * (1 - k / 9));
            ctx.beginPath();
            ctx.ellipse(cx, cy, rx, rx * TILT, 0, a0, a0 + step);
            ctx.stroke();
          }
        }

        // atmosphere glow
        ctx.globalCompositeOperation = "lighter";
        const halo = ctx.createRadialGradient(x, y, pr * 0.7, x, y, pr * (2.4 + p.hov));
        halo.addColorStop(0, rgba(gc, (isAct ? 0.24 : 0.07) + p.hov * 0.22));
        halo.addColorStop(1, rgba(gc, 0));
        ctx.fillStyle = halo;
        ctx.beginPath(); ctx.arc(x, y, pr * (2.4 + p.hov), 0, Math.PI * 2); ctx.fill();
        ctx.globalCompositeOperation = "source-over";

        // ring (models that can see images) — the far half goes behind
        const rgMul = Math.max(0.6, pcfg.rings);
        const ringTilt = -0.28 + (p.idx % 3) * 0.2;
        const drawRing = (front: boolean) => {
          if (!p.ring) return;
          for (let b = 0; b < 3; b++) {
            ctx.strokeStyle = rgba(b === 1 ? "232,222,205" : "196,190,214", (front ? 0.5 : 0.28) * (b === 1 ? 1 : 0.55));
            ctx.lineWidth = pr * (b === 1 ? 0.14 : 0.07);
            ctx.beginPath();
            ctx.ellipse(x, y, pr * (1.75 + b * 0.18) * rgMul, pr * (0.42 + b * 0.05) * rgMul, ringTilt,
              front ? 0 : Math.PI, front ? Math.PI : Math.PI * 2);
            ctx.stroke();
          }
        };
        drawRing(false);

        // body — lit side turned toward the core. The renders are lit from
        // the left, so planets left of the core are mirrored, crossfading
        // as they pass in front of or behind it.
        const half = pr * SPRITE_PAD;
        {
          const wRight = smooth(-0.2, 0.2, (x - cx) / p.rx);
          const drawSide = (mirror: boolean, alpha: number) => {
            if (alpha <= 0.01) return;
            ctx.save();
            ctx.globalAlpha *= alpha;
            ctx.translate(x, y);
            if (mirror) ctx.scale(-1, 1);
            ctx.drawImage(spr, -half, -half, half * 2, half * 2);
            ctx.restore();
          };
          if (wRight >= 0.5) { drawSide(false, 1); drawSide(true, 1 - wRight); }
          else { drawSide(true, 1); drawSide(false, wRight); }
        }
        // planets sit in the core's shadow so its light stays the brightest
        // thing on screen; farther ones deeper, the hovered one steps out
        const shade = (0.2 + 0.36 * Math.max(0, -p.z)) * (1 - p.hov) * (isAct ? 0.5 : 1);
        if (shade > 0.01) {
          ctx.fillStyle = `rgba(3,2,10,${shade.toFixed(3)})`;
          ctx.beginPath(); ctx.arc(x, y, pr * 0.995, 0, Math.PI * 2); ctx.fill();
        }
        // rim light from the core
        const toCore = Math.atan2(cy - y, cx - x);
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = rgba(gc, 0.22 + p.hov * 0.4 + (isAct ? 0.25 : 0));
        ctx.lineWidth = Math.max(1, pr * 0.07);
        ctx.beginPath(); ctx.arc(x, y, pr * 0.985, toCore - 1.1, toCore + 1.1); ctx.stroke();
        ctx.globalCompositeOperation = "source-over";
        drawRing(true);

        // the model answering right now wears a slow halo
        if (isAct) {
          const ph = (now / 1600) % 1;
          ctx.strokeStyle = rgba(gc, 0.55 * (1 - ph));
          ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(x, y, pr * (1.35 + ph * 0.9), 0, Math.PI * 2); ctx.stroke();
        }
        ctx.restore();
      };

      // Labels never pile up: nearer planets (and the hovered / answering one)
      // claim their space first; a label that would overlap is skipped.
      const taken: Array<[number, number, number, number]> = [];
      const drawLabel = (p: Planet) => {
        if (p.hidden || !p.seenAt) return;
        const isAct = p.id === activeId;
        // names are for the planet you point at and the one answering; the
        // "planet labels" setting adds quiet names to the near side only
        const passive = live.labels && p.z > 0.2;
        if (!isAct && p.hov <= 0.05 && !passive) return;
        if (p.z < 0 && Math.hypot(p.x - cx, p.y - cy) < R * 1.05) return; // behind the hole
        const meta = metaRef.current[p.id] || {};
        const name = meta.name || p.name;
        const role = meta.role || p.role;
        const depthA = 0.55 + 0.45 * (p.z + 1) / 2;
        const a = Math.max(passive ? depthA * 0.45 : 0, isAct ? 0.95 : 0, p.hov) * orbitFade;
        const ly = p.y + p.pr + 14;
        const two = p.hov > 0.05 || isAct;
        const w = Math.max(name.length, two ? role.length : 0) * 6.2 + 8;
        const box: [number, number, number, number] = [p.x - w / 2, ly - 11, p.x + w / 2, ly + (two ? 18 : 4)];
        if (taken.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) return;
        taken.push(box);
        ctx.save();
        ctx.textAlign = "center";
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur = 6;
        ctx.font = `500 ${(two ? 11.5 : 10.5) + p.hov * 1.5}px "Instrument Sans", "Segoe UI", sans-serif`;
        ctx.fillStyle = rgba(PHOTON, a);
        ctx.fillText(name, p.x, ly);
        if (p.hov > 0.05 || isAct) {
          ctx.font = `400 11px "Instrument Sans", "Segoe UI", sans-serif`;
          ctx.fillStyle = rgba("170,160,210", Math.max(p.hov, isAct ? 0.8 : 0) * orbitFade);
          ctx.fillText(isAct && p.hov < 0.5 ? "answering" : role, p.x, ly + 14);
        }
        ctx.restore();
      };

      const sorted = [...planets].sort((a, b) => a.z - b.z);
      drawOrbits(false);
      for (const p of sorted) if (p.z < 0) drawPlanet(p);

      // ---- the event horizon: nothing behind it gets through -----------
      const occ = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, R * 1.02);
      occ.addColorStop(0, "rgba(0,0,0,1)");
      occ.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = occ;
      ctx.beginPath(); ctx.arc(cx, cy, R * 1.02, 0, Math.PI * 2); ctx.fill();

      // ---- the film --------------------------------------------------------
      const k = R / VR;
      const filmRect = [cx - VCX * k, cy - VCY * k, VW * k, VH * k] as const;
      ctx.filter = `brightness(${(0.84 + 0.26 * glow).toFixed(3)}) saturate(${(0.95 + 0.2 * (glow - 1)).toFixed(3)})`;
      if (films) {
        const loopReady = films.loop.readyState >= 2;
        if (phase === "intro" && films.birth) {
          if (films.birth.readyState >= 2) ctx.drawImage(films.birth, ...filmRect);
        } else {
          const mix = films.birth && films.revealT ? Math.min(1, (now - films.revealT) / 700) : 1;
          if (mix < 1 && films.birth && films.birth.readyState >= 2) {
            ctx.globalAlpha = 1 - mix;
            ctx.drawImage(films.birth, ...filmRect);
          }
          if (loopReady) {
            // no startup: the core fades up as soon as its film can play
            if (!loopShownAt) loopShownAt = now;
            ctx.globalAlpha = mix * Math.min(1, (now - loopShownAt) / 900);
            ctx.drawImage(films.loop, ...filmRect);
          }
          ctx.globalAlpha = 1;
          if (mix >= 1 && films.birth) { films.birth.pause(); films.birth = null; }
        }
      }
      ctx.filter = "none";
      ctx.globalAlpha = 1;

      // ---- light answering what AURA is doing --------------------------
      ctx.globalCompositeOperation = "lighter";
      if (st === "listening") {
        const b = 0.5 + 0.5 * Math.sin(now / 1000 * 3.2);
        ctx.strokeStyle = rgba(SIGNAL, 0.14 + 0.12 * b);
        ctx.lineWidth = R * 0.05;
        ctx.beginPath(); ctx.arc(cx, cy, R * 1.06, 0, Math.PI * 2); ctx.stroke();
      }
      const bloom = ctx.createRadialGradient(cx, cy, R * 0.9, cx, cy, R * 2.6);
      bloom.addColorStop(0, rgba(VIOLET, 0.05 + 0.12 * Math.max(0, glow - 1) + near * 0.06));
      bloom.addColorStop(1, rgba(VIOLET, 0));
      ctx.fillStyle = bloom;
      ctx.beginPath(); ctx.arc(cx, cy, R * 2.6, 0, Math.PI * 2); ctx.fill();

      // gravity waves: a gentle one now and then, bigger when struck
      if (!reduceMotion && phase === "done" && now > nextWave) {
        waves.push({ at: now, strong: false });
        nextWave = now + 9000 + Math.random() * 5000;
      }
      for (let i = waves.length - 1; i >= 0; i--) {
        const w = waves[i];
        const t = (now - w.at) / (w.strong ? 1700 : 2400);
        if (t >= 1) { waves.splice(i, 1); continue; }
        const e = 1 - Math.pow(1 - t, 2.2);
        const rr = R * (1.05 + e * (w.strong ? 5.5 : 4.2));
        const a = (w.strong ? 0.45 : 0.16) * (1 - t) * (1 - t);
        ctx.strokeStyle = rgba("205,186,255", a);
        ctx.lineWidth = w.strong ? 2 : 1.2;
        ctx.beginPath(); ctx.ellipse(cx, cy, rr, rr * TILT, 0, 0, Math.PI * 2); ctx.stroke();
        if (w.strong) {
          ctx.strokeStyle = rgba(PHOTON, a * 0.7);
          ctx.beginPath(); ctx.arc(cx, cy, R * (1.02 + e * 1.4), 0, Math.PI * 2); ctx.stroke();
        }
      }
      ctx.globalCompositeOperation = "source-over";

      drawOrbits(true);
      for (const p of sorted) if (p.z >= 0) drawPlanet(p);
      const labelOrder = [...planets].sort((a, b) =>
        (b.hov + (b.id === activeId ? 2 : 0) + b.z * 0.5) - (a.hov + (a.id === activeId ? 2 : 0) + a.z * 0.5));
      for (const p of labelOrder) drawLabel(p);

      // ---- infall: light being pulled in and swallowed ------------------
      if (!reduceMotion && phase !== "intro" && now > nextAmbient) {
        // ambient dust drifting in from the outer disk, faster while thinking
        const ang = Math.random() * Math.PI * 2;
        const rr = R * (3 + Math.random() * 2);
        motes.push({
          x: cx + Math.cos(ang) * rr, y: cy + Math.sin(ang) * rr * TILT,
          vx: -Math.sin(ang) * 60, vy: Math.cos(ang) * 60 * TILT,
          delay: 0, life: 0, c: Math.random() < 0.3 ? PHOTON : "196,172,255",
        });
        nextAmbient = now + 1000 / Math.max(0.1, INFALL[st] * Math.max(0.2, live.density));
      }
      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";
      for (let i = motes.length - 1; i >= 0; i--) {
        const m = motes[i];
        if (m.delay > 0) { m.delay -= dt; continue; }
        m.life += dt;
        const dx = cx - m.x, dy = cy - m.y;
        const dist = Math.hypot(dx, dy) || 1;
        if (dist < R * 0.9 || m.life > 5) {
          if (dist < R * 0.9) glowBoost = Math.min(0.6, glowBoost + 0.006);
          motes.splice(i, 1);
          continue;
        }
        // gravity with a little swirl: the light spirals in, tighter as it nears
        const ux = dx / dist, uy = dy / dist;
        const pull = 4200 * Math.pow(R / Math.max(dist, R), 1.2);
        const swirl = 0.42;
        m.vx += (ux * pull - uy * pull * swirl) * dt;
        m.vy += (uy * pull + ux * pull * swirl) * dt;
        const damp = Math.pow(0.18, dt);
        m.vx *= damp; m.vy *= damp;
        const px = m.x, py = m.y;
        m.x += m.vx * dt; m.y += m.vy * dt;
        const fade = Math.min(1, m.life * 5) * smooth(R * 0.92, R * 1.4, dist);
        // a short, soft tail and a bright head
        ctx.strokeStyle = rgba(m.c, 0.38 * fade);
        ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(px - (m.x - px) * 2.2, py - (m.y - py) * 2.2); ctx.lineTo(m.x, m.y); ctx.stroke();
        const gs = 9 + 5 * fade;
        ctx.globalAlpha = 0.9 * fade;
        ctx.drawImage(glint(), m.x - gs / 2, m.y - gs / 2, gs, gs);
        ctx.globalAlpha = 1;
      }
      ctx.globalCompositeOperation = "source-over";
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", fit);
      offBus();
      coreGeom.hot = false;
    };
    // The planet set and dust density shape the scene; everything else is
    // read live through refs.
  }, [rosterKey, density]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- pointer: hover, click a planet, strike the core ---------------------
  useEffect(() => {
    const isUi = (el: EventTarget | null) =>
      !!(el as Element | null)?.closest?.(
        "button, a, input, textarea, select, label, [role='button'], [role='dialog'], " +
        ".dock, .rail, .stagetools, .winbar, .menu, .corestatus, .boot");
    const onMove = (e: MouseEvent) => {
      pointer.x = e.clientX; pointer.y = e.clientY;
      pointer.ui = isUi(e.target);
      coreGeom.pointer = true;
    };
    const onLeave = () => { coreGeom.pointer = false; };
    const onClick = (e: MouseEvent) => {
      if (isUi(e.target) || pEditingRef.current || coreCfgRef.current.editing) return;
      const hid = hoverRef.current;
      if (hid) {
        sfx.tap();
        window.dispatchEvent(new CustomEvent("aura:open-planet", { detail: hid }));
        return;
      }
      if (Math.hypot(e.clientX - coreGeom.x, e.clientY - coreGeom.y) < coreGeom.r * 1.15) {
        sfx.shock();
        emitCore({ kind: "shock", x: e.clientX, y: e.clientY });
      }
    };
    window.addEventListener("mousemove", onMove);
    document.documentElement.addEventListener("mouseleave", onLeave);
    window.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("mousemove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("click", onClick);
    };
  }, []);

  // ---- edit modes: drag a planet to another orbit, or move the core --------
  const coreDragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const g = geomRef.current;
    const px = e.clientX - g.left, py = e.clientY - g.top;
    if (pEditingRef.current) {
      let best: Planet | null = null;
      for (const p of planetsRef.current) {
        if (Math.hypot(px - p.x, py - p.y) <= p.pr + 10 && (!best || p.z > best.z)) best = p;
      }
      if (best) {
        e.preventDefault();
        planetDragRef.current = best.id;
      }
      return;
    }
    if (!editing) return;
    if (Math.hypot(px - g.cx, py - g.cy) > g.R * 1.3) return; // the core itself, not empty space
    e.preventDefault();
    coreDragRef.current = { sx: e.clientX, sy: e.clientY, ox: posX, oy: posY };
  };

  useEffect(() => {
    // A dragged planet follows the pointer around the orbital plane and
    // snaps to the nearest orbit; dropping on a taken orbit swaps tenants.
    const nearestSlot = (rEq: number) => {
      const g = geomRef.current;
      const fracs = slotFracsRef.current;
      const mul = planetCfgRef.current.orbit || 1;
      let best = 0, bestD = Infinity;
      for (let si = 0; si < fracs.length; si++) {
        const rr = (g.inner + (g.outer - g.inner) * fracs[si]) * mul;
        const d = Math.abs(rEq - rr);
        if (d < bestD) { bestD = d; best = si; }
      }
      return best;
    };
    const move = (e: MouseEvent) => {
      const g = geomRef.current;
      const cd = coreDragRef.current;
      if (cd) {
        const limX = Math.max(0, g.stageW / 2 - 40);
        const limY = Math.max(0, g.stageH / 2 - 40);
        setCfg({
          x: Math.max(-limX, Math.min(limX, cd.ox + e.clientX - cd.sx)),
          y: Math.max(-limY, Math.min(limY, cd.oy + e.clientY - cd.sy)),
        });
        return;
      }
      const id = planetDragRef.current;
      if (!id) return;
      const px = e.clientX - g.left - g.cx;
      const py = (e.clientY - g.top - g.cy) / TILT;
      const pl = planetsRef.current.find((p) => p.id === id);
      if (!pl) return;
      pl.a = Math.atan2(py, px);
      dragSlotRef.current = nearestSlot(Math.hypot(px, py));
    };
    const up = () => {
      coreDragRef.current = null;
      const id = planetDragRef.current;
      if (!id) return;
      const target = dragSlotRef.current;
      planetDragRef.current = null;
      dragSlotRef.current = null;
      if (target === null) return;
      const resolve = (pid: string) =>
        slotsRef.current[pid] ?? (planetsRef.current.find((p) => p.id === pid)?.def ?? 0);
      const prev = resolve(id);
      if (prev === target) return;
      const next: Record<string, number> = { ...slotsRef.current };
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
  }, [setCfg]);

  return (
    <div ref={hostRef} className="bh-host">
      <canvas
        ref={canvasRef}
        className={"bh-canvas" + (editing || pEditing ? " bh-canvas--edit" : "")}
        onMouseDown={handleMouseDown}
        title={pEditing ? "Drag any planet to a new orbit" : editing ? "Drag to move AURA's core" : undefined}
      />
      {editing && <div className="bh-editbadge">Drag the core to move it</div>}
      {!editing && pEditing && <div className="bh-editbadge">Drag planets onto any orbit</div>}
    </div>
  );
}
