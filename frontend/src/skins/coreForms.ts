// ============================================================================
// Core forms — the different black holes AURA can be.
//
// BlackHole.tsx owns the canvas, the clock, the planets and the editing; a
// form only paints the core itself, from the deep glow out to the light it
// throws. Every form reads the same per-frame signals, so each one reacts to
// AURA's state in its own way rather than ignoring it:
//
//   rot / w   — spin (thinking spins hard, focus slows)
//   glow      — eased brightness for the current state × the Glow setting
//   pulse     — phase clock; faster while speaking/thinking
//   flicker   — the shared electric "life" signal
//   talk      — a voice-rate oscillation, non-zero only while speaking
//
// Colours come from `pal` every frame, so switching skins recolours a form
// live; switching FORM rebuilds it (its particles are sized at creation).
// ============================================================================

import { rgba, type CoreFormId, type CorePalette } from "./skins";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "focus" | "alert";

export interface CoreFrame {
  ctx: CanvasRenderingContext2D;
  cx: number;
  cy: number;
  /** Event-horizon radius, px. */
  R: number;
  /** Scale of the composition relative to its 680px reference. */
  s: number;
  /** Logical canvas size — caps how far beams and jets may reach. */
  D: number;
  rot: number;
  /** Angular velocity this frame (rad/s), already state- and setting-scaled. */
  w: number;
  glow: number;
  pulse: number;
  flicker: number;
  breathe: number;
  talk: number;
  dt: number;
  /** performance.now() in ms. */
  now: number;
  os: OrbState;
  pal: CorePalette;
}

export type CoreRenderer = (f: CoreFrame) => void;
type PalKey = keyof CorePalette;
/** Scales a base particle count by the user's density setting. */
export type Counter = (base: number) => number;

const TAU = Math.PI * 2;

/** Pure black disc with a soft edge — the shadow every form shares. */
function horizonDisc(f: CoreFrame, r = f.R * f.breathe) {
  const { ctx, cx, cy } = f;
  const edge = ctx.createRadialGradient(cx, cy, r * 0.9, cx, cy, r * 1.1);
  edge.addColorStop(0, "rgba(0,0,0,1)");
  edge.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = edge;
  ctx.beginPath(); ctx.arc(cx, cy, r * 1.1, 0, TAU); ctx.fill();
  ctx.fillStyle = "#000";
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.fill();
}

/** Soft glow that breathes around the whole core. Expects "lighter". */
function bloom(f: CoreFrame, c: string, inner: number, outer: number, strength = 1) {
  const { ctx, cx, cy, R, glow } = f;
  const g = ctx.createRadialGradient(cx, cy, R * inner, cx, cy, R * outer);
  g.addColorStop(0, rgba(c, (0.15 * glow + 0.04) * strength));
  g.addColorStop(0.5, rgba(c, 0.05 * glow * strength));
  g.addColorStop(1, rgba(c, 0));
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(cx, cy, R * outer, 0, TAU); ctx.fill();
}

/** One luminous wave rolling out of the core every `period` seconds. */
function gravityWave(f: CoreFrame, period: number, ry = 1) {
  const { ctx, cx, cy, R, s, glow, pal, now } = f;
  const gp = ((now / 1000) % period) / period;
  if (gp >= 0.55) return;
  const t = gp / 0.55;
  const rr = R * (1.15 + t * 3.2);
  const a = 0.2 * (1 - t) * (1 - t) * (0.5 + 0.5 * glow);
  ctx.strokeStyle = rgba(pal.inner, a);
  ctx.lineWidth = (3 - 2 * t) * s;
  ctx.beginPath(); ctx.ellipse(cx, cy, rr, rr * ry, 0, 0, TAU); ctx.stroke();
  ctx.strokeStyle = rgba(pal.photon, a * 0.5);
  ctx.lineWidth = 1.2 * s;
  ctx.beginPath(); ctx.ellipse(cx, cy, rr * 0.94, rr * 0.94 * ry, 0, 0, TAU); ctx.stroke();
}

