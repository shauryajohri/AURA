// The ghost cursor's motion. The brain says where (move / click / home) and
// how long the glide should take; she travels there on a slight arc with an
// ease in and out, the way a hand moves a mouse, and her ring trails on a
// spring. The loop only runs while something is moving.
(() => {
  const ghost = document.getElementById("ghost");
  const ring = document.getElementById("ring");
  const label = document.querySelector(".tag .label");
  const typed = document.querySelector(".tag .typed");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const p = { x: -100, y: -100 };           // the photon
  const r = { x: -100, y: -100 };           // the ring
  const v = { x: 0, y: 0 };                 // ring velocity
  let path = null;                          // { x0, y0, cx, cy, x1, y1, t0, ms }
  let raf = 0;
  let last = 0;
  let typing = 0;

  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

  function go(x, y, ms) {
    if (reduce || ms <= 0) {
      ghost.classList.toggle("tag-up", y > innerHeight - 90);
      ghost.classList.toggle("tag-left", x > innerWidth - 260);
      p.x = x; p.y = y;
      if (ms <= 0) { r.x = x; r.y = y; v.x = v.y = 0; }
      path = null;
    } else {
      // bend the path a little to one side: hands don't move in rulers
      const dx = x - p.x, dy = y - p.y;
      const bend = Math.min(90, Math.hypot(dx, dy) * 0.12) * (dx > 0 ? -1 : 1);
      const len = Math.hypot(dx, dy) || 1;
      // near the bottom or right edge, the label goes above / to the left
      ghost.classList.toggle("tag-up", y > innerHeight - 90);
      ghost.classList.toggle("tag-left", x > innerWidth - 260);
      path = {
        x0: p.x, y0: p.y, x1: x, y1: y, t0: performance.now(), ms,
        cx: (p.x + x) / 2 + (-dy / len) * bend,
        cy: (p.y + y) / 2 + (dx / len) * bend,
      };
    }
    wake();
  }

  function wake() {
    if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (path) {
      const t = Math.min(1, (now - path.t0) / path.ms);
      const k = ease(t), u = 1 - k;
      p.x = u * u * path.x0 + 2 * u * k * path.cx + k * k * path.x1;
      p.y = u * u * path.y0 + 2 * u * k * path.cy + k * k * path.y1;
      if (t >= 1) path = null;
    }
    if (reduce) {
      r.x = p.x; r.y = p.y;
    } else {
      v.x += ((p.x - r.x) * 340 - v.x * 26) * dt;
      v.y += ((p.y - r.y) * 340 - v.y * 26) * dt;
      r.x += v.x * dt; r.y += v.y * dt;
    }
    const speed = Math.hypot(v.x, v.y);
    const s = reduce ? 0 : Math.min(0.4, speed / 3500);
    const ang = Math.atan2(v.y, v.x);
    ghost.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`;
    ring.style.transform =
      `translate3d(${r.x}px, ${r.y}px, 0) rotate(${ang}rad) scale(${1 + s}, ${1 - s * 0.6}) rotate(${-ang}rad)`;

    const settled = !path && Math.hypot(p.x - r.x, p.y - r.y) < 0.3 && speed < 2;
    raf = settled ? 0 : requestAnimationFrame(frame);
  }

  function ripple(x, y) {
    const el = document.createElement("span");
    el.className = "ripple";
    el.style.left = x + "px";
    el.style.top = y + "px";
    document.body.append(el);
    el.addEventListener("animationend", () => el.remove());
  }

  window.hands.onEvent((ev) => {
    switch (ev.kind) {
      case "move":
      case "home":
        go(ev.x, ev.y, ev.ms ?? 600);
        break;
      case "click":
        if (!reduce) ripple(ev.x, ev.y);
        break;
      case "type": {
        label.textContent = "typing";
        typed.textContent = "";
        clearInterval(typing);
        let i = 0;
        typing = setInterval(() => {
          typed.textContent = ev.text.slice(0, ++i).slice(-28);
          if (i >= ev.text.length) clearInterval(typing);
        }, ev.ms);
        break;
      }
      case "busy":
        document.body.classList.toggle("busy", ev.on);
        if (ev.on) { label.textContent = ev.label || ""; typed.textContent = ""; }
        else setTimeout(() => { if (!document.body.classList.contains("busy")) typed.textContent = ""; }, 400);
        break;
    }
  });
})();
