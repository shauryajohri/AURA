// ============================================================================
// Procedural backdrops — full-screen skies painted on one canvas.
//
// The filmed universe (UniverseBackground) and the constellation web
// (CosmicBackground) stay their own components; these are the extra skies a
// skin can wear. Each scene is size-agnostic (it is told W×H), so the same
// code paints the whole window and the little previews in the skin gallery.
//
// Every scene reacts to AURA's state through `tempo` (motion) and `bright`
// (light), and some to `speaking` directly, so the world behind her moves
// with her rather than looping on its own.
//
// Cost discipline: anything static is painted once into an offscreen canvas
// at resize and blitted; soft scenes (nebula, aurora) ask for a low render
// scale and let CSS upscale them, which is also what makes them soft.
// ============================================================================

import { rgba } from "./skins";

export type SkyKind = "starfield" | "nebula" | "aurora" | "warp" | "void";

export interface SkyFrame {
  ctx: CanvasRenderingContext2D;
  W: number;
  H: number;
  /** Seconds since start. */
  t: number;
  /** Seconds since last frame (clamped). */
  dt: number;
  tempo: number;
  bright: number;
  speaking: boolean;
  /** [base tone, primary gas, secondary gas, highlight] as "r,g,b". */
  sky: readonly string[];
}

export interface SkyScene {
  /** Fraction of device pixels to render at (soft scenes go low). */
  res: number;
  /**
   * W×H are logical (CSS) pixels; `k` is device pixels per logical pixel on
   * this canvas, so cached layers can be painted at the resolution they'll
   * actually be shown at.
   */
  resize(W: number, H: number, sky: readonly string[], k: number): void;
  draw(f: SkyFrame): void;
}

const TAU = Math.PI * 2;
const rand = (a: number, b: number) => a + Math.random() * (b - a);

/** A W×H (logical) layer backed by W·k × H·k pixels, pre-scaled by k. */
function offscreen(W: number, H: number, k: number) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.ceil(W * k));
  c.height = Math.max(1, Math.ceil(H * k));
  const t = c.getContext("2d")!;
  t.scale(k, k);
  return [c, t] as const;
}

/** Deep base fill: the skin's base tone glowing faintly in the middle. */
function baseFill(f: SkyFrame, lift = 1) {
  const { ctx, W, H, sky } = f;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, W, H);
  const g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.hypot(W, H) * 0.6);
  g.addColorStop(0, rgba(sky[0], 1 * lift));
  g.addColorStop(1, rgba(sky[0], 0));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
}

function paintStars(
  t: CanvasRenderingContext2D, W: number, H: number, n: number,
  rMin: number, rMax: number, aMin: number, aMax: number, tints: readonly string[],
) {
  for (let i = 0; i < n; i++) {
    const x = Math.random() * W, y = Math.random() * H;
    const r = rand(rMin, rMax);
    const c = Math.random() < 0.7 ? "255,255,255" : tints[(Math.random() * tints.length) | 0];
    t.fillStyle = rgba(c, rand(aMin, aMax));
    t.beginPath(); t.arc(x, y, r, 0, TAU); t.fill();
  }
}

// ---------------------------------------------------------------------------
// DEEP FIELD — three parallax layers of stars drifting past a galactic band.
// ---------------------------------------------------------------------------

