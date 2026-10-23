import { useEffect, useMemo, useRef } from "react";
import type { AuraState } from "../types";
import { useSkin } from "../skins/useSkin";
import { dustOf } from "../skins/skins";

interface Props {
  state: AuraState;
}

/* ------------------------------------------------------------------ */
/* Layer 5 — living particles above the universe video.                */
/*                                                                      */
/* Thousands of particles that react to:                                */
/*   • black-hole gravity  — slow orbital pull toward the center;       */
/*     anything falling into the protected core is re-emitted at the    */
/*     rim, so the video's empty center stays clean                     */
/*   • mouse movement      — a soft repulsion bubble around the cursor  */
/*   • AI state            — tempo/brightness follow idle/thinking/     */
/*     speaking; speaking also emits expanding light rings              */
/*                                                                      */
/* rAF pauses entirely while the window is hidden/minimized.            */
/*                                                                      */
/* The dots are drawn with WebGL, in one call. As ~1,400 separate       */
/* canvas fills a frame they cost the GPU process ~8 ms to replay —     */
/* most of what kept Home off 60 fps (docs/perf/2026-10-21-*). Same     */
/* circles: the shader uses the canvas's own anti-aliasing (coverage =  */
/* radius + ½ − distance) and its additive "lighter" blend. The few     */
/* gradient shapes (shooting stars, comet heads, speaking rings) stay   */
/* on a 2D canvas above. Without WebGL the dots go back on that canvas. */
/* ------------------------------------------------------------------ */

type RGB = readonly [number, number, number];

interface P {
  x: number; y: number;
  vx: number; vy: number;
  r: number;
  ci: number;        // index into the skin's dust colours (resolved per frame)
  base: number;      // base alpha
  tw: number;        // twinkle speed
  phase: number;
}
interface Ring { r: number; v: number; alpha: number; }
// A shooting star: one bright streak crossing part of the sky, then gone.
interface Shot { x: number; y: number; vx: number; vy: number; life: number; max: number; }
// Decorative comets — pure eye-candy, they orbit and do nothing else.
interface Comet {
  ox: number; oy: number;   // orbit center (fraction of screen)
  rx: number; ry: number;   // orbit radii (fraction of min dim)
  tilt: number;             // orbit rotation
  ang: number; w: number;   // angle + angular speed
  ci: number; size: number; // ci: 0 photon · 1 inner · 2 main
}

// Dust colours come from the active skin (skins.dustOf): for the default
// skin that's the monochrome violet set this field always had — deep
// purples and pale lavender, white for the bright ones, a rare accent.

const TEMPO: Record<string, number> = { idle: 1, listening: 1.2, thinking: 2.2, speaking: 1.5 };
const BRIGHT: Record<string, number> = { idle: 1, listening: 1.15, thinking: 1.3, speaking: 1.2 };

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const csvRgb = (s: string): RGB => {
  const [r, g, b] = s.split(",").map(Number);
  return [r / 255, g / 255, b / 255];
};

/* ---- WebGL dots ------------------------------------------------------ */
const FLOATS = 7; // per dot: x, y, radius (CSS px), then premultiplied r, g, b, a
const TAIL = 22;  // dots in each comet's tail

const VERT = `
attribute vec2 a_pos;
attribute float a_r;
attribute vec4 a_col;
uniform vec2 u_dev;      // canvas size, device px
uniform float u_dpr;
varying vec4 v_col;
varying vec2 v_center;   // device px, gl_FragCoord's bottom-left origin
varying float v_r;       // radius, device px
void main() {
  vec2 dev = a_pos * u_dpr;
  gl_Position = vec4(dev.x / u_dev.x * 2.0 - 1.0, 1.0 - dev.y / u_dev.y * 2.0, 0.0, 1.0);
  v_center = vec2(dev.x, u_dev.y - dev.y);
  // +0.04: the 2D canvas draws almost every arc() as a polygon whose
  // anti-aliased edge comes out ~0.04 device px fatter than a true circle —
  // measured dot by dot against it, so these dots carry the same light.
  v_r = a_r * u_dpr + 0.04;
  gl_PointSize = 2.0 * v_r + 3.0; // the circle plus its half-pixel fringe
  v_col = a_col;
}`;

const FRAG = `
precision highp float;
varying vec4 v_col;
varying vec2 v_center;
varying float v_r;
void main() {
  // the canvas's own circle anti-aliasing (Skia's CircleOp)
  float cov = clamp(v_r + 0.5 - distance(gl_FragCoord.xy, v_center), 0.0, 1.0);
  if (cov <= 0.0) discard;
  gl_FragColor = v_col * cov;
}`;

