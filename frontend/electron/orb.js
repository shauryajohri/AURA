// The floating orb — AURA's black hole held in a glass marble. The core is
// the same Higgsfield film the app uses (orb-core.mp4, cropped round); the
// glass, the bloom and the state colours are drawn here, so the orb can
// breathe with whatever AURA is doing right now.
(() => {
  const cv = document.getElementById("orb");
  const ctx = cv.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const film = document.createElement("video");
  film.src = "orb-core.mp4";
  film.muted = true;
  film.loop = true;
  film.playsInline = true;
  film.play().catch(() => {});

  // Each state is a look the orb eases toward, so switching never snaps.
  //   tint  — hue shift applied to the film (0 keeps its violet)
  //   rate  — film speed; bright — exposure; glow — bloom strength
  const LOOK = {
    idle:      { accent: [155, 123, 255], tint: 0,   rate: 0.8, bright: 1.0,  glow: 0.55, pulse: 0.02 },
    listening: { accent: [127, 231, 255], tint: -70, rate: 1.0, bright: 1.08, glow: 0.8,  pulse: 0.05 },
    thinking:  { accent: [190, 160, 255], tint: 0,   rate: 1.9, bright: 1.3,  glow: 0.95, pulse: 0.03 },
    speaking:  { accent: [214, 190, 255], tint: 0,   rate: 1.15, bright: 1.18, glow: 0.85, pulse: 0.07 },
  };
  const EMBER = [255, 180, 138];

  const status = { state: "idle", listening: false, unread: false, text: "" };
  const cur = { ...LOOK.idle, accent: [...LOOK.idle.accent] };
  let hover = 0;
  let hovering = false;
  let W = 0;

  const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${Math.max(0, Math.min(1, a))})`;
  const lerp = (a, b, t) => a + (b - a) * t;

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

  const ripples = [];
  let nextRipple = 0;
  let last = performance.now();
  let t = 0;
  let lastRate = 0;

  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    t += dt;

    const st = effective();
    const look = LOOK[st];
    const k = Math.min(1, dt * 4);                      // ~250ms ease between states
    for (const key of ["tint", "rate", "bright", "glow", "pulse"]) cur[key] = lerp(cur[key], look[key], k);
    for (let i = 0; i < 3; i++) cur.accent[i] = lerp(cur.accent[i], look.accent[i], k);
    hover = lerp(hover, hovering ? 1 : 0, Math.min(1, dt * 10));

    if (reduce) { if (!film.paused) film.pause(); }
    else if (Math.abs(cur.rate - lastRate) > 0.02) { film.playbackRate = cur.rate; lastRate = cur.rate; }

    const c = W / 2;
    const breathe = reduce ? 0 : Math.sin(t * (st === "speaking" ? 6.5 : 1.3)) * cur.pulse;
    const R = W * 0.36 * (1 + breathe) * (1 + 0.06 * hover);   // the marble
    ctx.clearRect(0, 0, W, W);

    // bloom — the only thing that reaches the window's edge
    const bloom = ctx.createRadialGradient(c, c, R * 0.85, c, c, W / 2);
    bloom.addColorStop(0, rgba(cur.accent, 0.42 * cur.glow * (1 + hover * 0.4)));
    bloom.addColorStop(0.5, rgba(cur.accent, 0.12 * cur.glow));
    bloom.addColorStop(1, rgba(cur.accent, 0));
    ctx.fillStyle = bloom;
    ctx.beginPath(); ctx.arc(c, c, W / 2, 0, Math.PI * 2); ctx.fill();

    // speaking: rings of her voice leaving the marble
    if (st === "speaking" && !reduce && t > nextRipple) { ripples.push(t); nextRipple = t + 0.55; }
    for (let i = ripples.length - 1; i >= 0; i--) {
      const age = (t - ripples[i]) / 1.2;
      if (age >= 1) { ripples.splice(i, 1); continue; }
      ctx.strokeStyle = rgba(cur.accent, 0.5 * (1 - age));
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(c, c, R * (1.02 + age * 0.34), 0, Math.PI * 2); ctx.stroke();
    }

    // the marble: the black hole film, clipped round
    ctx.save();
    ctx.beginPath(); ctx.arc(c, c, R, 0, Math.PI * 2); ctx.clip();
    ctx.fillStyle = "#000";
    ctx.fillRect(c - R, c - R, R * 2, R * 2);
    if (film.readyState >= 2) {
      const s = R * 2 * 1.32;                             // the ring fills ~70% of the marble
      ctx.filter = `hue-rotate(${cur.tint.toFixed(1)}deg) brightness(${cur.bright.toFixed(3)}) saturate(1.1)`;
      ctx.drawImage(film, c - s / 2, c - s / 2, s, s);
      ctx.filter = "none";
    }
    // glass: a dark lens edge, a lit floor, a highlight up top
    const edge = ctx.createRadialGradient(c, c, R * 0.55, c, c, R);
    edge.addColorStop(0, "rgba(10,6,30,0)");
    edge.addColorStop(1, "rgba(10,6,30,0.65)");
    ctx.fillStyle = edge;
    ctx.fillRect(c - R, c - R, R * 2, R * 2);
    const floor = ctx.createRadialGradient(c, c + R * 0.9, 0, c, c + R * 0.9, R * 0.9);
    floor.addColorStop(0, rgba(cur.accent, 0.35));
    floor.addColorStop(1, rgba(cur.accent, 0));
    ctx.fillStyle = floor;
    ctx.fillRect(c - R, c - R, R * 2, R * 2);
    const spec = ctx.createRadialGradient(c - R * 0.36, c - R * 0.46, 0, c - R * 0.36, c - R * 0.46, R * 0.62);
    spec.addColorStop(0, "rgba(255,255,255,0.5)");
    spec.addColorStop(0.35, "rgba(255,255,255,0.12)");
    spec.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = spec;
    ctx.fillRect(c - R, c - R, R * 2, R * 2);
    ctx.restore();

    // rim — thin glass edge, catching the state colour
    ctx.strokeStyle = "rgba(255,255,255,0.2)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(c, c, R - 0.5, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = rgba(cur.accent, 0.55 + 0.3 * hover);
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(c, c, R + 1, Math.PI * 0.15, Math.PI * 0.85); ctx.stroke();

    // she said something while you were away: an ember mark that keeps pinging
    if (status.unread) {
      const dx = c + R * 0.78, dy = c - R * 0.78, dr = Math.max(4, W * 0.05);
      const ping = reduce ? 0 : (t * 0.9) % 1;
      ctx.strokeStyle = rgba(EMBER, 0.7 * (1 - ping));
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(dx, dy, dr * (1 + ping * 1.6), 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = rgba(EMBER, 1);
      ctx.beginPath(); ctx.arc(dx, dy, dr, 0, Math.PI * 2); ctx.fill();
    }
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
  cv.addEventListener("pointerenter", () => { hovering = true; });
  cv.addEventListener("pointerleave", () => { hovering = false; });
})();
