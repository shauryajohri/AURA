// The floating orb — a pocket-sized AURA core: the same Higgsfield black hole
// the app uses, cut out of its background (orb-core.webm carries alpha), so
// only the void, the photon ring and the disk band float on the desktop.
// The event horizon, the state colours and the voice rings are drawn here.
(() => {
  const cv = document.getElementById("orb");
  const ctx = cv.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const film = document.createElement("video");
  film.src = "orb-core.webm";
  film.muted = true;
  film.loop = true;
  film.playsInline = true;
  film.play().catch(() => {});
  // In the clip (a square), the photon ring's radius is this share of its width.
  const RING = 173 / 600;

  // Each state is a look the orb eases toward, so switching never snaps.
  //   tint  — hue shift applied to the film (0 keeps its violet)
  //   rate  — film speed; bright — exposure; glow — halo strength
  const LOOK = {
    idle:      { accent: [155, 123, 255], tint: 0,   rate: 0.8,  bright: 1.0,  glow: 0.35, pulse: 0.015 },
    listening: { accent: [127, 231, 255], tint: -70, rate: 1.0,  bright: 1.1,  glow: 0.7,  pulse: 0.04 },
    thinking:  { accent: [190, 160, 255], tint: 0,   rate: 1.9,  bright: 1.32, glow: 0.8,  pulse: 0.02 },
    speaking:  { accent: [214, 190, 255], tint: 0,   rate: 1.15, bright: 1.18, glow: 0.7,  pulse: 0.05 },
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
    const F = W * 0.94 * (1 + breathe) * (1 + 0.06 * hover);   // the film's drawn size
    const R = F * RING;                                          // photon ring radius
    ctx.clearRect(0, 0, W, W);

    // a faint halo in the state colour — kept low so the cut-out stays clean
    const halo = ctx.createRadialGradient(c, c, R * 0.9, c, c, W / 2);
    halo.addColorStop(0, rgba(cur.accent, 0.22 * cur.glow * (1 + hover)));
    halo.addColorStop(1, rgba(cur.accent, 0));
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(c, c, W / 2, 0, Math.PI * 2); ctx.fill();

    // speaking: rings of her voice leaving the horizon
    if (st === "speaking" && !reduce && t > nextRipple) { ripples.push(t); nextRipple = t + 0.55; }
    for (let i = ripples.length - 1; i >= 0; i--) {
      const age = (t - ripples[i]) / 1.2;
      if (age >= 1) { ripples.splice(i, 1); continue; }
      ctx.strokeStyle = rgba(cur.accent, 0.55 * (1 - age));
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(c, c, R * (1.15 + age * 0.55), 0, Math.PI * 2); ctx.stroke();
    }

    // the event horizon: true black, soft only at its very edge
    const hole = ctx.createRadialGradient(c, c, R * 0.84, c, c, R * 1.0);
    hole.addColorStop(0, "rgba(0,0,0,1)");
    hole.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = hole;
    ctx.beginPath(); ctx.arc(c, c, R, 0, Math.PI * 2); ctx.fill();

    // the black hole itself — its light, cut out of the background
    if (film.readyState >= 2) {
      ctx.filter = `hue-rotate(${cur.tint.toFixed(1)}deg) brightness(${cur.bright.toFixed(3)}) saturate(1.1)`;
      ctx.drawImage(film, c - F / 2, c - F / 2, F, F);
      ctx.filter = "none";
    }

    // she said something while you were away: an ember mark that keeps pinging
    if (status.unread) {
      const dx = c + R * 1.25, dy = c - R * 1.25, dr = Math.max(4, W * 0.05);
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