interface DotGL {
  gl: WebGLRenderingContext;
  uDev: WebGLUniformLocation;
  uDpr: WebGLUniformLocation;
}

/** null when WebGL (or high-precision fragment shaders) isn't available. */
function initDotGL(canvas: HTMLCanvasElement): DotGL | null {
  const gl = canvas.getContext("webgl", {
    alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false,
  });
  if (!gl || gl.isContextLost()) return null;
  const shader = (type: number, src: string) => {
    const s = gl.createShader(type);
    if (!s) return null;
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
  };
  const vs = shader(gl.VERTEX_SHADER, VERT), fs = shader(gl.FRAGMENT_SHADER, FRAG);
  const prog = gl.createProgram();
  if (!vs || !fs || !prog) return null;
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
  gl.useProgram(prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  const attr = (name: string, size: number, offset: number) => {
    const loc = gl.getAttribLocation(prog, name);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, FLOATS * 4, offset * 4);
  };
  attr("a_pos", 2, 0);
  attr("a_r", 1, 2);
  attr("a_col", 4, 3);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE); // "lighter": premultiplied source + destination
  gl.clearColor(0, 0, 0, 0);
  const uDev = gl.getUniformLocation(prog, "u_dev");
  const uDpr = gl.getUniformLocation(prog, "u_dpr");
  return uDev && uDpr ? { gl, uDev, uDpr } : null;
}

