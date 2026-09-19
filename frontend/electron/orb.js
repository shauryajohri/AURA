// The floating orb — a pocket-sized AURA core. Black event horizon, a
// white-hot photon ring wrapped in electric violet, crackling filaments and a
// few orbiting sparks, all tinted by what AURA is doing right now.
(() => {
  const cv = document.getElementById("orb");
  const ctx = cv.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Each state is a look the orb eases toward, so switching never snaps.
  const LOOK = {
    idle:      { accent: [139, 92, 255],  ring: [243, 217, 255], glow: 0.55, spin: 0.35, pulse: 0.025, rate: 1.1 },
    listening: { accent: [56, 225, 255],  ring: [214, 250, 255], glow: 0.8,  spin: 0.55, pulse: 0.07,  rate: 2.2 },
    thinking:  { accent: [167, 109, 255], ring: [255, 252, 255], glow: 0.95, spin: 2.4,  pulse: 0.035, rate: 3.2 },
    speaking:  { accent: [196, 150, 255], ring: [255, 240, 255], glow: 0.85, spin: 0.9,  pulse: 0.09,  rate: 5.0 },
  };
  const AMBER = [245, 166, 35];

  const status = { state: "idle", listening: false, unread: false, text: "" };
  const cur = { ...LOOK.idle, accent: [...LOOK.idle.accent], ring: [...LOOK.idle.ring] };
  let hover = false;
  let W = 0;

  const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${Math.max(0, Math.min(1, a))})`;
  const lerp = (a, b, t) => a + (b - a) * t;

  const filaments = Array.from({ length: 12 }, () => ({
    r: 1.04 + Math.random() * 0.5,
    a0: Math.random() * Math.PI * 2,
    len: 0.5 + Math.random() * 1.6,
    sp: 0.3 + Math.random() * 0.5,
    w: 0.6 + Math.random() * 1.1,
    al: 0.15 + Math.random() * 0.35,
  }));
  const sparks = Array.from({ length: 9 }, () => ({
    r: 1.35 + Math.random() * 0.55,
    a: Math.random() * Math.PI * 2,
    sp: 0.4 + Math.random() * 0.7,
    sz: 0.6 + Math.random() * 0.9,
    al: 0.45 + Math.random() * 0.5,
  }));

  function fit() {
    const dpr = window.devicePixelRatio || 1;
    W = Math.min(window.innerWidth, window.innerHeight);
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(W * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener("resize", fit);
  fit();

  function effective() {
    if (status.state !== "idle") return status.state;
    return status.listening ? "listening" : "idle";
  }

  let last = performance.now();
  let t = 0;
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    t += dt;

    const look = LOOK[effective()];
    const k = Math.min(1, dt * 4);                      // ~250ms ease between states
    for (const key of ["glow", "spin", "pulse", "rate"]) cur[key] = lerp(cur[key], look[key], k);
    for (let i = 0; i < 3; i++) {
      cur.accent[i] = lerp(cur.accent[i], look.accent[i], k);
      cur.ring[i] = lerp(cur.ring[i], look.ring[i], k);
    }

    const c = W / 2;
    const breathe = reduce ? 0 : Math.sin(t * cur.rate) * cur.pulse;
    const R = W * 0.2 * (1 + breathe) * (hover ? 1.07 : 1);
    const glow = cur.glow * (hover ? 1.15 : 1);
    ctx.clearRect(0, 0, W, W);

    // soft bloom around the core — the only thing that reaches the edge
    const bloom = ctx.createRadialGradient(c, c, R * 0.8, c, c, W / 2);
    bloom.addColorStop(0, rgba(cur.accent, 0.5 * glow));
    bloom.addColorStop(0.45, rgba(cur.accent, 0.16 * glow));
    bloom.addColorStop(1, rgba(cur.accent, 0));
    ctx.fillStyle = bloom;
    ctx.beginPath(); ctx.arc(c, c, W / 2, 0, Math.PI * 2); ctx.fill();

    // crackling filaments hugging the ring
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    for (const f of filaments) {
      if (!reduce) f.a0 += f.sp * cur.spin * dt;
      const wob = Math.sin(t * 2.3 + f.a0 * 3) * 0.04;
      ctx.strokeStyle = rgba(cur.accent, f.al * glow);
      ctx.lineWidth = f.w * (W / 96);
      ctx.beginPath();
      ctx.arc(c, c, R * (f.r + wob), f.a0, f.a0 + f.len);
      ctx.stroke();
    }

    // photon ring: white-hot core wrapped in violet
    ctx.shadowColor = rgba(cur.accent, 0.9);
    ctx.shadowBlur = W * 0.08 * glow;
    ctx.strokeStyle = rgba(cur.accent, 0.85);
    ctx.lineWidth = R * 0.2;
    ctx.beginPath(); ctx.arc(c, c, R * 1.04, 0, Math.PI * 2); ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = rgba(cur.ring, 0.95);
    ctx.lineWidth = R * 0.07;
    ctx.beginPath(); ctx.arc(c, c, R * 1.02, 0, Math.PI * 2); ctx.stroke();

    // orbiting sparks
    for (const s of sparks) {
      if (!reduce) s.a += s.sp * cur.spin * dt;
      const x = c + Math.cos(s.a) * R * s.r;
      const y = c + Math.sin(s.a) * R * s.r * 0.92;
      ctx.fillStyle = rgba(cur.ring, s.al * glow);
      ctx.beginPath(); ctx.arc(x, y, s.sz * (W / 96), 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";

    // the event horizon — pure black
    ctx.fillStyle = "#000";
    ctx.beginPath(); ctx.arc(c, c, R * 0.94, 0, Math.PI * 2); ctx.fill();

    // she said something while you were away: an amber mark that keeps pinging
    if (status.unread) {
      const dx = c + R * 1.3, dy = c - R * 1.3, dr = Math.max(4, W * 0.055);
      const ping = reduce ? 0 : (t * 0.9) % 1;
      ctx.strokeStyle = rgba(AMBER, 0.7 * (1 - ping));
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(dx, dy, dr * (1 + ping * 1.6), 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = rgba(AMBER, 1);
      ctx.beginPath(); ctx.arc(dx, dy, dr, 0, Math.PI * 2); ctx.fill();
    }

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  const LABEL = { idle: "idle", listening: "listening", thinking: "thinking…", speaking: "speaking…" };
  function describe() {
    const lines = [`AURA — ${LABEL[effective()]}`];
    if (status.unread && status.text) lines.push(`She said: “${status.text}”`);
    lines.push("Click to open · drag to move · right-click for options");
    cv.title = lines.join("\n");
    cv.setAttribute("aria-label", status.unread ? "Open AURA — she has a new message" : "Open AURA");
  }
  describe();

  window.orb?.onUpdate((s) => {
    Object.assign(status, s);
    describe();
  });

  // ── click to open, drag to move ────────────────────────────────────────
  let press = null;
  cv.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    cv.setPointerCapture(e.pointerId);
    press = { x: e.screenX, y: e.screenY, moved: false };
  });
  cv.addEventListener("pointermove", (e) => {
    if (!press) return;
    const dx = e.screenX - press.x, dy = e.screenY - press.y;
    if (!press.moved && Math.abs(dx) + Math.abs(dy) > 4) {
      press.moved = true;
      window.orb?.dragStart();
    }
    if (press.moved) window.orb?.dragMove(dx, dy);
  });
  const release = (e) => {
    if (!press) return;
    const wasDrag = press.moved;
    press = null;
    if (cv.hasPointerCapture(e.pointerId)) cv.releasePointerCapture(e.pointerId);
    if (wasDrag) window.orb?.dragEnd();
    else if (e.type === "pointerup") window.orb?.open();
  };
  cv.addEventListener("pointerup", release);
  cv.addEventListener("pointercancel", release);
  cv.addEventListener("contextmenu", (e) => { e.preventDefault(); window.orb?.menu(); });
  cv.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); window.orb?.open(); }
  });
  cv.addEventListener("pointerenter", () => { hover = true; });
  cv.addEventListener("pointerleave", () => { hover = false; });
})();
