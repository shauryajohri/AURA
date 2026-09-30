import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { coreGeom } from "../lib/coreBus";
import { sfx } from "../lib/sfx";

/**
 * AURA's own cursor: a photon and its horizon.
 *
 *   photon  — a small point of light pinned exactly to the pointer (no lag;
 *             it is what you aim with)
 *   horizon — a thin ring that trails it on a spring and stretches with
 *             speed. Over a button it wraps the button's shape; over a
 *             text field the photon becomes a caret; near the black hole
 *             it gets pulled toward the core.
 *
 * Clicks leave a ripple. The OS cursor is hidden app-wide (styles), except
 * over resize grips, which keep the native arrows, and inside embedded pages
 * (iframes), which draw their own.
 *
 * It lives in <body>, above everything — popovers portalled to <body> (the
 * room picker) would otherwise cover it while the system cursor is hidden.
 */

const CLICKABLE =
  "button, a, [role='button'], [role='switch'], [role='tab'], select, summary, label, " +
  "input[type='range'], input[type='checkbox'], input[type='radio'], .clickable";
const TEXT = "input:not([type]), input[type='text'], input[type='search'], input[type='email'], " +
  "input[type='url'], input[type='password'], input[type='number'], textarea, [contenteditable='true']";
const NATIVE = ".resizer, [data-native-cursor]";
const RING = 34;

// Where the pointer was last seen, kept across mounts: switching the cursor
// back on in Settings shows it right there instead of waiting for a move.
const lastSeen = { x: 0, y: 0, known: false };