function createStarfield(): SkyScene {
  const TILE = 512;
  let layers: Array<{ pat: CanvasPattern | null; sp: number; x: number; y: number }> = [];
  let band: HTMLCanvasElement | null = null;
  let twinkles: Array<{ x: number; y: number; r: number; ph: number; sp: number; c: string }> = [];

  return {
    res: 1,
    resize(W, H, sky, k) {
      const make = (n: number, rMin: number, rMax: number, aMin: number, aMax: number) => {
        const [c, t] = offscreen(TILE, TILE, k);
        paintStars(t, TILE, TILE, n, rMin, rMax, aMin, aMax, [sky[3], sky[1]]);
        const pat = t.createPattern(c, "repeat");
        // the tile holds TILE·k pixels; map them back onto TILE logical px
        pat?.setTransform(new DOMMatrix([1 / k, 0, 0, 1 / k, 0, 0]));
        return pat;
      };
      layers = [
        { pat: make(260, 0.3, 0.7, 0.15, 0.5), sp: 3, x: 0, y: 0 },
        { pat: make(90, 0.5, 1.1, 0.3, 0.75), sp: 7, x: 0, y: 0 },
        { pat: make(26, 0.8, 1.6, 0.5, 0.95), sp: 14, x: 0, y: 0 },
      ];

      // the galactic band: a long diagonal river of soft light + dense dust
      const [c, t] = offscreen(W, H, k);
      t.translate(W / 2, H / 2);
      t.rotate(-0.42);
      const L = Math.hypot(W, H);
      t.globalCompositeOperation = "lighter";
      for (let i = 0; i < 70; i++) {
        const x = rand(-L / 2, L / 2);
        const y = rand(-1, 1) * rand(0, H * 0.12);
        const r = rand(H * 0.05, H * 0.2);
        const g = t.createRadialGradient(x, y, 0, x, y, r);
        const col = Math.random() < 0.6 ? sky[1] : Math.random() < 0.5 ? sky[2] : sky[3];
        g.addColorStop(0, rgba(col, rand(0.03, 0.08)));
        g.addColorStop(1, rgba(col, 0));
        t.fillStyle = g;
        t.beginPath(); t.arc(x, y, r, 0, TAU); t.fill();
      }
      for (let i = 0; i < 1600; i++) {
        const x = rand(-L / 2, L / 2);
        const y = (Math.random() + Math.random() + Math.random() - 1.5) * H * 0.1;
        t.fillStyle = rgba(Math.random() < 0.8 ? "255,255,255" : sky[3], rand(0.1, 0.55));
        t.fillRect(x, y, rand(0.6, 1.3), rand(0.6, 1.3));
      }
      // dark dust lanes cutting through the band
      t.globalCompositeOperation = "source-over";
      for (let i = 0; i < 26; i++) {
        const x = rand(-L / 2, L / 2);
        const y = rand(-1, 1) * H * 0.03;
        const r = rand(H * 0.02, H * 0.07);
        const g = t.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, "rgba(0,0,0,0.45)");
        g.addColorStop(1, "rgba(0,0,0,0)");
        t.fillStyle = g;
        t.beginPath(); t.ellipse(x, y, r * 2.4, r, 0, 0, TAU); t.fill();
      }
      band = c;

      twinkles = Array.from({ length: Math.round((W * H) / 18000) }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        r: rand(0.8, 1.8), ph: Math.random() * TAU, sp: rand(0.6, 2),
        c: Math.random() < 0.6 ? "255,255,255" : sky[3],
      }));
    },
    draw(f) {
      const { ctx, W, H, t, dt, tempo, bright } = f;
      baseFill(f, 0.9);
      if (band) {
        ctx.globalAlpha = Math.min(1, 0.85 * bright);
        ctx.drawImage(band, 0, 0, W, H);
        ctx.globalAlpha = 1;
      }
      for (const L of layers) {
        L.x = (L.x + L.sp * tempo * dt) % TILE;
        L.y = (L.y + L.sp * 0.45 * tempo * dt) % TILE;
        if (!L.pat) continue;
        ctx.save();
        ctx.translate(-L.x, -L.y);
        ctx.fillStyle = L.pat;
        ctx.fillRect(L.x, L.y, W, H);
        ctx.restore();
      }
      ctx.globalCompositeOperation = "lighter";
      for (const s of twinkles) {
        const a = (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * s.sp * tempo + s.ph))) * Math.min(1, bright);
        ctx.fillStyle = rgba(s.c, a);
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, TAU); ctx.fill();
        if (s.r > 1.5) {
          ctx.fillStyle = rgba(s.c, a * 0.35);
          ctx.fillRect(s.x - s.r * 5, s.y - 0.4, s.r * 10, 0.8);
          ctx.fillRect(s.x - 0.4, s.y - s.r * 5, 0.8, s.r * 10);
        }
      }
      ctx.globalCompositeOperation = "source-over";
    },
  };
}

// ---------------------------------------------------------------------------
// NEBULA — two counter-rotating cloud layers of glowing gas.
// ---------------------------------------------------------------------------

