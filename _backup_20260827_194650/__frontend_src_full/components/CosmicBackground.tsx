import { useEffect, useRef } from "react";
import type { AuraState } from "../types";

interface Props {
  state?: AuraState;
}

/* ------------------------------------------------------------------ */
/* types                                                                */
/* ------------------------------------------------------------------ */
interface Dust {
  x: number; y: number; r: number; color: string;
  base: number; tw: number; phase: number;
}
interface Node {
  x: number; y: number; r: number;      // fractional coords (0..1)
  color: string; glow: string;
  phase: number; spike: number;         // spike length multiplier
}
interface Link {
  a: number; b: number;                 // node indices
  bend: number;                         // curve bend factor
  color1: string; color2: string;
  phase: number;
}
interface Pulse { link: number; t: number; speed: number; }
interface Pillar {
  path: Path2D; topY: number; cx: number;
}
interface Ember { x: number; y: number; vy: number; vx: number; life: number; max: number; r: number; }
interface Ray { ang: number; len: number; w: number; color: string; phase: number; }
interface FunnelDrop { f: number; lane: number; speed: number; }

/* ------------------------------------------------------------------ */
/* palettes — pulled from the reference art                            */
/* ------------------------------------------------------------------ */
const DUST = [
  "#6a8cff", "#6a8cff", "#8b5cff", "#b06bff", "#ff5bd0",
  "#ff8a3c", "#38e1ff", "#ffffff", "#ffd27a", "#ff4d6d",
];

// each cluster = one constellation web with its own colour identity
const CLUSTERS: Array<{
  cx: number; cy: number; rx: number; ry: number; n: number;
  cols: string[]; glow: string;
}> = [
  // upper-left blues (over/near the pillars)
  { cx: 0.30, cy: 0.22, rx: 0.13, ry: 0.14, n: 9,  cols: ["#4d8dff", "#38b6ff", "#7aa8ff", "#ffffff"], glow: "rgba(80,140,255,0.9)" },
  // top-centre violet
  { cx: 0.52, cy: 0.12, rx: 0.11, ry: 0.09, n: 7,  cols: ["#8b5cff", "#b06bff", "#6a8cff"], glow: "rgba(150,100,255,0.9)" },
  // upper-right purple/magenta
  { cx: 0.75, cy: 0.20, rx: 0.13, ry: 0.14, n: 10, cols: ["#b06bff", "#d05bff", "#ff5bd0", "#7aa8ff"], glow: "rgba(190,90,255,0.9)" },
  // far right orange/red
  { cx: 0.90, cy: 0.45, rx: 0.09, ry: 0.16, n: 9,  cols: ["#ff8a3c", "#ff4d6d", "#ffd27a", "#ff5bd0"], glow: "rgba(255,120,70,0.9)" },
  // lower-right mixed blue/red
  { cx: 0.78, cy: 0.72, rx: 0.14, ry: 0.13, n: 10, cols: ["#38b6ff", "#ff4d6d", "#b06bff", "#ff8a3c"], glow: "rgba(255,90,140,0.85)" },
  // lower-left violet/blue
  { cx: 0.20, cy: 0.74, rx: 0.13, ry: 0.13, n: 9,  cols: ["#8b5cff", "#4d8dff", "#ff5bd0", "#38b6ff"], glow: "rgba(130,110,255,0.9)" },
  // mid-left cyan accents
  { cx: 0.11, cy: 0.50, rx: 0.07, ry: 0.11, n: 6,  cols: ["#38e1ff", "#4d8dff", "#ffffff"], glow: "rgba(80,200,255,0.9)" },
];

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const pick = <T,>(arr: T[]) => arr[(Math.random() * arr.length) | 0];

/**
 * LIVE cosmic scene matching the reference art:
 *  - deep space dust of twinkling multicolour stars
 *  - constellation webs: bright diffraction-spike nodes joined by glowing
 *    curved filaments in blue / violet / magenta / orange clusters,
 *    with energy pulses travelling along the lines
 *  - Pillars of Creation upper-left (blue nebula, rust silhouettes,
 *    hot orange rim-light, drifting embers)
 *  - a shimmering lattice funnel falling from the central black hole
 *    (the BlackHole component renders on top of this seam)
 *  - the Great Attractor burst low-centre with radiating filaments
 * Reacts to AURA's state (faster / brighter when thinking / speaking).
 */
