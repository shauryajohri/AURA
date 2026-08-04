import { useEffect, useRef } from "react";

/**
 * The cursor is a tiny black hole.
 *
 * A miniature void follows the pointer, wrapped in lensing arcs that stretch
 * along the direction of motion — the "light bending" — while tiny sparks of
 * light spiral in and vanish. Over anything clickable the lens widens and
 * charges cyan; pressing collapses it. The native cursor is hidden by CSS
 * (`cursor: none` app-wide); this canvas IS the cursor.
 *
 * Cheap on purpose: one 140px canvas, transform-only positioning, rAF.
 */

const S = 140; // canvas size — the lens lives inside this box

const CLICKABLE =
  "button, a, [role='button'], input, select, textarea, label, summary, " +
  ".osbar__item, .pageshell__tab, .san-toggle, [onclick]";

interface Spark { a: number; r: number; sp: number; sz: number; al: number; }

export default function CursorLens() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    c.width = S * DPR;
    c.height = S * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

    const pos = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    const tgt = { ...pos };
    let hover = false, down = false, visible = false;

    const sparks: Spark[] = Array.from({ length: 11 }, () => ({
      a: Math.random() * Math.PI * 2,
      r: 18 + Math.random() * 42,
      sp: 0.5 + Math.random() * 1.3,
      sz: 0.5 + Math.random() * 1.0,
      al: 0.3 + Math.random() * 0.5,
    }));

    const vel = { x: 0, y: 0 };
    const onMove = (e: MouseEvent) => {
      tgt.x = e.clientX; tgt.y = e.clientY;
      vel.x += e.movementX ?? 0;
      vel.y += e.movementY ?? 0;
      visible = true;
      const el = e.target as Element | null;
      hover = !!(el && el.closest && el.closest(CLICKABLE));
    };
    const onDown = () => { down = true; };
    const onUp = () => { down = false; };
    const onLeave = () => { visible = false; };

    let raf = 0;
    const t0 = performance.now();
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const t = (now - t0) / 1000;

      // The AURA trails the real (OS-drawn) cursor with a fast ease — that
      // slight drag is the gravity effect, and it can't feel laggy because
      // the pointer you aim with is the OS cursor, not this canvas.
      pos.x += (tgt.x - pos.x) * 0.42;
      pos.y += (tgt.y - pos.y) * 0.42;
      c.style.transform = `translate3d(${pos.x - S / 2}px, ${pos.y - S / 2}px, 0)`;
      vel.x *= 0.82; vel.y *= 0.82;
      const vx = vel.x, vy = vel.y;
      const v = Math.min(1, Math.hypot(vx, vy) / 30); // 0 still → 1 flying

      c.style.opacity = visible ? "1" : "0";
      if (!visible) return;

      ctx.clearRect(0, 0, S, S);
      const cx = S / 2, cy = S / 2;
      const R = down ? 3.6 : hover ? 7 : 5; // the void's radius

      ctx.globalCompositeOperation = "lighter";

      // light being dragged in — sparks spiral toward the void and vanish
      for (const sp of sparks) {
        sp.a += 0.02 * sp.sp * (hover ? 2.4 : 1.5);
        sp.r -= 0.16 * sp.sp * (down ? 3 : 1);
        if (sp.r < R + 3) { sp.r = 24 + Math.random() * 40; sp.a = Math.random() * Math.PI * 2; }
        const f = Math.min(1, (sp.r - R) / 12);
        ctx.fillStyle = `rgba(198,166,255,${sp.al * f})`;
        ctx.beginPath();
        ctx.arc(cx + Math.cos(sp.a) * sp.r, cy + Math.sin(sp.a) * sp.r * 0.92, sp.sz, 0, Math.PI * 2);
        ctx.fill();
      }

      // lensing arcs — rings of bent light that stretch along the motion
      // vector, so fast movement visibly warps the space around the cursor
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(Math.atan2(vy, vx));
      ctx.scale(1 + 0.4 * v, 1 - 0.22 * v);
      for (let i = 0; i < 3; i++) {
        const rr = R + 4 + i * 4.4;
        const wob = 1 + 0.06 * Math.sin(t * 3.1 + i * 2.2);
        ctx.strokeStyle = i === 0
          ? `rgba(243,217,255,${0.55 * (hover ? 1.4 : 1)})`
          : `rgba(165,110,255,${(0.4 - i * 0.12) * (hover ? 1.4 : 1)})`;
        ctx.lineWidth = i === 0 ? 1.4 : 1;
        ctx.beginPath(); ctx.arc(0, 0, rr * wob, 0, Math.PI * 2); ctx.stroke();
      }
      // one bright photon racing the innermost ring
      ctx.strokeStyle = "rgba(255,250,255,0.85)";
      ctx.lineWidth = 1.3;
      ctx.beginPath(); ctx.arc(0, 0, R + 4, t * 2.8, t * 2.8 + 1.1); ctx.stroke();
      ctx.restore();

      // soft violet gravity glow — the void itself is the OS cursor image,
      // so nothing solid is drawn here; only light.
      const g = ctx.createRadialGradient(cx, cy, R, cx, cy, R * 5);
      g.addColorStop(0, `rgba(139,92,255,${down ? 0.5 : 0.32})`);
      g.addColorStop(1, "rgba(139,92,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(cx, cy, R * 5, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
    };

    raf = requestAnimationFrame(draw);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    document.documentElement.addEventListener("mouseleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      document.documentElement.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return <canvas ref={ref} className="cursor-lens" aria-hidden="true" />;
}