function createNebula(): SkyScene {
  let a: HTMLCanvasElement | null = null;
  let b: HTMLCanvasElement | null = null;
  let size = 0;

  const cloud = (S: number, sky: readonly string[], n: number, cols: number[], k: number) => {
    const [c, t] = offscreen(S, S, k);
    t.globalCompositeOperation = "lighter";
    // gas gathers along a few long filaments, so it reads as structure
    // with dark sky between, not an even fog
    const arms = Array.from({ length: 3 }, () => ({
      x: rand(0.25, 0.75) * S, y: rand(0.25, 0.75) * S,
      a: rand(0, TAU), len: rand(0.25, 0.5) * S, bend: rand(-0.6, 0.6),
    }));
    for (let i = 0; i < n; i++) {
      const arm = arms[i % arms.length];
      const u = rand(-0.5, 0.5);
      const ang = arm.a + arm.bend * u;
      const x = arm.x + Math.cos(ang) * arm.len * u + rand(-1, 1) * S * 0.05;
      const y = arm.y + Math.sin(ang) * arm.len * u + rand(-1, 1) * S * 0.05;
      const r = rand(S * 0.025, S * 0.11);
      const col = sky[cols[(Math.random() * cols.length) | 0]];
      const g = t.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, rgba(col, rand(0.05, 0.12)));
      g.addColorStop(1, rgba(col, 0));
      t.fillStyle = g;
      t.beginPath(); t.arc(x, y, r, 0, TAU); t.fill();
    }
    // dark dust knotted through the gas
    t.globalCompositeOperation = "source-over";
    for (let i = 0; i < n / 5; i++) {
      const arm = arms[i % arms.length];
      const u = rand(-0.5, 0.5);
      const x = arm.x + Math.cos(arm.a) * arm.len * u + rand(-1, 1) * S * 0.04;
      const y = arm.y + Math.sin(arm.a) * arm.len * u + rand(-1, 1) * S * 0.04;
      const r = rand(S * 0.015, S * 0.05);
      const g = t.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, "rgba(0,0,0,0.35)");
      g.addColorStop(1, "rgba(0,0,0,0)");
      t.fillStyle = g;
      t.beginPath(); t.arc(x, y, r, 0, TAU); t.fill();
    }
    t.globalCompositeOperation = "lighter";
    // a scatter of embedded stars, softened by the low render scale
    paintStars(t, S, S, 220, 0.4, 1.4, 0.2, 0.8, [sky[3]]);
    return c;
  };

  return {
    res: 0.35,
    resize(W, H, sky, k) {
      size = Math.hypot(W, H) * 1.05;
      a = cloud(size, sky, 120, [1, 1, 2, 3], k);
      b = cloud(size, sky, 70, [2, 2, 1, 0], k);
    },
    draw(f) {
      const { ctx, W, H, t, tempo, bright, speaking } = f;
      baseFill(f, 0.7);
      const swell = speaking ? 1 + 0.06 * Math.sin(t * 5) : 1;
      ctx.globalCompositeOperation = "lighter";
      const layer = (img: HTMLCanvasElement | null, ang: number, sc: number, al: number) => {
        if (!img) return;
        ctx.save();
        ctx.translate(W / 2, H / 2);
        ctx.rotate(ang);
        ctx.scale(sc, sc);
        ctx.globalAlpha = Math.min(1, al);
        ctx.drawImage(img, -size / 2, -size / 2, size, size);
        ctx.restore();
      };
      layer(a, t * 0.006 * tempo, 1 + 0.03 * Math.sin(t * 0.05), 0.9 * bright * swell);
      layer(b, -t * 0.009 * tempo + 1.3, 1.08 + 0.04 * Math.sin(t * 0.07 + 1), 0.65 * bright * swell);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    },
  };
}

// ---------------------------------------------------------------------------
// AURORA — curtains of light rippling across the upper sky.
// Like the real thing, each curtain has a sharp bright lower edge and rays
// rising from it that fade (and shift colour) with height. A curtain is a run
// of thin vertical strips under one gradient; the edge follows a sum of
// sines, so the whole curtain folds and drifts.
// ---------------------------------------------------------------------------