export default function ParticleField({ state }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const glCanvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  // Read per frame, so changing skin recolours the field without a rebuild.
  // Each dust colour comes as CSS for the 2D canvas and 0–1 for WebGL.
  const { skin } = useSkin();
  const fills = useMemo(() => dustOf(skin).map((c) => ({ css: `rgb(${c})`, rgb: csvRgb(c) })), [skin]);
  const fillsRef = useRef(fills);
  fillsRef.current = fills;
  const palRef = useRef(skin.pal);
  palRef.current = skin.pal;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const glCanvas = glCanvasRef.current!;
    let dotGL = initDotGL(glCanvas);
    if (!dotGL) glCanvas.style.display = "none";
    let dots = new Float32Array(0);
    let nDots = 0;
    let raf = 0;
    let W = 0, H = 0, DPR = 1;
    let ps: P[] = [];
    let rings: Ring[] = [];
    let comets: Comet[] = [];
    let shots: Shot[] = [];
    let nextShot = performance.now() + rand(4000, 9000);
    let lastRing = 0;
    const mouse = { x: -9999, y: -9999 };

    const spawn = (edge = false): P => {
      let x: number, y: number;
      if (edge) {
        // re-emit on a wide circle around the center (escaped the black hole)
        const a = Math.random() * Math.PI * 2;
        const rr = rand(Math.min(W, H) * 0.35, Math.max(W, H) * 0.6);
        x = W / 2 + Math.cos(a) * rr;
        y = H / 2 + Math.sin(a) * rr;
      } else {
        x = Math.random() * W;
        y = Math.random() * H;
      }
      return {
        x, y,
        vx: rand(-0.05, 0.05), vy: rand(-0.05, 0.05),
        r: Math.random() > 0.94 ? rand(1.3, 2.1) : rand(0.4, 1.1),
        ci: (Math.random() * 64) | 0,
        base: rand(0.2, 0.8),
        tw: rand(0.5, 2.0),
        phase: Math.random() * Math.PI * 2,
      };
    };

    const build = () => {
      DPR = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth; H = window.innerHeight;
      for (const c of [canvas, glCanvas]) {
        c.width = W * DPR; c.height = H * DPR;
        c.style.width = W + "px"; c.style.height = H + "px";
      }
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      const n = Math.min(2400, Math.round((W * H) / 900));
      ps = Array.from({ length: n }, () => spawn(false));
      rings = [];
      comets = Array.from({ length: 3 }, (_, i) => ({
        ox: rand(0.25, 0.75), oy: rand(0.25, 0.75),
        rx: rand(0.35, 0.65), ry: rand(0.18, 0.4),
        tilt: rand(0, Math.PI),
        ang: rand(0, Math.PI * 2),
        w: rand(0.00018, 0.00034) * (Math.random() < 0.5 ? 1 : -1),
        ci: i,
        size: rand(1.8, 2.6),
      }));
      dots = new Float32Array((n + comets.length * TAIL) * FLOATS);
    };

    // One dot: into the WebGL batch, or — without WebGL — straight onto the
    // 2D canvas exactly as it used to be drawn ("lighter" is set by then).
    const dot = (x: number, y: number, r: number, rgb: RGB, css: string, a: number) => {
      if (!dotGL) {
        ctx.globalAlpha = a;
        ctx.fillStyle = css;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
        return;
      }
      if (a <= 0) return;
      const o = nDots++ * FLOATS;
      dots[o] = x; dots[o + 1] = y; dots[o + 2] = r;
      dots[o + 3] = rgb[0] * a; dots[o + 4] = rgb[1] * a; dots[o + 5] = rgb[2] * a; dots[o + 6] = a;
    };
    const flushDots = () => {
      if (!dotGL) return;
      const { gl, uDev, uDpr } = dotGL;
      gl.viewport(0, 0, glCanvas.width, glCanvas.height);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(uDev, glCanvas.width, glCanvas.height);
      gl.uniform1f(uDpr, DPR);
      gl.bufferData(gl.ARRAY_BUFFER, dots.subarray(0, nDots * FLOATS), gl.DYNAMIC_DRAW);
      gl.drawArrays(gl.POINTS, 0, nDots);
      nDots = 0;
    };
    // A lost context (driver reset, GPU switch) falls back to the 2D dots
    // until the browser hands it back.
    const onLost = (e: Event) => {
      e.preventDefault();
      dotGL = null;
      glCanvas.style.display = "none";
    };
    const onRestored = () => {
      dotGL = initDotGL(glCanvas);
      glCanvas.style.display = dotGL ? "" : "none";
    };

    let prev = performance.now();
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      const dt = Math.min(50, t - prev); prev = t;

      const st = stateRef.current as string;
      const pal = palRef.current;
      const dust = fillsRef.current;
      const tempo = TEMPO[st] ?? 1;
      const bright = BRIGHT[st] ?? 1;
      const cx = W / 2, cy = H / 2;
      const core = Math.min(W, H) * 0.06;         // protected center
      const step = (dt / 16.7) * tempo;

      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      /* speaking → expanding light rings from the core */
      if (st === "speaking" && t - lastRing > 900) {
        lastRing = t;
        rings.push({ r: core * 1.4, v: 2.2, alpha: 0.5 });
      }
      for (let i = rings.length - 1; i >= 0; i--) {
        const rg = rings[i];
        rg.r += rg.v * step;
        rg.alpha *= Math.pow(0.985, step);
        if (rg.alpha < 0.01) { rings.splice(i, 1); continue; }
        ctx.globalAlpha = rg.alpha;
        ctx.strokeStyle = `rgb(${pal.soft})`;
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(cx, cy, rg.r, 0, Math.PI * 2); ctx.stroke();
      }

      /* occasional shooting star — a white streak in the skin's colours */
      if (t > nextShot) {
        nextShot = t + rand(5000, 13000);
        const fromLeft = Math.random() < 0.5;
        const sp2 = rand(0.55, 0.95);
        shots.push({
          x: fromLeft ? -30 : W + 30,
          y: rand(H * 0.06, H * 0.55),
          vx: (fromLeft ? 1 : -1) * sp2,
          vy: rand(0.08, 0.28),
          life: 0,
          max: rand(1400, 2200),
        });
      }
      for (let i = shots.length - 1; i >= 0; i--) {
        const sh = shots[i];
        sh.life += dt;
        sh.x += sh.vx * dt; sh.y += sh.vy * dt;
        if (sh.life > sh.max || sh.x < -80 || sh.x > W + 80) { shots.splice(i, 1); continue; }
        const fade = Math.sin(Math.PI * Math.min(1, sh.life / sh.max)); // in → out
        const tail = 90;
        const gsh = ctx.createLinearGradient(sh.x, sh.y, sh.x - sh.vx * tail, sh.y - sh.vy * tail);
        gsh.addColorStop(0, `rgba(${pal.photon},${0.85 * fade})`);
        gsh.addColorStop(0.35, `rgba(${pal.soft},${0.4 * fade})`);
        gsh.addColorStop(1, `rgba(${pal.main},0)`);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = gsh;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(sh.x, sh.y);
        ctx.lineTo(sh.x - sh.vx * tail, sh.y - sh.vy * tail);
        ctx.stroke();
        ctx.fillStyle = `rgba(255,252,255,${0.9 * fade})`;
        ctx.beginPath(); ctx.arc(sh.x, sh.y, 1.6, 0, Math.PI * 2); ctx.fill();
      }

      for (const p of ps) {
        /* black-hole gravity: gentle radial pull + tangential swirl */
        const dx = cx - p.x, dy = cy - p.y;
        const d2 = dx * dx + dy * dy;
        const d = Math.sqrt(d2) || 1;
        const g = Math.min(0.05, 2600 / d2) * 0.004 * tempo;
        p.vx += (dx / d) * g * dt;
        p.vy += (dy / d) * g * dt;
        // swirl (perpendicular), stronger nearer the hole
        const s = Math.min(0.03, 1200 / d2) * 0.004 * tempo;
        p.vx += (-dy / d) * s * dt;
        p.vy += (dx / d) * s * dt;

        /* mouse: soft repulsion bubble */
        const mx = p.x - mouse.x, my = p.y - mouse.y;
        const md2 = mx * mx + my * my;
        if (md2 < 160 * 160) {
          const md = Math.sqrt(md2) || 1;
          const f = (1 - md / 160) * 0.06;
          p.vx += (mx / md) * f * dt;
          p.vy += (my / md) * f * dt;
        }

        /* integrate + drag */
        p.x += p.vx * step; p.y += p.vy * step;
        p.vx *= 0.985; p.vy *= 0.985;

        /* fell into the black hole, or drifted off-screen → re-emit */
        if (d < core || p.x < -40 || p.x > W + 40 || p.y < -40 || p.y > H + 40) {
          Object.assign(p, spawn(true));
          continue;
        }

        const a = p.base * (0.55 + 0.45 * Math.sin(t * 0.001 * p.tw * tempo + p.phase)) * bright;
        const fill = dust[p.ci % dust.length];
        dot(p.x, p.y, p.r, fill.rgb, fill.css, Math.min(1, Math.max(0, a)));
      }

      /* comets — slow decorative orbits with glowing tails */
      for (const c of comets) {
        const col = c.ci === 0 ? pal.photon : c.ci === 1 ? pal.inner : pal.main;
        const colRgb = csvRgb(col), colCss = `rgba(${col},1)`;
        c.ang += c.w * dt * tempo;
        const m = Math.min(W, H);
        const pt = (a: number) => {
          const ex = Math.cos(a) * c.rx * m, ey = Math.sin(a) * c.ry * m;
          return [
            c.ox * W + ex * Math.cos(c.tilt) - ey * Math.sin(c.tilt),
            c.oy * H + ex * Math.sin(c.tilt) + ey * Math.cos(c.tilt),
          ] as const;
        };
        // tail: fading samples trailing behind along the orbit
        const dir = c.w >= 0 ? 1 : -1;
        for (let k = TAIL; k >= 1; k--) {
          const [tx, ty] = pt(c.ang - dir * k * 0.014);
          const f = 1 - k / (TAIL + 1);
          dot(tx, ty, c.size * (0.25 + 0.75 * f), colRgb, colCss, 0.4 * f * f);
        }
        // head with a soft glow
        const [hx, hy] = pt(c.ang);
        const g = ctx.createRadialGradient(hx, hy, 0, hx, hy, c.size * 7);
        g.addColorStop(0, `rgba(${col},0.9)`);
        g.addColorStop(0.3, `rgba(${col},0.35)`);
        g.addColorStop(1, `rgba(${col},0)`);
        ctx.globalAlpha = 1;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(hx, hy, c.size * 7, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.95)";
        ctx.beginPath(); ctx.arc(hx, hy, c.size * 0.9, 0, Math.PI * 2); ctx.fill();
      }

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      flushDots();
    };

    const onMouse = (e: MouseEvent) => { mouse.x = e.clientX; mouse.y = e.clientY; };
    const onLeave = () => { mouse.x = -9999; mouse.y = -9999; };
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) { prev = performance.now(); raf = requestAnimationFrame(draw); }
    };

    build();
    prev = performance.now();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", build);
    window.addEventListener("mousemove", onMouse);
    window.addEventListener("mouseout", onLeave);
    document.addEventListener("visibilitychange", onVis);
    glCanvas.addEventListener("webglcontextlost", onLost);
    glCanvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", build);
      window.removeEventListener("mousemove", onMouse);
      window.removeEventListener("mouseout", onLeave);
      document.removeEventListener("visibilitychange", onVis);
      glCanvas.removeEventListener("webglcontextlost", onLost);
      glCanvas.removeEventListener("webglcontextrestored", onRestored);
    };
  }, []);

  // Dots underneath (WebGL), the gradient shapes on top (2D). Both add light,
  // so which one sits on top makes no visible difference.
  return (
    <>
      <canvas ref={glCanvasRef} className="particle-field" aria-hidden="true" />
      <canvas ref={canvasRef} className="particle-field" aria-hidden="true" />
    </>
  );
}