/** A layered beam of light (haze → glow → blade → razor) along one axis. */
function beamPair(
  f: CoreFrame, axis: "x" | "y", from: number, len: number,
  layers: Array<[thick: number, alpha: number, c: string]>, gain: number,
) {
  const { ctx, cx, cy } = f;
  for (const [h, a0, c] of layers) {
    const aa = a0 * gain;
    for (const side of [-1, 1] as const) {
      if (axis === "x") {
        const hx = cx + side * from;
        const g = ctx.createLinearGradient(hx, 0, hx + side * len, 0);
        g.addColorStop(0, rgba(c, aa));
        g.addColorStop(0.3, rgba(c, aa * 0.4));
        g.addColorStop(1, rgba(c, 0));
        ctx.fillStyle = g;
        ctx.fillRect(side === -1 ? hx - len : hx, cy - h / 2, len, h);
      } else {
        const hy = cy + side * from;
        const g = ctx.createLinearGradient(0, hy, 0, hy + side * len);
        g.addColorStop(0, rgba(c, aa));
        g.addColorStop(0.3, rgba(c, aa * 0.4));
        g.addColorStop(1, rgba(c, 0));
        ctx.fillStyle = g;
        ctx.fillRect(cx - h / 2, side === -1 ? hy - len : hy, h, len);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// HORIZON — the original AURA core, moved here unchanged apart from reading
// its colours from the palette: a white-hot ring wrapped in its main colour,
// crackling filaments, twin hotspots and the horizontal lens-flare blade.
// ---------------------------------------------------------------------------

interface Filament {
  r: number; a0: number; len: number; w: number; c: PalKey;
  al: number; sp: number; ph: number; amp: number;
}

function createHorizon(N: Counter): CoreRenderer {
  const filaments: Filament[] = [];
  for (let i = 0; i < N(110); i++) {
    const rn = 1.05 + Math.pow(Math.random(), 1.8) * 0.95; // dense near the ring
    const roll = Math.random();
    filaments.push({
      r: rn,
      a0: Math.random() * TAU,
      len: 0.5 + Math.random() * 2.3,
      w: roll > 0.85 ? 0.4 + Math.random() * 0.5 : 0.6 + Math.random() * 1.3,
      c: roll > 0.92 ? "white" : roll > 0.62 ? "inner" : roll > 0.28 ? "main" : "soft",
      al: (0.08 + Math.random() * 0.26) + Math.max(0, 1.55 - rn) * 0.22,
      sp: 0.22 / rn + 0.07,
      ph: Math.random() * TAU,
      amp: 0.015 + Math.random() * 0.05,
    });
  }
  // Faint concentric swirl echoes — the ghost circles around the still.
  const echoes = Array.from({ length: 6 }, (_, i) => ({
    r: 1.28 + i * 0.17 + Math.random() * 0.05,
    al: 0.055 - i * 0.007,
  }));

  return (f) => {
    const { ctx, cx, cy, R, s, D, rot, w, dt, glow, pulse, flicker, breathe, talk, os, pal } = f;
    for (const fl of filaments) fl.a0 = (fl.a0 + w * dt * fl.sp * 6) % TAU;

    ctx.globalCompositeOperation = "lighter";

    // swirl echoes — each one slowly swells and dims on its own phase
    for (let ei = 0; ei < echoes.length; ei++) {
      const e = echoes[ei];
      const er = R * e.r * (1 + 0.025 * Math.sin(pulse * 0.7 + ei * 1.9));
      ctx.beginPath();
      ctx.arc(cx, cy, er, 0, TAU);
      ctx.strokeStyle = rgba(
        pal.main,
        Math.max(0, e.al) * (0.5 + 0.6 * glow) * (0.6 + 0.5 * Math.sin(pulse * 1.1 + ei)),
      );
      ctx.lineWidth = 1 * s;
      ctx.stroke();
    }

    // electric filaments — radius wobbles on two frequencies so each thread
    // reads as living lightning, not a clean circle
    ctx.lineCap = "round";
    for (const fl of filaments) {
      ctx.beginPath();
      const STEPS = 16;
      for (let k = 0; k <= STEPS; k++) {
        const t = k / STEPS;
        const ang = fl.a0 + rot * 0.4 + fl.len * t;
        const wob =
          1 +
          fl.amp * Math.sin(ang * 7 + fl.ph + pulse * 0.7) +
          fl.amp * 0.6 * Math.sin(ang * 17 + fl.ph * 2.3);
        const rr = fl.r * wob * R;
        const px = cx + rr * Math.cos(ang);
        const py = cy + rr * Math.sin(ang);
        if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      const tw = 0.55 + 0.45 * Math.sin(pulse * (1.3 + fl.sp * 5) + fl.ph * 3.1);
      ctx.strokeStyle = rgba(pal[fl.c], fl.al * (0.4 + 0.7 * glow) * (0.5 + tw));
      ctx.lineWidth = fl.w * s * (0.85 + 0.3 * tw);
      ctx.stroke();
    }

    bloom(f, pal.main, 0.8, 2.7);
    ctx.globalCompositeOperation = "source-over";

    horizonDisc(f);

    // THE ring — a white-hot filament wrapped in the main colour
    const ringR = R * 1.03 * breathe;
    ctx.globalCompositeOperation = "lighter";
    ctx.save();
    ctx.shadowColor = rgba(pal.main, 1);
    ctx.shadowBlur = 34 * s;
    ctx.strokeStyle = rgba(pal.main, 0.45 * glow + 0.18);
    ctx.lineWidth = 9 * s;
    ctx.beginPath(); ctx.arc(cx, cy, ringR * 1.06, 0, TAU); ctx.stroke();
    ctx.shadowColor = rgba(pal.inner, 1);
    ctx.shadowBlur = 24 * s;
    ctx.strokeStyle = rgba(pal.inner, 0.7 * glow + 0.22);
    ctx.lineWidth = 4.5 * s;
    ctx.beginPath(); ctx.arc(cx, cy, ringR, 0, TAU); ctx.stroke();
    ctx.shadowColor = rgba(pal.photon, 1);
    ctx.shadowBlur = 15 * s;
    ctx.strokeStyle = rgba(pal.photon, (0.72 + 0.28 * glow) * flicker);
    ctx.lineWidth = 2.1 * s;
    ctx.beginPath(); ctx.arc(cx, cy, ringR * 0.985, 0, TAU); ctx.stroke();
    // shimmer arcs racing around the ring at different speeds/directions
    for (let si = 0; si < 3; si++) {
      const dir = si % 2 ? -1 : 1;
      const sa = rot * (1.6 + si * 0.7) * dir + si * 2.3;
      const alen = 0.7 + 0.35 * Math.sin(pulse * 1.7 + si * 2.1);
      ctx.shadowBlur = 20 * s;
      ctx.strokeStyle = rgba(pal.photon, (0.2 + 0.22 * Math.sin(pulse * 2.4 + si * 1.4)) * glow + 0.05);
      ctx.lineWidth = 2.6 * s;
      ctx.beginPath(); ctx.arc(cx, cy, ringR, sa, sa + alen); ctx.stroke();
    }
    if (os === "speaking") {
      ctx.shadowBlur = 0;
      ctx.strokeStyle = rgba(pal.accent, 0.18 + 0.18 * Math.sin(pulse * 2));
      ctx.lineWidth = 1.8 * s;
      ctx.beginPath(); ctx.arc(cx, cy, ringR * 1.12, 0, TAU); ctx.stroke();
    }
    ctx.restore();

    // twin hotspots where the blade pierces the ring
    for (const side of [-1, 1] as const) {
      const hx = cx + side * ringR;
      const flick =
        (1 + 0.13 * Math.sin(pulse * 3.2 + side * 1.7) + 0.07 * Math.sin(pulse * 8.9 + side * 0.6)) *
        (0.75 + 0.35 * flicker);
      const hr = R * 0.6 * flick;
      const g1 = ctx.createRadialGradient(hx, cy, 0, hx, cy, hr);
      g1.addColorStop(0, rgba(pal.white, (0.9 * glow + 0.1) * flicker));
      g1.addColorStop(0.16, rgba(pal.photon, (0.55 * glow + 0.1) * flicker));
      g1.addColorStop(0.45, rgba(pal.inner, 0.22 * glow + 0.03));
      g1.addColorStop(1, rgba(pal.main, 0));
      ctx.fillStyle = g1;
      ctx.beginPath(); ctx.arc(hx, cy, hr, 0, TAU); ctx.fill();
    }

    // the horizontal lens-flare blade — breathes, and pulses with her voice
    const beamLen = Math.min(D * 0.46, R * 6.5) * (0.9 + 0.12 * Math.sin(pulse * 0.8) + talk * 0.3);
    const bh = 1 + 0.18 * (flicker - 0.84) + talk;
    const gain = flicker * (1 + talk) * (0.55 + 0.55 * glow);
    beamPair(f, "x", ringR * 0.88, beamLen, [
      [30 * s * bh, 0.09, pal.main],
      [11 * s * bh, 0.26, pal.inner],
      [3.4 * s * bh, 0.85, pal.photon],
    ], gain);
    // the razor core keeps its thickness even while she talks
    beamPair(f, "x", ringR * 0.88, beamLen, [[1.4 * s, 1.0, pal.white]], gain);

    gravityWave(f, 9);
    ctx.globalCompositeOperation = "source-over";
  };
}

// ---------------------------------------------------------------------------
// FILMED HORIZON — not drawn but filmed: the Higgsfield render of the violet
// black hole (Kling 3.0, Sep 19, from the Event Horizon redesign), looped and
// encoded as VP9 WebM whose alpha is its own light, so it lays over any sky
// and the void stays empty. A skin's main colour turns the film's hue, so it
// can be worn by any skin. Until the film can play, or if the file is
// missing, the drawn horizon stands in.
// ---------------------------------------------------------------------------

const FILM_SRC = "./skins/horizon-film.webm";
// Where the photon ring sits in the film's 1600×650 frames.
const FILM_W = 1600, FILM_H = 650, FILM_CX = 804, FILM_CY = 326, FILM_RING = 173;
/** The film's own violet, in degrees; a skin's `main` hue is measured from it. */
const FILM_HUE = 255;
const FILM_RATE: Record<OrbState, number> = {
  idle: 0.8, listening: 0.95, thinking: 1.7, speaking: 1.1, focus: 0.6, alert: 2,
};

/** One <video> for every canvas wearing the film (the core and the gallery). */
interface SharedFilm { v: HTMLVideoElement; failed: boolean; rate: number; rateAt: number }
let FILM: SharedFilm | null = null;

function sharedFilm(): SharedFilm {
  if (FILM) return FILM;
  const v = document.createElement("video");
  v.src = FILM_SRC;
  v.muted = true;
  v.loop = true;
  v.playsInline = true;
  v.preload = "auto";
  v.setAttribute("aria-hidden", "true");
  // Kept in the DOM (1px, invisible) so Chromium never parks the decoder.
  v.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none";
  document.body.append(v);
  const film: SharedFilm = { v, failed: false, rate: 1, rateAt: 0 };
  v.addEventListener("error", () => { film.failed = true; });
  const play = () => { if (v.paused && !film.failed) void v.play().catch(() => {}); };
  play();
  window.addEventListener("pointerdown", play); // in case autoplay was refused
  return (FILM = film);
}

/** Several canvases share one film: the fastest state asked for wins. */
function askRate(film: SharedFilm, rate: number, now: number) {
  if (rate >= film.rate || now - film.rateAt > 250) { film.rate = rate; film.rateAt = now; }
  if (Math.abs(film.v.playbackRate - film.rate) > 0.01) film.v.playbackRate = film.rate;
}

/** The CSS filter that turns the film's violet toward `main`. */
function filmTint(main: string): string {
  const [r, g, b] = main.split(",").map((n) => Number(n) / 255);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  if (mx - mn < 0.25 * mx) return "saturate(0.12)"; // a grey skin wears it grey
  const h = mx === r ? ((g - b) / (mx - mn)) % 6 : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4;
  const turn = ((h * 60 - FILM_HUE + 540) % 360) - 180;
  return Math.abs(turn) < 6 ? "" : `hue-rotate(${turn.toFixed(0)}deg)`;
}

function createFilm(N: Counter): CoreRenderer {
  const film = sharedFilm();
  const standIn = createHorizon(N);
  let tintFor = "", tint = "", shownAt = 0;

  return (f) => {
    const { ctx, cx, cy, R, s, breathe, glow, pulse, talk, now, os, pal } = f;
    const v = film.v;
    if (film.failed || v.readyState < 2) { shownAt = 0; standIn(f); return; }
    if (!shownAt) shownAt = now;
    askRate(film, FILM_RATE[os] ?? 1, now);
    if (tintFor !== pal.main) { tintFor = pal.main; tint = filmTint(pal.main); }

    const ring = R * 1.03 * breathe;
    // the event horizon: nothing behind it gets through
    const occ = ctx.createRadialGradient(cx, cy, ring * 0.8, cx, cy, ring * 1.02);
    occ.addColorStop(0, "rgba(0,0,0,1)");
    occ.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = occ;
    ctx.beginPath(); ctx.arc(cx, cy, ring * 1.02, 0, TAU); ctx.fill();

    // The film, brighter as she works (glow is 0.55 at idle). Its alpha is its
    // light, so dimming is just alpha and brightening is the same frame added
    // again: no canvas filter, which costs a whole extra layer on weak GPUs.
    // Only a skin of another hue pays for one (the tint).
    const g = glow / 0.55;
    const fade = Math.min(1, (now - shownAt) / 900);
    const k = ring / FILM_RING;
    const x = cx - FILM_CX * k, y = cy - FILM_CY * k, fw = FILM_W * k, fh = FILM_H * k;
    if (tint) ctx.filter = tint;
    ctx.globalAlpha = fade * Math.min(1, 0.75 + 0.35 * g);
    ctx.drawImage(v, x, y, fw, fh);
    if (g > 1.05) {
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = fade * Math.min(0.45, (g - 1) * 0.5);
      ctx.drawImage(v, x, y, fw, fh);
    }
    if (tint) ctx.filter = "none";
    ctx.globalAlpha = 1;

    // light answering what she's doing
    ctx.globalCompositeOperation = "lighter";
    if (os === "listening" || os === "speaking") {
      const b = 0.5 + 0.5 * Math.sin(pulse * 2);
      ctx.strokeStyle = rgba(pal.accent, 0.14 + 0.14 * b + Math.abs(talk) * 0.3);
      ctx.lineWidth = (os === "speaking" ? 1.8 : 1.2) * s;
      ctx.beginPath(); ctx.arc(cx, cy, ring * 1.12, 0, TAU); ctx.stroke();
    }
    gravityWave(f, os === "thinking" ? 2.2 : 9);
    ctx.globalCompositeOperation = "source-over";
  };
}

// ---------------------------------------------------------------------------
// Shared accretion-disk machinery (Gargantua + Quasar).
// A disk seen near edge-on is an ellipse; the half with sin(a) < 0 lies
// behind the shadow, the other half crosses in front of it. Particles orbit
// at Keplerian speed (inner gas laps the outer), and the side moving toward
// the viewer is Doppler-brightened.
// ---------------------------------------------------------------------------

interface DiskBit { rn: number; a: number; sp: number; len: number; w: number; al: number; c: PalKey; }

function makeDisk(n: number, rMin: number, rMax: number, hotBias: number): DiskBit[] {
  return Array.from({ length: n }, () => {
    const t = Math.pow(Math.random(), 1.6);
    const rn = rMin + t * (rMax - rMin);
    const roll = Math.random();
    return {
      rn,
      a: Math.random() * TAU,
      sp: 1 / Math.pow(rn, 1.5),
      len: 0.08 + Math.random() * 0.3,
      w: 0.6 + Math.random() * 1.6,
      al: 0.25 + Math.random() * 0.5,
      c: (t < hotBias ? (roll > 0.5 ? "hot" : "white") : roll > 0.6 ? "inner" : roll > 0.25 ? "main" : "soft") as PalKey,
    };
  });
}

function drawDiskBits(
  f: CoreFrame, bits: DiskBit[], tilt: number, front: boolean, gain: number,
) {
  const { ctx, cx, cy, R, s, pal } = f;
  ctx.lineCap = "round";
  for (const b of bits) {
    const sn = Math.sin(b.a);
    if (front ? sn < 0 : sn >= 0) continue;
    const rr = b.rn * R;
    const a1 = b.a - b.len / b.rn;
    // approaching side (left, cos < 0) burns brighter — relativistic beaming
    const doppler = 1 + 0.65 * -Math.cos(b.a);
    ctx.strokeStyle = rgba(pal[b.c], b.al * doppler * gain);
    ctx.lineWidth = b.w * s;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a1) * rr, cy + Math.sin(a1) * rr * tilt);
    ctx.lineTo(cx + Math.cos(b.a) * rr, cy + Math.sin(b.a) * rr * tilt);
    ctx.stroke();
  }
}

/**
 * The disk's gas — rear half (above the centre line, behind the shadow) or
 * front half (below it, crossing in front). A smooth elliptical annulus
 * fading from white-hot at the inner edge to nothing at the rim, a Doppler
 * wash on the approaching side, and a few faint lanes for texture.
 */
function drawDiskGas(
  f: CoreFrame, rMin: number, rMax: number, tilt: number, front: boolean, gain: number,
) {
  const { ctx, cx, cy, R, s, pal } = f;
  const r0 = R * rMin, r1 = R * rMax;
  ctx.save();
  ctx.beginPath();
  ctx.rect(cx - r1 - 2, front ? cy : cy - r1, 2 * r1 + 4, r1);
  ctx.clip();
  // fills are painted as circles in a squashed space; strokes are not, or
  // their width would squash with it
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, tilt);

  const g = ctx.createRadialGradient(0, 0, r0, 0, 0, r1);
  g.addColorStop(0, rgba(pal.white, 0.8 * gain));
  g.addColorStop(0.06, rgba(pal.hot, 0.62 * gain));
  g.addColorStop(0.22, rgba(pal.inner, 0.4 * gain));
  g.addColorStop(0.55, rgba(pal.main, 0.16 * gain));
  g.addColorStop(1, rgba(pal.main, 0));
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(0, 0, r1, 0, TAU);
  ctx.arc(0, 0, r0, 0, TAU, true);
  ctx.fill();

  // relativistic beaming: the side turning toward us burns brighter
  const d = ctx.createLinearGradient(-r1, 0, r1, 0);
  d.addColorStop(0, rgba(pal.hot, 0.3 * gain));
  d.addColorStop(0.45, rgba(pal.hot, 0.06 * gain));
  d.addColorStop(1, rgba(pal.hot, 0));
  ctx.fillStyle = d;
  ctx.beginPath();
  ctx.arc(0, 0, r1 * 0.7, 0, TAU);
  ctx.arc(0, 0, r0, 0, TAU, true);
  ctx.fill();

  ctx.restore();

  // faint lanes — the disk's grain
  ctx.lineWidth = 1.1 * s;
  for (let k = 1; k <= 5; k++) {
    const rr = r0 + (r1 - r0) * (k / 7) * (k / 7) * 1.6;
    ctx.strokeStyle = rgba(pal.photon, (0.12 - k * 0.016) * gain);
    ctx.beginPath(); ctx.ellipse(cx, cy, rr, rr * tilt, 0, 0, TAU); ctx.stroke();
  }
  ctx.restore();
}

// ---------------------------------------------------------------------------
// GARGANTUA — the Interstellar black hole. A thin, tilted disk whose far side
// is lensed up and over the shadow into a glowing arch, with a fainter
// secondary image curling under it.
// ---------------------------------------------------------------------------

function createGargantua(N: Counter): CoreRenderer {
  const TILT = 0.15;
  const bits = makeDisk(N(260), 1.35, 4.4, 0.18);
  const flares = Array.from({ length: 3 }, (_, i) => ({ a: (i * TAU) / 3, rn: 1.6 + i * 0.5 }));

  return (f) => {
    const { ctx, cx, cy, R, s, w, dt, glow, pulse, flicker, breathe, talk, os, pal } = f;
    for (const b of bits) b.a = (b.a + w * dt * b.sp * 5) % TAU;
    for (const fl of flares) fl.a = (fl.a + w * dt * 5 / Math.pow(fl.rn, 1.5)) % TAU;
    const gain = (0.55 + 0.6 * glow) * (1 + talk * 0.8) * (0.9 + 0.1 * flicker);

    ctx.globalCompositeOperation = "lighter";
    bloom(f, pal.main, 0.9, 4.2, 1.1);

    // rear half of the disk, behind the shadow
    drawDiskGas(f, 1.35, 4.4, TILT, false, gain);
    drawDiskBits(f, bits, TILT, false, gain * 0.8);

    // the lensed image of the far disk — an arch over the top of the shadow
    ctx.save();
    ctx.shadowColor = rgba(pal.inner, 1);
    for (let k = 0; k < 7; k++) {
      const t = k / 6;
      const rx = R * (1.12 + t * 0.55) * breathe;
      const ry = R * (1.08 + t * 0.75) * breathe;
      ctx.shadowBlur = (16 - t * 10) * s;
      ctx.strokeStyle = rgba(t < 0.3 ? pal.hot : t < 0.6 ? pal.inner : pal.main, (0.5 - t * 0.38) * gain);
      ctx.lineWidth = (4.2 - t * 2.4) * s;
      ctx.beginPath(); ctx.ellipse(cx, cy - R * 0.04, rx, ry, 0, Math.PI, TAU); ctx.stroke();
    }
    // and its fainter secondary image wrapping underneath
    for (let k = 0; k < 3; k++) {
      ctx.shadowBlur = 8 * s;
      ctx.strokeStyle = rgba(pal.inner, (0.26 - k * 0.07) * gain);
      ctx.lineWidth = (2.2 - k * 0.5) * s;
      ctx.beginPath();
      ctx.ellipse(cx, cy + R * 0.02, R * (1.08 + k * 0.05) * breathe, R * (1.04 + k * 0.08) * breathe, 0, 0, Math.PI);
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalCompositeOperation = "source-over";

    horizonDisc(f);

    ctx.globalCompositeOperation = "lighter";
    // photon ring — razor-thin, hugging the shadow
    ctx.save();
    ctx.shadowColor = rgba(pal.photon, 1);
    ctx.shadowBlur = 12 * s;
    ctx.strokeStyle = rgba(pal.photon, (0.6 + 0.35 * glow) * flicker);
    ctx.lineWidth = 1.6 * s;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.015 * breathe, 0, TAU); ctx.stroke();
    ctx.restore();

    // front half of the disk, sweeping across the shadow
    drawDiskGas(f, 1.35, 4.4, TILT, true, gain * 1.15);
    drawDiskBits(f, bits, TILT, true, gain);

    // hot flares riding the disk — thinking makes them whip round
    for (const fl of flares) {
      const x = cx + Math.cos(fl.a) * fl.rn * R;
      const y = cy + Math.sin(fl.a) * fl.rn * R * TILT;
      if (Math.sin(fl.a) < 0 && Math.abs(x - cx) < R) continue; // hidden behind the shadow
      const fr = R * 0.35 * (0.8 + 0.3 * Math.sin(pulse * 3 + fl.rn));
      const g = ctx.createRadialGradient(x, y, 0, x, y, fr);
      g.addColorStop(0, rgba(pal.white, 0.55 * gain));
      g.addColorStop(0.3, rgba(pal.hot, 0.25 * gain));
      g.addColorStop(1, rgba(pal.main, 0));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, fr, 0, TAU); ctx.fill();
    }

    if (os === "speaking") {
      ctx.strokeStyle = rgba(pal.accent, 0.16 + 0.16 * Math.sin(pulse * 2));
      ctx.lineWidth = 1.6 * s;
      ctx.beginPath(); ctx.ellipse(cx, cy, R * 4.7, R * 4.7 * TILT, 0, 0, TAU); ctx.stroke();
    }

    gravityWave(f, 10, TILT * 2.2);
    ctx.globalCompositeOperation = "source-over";
  };
}

// ---------------------------------------------------------------------------
// ECLIPSE — totality. The core is a moon across a star: pearly corona
// streamers fanning out, a red chromosphere with prominences, and one
// diamond-ring flare where the last light slips past the limb.
// ---------------------------------------------------------------------------

interface Streamer { a: number; len: number; wid: number; al: number; ph: number; c: PalKey; }

function createEclipse(N: Counter): CoreRenderer {
  const streamers: Streamer[] = Array.from({ length: N(72) }, () => {
    const roll = Math.random();
    return {
      a: Math.random() * TAU,
      len: 0.5 + Math.pow(Math.random(), 1.4) * 2.1,
      wid: 0.05 + Math.random() * 0.16,
      al: 0.05 + Math.random() * 0.12,
      ph: Math.random() * TAU,
      c: (roll > 0.75 ? "photon" : roll > 0.4 ? "soft" : "main") as PalKey,
    };
  });
  const proms = Array.from({ length: 5 }, () => ({
    a: Math.random() * TAU, h: 0.06 + Math.random() * 0.1, w: 0.08 + Math.random() * 0.1,
  }));

  return (f) => {
    const { ctx, cx, cy, R, s, rot, glow, pulse, flicker, breathe, talk, os, pal } = f;
    const rr = R * breathe;
    const reach = 1 + talk * 0.9 + (os === "thinking" ? 0.15 : 0);

    ctx.globalCompositeOperation = "lighter";
    // outer corona haze
    const haze = ctx.createRadialGradient(cx, cy, rr, cx, cy, rr * 3.4);
    haze.addColorStop(0, rgba(pal.photon, 0.32 * glow + 0.1));
    haze.addColorStop(0.18, rgba(pal.soft, 0.14 * glow + 0.04));
    haze.addColorStop(0.55, rgba(pal.main, 0.04 * glow));
    haze.addColorStop(1, rgba(pal.main, 0));
    ctx.fillStyle = haze;
    ctx.beginPath(); ctx.arc(cx, cy, rr * 3.4, 0, TAU); ctx.fill();

    // streamers — tapered petals of light following the field lines
    for (const st of streamers) {
      const a = st.a + rot * 0.05;
      const len = rr * st.len * (0.85 + 0.15 * Math.sin(pulse * 0.6 + st.ph)) * reach;
      const base = rr * 0.98;
      const ca = Math.cos(a), sa = Math.sin(a);
      const nx = -sa, ny = ca;
      const bw = rr * st.wid;
      const x0 = cx + ca * base, y0 = cy + sa * base;
      const x1 = cx + ca * (base + len), y1 = cy + sa * (base + len);
      const g = ctx.createLinearGradient(x0, y0, x1, y1);
      g.addColorStop(0, rgba(pal[st.c], st.al * (0.6 + 0.6 * glow) * (0.8 + 0.25 * flicker)));
      g.addColorStop(1, rgba(pal[st.c], 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(x0 + nx * bw, y0 + ny * bw);
      ctx.quadraticCurveTo(
        cx + ca * (base + len * 0.5) + nx * bw * 0.6, cy + sa * (base + len * 0.5) + ny * bw * 0.6, x1, y1);
      ctx.quadraticCurveTo(
        cx + ca * (base + len * 0.5) - nx * bw * 0.6, cy + sa * (base + len * 0.5) - ny * bw * 0.6,
        x0 - nx * bw, y0 - ny * bw);
      ctx.closePath();
      ctx.fill();
    }

    // inner corona — the bright pearl ring right at the limb
    ctx.save();
    ctx.shadowColor = rgba(pal.photon, 1);
    ctx.shadowBlur = 26 * s;
    ctx.strokeStyle = rgba(pal.photon, (0.55 + 0.35 * glow) * flicker);
    ctx.lineWidth = 5 * s;
    ctx.beginPath(); ctx.arc(cx, cy, rr * 1.02, 0, TAU); ctx.stroke();
    ctx.restore();
    ctx.globalCompositeOperation = "source-over";

    horizonDisc(f, rr);

    ctx.globalCompositeOperation = "lighter";
    // chromosphere — a hair-thin red rim with prominences looping off it
    ctx.strokeStyle = rgba(pal.hot, 0.55 * glow + 0.15);
    ctx.lineWidth = 1.3 * s;
    ctx.beginPath(); ctx.arc(cx, cy, rr * 1.004, 0, TAU); ctx.stroke();
    for (const p of proms) {
      const a = p.a + rot * 0.05;
      const h = p.h * (1 + 0.25 * Math.sin(pulse * 0.9 + p.a * 3)) * (1 + talk);
      ctx.strokeStyle = rgba(pal.hot, 0.5 * glow + 0.12);
      ctx.lineWidth = 2 * s;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a - p.w) * rr, cy + Math.sin(a - p.w) * rr);
      ctx.quadraticCurveTo(
        cx + Math.cos(a) * rr * (1 + h * 2.2), cy + Math.sin(a) * rr * (1 + h * 2.2),
        cx + Math.cos(a + p.w) * rr, cy + Math.sin(a + p.w) * rr);
      ctx.stroke();
    }

    // the diamond ring — last light slipping past the limb, slowly orbiting
    const da = -Math.PI * 0.28 + rot * 0.12;
    const dx = cx + Math.cos(da) * rr * 1.01, dy = cy + Math.sin(da) * rr * 1.01;
    const beat = os === "thinking" ? 0.25 * Math.sin(pulse * 6) : 0.1 * Math.sin(pulse * 1.6);
    const dr = rr * (0.75 + beat + talk * 0.5) * (0.85 + 0.25 * flicker);
    const dg = ctx.createRadialGradient(dx, dy, 0, dx, dy, dr);
    dg.addColorStop(0, rgba(pal.white, 0.95 * flicker));
    dg.addColorStop(0.12, rgba(pal.photon, 0.6 * glow + 0.15));
    dg.addColorStop(0.4, rgba(pal.soft, 0.18 * glow));
    dg.addColorStop(1, rgba(pal.main, 0));
    ctx.fillStyle = dg;
    ctx.beginPath(); ctx.arc(dx, dy, dr, 0, TAU); ctx.fill();
    // four-point star flare through it
    const spike = dr * 2.4;
    ctx.save();
    ctx.translate(dx, dy);
    ctx.rotate(Math.PI / 4 + rot * 0.02);
    for (const [len, th, al] of [[spike, 2.2, 0.35], [spike * 0.55, 1.2, 0.55]] as const) {
      for (let k = 0; k < 2; k++) {
        ctx.rotate(Math.PI / 2);
        const g = ctx.createLinearGradient(-len, 0, len, 0);
        g.addColorStop(0, rgba(pal.photon, 0));
        g.addColorStop(0.5, rgba(pal.white, al * flicker));
        g.addColorStop(1, rgba(pal.photon, 0));
        ctx.fillStyle = g;
        ctx.fillRect(-len, (-th * s) / 2, len * 2, th * s);
      }
    }
    ctx.restore();
    // Baily's beads trailing the diamond
    for (let k = 1; k <= 4; k++) {
      const ba = da - k * 0.09;
      const br = rr * (0.05 - k * 0.008) * (1 + 0.5 * Math.sin(pulse * 2 + k));
      ctx.fillStyle = rgba(pal.white, 0.7 - k * 0.12);
      ctx.beginPath(); ctx.arc(cx + Math.cos(ba) * rr * 1.008, cy + Math.sin(ba) * rr * 1.008, Math.max(0.6, br), 0, TAU); ctx.fill();
    }

    if (os === "speaking") {
      ctx.strokeStyle = rgba(pal.accent, 0.16 + 0.16 * Math.sin(pulse * 2));
      ctx.lineWidth = 1.6 * s;
      ctx.beginPath(); ctx.arc(cx, cy, rr * 1.18, 0, TAU); ctx.stroke();
    }

    gravityWave(f, 11);
    ctx.globalCompositeOperation = "source-over";
  };
}

// ---------------------------------------------------------------------------
// QUASAR — a fat, white-hot disk and twin relativistic jets fired along the
// spin axis, with knots of plasma racing out along a helix.
// ---------------------------------------------------------------------------

interface Knot { t: number; sp: number; ph: number; sz: number; }

function createQuasar(N: Counter): CoreRenderer {
  const TILT = 0.3;
  const bits = makeDisk(N(220), 1.15, 3.4, 0.35);
  const knots: Knot[][] = [0, 1].map(() =>
    Array.from({ length: Math.max(4, N(12)) }, () => ({
      t: Math.random(), sp: 0.08 + Math.random() * 0.12, ph: Math.random() * TAU, sz: 0.5 + Math.random() * 0.8,
    })),
  );

  return (f) => {
    const { ctx, cx, cy, R, s, D, w, dt, glow, pulse, flicker, breathe, talk, os, pal } = f;
    for (const b of bits) b.a = (b.a + w * dt * b.sp * 6) % TAU;
    const rush = os === "thinking" ? 3.2 : os === "speaking" ? 1.8 : 1;
    for (const jet of knots) for (const k of jet) k.t = (k.t + k.sp * dt * rush) % 1;
    const gain = (0.6 + 0.6 * glow) * (1 + talk * 0.6) * (0.85 + 0.15 * flicker);

    ctx.globalCompositeOperation = "lighter";
    bloom(f, pal.main, 0.6, 3.6, 1.4);

    // jets — layered blades along the vertical axis
    const jetLen = Math.min(D * 0.46, R * 7) * (0.92 + 0.1 * Math.sin(pulse * 0.7) + talk * 0.35);
    const jh = 1 + 0.2 * (flicker - 0.84) + talk;
    beamPair(f, "y", R * 0.5, jetLen, [
      [90 * s * jh, 0.12, pal.main],
      [40 * s * jh, 0.24, pal.main],
      [16 * s * jh, 0.42, pal.inner],
      [5 * s * jh, 0.8, pal.photon],
      [1.8 * s, 1.0, pal.white],
    ], gain);
    // knots of plasma corkscrewing out along each jet
    for (let j = 0; j < 2; j++) {
      const dir = j === 0 ? -1 : 1;
      for (const k of knots[j]) {
        const d = R * 0.6 + k.t * jetLen;
        const x = cx + Math.sin(k.t * 14 + k.ph + pulse * 0.8) * R * 0.1 * (0.3 + k.t);
        const y = cy + dir * d;
        const kr = R * 0.4 * k.sz * (1 - k.t * 0.55);
        const g = ctx.createRadialGradient(x, y, 0, x, y, kr);
        g.addColorStop(0, rgba(pal.white, 0.7 * (1 - k.t) * gain));
        g.addColorStop(0.35, rgba(pal.inner, 0.3 * (1 - k.t) * gain));
        g.addColorStop(1, rgba(pal.main, 0));
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, kr, 0, TAU); ctx.fill();
      }
    }

    drawDiskGas(f, 1.0, 3.4, TILT, false, gain * 1.2);
    drawDiskBits(f, bits, TILT, false, gain * 0.9);
    ctx.globalCompositeOperation = "source-over";

    horizonDisc(f, R * 0.92 * breathe);

    ctx.globalCompositeOperation = "lighter";
    // white-hot inner edge of the disk
    ctx.save();
    ctx.shadowColor = rgba(pal.hot, 1);
    ctx.shadowBlur = 22 * s;
    ctx.strokeStyle = rgba(pal.hot, (0.6 + 0.35 * glow) * flicker);
    ctx.lineWidth = 3 * s;
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.95 * breathe, 0, TAU); ctx.stroke();
    ctx.restore();

    drawDiskGas(f, 1.0, 3.4, TILT, true, gain * 1.35);
    drawDiskBits(f, bits, TILT, true, gain);

    if (os === "speaking") {
      ctx.strokeStyle = rgba(pal.accent, 0.16 + 0.16 * Math.sin(pulse * 2));
      ctx.lineWidth = 1.6 * s;
      ctx.beginPath(); ctx.ellipse(cx, cy, R * 3.7, R * 3.7 * TILT, 0, 0, TAU); ctx.stroke();
    }

    gravityWave(f, 8, TILT * 1.6);
    ctx.globalCompositeOperation = "source-over";
  };
}