interface Curtain { y: number; h: number; amp: number; f1: number; f2: number; sp: number; ph: number; c: number; al: number; }

function createAurora(): SkyScene {
  let curtains: Curtain[] = [];
  let stars: HTMLCanvasElement | null = null;
  return {
    res: 0.4,
    resize(W, H, sky, k) {
      curtains = Array.from({ length: 4 }, (_, i) => ({
        y: H * (0.36 + i * 0.06 + Math.random() * 0.04),
        h: H * rand(0.22, 0.34),
        amp: H * rand(0.03, 0.07),
        f1: rand(1.2, 2.4) / W * TAU,
        f2: rand(3, 6) / W * TAU,
        sp: rand(0.08, 0.2) * (i % 2 ? -1 : 1),
        ph: Math.random() * TAU,
        c: i === 3 ? 2 : 1,
        al: rand(0.28, 0.45),
      }));
      const [c, t] = offscreen(W, H, k);
      paintStars(t, W, H, Math.round((W * H) / 2500), 0.4, 1.1, 0.2, 0.7, [sky[3]]);
      stars = c;
    },
    draw(f) {
      const { ctx, W, H, t, tempo, bright, speaking, sky } = f;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, W, H);
      // night sky: black overhead, a faint glow of the base tone low down
      const g0 = ctx.createLinearGradient(0, 0, 0, H);
      g0.addColorStop(0, rgba(sky[0], 0.4));
      g0.addColorStop(0.75, rgba(sky[0], 1));
      g0.addColorStop(1, rgba(sky[1], 0.08));
      ctx.fillStyle = g0;
      ctx.fillRect(0, 0, W, H);
      if (stars) ctx.drawImage(stars, 0, 0, W, H);

      ctx.globalCompositeOperation = "lighter";
      const STEP = Math.max(2, Math.round(W / 220));
      for (const cu of curtains) {
        const col = sky[cu.c];
        const ripple = speaking ? 1 + 0.25 * Math.sin(t * 6 + cu.ph) : 1;
        const al = cu.al * bright * ripple;
        // local y: 0 = the bright lower edge, h = the faded tops of the rays
        const grad = ctx.createLinearGradient(0, 0, 0, cu.h);
        grad.addColorStop(0, rgba(sky[3], 0));
        grad.addColorStop(0.03, rgba(sky[3], al * 0.6));
        grad.addColorStop(0.1, rgba(col, al * 0.55));
        grad.addColorStop(0.45, rgba(col, al * 0.16));
        grad.addColorStop(0.8, rgba(sky[2], al * 0.07));
        grad.addColorStop(1, rgba(sky[2], 0));
        ctx.fillStyle = grad;
        const ph = cu.ph + t * cu.sp * tempo;
        for (let x = 0; x < W; x += STEP) {
          const edge = cu.y + Math.sin(x * cu.f1 + ph) * cu.amp + Math.sin(x * cu.f2 - ph * 1.7) * cu.amp * 0.35;
          // rays are taller where the curtain folds
          const ray = 0.55 + 0.45 * Math.sin(x * cu.f2 * 1.9 + ph * 2.3);
          ctx.save();
          ctx.translate(x, edge);
          ctx.scale(1, -ray); // grow upward from the edge
          ctx.fillRect(0, 0, STEP + 0.5, cu.h);
          ctx.restore();
        }
      }
      ctx.globalCompositeOperation = "source-over";
    },
  };
}

// ---------------------------------------------------------------------------
// WARP — stars streaking out of the centre. Idle is a slow cruise; thinking
// jumps to warp; speaking surges with her voice.
// ---------------------------------------------------------------------------

interface WarpStar { x: number; y: number; z: number; c: number; }

