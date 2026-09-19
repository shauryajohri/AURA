/* ==========================================================================
   AURA · the black hole
   The core from the desktop app (frontend/src/components/BlackHole.tsx),
   redrawn for the page: a pure black void, a white-hot ring wrapped in
   electric violet, crackling plasma filaments, twin hotspots and the
   horizontal light blade, with sparks orbiting the ring, faint rings of bent
   light around it and ripples while she speaks. Every <canvas class="bh">
   gets one. A single loop draws only the cores that are on screen, and each
   reads AURA's state (idle, thinking, speaking) from body[data-aura] and the
   colour of her nature from body[data-nature].
   ========================================================================== */
(() => {
'use strict';

const RM = matchMedia('(prefers-reduced-motion: reduce)');
const LIGHT = matchMedia('(pointer: coarse)').matches;   /* phones get fewer particles */

/* nature -> [main, inner, photon, soft] */
const PALETTES = {
  auto:         [[125, 60, 255], [167, 109, 255], [243, 217, 255], [196, 150, 255]],
  chill:        [[64, 120, 255], [128, 168, 255], [222, 236, 255], [160, 196, 255]],
  focus:        [[140, 120, 255], [196, 182, 255], [248, 246, 255], [214, 204, 255]],
  savage:       [[232, 36, 150], [255, 84, 196], [255, 218, 242], [255, 150, 214]],
  professional: [[112, 92, 214], [176, 160, 238], [238, 234, 255], [196, 186, 242]],
};
const WHITE = [255, 252, 255];
const CYAN = [56, 225, 255];
const SPIN = { idle: 1, thinking: 5, speaking: 2.4 };
const GLOW = { idle: 0.6, thinking: 0.95, speaking: 0.9 };
const TAU = Math.PI * 2;

const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a < 0 ? 0 : a > 1 ? 1 : a})`;

const cores = [];
const pal = PALETTES.auto.map((c) => c.slice());   /* live palette, eased toward the nature's */
let rot = 0, glow = 0.6, pulse = 0, spinW = TAU / 90, raf = 0, last = 0;

function build(core) {
  const R = core.R;
  const filaments = R < 9 ? 0 : Math.round(Math.min(1, R / 30) * (LIGHT ? 56 : 104));
  core.filaments = Array.from({ length: filaments }, () => {
    const r = 1.05 + Math.pow(Math.random(), 1.8) * 0.95;   /* dense near the ring */
    const roll = Math.random();
    return {
      r,
      a0: Math.random() * TAU,
      len: 0.5 + Math.random() * 2.3,
      w: roll > 0.85 ? 0.4 + Math.random() * 0.5 : 0.6 + Math.random() * 1.3,
      c: roll > 0.92 ? -1 : roll > 0.62 ? 1 : roll > 0.28 ? 0 : 3,   /* -1 is white, otherwise a palette slot */
      al: 0.08 + Math.random() * 0.26 + Math.max(0, 1.55 - r) * 0.22,
      sp: 0.22 / r + 0.07,
      ph: Math.random() * TAU,
      amp: 0.015 + Math.random() * 0.05,
    };
  });
  core.echoes = R < 9 ? [] : Array.from({ length: 6 }, (_, i) => ({ r: 1.28 + i * 0.17 + Math.random() * 0.05, al: 0.055 - i * 0.007 }));
  /* sparks: bright motes on orbits just outside the ring, faster the closer they fly */
  const sparks = R < 7 ? 0 : Math.round(Math.min(1, R / 22) * (LIGHT ? 28 : 48));
  core.sparks = Array.from({ length: sparks }, () => {
    const r = 1.12 + Math.pow(Math.random(), 1.7) * 1.2;
    return {
      r,
      a: Math.random() * TAU,
      w: (1.15 / Math.pow(r, 1.5)) * (0.75 + Math.random() * 0.5),
      len: 0.14 + Math.random() * 0.34,
      size: 0.55 + Math.random() * 1.1,
      al: 0.3 + Math.random() * 0.55,
      c: Math.random() < 0.3 ? -1 : Math.random() < 0.5 ? 2 : 1,
    };
  });
}

function measure(core) {
  const size = core.host.offsetWidth;
  const D = core.canvas.offsetWidth;
  if (!size || !D) return false;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const px = Math.round(D * dpr);
  if (core.canvas.width !== px) { core.canvas.width = px; core.canvas.height = px; }
  const R = size * 0.2;
  const rebuild = Math.abs(R - core.R) > 0.25;
  core.D = D;
  core.R = R;
  core.dpr = px / D;
  if (rebuild) build(core);
  return true;
}

function draw(core, dt, state, now) {
  const { ctx, D, R } = core;
  const [MAIN, INNER, PHOTON] = pal;
  const s = R / 168;                                    /* the app's scale: its horizon is 168px */
  const floor = Math.min(1, Math.max(0.35, R / 20));    /* small cores keep a readable minimum line */
  const px = (v, min) => Math.max(min * floor, v * s);
  const boost = Math.min(1.8, Math.max(1, 26 / R));     /* small cores glow a little harder so they still read */
  const cx = D / 2, cy = D / 2;
  const breathe = 1 + 0.015 * Math.sin(pulse);
  const flicker = 0.84 + 0.12 * Math.sin(pulse * 5.1) + 0.05 * Math.sin(pulse * 12.7 + 1.3) + 0.04 * Math.sin(pulse * 2.3 + 0.7);

  ctx.setTransform(core.dpr, 0, 0, core.dpr, 0, 0);
  ctx.globalCompositeOperation = 'source-over';
  ctx.clearRect(0, 0, D, D);

  /* deep black backing, so the ring is the only light near the void */
  const backing = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 3);
  backing.addColorStop(0, 'rgba(0,0,0,0.94)');
  backing.addColorStop(0.5, 'rgba(0,0,3,0.62)');
  backing.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = backing;
  ctx.beginPath(); ctx.arc(cx, cy, R * 3, 0, TAU); ctx.fill();

  ctx.globalCompositeOperation = 'lighter';

  /* soft violet bloom and a hot inner glow hugging the ring */
  const bloom = ctx.createRadialGradient(cx, cy, R * 0.8, cx, cy, R * 3.1);
  bloom.addColorStop(0, rgba(MAIN, (0.2 * glow + 0.07) * boost));
  bloom.addColorStop(0.45, rgba(MAIN, 0.07 * glow * boost));
  bloom.addColorStop(1, rgba(MAIN, 0));
  ctx.fillStyle = bloom;
  ctx.beginPath(); ctx.arc(cx, cy, R * 3.1, 0, TAU); ctx.fill();
  const inner = ctx.createRadialGradient(cx, cy, R, cx, cy, R * 1.7);
  inner.addColorStop(0, rgba(INNER, 0.28 * glow));
  inner.addColorStop(1, rgba(INNER, 0));
  ctx.fillStyle = inner;
  ctx.beginPath(); ctx.arc(cx, cy, R * 1.7, 0, TAU); ctx.fill();

  /* lensing: light bent into faint rings around the void */
  for (const [k, a0] of [[1.55, 0.18], [2.3, 0.09]]) {
    ctx.strokeStyle = rgba(INNER, a0 * (0.6 + 0.5 * glow) * (0.8 + 0.2 * Math.sin(pulse * 0.9 + k)) * boost);
    ctx.lineWidth = px(1.4, 0.7);
    ctx.beginPath(); ctx.arc(cx, cy, R * k * breathe, 0, TAU); ctx.stroke();
  }

  /* faint concentric echoes, each breathing on its own phase */
  core.echoes.forEach((e, i) => {
    ctx.beginPath();
    ctx.arc(cx, cy, R * e.r * (1 + 0.025 * Math.sin(pulse * 0.7 + i * 1.9)), 0, TAU);
    ctx.strokeStyle = rgba(MAIN, Math.max(0, e.al) * (0.5 + 0.6 * glow) * (0.6 + 0.5 * Math.sin(pulse * 1.1 + i)));
    ctx.lineWidth = px(1, 0.6);
    ctx.stroke();
  });

  /* electric filaments: plasma threads whose radius wobbles on two frequencies */
  ctx.lineCap = 'round';
  const fw = Math.max(s, 0.38);
  for (const f of core.filaments) {
    f.a0 = (f.a0 + spinW * dt * f.sp * 6) % TAU;
    ctx.beginPath();
    for (let k = 0; k <= 14; k++) {
      const ang = f.a0 + rot * 0.4 + f.len * (k / 14);
      const wob = 1 + f.amp * Math.sin(ang * 7 + f.ph + pulse * 0.7) + f.amp * 0.6 * Math.sin(ang * 17 + f.ph * 2.3);
      const rr = f.r * wob * R;
      const x = cx + rr * Math.cos(ang), y = cy + rr * Math.sin(ang);
      if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    const tw = 0.55 + 0.45 * Math.sin(pulse * (1.3 + f.sp * 5) + f.ph * 3.1);
    ctx.strokeStyle = rgba(f.c < 0 ? WHITE : pal[f.c], f.al * (0.4 + 0.7 * glow) * (0.5 + tw) * boost);
    ctx.lineWidth = Math.max(0.5, f.w * fw * (0.85 + 0.3 * tw));
    ctx.stroke();
  }

  /* the event horizon: textureless black */
  ctx.globalCompositeOperation = 'source-over';
  const edge = ctx.createRadialGradient(cx, cy, R * 0.9 * breathe, cx, cy, R * 1.1 * breathe);
  edge.addColorStop(0, 'rgba(0,0,0,1)');
  edge.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = edge;
  ctx.beginPath(); ctx.arc(cx, cy, R * 1.1 * breathe, 0, TAU); ctx.fill();
  ctx.fillStyle = '#000';
  ctx.beginPath(); ctx.arc(cx, cy, R * breathe, 0, TAU); ctx.fill();

  /* the ring: a white-hot filament wrapped in violet */
  const ringR = R * 1.03 * breathe;
  ctx.globalCompositeOperation = 'lighter';
  ctx.save();
  ctx.shadowColor = rgba(MAIN, 1);
  ctx.shadowBlur = px(34, 12);
  ctx.strokeStyle = rgba(MAIN, 0.5 * glow + 0.2);
  ctx.lineWidth = px(9, 3);
  ctx.beginPath(); ctx.arc(cx, cy, ringR * 1.06, 0, TAU); ctx.stroke();
  ctx.shadowColor = rgba(INNER, 1);
  ctx.shadowBlur = px(24, 8);
  ctx.strokeStyle = rgba(INNER, 0.75 * glow + 0.22);
  ctx.lineWidth = px(4.5, 1.9);
  ctx.beginPath(); ctx.arc(cx, cy, ringR, 0, TAU); ctx.stroke();
  ctx.shadowColor = rgba(PHOTON, 1);
  ctx.shadowBlur = px(15, 5);
  ctx.strokeStyle = rgba(PHOTON, (0.78 + 0.22 * glow) * flicker);
  ctx.lineWidth = px(2.1, 1.25);
  ctx.beginPath(); ctx.arc(cx, cy, ringR * 0.985, 0, TAU); ctx.stroke();
  /* shimmer arcs racing around the ring; thinking whips them faster */
  for (let i = 0; i < 3; i++) {
    const dir = i % 2 ? -1 : 1;
    const sa = rot * (1.6 + i * 0.7) * dir + i * 2.3;
    const len = 0.7 + 0.35 * Math.sin(pulse * 1.7 + i * 2.1);
    ctx.shadowBlur = px(20, 7);
    ctx.strokeStyle = rgba(PHOTON, (0.24 + 0.24 * Math.sin(pulse * 2.4 + i * 1.4)) * glow + 0.06);
    ctx.lineWidth = px(2.6, 1.4);
    ctx.beginPath(); ctx.arc(cx, cy, ringR, sa, sa + len); ctx.stroke();
  }
  ctx.restore();

  /* sparks orbiting just outside the ring, each a bright head with a short trail */
  for (const p of core.sparks) {
    p.a = (p.a + p.w * dt * (0.4 + spinW * 7)) % TAU;
    const rr = p.r * R * (1 + 0.02 * Math.sin(pulse + p.a * 3));
    const col = p.c < 0 ? WHITE : pal[p.c];
    ctx.strokeStyle = rgba(col, p.al * (0.45 + 0.55 * glow) * 0.5);
    ctx.lineWidth = Math.max(0.5, p.size * Math.max(s * 1.6, 0.42));
    ctx.beginPath(); ctx.arc(cx, cy, rr, p.a - p.len, p.a); ctx.stroke();
    ctx.fillStyle = rgba(col, p.al * (0.6 + 0.4 * glow));
    ctx.beginPath(); ctx.arc(cx + rr * Math.cos(p.a), cy + rr * Math.sin(p.a), Math.max(0.6, p.size * Math.max(s * 2, 0.55)), 0, TAU); ctx.fill();
  }

  /* twin hotspots where the blade pierces the ring */
  for (const side of [-1, 1]) {
    const hx = cx + side * ringR;
    const flick = (1 + 0.13 * Math.sin(pulse * 3.2 + side * 1.7) + 0.07 * Math.sin(pulse * 8.9 + side * 0.6)) * (0.75 + 0.35 * flicker);
    const hr = R * 0.62 * flick;
    const g = ctx.createRadialGradient(hx, cy, 0, hx, cy, hr);
    g.addColorStop(0, rgba(WHITE, (0.9 * glow + 0.1) * flicker));
    g.addColorStop(0.16, rgba(PHOTON, (0.55 * glow + 0.1) * flicker));
    g.addColorStop(0.45, rgba(INNER, 0.24 * glow + 0.04));
    g.addColorStop(1, rgba(MAIN, 0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(hx, cy, hr, 0, TAU); ctx.fill();
  }

  /* the horizontal light blade; it pulses with her voice while she speaks */
  const talk = state === 'speaking' ? 0.25 * Math.sin(pulse * 6) : 0;
  const beamLen = Math.min(D * 0.46, R * 6.5) * (0.9 + 0.12 * Math.sin(pulse * 0.8) + talk * 0.3);
  const thick = 1 + 0.18 * (flicker - 0.84) + talk;
  const beam = (h, a0, col) => {
    const aa = a0 * flicker * (1 + talk);
    for (const side of [-1, 1]) {
      const hx = cx + side * ringR * 0.88;
      const g = ctx.createLinearGradient(hx, 0, hx + side * beamLen, 0);
      g.addColorStop(0, rgba(col, aa * (0.55 + 0.55 * glow)));
      g.addColorStop(0.3, rgba(col, aa * 0.4 * (0.55 + 0.55 * glow)));
      g.addColorStop(1, rgba(col, 0));
      ctx.fillStyle = g;
      ctx.fillRect(side < 0 ? hx - beamLen : hx, cy - h / 2, beamLen, h);
    }
  };
  beam(px(30, 6) * thick, 0.1, MAIN);
  beam(px(11, 2.4) * thick, 0.28, INNER);
  beam(px(3.4, 1.1) * thick, 0.85, PHOTON);
  beam(px(1.4, 0.75), 1, WHITE);

  /* while she speaks, ripples roll out from the ring */
  if (state === 'speaking') {
    for (let i = 0; i < 2; i++) {
      const t = ((now / 1000 + i * 0.8) % 1.6) / 1.6;
      ctx.strokeStyle = rgba(i ? CYAN : INNER, 0.42 * (1 - t) * (1 - t));
      ctx.lineWidth = px(2, 1.1);
      ctx.beginPath(); ctx.arc(cx, cy, ringR * (1.1 + t * 1.5), 0, TAU); ctx.stroke();
    }
  }

  /* about every nine seconds a gravitational pulse rolls out from the horizon */
  const gp = ((now / 1000) % 9) / 9;
  if (gp < 0.55 && R >= 9) {
    const t = gp / 0.55;
    const rr = R * (1.15 + t * 3.2);
    const a = 0.2 * (1 - t) * (1 - t) * (0.5 + 0.5 * glow);
    ctx.strokeStyle = rgba(INNER, a);
    ctx.lineWidth = px(3 - 2 * t, 0.8);
    ctx.beginPath(); ctx.arc(cx, cy, rr, 0, TAU); ctx.stroke();
    ctx.strokeStyle = rgba(PHOTON, a * 0.5);
    ctx.lineWidth = px(1.2, 0.6);
    ctx.beginPath(); ctx.arc(cx, cy, rr * 0.94, 0, TAU); ctx.stroke();
  }
  ctx.globalCompositeOperation = 'source-over';
}

function frame(now) {
  raf = 0;
  const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
  last = now;
  const body = document.body;
  const state = SPIN[body.dataset.aura] ? body.dataset.aura : 'idle';
  const want = PALETTES[body.dataset.nature] || PALETTES.auto;
  const still = RM.matches;
  const ease = still ? 1 : Math.min(1, dt * 3);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) pal[i][j] += (want[i][j] - pal[i][j]) * ease;
  spinW = (TAU / 90) * SPIN[state];
  rot = (rot + spinW * dt) % TAU;
  glow += (GLOW[state] - glow) * (still ? 1 : Math.min(1, dt * 4));
  pulse += dt * (state === 'speaking' ? 2.6 : state === 'thinking' ? 1.8 : 0.9);

  let drawn = 0;
  for (const core of cores) {
    if (!core.visible || (!core.D && !measure(core))) continue;
    draw(core, dt, state, now);
    drawn++;
  }
  /* reduced motion draws one still frame per change; hidden tabs and off-screen cores rest */
  if (drawn && !still && !document.hidden) raf = requestAnimationFrame(frame);
  else last = 0;
}

function wake() { if (!raf) raf = requestAnimationFrame(frame); }

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const core = cores.find((c) => c.canvas === e.target);
    if (core) core.visible = e.isIntersecting;
  }
  wake();
}, { rootMargin: '60px' });

const ro = new ResizeObserver((entries) => {
  for (const e of entries) {
    const core = cores.find((c) => c.host === e.target);
    if (core) measure(core);
  }
  wake();
});

document.querySelectorAll('canvas.bh').forEach((canvas) => {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const core = { canvas, host: canvas.parentElement, ctx, D: 0, R: 0, dpr: 1, visible: false, filaments: [], echoes: [], sparks: [] };
  cores.push(core);
  io.observe(canvas);
  ro.observe(core.host);
});

new MutationObserver(wake).observe(document.body, { attributes: true, attributeFilter: ['data-aura', 'data-nature'] });
document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });
RM.addEventListener('change', wake);
})();