// ---------------------------------------------------------------------------
// WORMHOLE — rings of light falling endlessly into a tunnel, spiral dust
// streaming down its throat, and a different sky glowing at the far end.
// ---------------------------------------------------------------------------

interface Mote { a: number; z: number; sp: number; c: PalKey; }

function createWormhole(N: Counter): CoreRenderer {
  const RINGS = 14;
  const INFALL = 5;
  let phase = 0;
  let infall = 0;
  const motes: Mote[] = Array.from({ length: N(140) }, () => ({
    a: Math.random() * TAU,
    z: Math.random(),
    sp: 0.6 + Math.random() * 0.8,
    c: (Math.random() > 0.8 ? "white" : Math.random() > 0.5 ? "inner" : "soft") as PalKey,
  }));
  const farStars = Array.from({ length: 18 }, () => ({
    a: Math.random() * TAU, r: Math.sqrt(Math.random()) * 0.4, ph: Math.random() * TAU,
  }));

  // depth z in (0,1]: 1 = the mouth, 0 = the far end. Radius shrinks fast.
  const depthR = (z: number) => Math.pow(z, 2.2);

  return (f) => {
    const { ctx, cx, cy, R, s, rot, w, dt, glow, pulse, flicker, breathe, talk, os, pal } = f;
    const speed = Math.max(0.15, w * 3.2) * (1 + talk);
    phase = (phase + dt * speed * 0.25) % 1;
    infall = (infall + dt * speed * 0.12) % 1;
    for (const m of motes) {
      m.z -= dt * speed * 0.3 * m.sp;
      m.a += (dt * speed * 0.6 * m.sp) / Math.max(0.15, m.z);
      if (m.z <= 0.02) { m.z = 1; m.a = Math.random() * TAU; }
    }
    // the mouth sits where every other form's horizon does, so planets and
    // orbit slots keep their clearance; the tunnel lives inside it
    const mouth = R * 1.04 * breathe;
    // the throat drifts a little, so the tunnel reads as having depth
    const vx = cx + Math.sin(pulse * 0.23) * mouth * 0.12;
    const vy = cy + Math.cos(pulse * 0.19) * mouth * 0.09;
    const at = (z: number) => [vx + (cx - vx) * z, vy + (cy - vy) * z] as const;

    ctx.globalCompositeOperation = "lighter";
    bloom(f, pal.main, 0.9, 2.9);
    // space falling in — faint rings outside the mouth contracting toward it
    for (let i = 0; i < INFALL; i++) {
      const t = (i / INFALL + infall) % 1; // 0 = far out, 1 = at the lip
      const rr = mouth * (2.3 - t * 1.25);
      const a = 0.09 * Math.sin(Math.PI * t) * (0.5 + 0.6 * glow);
      ctx.strokeStyle = rgba(pal.main, a);
      ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, TAU); ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";

    horizonDisc(f, mouth);

    ctx.globalCompositeOperation = "lighter";
    // the tunnel wall — lit at the lip, falling into darkness, so the
    // inside reads as depth rather than a flat black disc
    const wall = ctx.createRadialGradient(vx, vy, mouth * 0.15, cx, cy, mouth);
    wall.addColorStop(0, rgba(pal.main, 0));
    wall.addColorStop(0.55, rgba(pal.deep, 0.06 * glow + 0.02));
    wall.addColorStop(0.9, rgba(pal.main, 0.2 * glow + 0.05));
    wall.addColorStop(1, rgba(pal.inner, 0.3 * glow + 0.08));
    ctx.fillStyle = wall;
    ctx.beginPath(); ctx.arc(cx, cy, mouth, 0, TAU); ctx.fill();

    // the other sky, glowing at the end of the throat
    const farR = mouth * 0.5;
    const far = ctx.createRadialGradient(vx, vy, 0, vx, vy, farR);
    far.addColorStop(0, rgba(pal.white, 0.5 * glow + 0.15));
    far.addColorStop(0.35, rgba(pal.accent, 0.25 * glow + 0.06));
    far.addColorStop(1, rgba(pal.accent, 0));
    ctx.fillStyle = far;
    ctx.beginPath(); ctx.arc(vx, vy, farR, 0, TAU); ctx.fill();
    for (const st of farStars) {
      const tw = 0.5 + 0.5 * Math.sin(pulse * 2 + st.ph);
      ctx.fillStyle = rgba(pal.white, 0.5 * tw);
      ctx.beginPath();
      ctx.arc(vx + Math.cos(st.a + rot * 0.2) * st.r * farR, vy + Math.sin(st.a + rot * 0.2) * st.r * farR, 0.9 * s, 0, TAU);
      ctx.fill();
    }

    // the falling rings — each one slides deeper and fades, forever
    for (let i = 0; i < RINGS; i++) {
      const z = 1 - ((i / RINGS + phase) % 1);
      const rr = Math.max(1, mouth * 0.97 * depthR(z));
      const [x, y] = at(z);
      const fade = Math.min(1, z * 2.4) * Math.min(1, (1 - z) * 6);
      const lit = i % 3 === 0 ? pal.photon : pal.inner;
      ctx.strokeStyle = rgba(lit, (0.12 + 0.5 * fade) * (0.5 + 0.6 * glow) * (0.85 + 0.15 * flicker));
      ctx.lineWidth = (0.6 + 2.4 * z) * s;
      ctx.beginPath(); ctx.arc(x, y, rr, 0, TAU); ctx.stroke();
    }

    // dust streaming down the throat in spirals
    ctx.lineCap = "round";
    for (const m of motes) {
      const z0 = Math.min(1, m.z + 0.03);
      const [x0, y0] = at(z0);
      const [x1, y1] = at(m.z);
      const r0 = mouth * 0.97 * depthR(z0), r1 = mouth * 0.97 * depthR(m.z);
      const a0 = m.a - 0.08 / Math.max(0.15, m.z);
      ctx.strokeStyle = rgba(pal[m.c], 0.55 * Math.min(1, m.z * 3) * (0.5 + 0.6 * glow));
      ctx.lineWidth = (0.5 + 1.2 * m.z) * s;
      ctx.beginPath();
      ctx.moveTo(x0 + Math.cos(a0) * r0, y0 + Math.sin(a0) * r0);
      ctx.lineTo(x1 + Math.cos(m.a) * r1, y1 + Math.sin(m.a) * r1);
      ctx.stroke();
    }

    // the mouth — a bright lip of bent light
    ctx.save();
    ctx.shadowColor = rgba(pal.main, 1);
    ctx.shadowBlur = 30 * s;
    ctx.strokeStyle = rgba(pal.main, 0.4 * glow + 0.15);
    ctx.lineWidth = 7 * s;
    ctx.beginPath(); ctx.arc(cx, cy, mouth * 1.03, 0, TAU); ctx.stroke();
    ctx.shadowColor = rgba(pal.photon, 1);
    ctx.shadowBlur = 14 * s;
    ctx.strokeStyle = rgba(pal.photon, (0.6 + 0.3 * glow) * flicker);
    ctx.lineWidth = 2 * s;
    ctx.beginPath(); ctx.arc(cx, cy, mouth, 0, TAU); ctx.stroke();
    // shimmer racing around the lip
    for (let k = 0; k < 2; k++) {
      const sa = rot * (1.4 + k) * (k ? -1 : 1) + k * 2.6;
      ctx.strokeStyle = rgba(pal.white, 0.3 * glow + 0.08);
      ctx.lineWidth = 2.6 * s;
      ctx.beginPath(); ctx.arc(cx, cy, mouth, sa, sa + 0.6); ctx.stroke();
    }
    if (os === "speaking") {
      ctx.shadowBlur = 0;
      ctx.strokeStyle = rgba(pal.accent, 0.18 + 0.18 * Math.sin(pulse * 2));
      ctx.lineWidth = 1.8 * s;
      ctx.beginPath(); ctx.arc(cx, cy, mouth * 1.12, 0, TAU); ctx.stroke();
    }
    ctx.restore();

    gravityWave(f, 9);
    ctx.globalCompositeOperation = "source-over";
  };
}

const FACTORIES: Record<CoreFormId, (N: Counter) => CoreRenderer> = {
  horizon: createHorizon,
  film: createFilm,
  gargantua: createGargantua,
  eclipse: createEclipse,
  quasar: createQuasar,
  wormhole: createWormhole,
};

export function createCore(form: CoreFormId, N: Counter): CoreRenderer {
  return (FACTORIES[form] ?? createHorizon)(N);
}

/** How far the form's light reaches, in horizon radii — used to size previews. */
export const CORE_EXTENT: Record<CoreFormId, number> = {
  horizon: 2.8, film: 4.8, gargantua: 4.6, eclipse: 3.2, quasar: 3.8, wormhole: 2.4,
};