export default function CosmicBackground({ state = "idle" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let W = 0, H = 0, DPR = 1;

    let dust: Dust[] = [];
    let nodes: Node[] = [];
    let links: Link[] = [];
    let pulses: Pulse[] = [];
    let pillars: Pillar[] = [];
    let embers: Ember[] = [];
    let rays: Ray[] = [];
    let drops: FunnelDrop[] = [];

    /* ---------------- pillars (kept from the original design) ------- */
    const buildPillar = (baseX: number, baseHalf: number, topY: number, lean: number): Pillar => {
      const baseY = H + 10;
      const steps = 22;
      const left: [number, number][] = [];
      const right: [number, number][] = [];
      const s1 = Math.random() * 10, s2 = Math.random() * 10;
      for (let i = 0; i <= steps; i++) {
        const f = i / steps;
        const y = baseY + (topY - baseY) * f;
        const cx = baseX + lean * (baseY - y);
        const half = baseHalf * (1 - 0.55 * f) * (0.85 + 0.15 * Math.sin(f * 7 + s1));
        left.push([cx - half + Math.sin(f * 9 + s1) * baseHalf * 0.18, y]);
        right.push([cx + half + Math.sin(f * 8 + s2) * baseHalf * 0.18, y]);
      }
      const p = new Path2D();
      p.moveTo(left[0][0], left[0][1]);
      for (const [x, y] of left) p.lineTo(x, y);
      for (let i = right.length - 1; i >= 0; i--) p.lineTo(right[i][0], right[i][1]);
      p.closePath();
      return { path: p, topY, cx: baseX };
    };

    const spawnEmber = (): Ember => {
      const p = pillars.length ? pillars[(Math.random() * pillars.length) | 0] : null;
      const x = p ? p.cx + rand(-40, 60) : rand(0, W * 0.3);
      const y = p ? rand(p.topY, H) : rand(0, H);
      const max = rand(2600, 6000);
      return { x, y, vy: -rand(4, 12) / 100, vx: rand(2, 8) / 100, life: Math.random() * max, max, r: rand(0.6, 1.8) };
    };

    /* ---------------- scene construction ---------------------------- */
    const build = () => {
      DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

      // --- background dust ---
      dust = [];
      const count = Math.round((W * H) / 3800);
      for (let i = 0; i < count; i++) {
        const bright = Math.random();
        dust.push({
          x: Math.random() * W, y: Math.random() * H,
          r: bright > 0.96 ? rand(1.4, 2.2) : rand(0.4, 1.2),
          color: pick(DUST),
          base: rand(0.25, 0.85), tw: rand(0.6, 2.2),
          phase: Math.random() * Math.PI * 2,
        });
      }

      // --- constellation webs ---
      nodes = []; links = []; pulses = [];
      const clusterStart: number[] = [];
      for (const c of CLUSTERS) {
        clusterStart.push(nodes.length);
        for (let i = 0; i < c.n; i++) {
          const a = Math.random() * Math.PI * 2;
          const rr = Math.pow(Math.random(), 0.7);
          nodes.push({
            x: c.cx + Math.cos(a) * rr * c.rx,
            y: c.cy + Math.sin(a) * rr * c.ry,
            r: rand(1.6, 3.4),
            color: pick(c.cols), glow: c.glow,
            phase: Math.random() * Math.PI * 2,
            spike: rand(2.6, 5.2),
          });
        }
        // intra-cluster: connect each node to its 2 nearest siblings
        const s = clusterStart[clusterStart.length - 1];
        for (let i = s; i < nodes.length; i++) {
          const near = [];
          for (let j = s; j < nodes.length; j++) {
            if (i === j) continue;
            near.push({ j, d: Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y) });
          }
          near.sort((a2, b2) => a2.d - b2.d);
          for (let k = 0; k < Math.min(2, near.length); k++) {
            const j = near[k].j;
            if (!links.some((l) => (l.a === i && l.b === j) || (l.a === j && l.b === i))) {
              links.push({
                a: i, b: j, bend: rand(-0.18, 0.18),
                color1: nodes[i].color, color2: nodes[j].color,
                phase: Math.random() * Math.PI * 2,
              });
            }
          }
        }
      }
      // inter-cluster bridges: long sweeping arcs like in the art
      for (let c = 0; c < CLUSTERS.length; c++) {
        const d = (c + 1) % CLUSTERS.length;
        const i = clusterStart[c] + ((Math.random() * CLUSTERS[c].n) | 0);
        const j = clusterStart[d] + ((Math.random() * CLUSTERS[d].n) | 0);
        links.push({
          a: i, b: j, bend: rand(-0.3, 0.3),
          color1: nodes[i].color, color2: nodes[j].color,
          phase: Math.random() * Math.PI * 2,
        });
      }
      // energy pulses travelling the web
      for (let i = 0; i < Math.min(18, links.length); i++) {
        pulses.push({ link: (Math.random() * links.length) | 0, t: Math.random(), speed: rand(0.00004, 0.00012) });
      }

      // --- pillars, upper-left ---
      const u = W / 1500;
      pillars = [
        buildPillar(W * 0.05, 78 * u, H * 0.30, 0.10),
        buildPillar(W * 0.14, 62 * u, H * 0.18, 0.12),
        buildPillar(W * 0.21, 48 * u, H * 0.34, 0.14),
        buildPillar(W * 0.26, 34 * u, H * 0.46, 0.16),
      ];
      embers = [];
      for (let i = 0; i < 46; i++) embers.push(spawnEmber());

      // --- attractor rays (precomputed => no flicker) ---
      rays = [];
      for (let k = 0; k < 42; k++) {
        // sweep the full lower hemisphere and curl up the sides
        const ang = -Math.PI + (Math.PI * 1.4) * (k / 41) - Math.PI * 0.2;
        rays.push({
          ang, len: rand(H * 0.18, H * 0.55),
          w: rand(0.6, 1.4),
          color: pick(["rgba(255,150,190,", "rgba(190,110,255,", "rgba(255,170,110,", "rgba(120,150,255,"]),
          phase: Math.random() * Math.PI * 2,
        });
      }

      // --- funnel particles ---
      drops = [];
      for (let i = 0; i < 26; i++) drops.push({ f: Math.random(), lane: rand(-1, 1), speed: rand(0.00006, 0.00016) });
    };

    /* ---------------- helpers --------------------------------------- */
    const linkPts = (l: Link) => {
      const ax = nodes[l.a].x * W, ay = nodes[l.a].y * H;
      const bx = nodes[l.b].x * W, by = nodes[l.b].y * H;
      const mx = (ax + bx) / 2 - (by - ay) * l.bend;
      const my = (ay + by) / 2 + (bx - ax) * l.bend;
      return { ax, ay, bx, by, mx, my };
    };
    const qPoint = (p: ReturnType<typeof linkPts>, t: number) => ({
      x: (1 - t) * (1 - t) * p.ax + 2 * (1 - t) * t * p.mx + t * t * p.bx,
      y: (1 - t) * (1 - t) * p.ay + 2 * (1 - t) * t * p.my + t * t * p.by,
    });

    /* ---------------- frame ------------------------------------------ */
    const draw = (t: number) => {
      const st = stateRef.current;
      const tempo = st === "thinking" ? 2.2 : st === "speaking" ? 1.5 : 1;
      const breathe = 0.82 + 0.18 * Math.sin(t * 0.0005 * tempo);
      const cx = W / 2;

      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      /* nebula glows */
      const neb = (x: number, y: number, r: number, col: string, a: number) => {
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, col); g.addColorStop(1, "transparent");
        ctx.globalAlpha = a * breathe; ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      };
      neb(W * 0.14, H * 0.30, W * 0.20, "rgba(80,130,255,0.9)", 0.22);
      neb(W * 0.10, H * 0.46, W * 0.16, "rgba(140,90,255,0.9)", 0.16);
      neb(W * 0.20, H * 0.22, W * 0.13, "rgba(120,200,255,0.9)", 0.14);
      neb(W * 0.78, H * 0.20, W * 0.16, "rgba(170,90,255,0.8)", 0.10);
      neb(W * 0.90, H * 0.50, W * 0.13, "rgba(255,110,60,0.8)", 0.09);

      /* dust stars */
      for (const s of dust) {
        const a = s.base * (0.6 + 0.4 * Math.sin(t * 0.001 * s.tw + s.phase));
        ctx.globalAlpha = Math.max(0, a); ctx.fillStyle = s.color;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
      }

      /* constellation filaments */
      for (const l of links) {
        const p = linkPts(l);
        const g = ctx.createLinearGradient(p.ax, p.ay, p.bx, p.by);
        g.addColorStop(0, l.color1); g.addColorStop(1, l.color2);
        ctx.strokeStyle = g; ctx.lineWidth = 1;
        ctx.globalAlpha = 0.16 + 0.10 * Math.sin(t * 0.0008 * tempo + l.phase);
        ctx.beginPath(); ctx.moveTo(p.ax, p.ay);
        ctx.quadraticCurveTo(p.mx, p.my, p.bx, p.by); ctx.stroke();
      }

      /* pulses running along the filaments */
      for (const pu of pulses) {
        pu.t += pu.speed * 16 * tempo;
        if (pu.t > 1) { pu.t = 0; pu.link = (Math.random() * links.length) | 0; }
        const l = links[pu.link];
        const pos = qPoint(linkPts(l), pu.t);
        ctx.globalAlpha = 0.85;
        ctx.fillStyle = "#ffffff";
        ctx.beginPath(); ctx.arc(pos.x, pos.y, 1.3, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 0.25; ctx.fillStyle = l.color1;
        ctx.beginPath(); ctx.arc(pos.x, pos.y, 3.6, 0, Math.PI * 2); ctx.fill();
      }

      /* constellation nodes with diffraction spikes */
      for (const n of nodes) {
        const x = n.x * W, y = n.y * H;
        const a = 0.65 + 0.35 * Math.sin(t * 0.0012 * tempo + n.phase);
        const sp = n.r * n.spike * (0.8 + 0.2 * a);
        // halo
        const g = ctx.createRadialGradient(x, y, 0, x, y, sp * 2.2);
        g.addColorStop(0, n.glow); g.addColorStop(1, "transparent");
        ctx.globalAlpha = 0.30 * a; ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, sp * 2.2, 0, Math.PI * 2); ctx.fill();
        // spikes (4-point cross)
        ctx.globalAlpha = 0.75 * a; ctx.strokeStyle = n.color; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x - sp, y); ctx.lineTo(x + sp, y);
        ctx.moveTo(x, y - sp); ctx.lineTo(x, y + sp);
        ctx.stroke();
        // core
        ctx.globalAlpha = a; ctx.fillStyle = "#ffffff";
        ctx.beginPath(); ctx.arc(x, y, n.r * 0.9, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = a * 0.8; ctx.fillStyle = n.color;
        ctx.beginPath(); ctx.arc(x, y, n.r * 1.6, 0, Math.PI * 2); ctx.fill();
      }

      /* pillars: dark silhouettes + hot rim */
      ctx.globalCompositeOperation = "source-over";
      for (const pl of pillars) {
        const g = ctx.createLinearGradient(0, pl.topY, 0, H);
        g.addColorStop(0, "rgba(40,20,30,0.96)");
        g.addColorStop(0.5, "rgba(14,7,14,0.99)");
        g.addColorStop(1, "#050208");
        ctx.globalAlpha = 1; ctx.fillStyle = g; ctx.fill(pl.path);
      }
      ctx.globalCompositeOperation = "lighter";
      for (const pl of pillars) {
        const g = ctx.createLinearGradient(0, pl.topY, 0, H);
        g.addColorStop(0, "rgba(255,190,90,0.9)");
        g.addColorStop(0.4, "rgba(255,120,40,0.5)");
        g.addColorStop(1, "rgba(180,50,30,0.15)");
        ctx.strokeStyle = g; ctx.lineWidth = 1.6;
        ctx.shadowColor = "rgba(255,140,50,0.8)"; ctx.shadowBlur = 12 * breathe;
        ctx.globalAlpha = 0.55 * breathe; ctx.stroke(pl.path);
      }
      ctx.shadowBlur = 0;

      /* embers */
      for (const e of embers) {
        e.life += 16; e.x += e.vx * 16; e.y += e.vy * 16;
        if (e.life > e.max || e.y < H * 0.12) Object.assign(e, spawnEmber());
        const lf = 1 - e.life / e.max;
        ctx.globalAlpha = Math.max(0, lf) * 0.8;
        ctx.fillStyle = "#ffb057";
        ctx.beginPath(); ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2); ctx.fill();
      }

      /* lattice funnel: black hole -> attractor burst */
      const fTop = H * 0.55, fBot = H * 0.90;
      const lanes = 7;
      for (let ln = 0; ln < lanes; ln++) {
        const off = (ln / (lanes - 1) - 0.5) * 2;            // -1..1
        ctx.globalAlpha = 0.10 + 0.06 * Math.sin(t * 0.001 * tempo + ln);
        ctx.strokeStyle = ln % 2 ? "rgba(200,120,255,1)" : "rgba(255,150,120,1)";
        ctx.lineWidth = 0.9;
        ctx.beginPath();
        for (let i = 0; i <= 20; i++) {
          const f = i / 20;
          const width = (1 - f) * W * 0.045 * (1 + 0.3 * Math.sin(f * 6 + t * 0.0008 + ln));
          const x = cx + off * width;
          const y = fTop + (fBot - fTop) * f;
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      // falling sparks in the funnel
      for (const d of drops) {
        d.f += d.speed * 16 * tempo;
        if (d.f > 1) { d.f = 0; d.lane = rand(-1, 1); }
        const width = (1 - d.f) * W * 0.045;
        const x = cx + d.lane * width;
        const y = fTop + (fBot - fTop) * d.f;
        ctx.globalAlpha = 0.7 * (0.4 + 0.6 * d.f);
        ctx.fillStyle = d.lane > 0 ? "#d08cff" : "#ffb693";
        ctx.beginPath(); ctx.arc(x, y, 1.1, 0, Math.PI * 2); ctx.fill();
      }

      /* Great Attractor burst */
      const ax = cx, ay = fBot;
      const flare = st === "speaking" ? 1.3 : st === "thinking" ? 1.15 : 1;
      const glow = ctx.createRadialGradient(ax, ay, 0, ax, ay, 240 * flare);
      glow.addColorStop(0, "rgba(255,200,140,0.65)");
      glow.addColorStop(0.2, "rgba(255,120,180,0.32)");
      glow.addColorStop(0.55, "rgba(160,90,255,0.14)");
      glow.addColorStop(1, "rgba(160,90,255,0)");
      ctx.globalAlpha = breathe; ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(ax, ay, 240 * flare, 0, Math.PI * 2); ctx.fill();
      // radiating filaments (stable, shimmering)
      for (const r of rays) {
        const shim = 0.5 + 0.5 * Math.sin(t * 0.0009 * tempo + r.phase);
        ctx.globalAlpha = (0.05 + 0.09 * shim) * flare;
        ctx.strokeStyle = r.color + "1)";
        ctx.lineWidth = r.w;
        const ex = ax + Math.cos(r.ang) * r.len;
        const ey = ay + Math.sin(r.ang) * r.len * 0.85;
        const mx2 = ax + Math.cos(r.ang) * r.len * 0.5 + Math.sin(r.ang) * 30;
        const my2 = ay + Math.sin(r.ang) * r.len * 0.45;
        ctx.beginPath(); ctx.moveTo(ax, ay);
        ctx.quadraticCurveTo(mx2, my2, ex, ey); ctx.stroke();
      }
      // white-hot core
      ctx.globalAlpha = 0.9 * breathe;
      const core = ctx.createRadialGradient(ax, ay, 0, ax, ay, 26 * flare);
      core.addColorStop(0, "rgba(255,255,255,0.95)");
      core.addColorStop(0.4, "rgba(255,190,130,0.6)");
      core.addColorStop(1, "transparent");
      ctx.fillStyle = core;
      ctx.beginPath(); ctx.arc(ax, ay, 26 * flare, 0, Math.PI * 2); ctx.fill();

      ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
      raf = requestAnimationFrame(draw);
    };

    build();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", build); };
  }, []);

  return <canvas ref={canvasRef} className="cosmic" />;
}