function createWarp(): SkyScene {
  let stars: WarpStar[] = [];
  let speed = 0.05;
  const spawn = (far: boolean): WarpStar => ({
    x: rand(-1, 1), y: rand(-1, 1),
    z: far ? rand(0.75, 1) : rand(0.05, 1),
    c: Math.random() < 0.55 ? 3 : Math.random() < 0.6 ? 1 : 2,
  });
  return {
    res: 1,
    resize(W, H) {
      const n = Math.min(700, Math.round((W * H) / 2600));
      stars = Array.from({ length: n }, () => spawn(false));
    },
    draw(f) {
      const { ctx, W, H, t, dt, tempo, bright, speaking, sky } = f;
      // ease toward the state's cruise speed so jumps feel like acceleration
      const target = 0.035 * tempo * tempo * (speaking ? 1 + 0.5 * Math.max(0, Math.sin(t * 6)) : 1);
      speed += (target - speed) * Math.min(1, dt * 1.6);

      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, W, H);
      const cx = W / 2, cy = H / 2;
      const F = Math.max(W, H) * 0.5;
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * 0.5);
      glow.addColorStop(0, rgba(sky[1], 0.12 * bright));
      glow.addColorStop(0.4, rgba(sky[0], 0.6));
      glow.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, W, H);

      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";
      for (const s of stars) {
        const z0 = s.z;
        s.z -= speed * dt * 2;
        if (s.z <= 0.02) { Object.assign(s, spawn(true)); continue; }
        const x1 = cx + (s.x / s.z) * F, y1 = cy + (s.y / s.z) * F;
        if (x1 < -50 || x1 > W + 50 || y1 < -50 || y1 > H + 50) { Object.assign(s, spawn(true)); continue; }
        // trail length grows with speed so a cruise is dots and warp is lines
        const zt = Math.min(1, z0 + speed * 0.9);
        const x0 = cx + (s.x / zt) * F, y0 = cy + (s.y / zt) * F;
        const near = 1 - s.z;
        ctx.strokeStyle = rgba(sky[s.c], Math.min(1, (0.15 + near * 0.85) * bright));
        ctx.lineWidth = 0.4 + near * 1.8;
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1 + 0.01, y1); ctx.stroke();
      }
      ctx.globalCompositeOperation = "source-over";
    },
  };
}

// ---------------------------------------------------------------------------
// VOID — nearly nothing: sparse still stars and one slow breath of colour.
// The quiet option, and the cheapest to render.
// ---------------------------------------------------------------------------

function createVoid(): SkyScene {
  let stars: HTMLCanvasElement | null = null;
  let tw: Array<{ x: number; y: number; ph: number }> = [];
  return {
    res: 1,
    resize(W, H, sky, k) {
      const [c, t] = offscreen(W, H, k);
      paintStars(t, W, H, Math.round((W * H) / 9000), 0.3, 0.9, 0.12, 0.45, [sky[3]]);
      stars = c;
      tw = Array.from({ length: 24 }, () => ({ x: Math.random() * W, y: Math.random() * H, ph: Math.random() * TAU }));
    },
    draw(f) {
      const { ctx, W, H, t, tempo, bright, sky } = f;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, W, H);
      const breath = 0.5 + 0.5 * Math.sin(t * 0.12 * tempo);
      const g = ctx.createRadialGradient(W / 2, H * 0.55, 0, W / 2, H * 0.55, Math.max(W, H) * 0.7);
      g.addColorStop(0, rgba(sky[1], (0.025 + 0.025 * breath) * bright));
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      if (stars) ctx.drawImage(stars, 0, 0, W, H);
      for (const s of tw) {
        ctx.fillStyle = rgba(sky[3], 0.5 * (0.5 + 0.5 * Math.sin(t * 0.8 * tempo + s.ph)) * bright);
        ctx.beginPath(); ctx.arc(s.x, s.y, 1, 0, TAU); ctx.fill();
      }
    },
  };
}

const FACTORIES: Record<SkyKind, () => SkyScene> = {
  starfield: createStarfield,
  nebula: createNebula,
  aurora: createAurora,
  warp: createWarp,
  void: createVoid,
};

export const isSkyKind = (k: string): k is SkyKind => k in FACTORIES;

export function createSky(kind: SkyKind): SkyScene {
  return FACTORIES[kind]();
}

/** Same state language the universe video and particle field use. */
export const SKY_TEMPO: Record<string, number> = { idle: 1, listening: 1.2, thinking: 2.4, speaking: 1.4 };
export const SKY_BRIGHT: Record<string, number> = { idle: 1, listening: 1.1, thinking: 1.25, speaking: 1.15 };