export default function AuraCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dot = dotRef.current!;
    const ring = ringRef.current!;
    const layer = layerRef.current!;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const p = { x: lastSeen.x, y: lastSeen.y };     // the pointer
    const r = { x: p.x, y: p.y, w: RING, h: RING, rad: RING / 2 }; // the ring (animated)
    const v = { x: 0, y: 0 };                       // ring velocity (spring)
    let mode: "free" | "snap" | "text" | "native" = "free";
    let snap: DOMRect | null = null;
    let snapRad = 12;
    let hot = false;
    let down = false;
    let visible = false;
    let lastTarget: Element | null = null;

    const classify = (el: Element | null) => {
      if (!el || !el.closest) { mode = "free"; hot = false; snap = null; return; }
      // an embedded page gets no events from us while the pointer is inside it
      if (el.closest(NATIVE) || el.tagName === "IFRAME") { mode = "native"; hot = false; snap = null; return; }
      if (el.closest(TEXT)) { mode = "text"; hot = false; snap = null; return; }
      const c = el.closest(CLICKABLE) as HTMLElement | null;
      if (c && !(c as HTMLButtonElement).disabled) {
        const b = c.getBoundingClientRect();
        if (b.width <= 132 && b.height <= 64 && b.width > 0) {
          mode = "snap";
          snap = b;
          const br = parseFloat(getComputedStyle(c).borderTopLeftRadius) || 8;
          snapRad = Math.min(b.height / 2 + 5, br + 5);
        } else {
          mode = "free";
          snap = null;
        }
        if (c !== lastTarget) sfx.hover();
        lastTarget = c;
        hot = true;
        return;
      }
      lastTarget = null;
      mode = "free"; hot = false; snap = null;
    };

    const show = () => {
      dot.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`;
      if (!visible) {
        visible = true;
        layer.classList.add("acur--on");
        r.x = p.x; r.y = p.y;
      }
    };
    const onMove = (e: MouseEvent) => {
      p.x = e.clientX; p.y = e.clientY;
      lastSeen.x = p.x; lastSeen.y = p.y; lastSeen.known = true;
      show();
      classify(e.target as Element);
    };
    // Native drag-and-drop (a file dragged onto the dock) sends no mousemove.
    const onDrag = (e: DragEvent) => {
      if (!e.clientX && !e.clientY) return;
      p.x = e.clientX; p.y = e.clientY;
      lastSeen.x = p.x; lastSeen.y = p.y; lastSeen.known = true;
      show();
    };
    if (lastSeen.known) {
      show();
      classify(document.elementFromPoint(p.x, p.y));
    }
    // Elements move under a still pointer (scrolling, reflow) — re-check.
    const onScroll = () => {
      if (!visible) return;
      classify(document.elementFromPoint(p.x, p.y));
    };
    const onDown = (e: MouseEvent) => {
      down = true;
      if (e.button === 0 && (hot || coreGeom.hot)) sfx.tap();
    };
    const onUp = (e: MouseEvent) => {
      down = false;
      if (e.button !== 0 || mode === "native" || reduce) return;
      const rip = document.createElement("span");
      rip.className = "acur__ripple" + (hot || coreGeom.hot ? " acur__ripple--hot" : "");
      rip.style.left = e.clientX + "px";
      rip.style.top = e.clientY + "px";
      layer.append(rip);
      rip.addEventListener("animationend", () => rip.remove());
    };
    const onLeave = () => { visible = false; lastSeen.known = false; layer.classList.remove("acur--on"); };

    let raf = 0;
    let last = performance.now();
    let recheck = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      // The page changes under a still pointer (a menu closes, a page opens):
      // look again at what's under it, so the ring never hugs a ghost.
      if (visible && now > recheck) {
        recheck = now + 250;
        classify(document.elementFromPoint(p.x, p.y));
      }
      const sceneHot = mode === "free" && coreGeom.hot;

      // where the ring wants to be, and what shape
      let tx = p.x, ty = p.y, tw = RING, th = RING, trad = RING / 2;
      if (mode === "snap" && snap) {
        tx = snap.left + snap.width / 2 + (p.x - (snap.left + snap.width / 2)) * 0.12;
        ty = snap.top + snap.height / 2 + (p.y - (snap.top + snap.height / 2)) * 0.12;
        tw = snap.width + 10; th = snap.height + 10; trad = snapRad;
      } else if (hot || sceneHot) {
        tw = th = 52; trad = 26;
      } else if (mode === "text") {
        tw = th = 12; trad = 6;
      }
      if (down) { tw *= 0.86; th *= 0.86; trad *= 0.86; }

      // the black hole pulls the ring toward itself
      if (mode === "free" && coreGeom.r > 0) {
        const dx = coreGeom.x - p.x, dy = coreGeom.y - p.y;
        const d = Math.hypot(dx, dy) || 1;
        const reach = coreGeom.r * 4;
        if (d < reach) {
          const f = Math.pow(1 - d / reach, 1.6) * 14;
          tx += (dx / d) * f; ty += (dy / d) * f;
        }
      }

      if (reduce) {
        r.x = tx; r.y = ty;
      } else {
        // spring: stiff enough to feel attached, loose enough to trail
        const k = mode === "snap" ? 520 : 380, c = mode === "snap" ? 34 : 26;
        v.x += ((tx - r.x) * k - v.x * c) * dt;
        v.y += ((ty - r.y) * k - v.y * c) * dt;
        r.x += v.x * dt; r.y += v.y * dt;
      }
      const ease = Math.min(1, dt * 16);
      r.w += (tw - r.w) * ease; r.h += (th - r.h) * ease; r.rad += (trad - r.rad) * ease;

      // stretch along the direction of travel when free
      const speed = Math.hypot(v.x, v.y);
      const s = mode === "snap" || reduce ? 0 : Math.min(0.35, speed / 4000);
      const ang = Math.atan2(v.y, v.x);
      ring.style.width = r.w + "px";
      ring.style.height = r.h + "px";
      ring.style.borderRadius = r.rad + "px";
      ring.style.transform =
        `translate3d(${r.x - r.w / 2}px, ${r.y - r.h / 2}px, 0) rotate(${ang}rad) scale(${1 + s}, ${1 - s * 0.6}) rotate(${-ang}rad)`;
      layer.dataset.mode = mode;
      layer.classList.toggle("acur--hot", hot || sceneHot);
      layer.classList.toggle("acur--down", down);
    };
    raf = requestAnimationFrame(frame);

    // Capture phase: nothing that stops propagation can starve the cursor.
    const cap = { capture: true, passive: true } as const;
    window.addEventListener("mousemove", onMove, cap);
    window.addEventListener("dragover", onDrag, cap);
    window.addEventListener("scroll", onScroll, cap);
    window.addEventListener("mousedown", onDown, cap);
    window.addEventListener("mouseup", onUp, cap);
    document.documentElement.addEventListener("mouseleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove, cap);
      window.removeEventListener("dragover", onDrag, cap);
      window.removeEventListener("scroll", onScroll, cap);
      window.removeEventListener("mousedown", onDown, cap);
      window.removeEventListener("mouseup", onUp, cap);
      document.documentElement.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return createPortal(
    <div ref={layerRef} className="acur" aria-hidden="true">
      <div ref={ringRef} className="acur__ring" />
      <div ref={dotRef} className="acur__dot"><span /></div>
    </div>,
    document.body,
  );
}
