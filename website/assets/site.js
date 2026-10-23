/* ==========================================================================
   AURA · the site
   The hero scrub, AURA's tour, and the live console that talks to
   web_api.py. No framework, no build step.
   ========================================================================== */
(() => {
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const smoothstep = (p, e0, e1) => { const t = clamp((p - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
const RM = matchMedia('(prefers-reduced-motion: reduce)');
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const MSG_UNREACHABLE = "Can't reach my brain right now. The code is on GitHub if you want to run me yourself.";

/* --------------------------------------------------------------------------
   Presence: every core on the page shows one state
   -------------------------------------------------------------------------- */
const presence = {
  chat: 'idle',
  voice: false,
  apply() {
    const s = this.voice ? 'speaking' : this.chat;
    if (document.body.dataset.aura !== s) document.body.dataset.aura = s;
  },
};
const setChatState = (s) => { presence.chat = s; presence.apply(); };

document.addEventListener('visibilitychange', () => document.body.classList.toggle('paused', document.hidden));

/* --------------------------------------------------------------------------
   Nav state and the spine (rAF-throttled, written only on change)
   -------------------------------------------------------------------------- */
const nav = $('#nav');
const spineFill = $('.spine i');
let navStuck = null, lastSpine = -1, pageRaf = 0;
function onPageScroll() {
  if (pageRaf) return;
  pageRaf = requestAnimationFrame(() => {
    pageRaf = 0;
    const stuck = scrollY > 12;
    if (stuck !== navStuck) { navStuck = stuck; nav.classList.toggle('stuck', stuck); }
    const max = document.documentElement.scrollHeight - innerHeight;
    const p = max > 0 ? clamp(scrollY / max, 0, 1) : 0;
    if (Math.abs(p - lastSpine) > 0.0015) { lastSpine = p; spineFill.style.transform = `scaleY(${p.toFixed(4)})`; }
  });
}
addEventListener('scroll', onPageScroll, { passive: true });
onPageScroll();

/* --------------------------------------------------------------------------
   Entrances
   -------------------------------------------------------------------------- */
const pinnedByRM = new Set();
const revealIO = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    const el = e.target;
    el.classList.add('in');
    revealIO.unobserve(el);
    pinnedByRM.delete(el);
    setTimeout(() => el.classList.add('settled'), 1600);
  });
}, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
$$('.reveal').forEach((el) => revealIO.observe(el));

/* An in-page link lands on where its target will rest. The console waits for its
   entrance 24px low, so "Skip the intro" used to finish with its header under the
   nav once the entrance moved it up. Links to it skip the entrance. */
document.addEventListener('click', (e) => {
  const a = e.target instanceof Element ? e.target.closest('a[href^="#"]') : null;
  const target = a && a.getAttribute('href').length > 1 ? document.getElementById(a.getAttribute('href').slice(1)) : null;
  if (!target || !target.classList.contains('reveal') || target.classList.contains('in')) return;
  target.style.transition = 'none';
  target.classList.add('in', 'settled');
  revealIO.unobserve(target);
  pinnedByRM.delete(target);
  void target.offsetWidth;
  target.style.transition = '';
}, true);

const pipeline = $('.pipeline');
const pipeIO = new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting)) { pipeline.classList.add('drawn'); pipeIO.disconnect(); }
}, { threshold: 0.35 });
if (pipeline) pipeIO.observe(pipeline);

const demoSection = $('#demo');
new IntersectionObserver((entries) => {
  entries.forEach((e) => demoSection.classList.toggle('onscreen', e.isIntersecting));
}).observe(demoSection);

/* --------------------------------------------------------------------------
   Voice: AURA's voice, on by default, one line at a time.
   - Her reply always gets the floor, even over the tour.
   - An intro or tour line never cuts another one off: it waits its turn and
     is dropped if what it was about has left the screen by then. Scrolling
     the intro at reading pace used to cut each line off a few seconds in.
   - Browsers keep a page silent until the first click, tap or key press, so
     until then a small cue says so. That first gesture unlocks the audio with
     a silent blip (iPhones need one) and she says what is on screen.
   -------------------------------------------------------------------------- */
const voiceBtn = $('#voiceToggle');
const unlockCue = $('#voiceUnlock');
const audio = new Audio();
audio.preload = 'auto';
const SILENT = 'data:audio/wav;base64,UklGRhQBAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YfAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIA=';
const RANK = { hero: 1, tour: 2, reply: 3 };
let speaking = null;          /* the line playing now: { kind, onEnd } */
let waiting = null;           /* the one line waiting its turn */
let fetching = 0;             /* replies still being turned into audio */
let token = 0, replySeq = 0, lastBlobUrl = '';

if (matchMedia('(pointer: coarse)').matches) $('.lbl', unlockCue).textContent = 'Tap anywhere to hear me';

function showUnlock(on) {
  on = on && voice.on;
  if (on === unlockCue.classList.contains('on')) return;
  if (on) {
    unlockCue.hidden = false;
    requestAnimationFrame(() => unlockCue.classList.add('on'));
  } else {
    unlockCue.classList.remove('on');
    setTimeout(() => { if (!unlockCue.classList.contains('on')) unlockCue.hidden = true; }, 450);
  }
}

function playLine(line) {
  const my = ++token;
  speaking = { kind: line.kind, onEnd: line.onEnd };
  const done = () => {
    if (my !== token) return;
    speaking = null;
    presence.voice = false; presence.apply();
    if (line.onEnd) line.onEnd();
    advance();
  };
  audio.onended = done;
  audio.onerror = done;
  audio.src = line.src;
  audio.play().then(() => {
    if (my !== token) return;
    voice.blocked = false;
    showUnlock(false);
    presence.voice = true; presence.apply();
    if (line.onStart) line.onStart();
  }, (err) => {
    if (my !== token) return;
    audio.onended = null; audio.onerror = null;
    speaking = null;
    presence.voice = false; presence.apply();
    if (err && err.name === 'NotAllowedError') { voice.blocked = true; waiting = null; showUnlock(true); }
    else advance();
  });
}

function advance() {
  if (speaking || fetching || !waiting) return;
  const line = waiting;
  waiting = null;
  if (line.wanted && !line.wanted()) return;
  playLine(line);
}

function hush() {
  token++;
  audio.onended = null; audio.onerror = null;
  audio.pause();
  speaking = null;
  presence.voice = false; presence.apply();
}

const voice = {
  on: store.get('aura.voice') !== 'off',
  blocked: false,
  get replyActive() { return fetching > 0 || (!!speaking && speaking.kind === 'reply'); },
  say(line) {
    if (!this.on) return false;
    if (line.kind === 'reply') { this.sayReply(line); return true; }
    if (speaking || fetching) {
      if (!waiting || RANK[waiting.kind] <= RANK[line.kind]) waiting = line;
      return true;
    }
    playLine(line);
    return true;
  },
  async sayReply(line) {
    const mine = ++replySeq;
    fetching++;
    let url = null;
    try { url = await demo.ttsUrl(line.text); } finally { fetching--; }
    if (mine !== replySeq || !this.on || !url) {
      if (url) URL.revokeObjectURL(url);
      advance();
      return;
    }
    if (speaking) {
      const cut = speaking;
      hush();
      if (cut.kind !== 'reply' && cut.onEnd) cut.onEnd();
    }
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    lastBlobUrl = url;
    playLine({ ...line, src: url });
  },
  stopTour() {
    if (waiting && waiting.kind !== 'reply') waiting = null;
    if (speaking && speaking.kind !== 'reply') { hush(); advance(); }
  },
  stopReply() {
    replySeq++;
    if (speaking && speaking.kind === 'reply') { hush(); advance(); }
  },
  stop() { replySeq++; waiting = null; hush(); },
  set(on) {
    this.on = on;
    store.set('aura.voice', on ? 'on' : 'off');
    paintVoiceButton();
    if (on) speakWhatIsOnScreen();
    else { this.stop(); showUnlock(false); }
  },
};

function paintVoiceButton() {
  voiceBtn.setAttribute('aria-pressed', String(voice.on));
  $('.lbl', voiceBtn).textContent = voice.on ? 'Mute AURA' : 'Hear AURA';
}
paintVoiceButton();
voiceBtn.addEventListener('click', () => voice.set(!voice.on));

/* The first real gesture anywhere is what lets the browser play sound, and
   play() has to start inside that handler. The mute button is left out:
   pressing it means "be quiet", not "start talking". */
function unlock() {
  if (!voice.on || !voice.blocked) return;
  voice.blocked = false;
  showUnlock(false);
  audio.onended = null; audio.onerror = null;
  audio.src = SILENT;
  audio.play().catch(() => {}).then(() => { if (!speaking) speakWhatIsOnScreen(); });
}
unlockCue.addEventListener('click', unlock);
addEventListener('pointerdown', (e) => { if (!(e.target instanceof Element && e.target.closest('#voiceToggle'))) unlock(); }, { capture: true, passive: true });
addEventListener('keydown', unlock, { capture: true, passive: true });

function speakWhatIsOnScreen() {
  if (hero.scrubOn && hero.onScreen) {
    const band = hero.bands.find((b) => b.op > 0.5);
    if (band) { band.heard = true; voice.say({ src: `assets/voice/${band.voice}.mp3`, kind: 'hero', wanted: () => band.op > 0.5 }); return; }
  }
  if (!hero.scrubOn) {
    const r = $('.hero-static').getBoundingClientRect();
    if (r.bottom > innerHeight * 0.4) { voice.say({ src: 'assets/voice/hero-1.mp3', kind: 'hero' }); return; }
  }
  tour.speakCurrent();
}
/* --------------------------------------------------------------------------
   Hero: the portal descent, scrubbed by scroll
   -------------------------------------------------------------------------- */
const hero = (() => {
  const GATES = [
    '(max-width: 720px)',
    '(orientation: portrait) and (max-width: 1024px)',
    '(orientation: portrait) and (pointer: coarse)',
    '(orientation: landscape) and (pointer: coarse) and (max-height: 560px)',
    '(prefers-reduced-motion: reduce)',
  ];
  const MQLS = GATES.map((q) => matchMedia(q));
  const VIDEO_URL = 'assets/hero-scrub.mp4';
  const VIDEO_BYTES = 5042009;
  const POSTER = 'assets/hero-poster.jpg';
  const POSTER_END = 'assets/hero-ending.jpg';

  const root = $('.hero-scrub');
  const stage = $('.stage');
  const video = $('#hero');
  const poster = $('.poster');
  const posterEnd = $('.poster-end');
  const ring = $('.ring');
  const foot = $('.hero-foot');

  const state = {
    scrubOn: false, onScreen: true, bands: [],
    init: false, target: 0, shown: 0, rafId: null, lastTick: 0, loadK: 0,
    seekBusy: false, pendingTime: null, failed: false, footGone: null, endOp: -1,
  };

  /* split headlines into word and character spans, seeded so it is identical every load */
  function rng(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }
  $$('.band [data-split]').forEach((h, n) => {
    const text = h.textContent.trim();
    const rand = rng(97 + n * 31);
    const words = text.split(/\s+/);
    h.textContent = '';
    const sr = document.createElement('span');
    sr.className = 'sr-only'; sr.textContent = text;
    const vis = document.createElement('span');
    vis.setAttribute('aria-hidden', 'true');
    words.forEach((word, i) => {
      const w = document.createElement('span');
      w.className = 'w';
      w.style.setProperty('--th', ((i / Math.max(1, words.length)) * 0.5 + rand() * 0.06).toFixed(3));
      w.textContent = word;
      vis.append(w);
      if (i < words.length - 1) vis.append(' ');
    });
    h.append(sr, vis);
  });

  state.bands = $$('.band').map((el, i, all) => ({
    el, a: +el.dataset.a, b: +el.dataset.b, ramp: +el.dataset.ramp || 0,
    first: i === 0, last: i === all.length - 1,
    op: -1, k: -1, voice: el.dataset.voice, heard: false,
  }));

  function progress() {
    const range = root.offsetHeight - innerHeight;
    if (range <= 0) return 0;
    return clamp(-root.getBoundingClientRect().top / range, 0, 1);
  }

  /* seeks never overlap: coalesce to the newest, one follow-up, and an error escape */
  function requestSeek(t) {
    if (!video.duration || !isFinite(video.duration)) return;
    if (state.seekBusy) { state.pendingTime = t; return; }
    if (Math.abs(video.currentTime - t) < 0.002) return;
    state.seekBusy = true;
    video.currentTime = t;
  }
  video.addEventListener('seeked', () => {
    state.seekBusy = false;
    if (state.pendingTime !== null) { const t = state.pendingTime; state.pendingTime = null; requestSeek(t); }
  });
  video.addEventListener('error', () => { state.seekBusy = false; state.pendingTime = null; fail(); });

  function captions(p) {
    for (const bd of state.bands) {
      const f = Math.min(0.02, (bd.b - bd.a) / 3);
      const inOp = bd.first ? 1 : smoothstep(p, bd.a, bd.a + f);
      const outOp = bd.last ? 1 : 1 - smoothstep(p, bd.b - f, bd.b);
      const op = inOp * outOp;
      const ramp = bd.ramp || Math.min(0.025, (bd.b - bd.a) * 0.35);
      let k = clamp((p - bd.a) / ramp, 0, 1);
      if (bd.first) k = Math.max(k, state.loadK);
      if (Math.abs(op - bd.op) > 0.004 || (op === 0 && bd.op !== 0) || (op === 1 && bd.op !== 1)) {
        bd.el.style.opacity = op.toFixed(3);
        bd.el.style.visibility = op < 0.01 ? 'hidden' : 'visible';
        bd.op = op;
      }
      if (Math.abs(k - bd.k) > 0.008 || (k === 1 && bd.k !== 1) || (k === 0 && bd.k !== 0)) {
        bd.el.style.setProperty('--k', k.toFixed(3));
        bd.k = k;
      }
      if (op > 0.95 && k > 0.6 && !bd.heard && voice.on) {
        bd.heard = true;
        voice.say({ src: `assets/voice/${bd.voice}.mp3`, kind: 'hero', wanted: () => bd.op > 0.5 });
      }
    }
    const gone = p > 0.62;
    if (gone !== state.footGone) { state.footGone = gone; foot.classList.toggle('gone', gone); }
    if (state.failed) {
      const e = smoothstep(p, 0.45, 0.9);
      if (Math.abs(e - state.endOp) > 0.005) { posterEnd.style.opacity = e.toFixed(3); state.endOp = e; }
    }
  }

  function tick(now) {
    const dt = Math.min(100, now - (state.lastTick || now));
    state.lastTick = now;
    const k = 0.14;
    state.shown += (state.target - state.shown) * (1 - Math.pow(1 - k, dt / 16.667));
    if (Math.abs(state.target - state.shown) < 0.0005) {
      state.shown = state.target; state.rafId = null; state.lastTick = 0;
    } else {
      state.rafId = requestAnimationFrame(tick);
    }
    if (video.duration) requestSeek(state.shown * Math.max(0, video.duration - 0.05));
    captions(state.shown);
  }

  function onScroll() {
    state.target = progress();
    if (state.rafId === null && state.onScreen) state.rafId = requestAnimationFrame(tick);
  }

  function loadRamp() {
    if (RM.matches) { state.loadK = 1; captions(state.shown); return; }
    const t0 = performance.now();
    const step = (now) => {
      const t = clamp((now - t0 - 300) / 1400, 0, 1);
      state.loadK = 1 - Math.pow(1 - t, 3);
      captions(state.shown);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function fail() {
    if (state.failed) return;
    state.failed = true;
    stage.classList.add('video-failed');
    ring.classList.add('done');
    posterEnd.style.backgroundImage = `url('${POSTER_END}')`;
    captions(state.shown);
  }

  async function loadBlob() {
    if (location.protocol === 'file:') throw new Error('file:// cannot fetch');
    const ctrl = new AbortController();
    let watchdog = setTimeout(() => ctrl.abort(), 20000);
    const res = await fetch(VIDEO_URL, { priority: 'low', signal: ctrl.signal });
    if (!res.ok || !res.body) throw new Error(`video ${res.status}`);
    const total = Number(res.headers.get('Content-Length')) || VIDEO_BYTES;
    const reader = res.body.getReader();
    const chunks = [];
    let got = 0, lastRing = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      clearTimeout(watchdog);
      watchdog = setTimeout(() => ctrl.abort(), 20000);
      chunks.push(value);
      got += value.length;
      const frac = Math.min(1, got / total);
      const now = performance.now();
      if (now - lastRing > 100 || frac === 1) { lastRing = now; ring.style.setProperty('--ld', Math.round(126 * (1 - frac))); }
    }
    clearTimeout(watchdog);
    ring.style.setProperty('--ld', 0);
    video.src = URL.createObjectURL(new Blob(chunks, { type: 'video/mp4' }));
    video.addEventListener('loadeddata', () => {
      requestSeek(progress() * Math.max(0, video.duration - 0.05));
      stage.classList.add('video-ready');
      setTimeout(() => ring.classList.add('done'), 400);
    }, { once: true });
    video.load();
  }

  function initOnce() {
    if (state.init) return;
    state.init = true;
    poster.style.backgroundImage = `url('${POSTER}')`;
    let started = false;
    const start = () => { if (started) return; started = true; loadBlob().catch(fail); };
    const img = new Image();
    img.onload = start; img.onerror = start; img.src = POSTER;
    setTimeout(start, 4000);
    loadRamp();
  }

  function enable() {
    if (state.scrubOn) return;
    state.scrubOn = true;
    initOnce();
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('resize', onScroll, { passive: true });
    state.bands.forEach((b) => { b.op = -1; b.k = -1; });
    state.footGone = null;
    state.target = state.shown = progress();
    captions(state.shown);
    onScroll();
  }
  function disable() {
    if (!state.scrubOn) return;
    state.scrubOn = false;
    removeEventListener('scroll', onScroll);
    removeEventListener('resize', onScroll);
    if (state.rafId !== null) { cancelAnimationFrame(state.rafId); state.rafId = null; state.lastTick = 0; }
  }
  function applyMode() { if (MQLS.some((m) => m.matches)) disable(); else enable(); }

  MQLS.forEach((m) => m.addEventListener('change', applyMode));
  new IntersectionObserver((entries) => {
    state.onScreen = entries[0].isIntersecting;
    if (state.onScreen && state.scrubOn) onScroll();
  }).observe(root);
  applyMode();

  return {
    get scrubOn() { return state.scrubOn; },
    get onScreen() { return state.onScreen; },
    get bands() { return state.bands; },
    applyMode,
  };
})();

/* --------------------------------------------------------------------------
   AURA's tour. Her mini black hole flies to each part of the page as it
   reaches the middle of the screen, lights it up, dims everything else and
   explains it. Her bubble goes wherever it covers neither what she is
   explaining nor the message box. Click her to ask anything; drag her to
   move her.
   -------------------------------------------------------------------------- */
const tour = (() => {
  /* Each line plays when the element with data-tour="<id>" reaches the middle
     of the screen. Its voice is assets/voice/tour-<id>.mp3, rendered from this
     text by tools/render_site_voice.py, so the words only ever change here. */
  const LINES = [
    { id: 'console',   text: "This is me, live. Nothing here is scripted. Pick a nature and a mode, then type anything. You can also click me to ask." },
    { id: 'counter',   text: "This counts your fifty free messages. It resets a day after you use them." },
    { id: 'natures',   text: "Natures are locks. Whatever you pick gets added to my instructions until you change it." },
    { id: 'modes',     text: "Modes change the job. Code writes code, research writes a report, discussion argues with you, and plan gives you steps." },
    { id: 'starters',  text: "Stuck for something to ask? Tap one of these and it lands in the box, ready to send." },
    { id: 'composer',  text: "Type here and press Enter. Ask about this project, about code, or about anything else." },
    { id: 'trace',     text: "Watch this panel while I answer. It shows the intent I read, the model that took it, and what my guard cut." },
    { id: 'classify',  text: "Every message takes four steps. First I classify it. A small model names the intent, and a rule layer checks its work." },
    { id: 'gather',    text: "Then I gather context: recent turns, what I know, and the project. In this demo, only this tab." },
    { id: 'route',     text: "Then I route it. Each job has a chain of models, so if one is rate limited, the next one answers and you never see it." },
    { id: 'guard',     text: "Last comes the guard. Reasoning models love to think out loud, so it makes sure you only get the answer." },
    { id: 'roster',    text: "These are the models I switch between. Different minds for code, research and chat, with a fast safety net on Groq." },
    { id: 'companion', text: "This is my home on Shaurya's desktop. There I talk out loud, remember things, and read the screen when asked." },
    { id: 'domain',    text: "And this is Domain. Talk about a project and it becomes features, tasks and a knowledge graph." },
    { id: 'call1',     text: "Groq once retired two models while people were mid conversation. Since then, every message has a backup chain." },
    { id: 'call2',     text: "My reasoning kept leaking into replies. It took five fixes and three layers to keep it out." },
    { id: 'call3',     text: "And I only move a conversation to another room when I'm sure. A wrong move loses the thread." },
    { id: 'stack',     text: "Python and FastAPI run my brain. React, TypeScript and Electron draw my face." },
    { id: 'code',      text: "All of it is on GitHub. Clone it and I'll be running on your machine in about five minutes." },
    { id: 'term',      text: "Four commands and a free Groq key. That's the whole setup." },
  ];
  const ASK_PROMPT = "Ask me anything. This project, Shaurya's work, or something else entirely.";

  const guide = $('#guide');
  const coreBtn = $('#guideCore');
  const bubble = $('#guideBubble');
  const textEl = $('#guideText');
  const sizer = $('#guideSizer');
  const srEl = $('#guideSr');
  const askForm = $('#guideAsk');
  const askInput = $('#guideInput');
  const btnAsk = $('#guideAskBtn');
  const btnMore = $('#guideMore');
  const btnResume = $('#guideResume');
  const btnHide = $('#guideHide');
  const spot = $('#spot');
  const lens = $('#lens');
  const ring = $('rect', lens);
  const composer = $('#composer');
  const consoleInput = $('#input');
  const modal = $('#limitModal');

  LINES.forEach((l) => { l.el = $(`[data-tour="${l.id}"]`); });

  const said = new Set();
  const queue = [];
  let off = store.get('aura.tour') === 'off';
  let mode = 'dock';                 /* dock | line | ask | answer */
  let started = false, heroInView = true;
  let current = null, lineTimer = 0, typeTimer = 0, lostSince = 0, heldForLine = false;
  let dock = null;
  try { dock = JSON.parse(sessionStorage.getItem('aura.guide.dock') || 'null'); } catch { dock = null; }
  let pos = null, place = '', placedAt = 0, aliveUntil = 0;
  let raf = 0, lastTick = 0, drag = null, swallowClick = false;
  let spotBox = null, spotShown = false;
  const painted = { g: '', bx: '', by: '', spot: '', open: null };

  let navH = 64;
  const syncNav = () => {
    navH = nav.offsetHeight;
    document.documentElement.style.setProperty('--nav-h', `${navH}px`);
  };
  syncNav();

  /* ---- geometry: everything in viewport pixels ---- */
  const box = (l, t, r, b) => ({ l, t, r, b });
  const rectOf = (el) => { const r = el.getBoundingClientRect(); return box(r.left, r.top, r.right, r.bottom); };
  const overlap = (a, b) => Math.max(0, Math.min(a.r, b.r) - Math.max(a.l, b.l)) * Math.max(0, Math.min(a.b, b.b) - Math.max(a.t, b.t));
  const viewBox = () => box(8, navH + 8, innerWidth - 8, innerHeight - 8);
  const coreSize = () => coreBtn.offsetWidth || 56;

  /* what she and her bubble must never sit on */
  function keepClear() {
    const out = [];
    const c = rectOf(composer);
    if (c.r > c.l && c.b > 0 && c.t < innerHeight) out.push(box(c.l - 6, c.t - 6, c.r + 6, c.b + 6));
    if (!modal.hidden) out.push(rectOf($('.modal-card', modal)));
    return out;
  }

  /* what her bubble should rather not cover: the console's own controls */
  const SOFT = ['#dial', '#modes', '#starters', '.c-tools', '#natureNote'].map((sel) => $(sel)).filter(Boolean);
  function softClear() {
    const out = [];
    for (const el of SOFT) {
      const r = rectOf(el);
      if (r.r - r.l > 1 && r.b > 0 && r.t < innerHeight) out.push(r);
    }
    return out;
  }

  /* the visible part of a target, padded, never up into the nav bar */
  function targetBox(el) {
    if (!el || !el.isConnected) return null;
    const r = rectOf(el);
    if (r.r - r.l < 2 || r.b - r.t < 2) return null;   /* not rendered, like the starters after a first message */
    const v = viewBox(), pad = 10;
    const b = box(r.l - pad, Math.max(r.t - pad, v.t), r.r + pad, Math.min(r.b + pad, v.b));
    const full = r.b - r.t + pad * 2;
    return b.b - b.t >= Math.min(64, full) - 1 ? b : null;
  }

  /* iML and iMR sit halfway down a target taller than the screen, like the console on a
     phone, where every other spot put her on its buttons */
  const ANCHORS = ['L', 'R', 'TL', 'TR', 'BL', 'BR', 'iTL', 'iTR', 'iML', 'iMR', 'iBL', 'iBR'];
  const SIDES = ['right', 'left', 'below', 'above'];

  /* where the core and the bubble go for one placement key, like "TL:right" */
  function layout(key, T, fixed) {
    const c = coreSize(), h = c / 2, gap = 14, v = viewBox();
    const bw = bubble.offsetWidth, bh = bubble.offsetHeight;
    const [anchor, side] = key.split(':');
    let x, y;
    if (fixed) { x = fixed.x; y = fixed.y; }
    else {
      const top = Math.max(T.t, v.t) + h + 8;
      switch (anchor) {
        case 'L': x = T.l - h - gap; y = top; break;
        case 'R': x = T.r + h + gap; y = top; break;
        case 'TL': x = T.l + h + 8; y = T.t - h - gap; break;
        case 'TR': x = T.r - h - 8; y = T.t - h - gap; break;
        case 'BL': x = T.l + h + 8; y = T.b + h + gap; break;
        case 'BR': x = T.r - h - 8; y = T.b + h + gap; break;
        case 'iTL': x = T.l + h + 16; y = T.t + h + 16; break;
        case 'iTR': x = T.r - h - 16; y = T.t + h + 16; break;
        case 'iML': x = T.l + h + 16; y = (T.t + T.b) / 2; break;
        case 'iMR': x = T.r - h - 16; y = (T.t + T.b) / 2; break;
        case 'iBL': x = T.l + h + 16; y = T.b - h - 16; break;
        default: x = T.r - h - 16; y = T.b - h - 16;
      }
    }
    x = clamp(x, v.l + h, v.r - h);
    y = clamp(y, v.t + h, v.b - h);
    let bx, by;
    if (side === 'right') { bx = x + h + 10; by = y - h; }
    else if (side === 'left') { bx = x - h - 10 - bw; by = y - h; }
    else if (side === 'below') { bx = x - h; by = y + h + 10; }
    else { bx = x - h; by = y - h - 10 - bh; }
    bx = clamp(bx, v.l, Math.max(v.l, v.r - bw));
    by = clamp(by, v.t, Math.max(v.t, v.b - bh));
    return { key, x, y, bx, by, core: box(x - h, y - h, x + h, y + h), bub: box(bx, by, bx + bw, by + bh) };
  }

  /* the best placement: off the message box, off the target, close to it, and sticky so she does not jitter */
  function choose(T, fixed, open) {
    const clear = keepClear();
    const soft = open ? softClear() : [];
    let best = null, bestScore = Infinity;
    for (const anchor of fixed ? ['D'] : ANCHORS) {
      for (const side of SIDES) {
        const p = layout(`${anchor}:${side}`, T, fixed);
        let score = 0;
        /* the message box is off limits, not merely expensive: a big target like the
           console once made a sliver of overlap look cheaper than moving */
        let blocked = 0;
        for (const k of clear) blocked += overlap(p.core, k) + (open ? overlap(p.bub, k) : 0);
        if (blocked) score += 1e7 + blocked * 100;
        for (const k of soft) score += overlap(p.bub, k) * 3 + overlap(p.core, k) * 2;
        if (open) score += overlap(p.bub, p.core) * 40;
        if (T) {
          if (open) score += overlap(p.bub, T) * 5;
          score += overlap(p.core, T) * 1.5;
          const dx = Math.max(T.l - p.x, 0, p.x - T.r), dy = Math.max(T.t - p.y, 0, p.y - T.b);
          score += Math.hypot(dx, dy) * 10;
          if (anchor[0] === 'i') score += 4000;
        }
        if (p.key === place) score -= 3000;
        if (score < bestScore) { bestScore = score; best = p; }
      }
    }
    return best;
  }

  function pick(T, fixed, open, now, force) {
    if (force || !place || now - placedAt > 160 || place.startsWith('D:') !== !!fixed) {
      place = choose(T, fixed, open).key;
      placedAt = now;
    }
    return place;
  }

  /* her resting spot: where the visitor last dropped her, else a free corner */
  function dockPoint() {
    const h = coreSize() / 2, v = viewBox(), m = 16;
    const clear = keepClear();
    const options = dock ? [dock] : [];
    options.push({ x: v.l + m + h, y: v.b - m - h }, { x: v.r - m - h, y: v.b - m - h },
                 { x: v.r - m - h, y: v.t + m + h }, { x: v.l + m + h, y: v.t + m + h });
    let first = null;
    for (const o of options) {
      const x = clamp(o.x, v.l + h, v.r - h), y = clamp(o.y, v.t + h, v.b - h);
      if (!first) first = { x, y };
      const core = box(x - h - 6, y - h - 6, x + h + 6, y + h + 6);
      if (!clear.some((k) => overlap(core, k) > 0)) return { x, y };
    }
    return first;
  }

  /* ---- the drive loop: rests when nothing is moving, wakes on scroll ---- */
  function frame(now) {
    raf = 0;
    if (!started) return;
    const dt = lastTick ? Math.min(64, now - lastTick) : 16.667;
    lastTick = now;

    const typingInConsole = document.activeElement === consoleInput;
    const target = mode === 'line' && current ? targetBox(current.el) : null;
    const open = !typingInConsole && (mode === 'ask' || mode === 'answer' || (mode === 'line' && !!current));

    /* a line whose target has scrolled away gives way to one that is on screen */
    if (mode === 'line' && current && !target) {
      if (!lostSince) lostSince = now;
      else if (now - lostSince > 700 && queue.some((q) => targetBox(q.el))) {
        voice.stopTour();
        next(true);
        return;
      }
    } else lostSince = 0;

    const dragging = !!(drag && drag.moved);
    const follow = !!target && !typingInConsole && !heldForLine && !dragging;
    let p;
    if (dragging) p = layout(pick(null, drag, open, now, true), null, drag);
    else if (follow) p = layout(pick(target, null, open, now), target, null);
    else { const d = dockPoint(); p = layout(pick(null, d, open, now), null, d); }

    if (!pos || dragging || RM.matches) pos = { x: p.x, y: p.y };
    else {
      const k = 1 - Math.pow(1 - 0.18, dt / 16.667);
      pos.x += (p.x - pos.x) * k;
      pos.y += (p.y - pos.y) * k;
    }
    const settled = Math.abs(p.x - pos.x) < 0.4 && Math.abs(p.y - pos.y) < 0.4;
    if (settled) { pos.x = p.x; pos.y = p.y; }

    const g = `translate3d(${pos.x.toFixed(1)}px,${pos.y.toFixed(1)}px,0)`;
    if (g !== painted.g) { guide.style.transform = g; painted.g = g; }
    /* the bubble is placed for where she is heading, so it lands with her */
    const bx = `${Math.round(p.bx - p.x)}px`, by = `${Math.round(p.by - p.y)}px`;
    if (bx !== painted.bx) { guide.style.setProperty('--bx', bx); painted.bx = bx; }
    if (by !== painted.by) { guide.style.setProperty('--by', by); painted.by = by; }
    if (open !== painted.open) { guide.classList.toggle('open', open); painted.open = open; }

    const lit = follow && modal.hidden;
    let spotSettled = true;
    if (lit) {
      if (!spotShown || !spotBox || RM.matches) spotBox = { ...target };
      else {
        const k = 1 - Math.pow(1 - 0.2, dt / 16.667);
        for (const e of ['l', 't', 'r', 'b']) spotBox[e] += (target[e] - spotBox[e]) * k;
        spotSettled = ['l', 't', 'r', 'b'].every((e) => Math.abs(target[e] - spotBox[e]) < 0.5);
        if (spotSettled) spotBox = { ...target };
      }
      const x = Math.round(spotBox.l), y = Math.round(spotBox.t);
      const w = Math.round(spotBox.r - spotBox.l), h = Math.round(spotBox.b - spotBox.t);
      const key = `${x},${y},${w},${h}`;
      if (key !== painted.spot) {
        spot.style.transform = `translate(${x}px,${y}px)`;
        spot.style.width = `${w}px`;
        spot.style.height = `${h}px`;
        ring.setAttribute('x', x); ring.setAttribute('y', y);
        ring.setAttribute('width', w); ring.setAttribute('height', h);
        painted.spot = key;
      }
    }
    if (lit !== spotShown) {
      spotShown = lit;
      spot.classList.toggle('on', lit);
      lens.classList.toggle('on', lit);
      if (lit) redrawRing();
    }

    if (!settled || !spotSettled || dragging || now < aliveUntil) raf = requestAnimationFrame(frame);
    else lastTick = 0;
  }

  function wake() { if (started && !raf) raf = requestAnimationFrame(frame); }
  function redrawRing() { lens.classList.remove('draw'); void lens.getBoundingClientRect(); lens.classList.add('draw'); }

  function start() {
    if (started) return;
    started = true;
    guide.hidden = false;
    requestAnimationFrame(() => guide.classList.add('on'));
    wake();
  }

  function syncAway() { guide.classList.toggle('away', heroInView && mode !== 'ask' && mode !== 'answer'); }

  /* ---- the bubble ---- */
  function setText(text, typeIt) {
    clearInterval(typeTimer);
    sizer.textContent = text;          /* the bubble sizes to the finished line, so it never grows while typing */
    srEl.textContent = text;
    if (!typeIt || RM.matches) { textEl.textContent = text; return; }
    let i = 0;
    textEl.textContent = '';
    typeTimer = setInterval(() => {
      i = Math.min(text.length, i + 2);
      textEl.textContent = text.slice(0, i);
      if (i >= text.length) clearInterval(typeTimer);
    }, 20);
  }

  function setMode(next) {
    mode = next;
    bubble.dataset.mode = next;
    askForm.hidden = next !== 'ask';
    btnAsk.hidden = !(next === 'line' || next === 'answer');
    btnAsk.textContent = next === 'answer' ? 'Ask another' : 'Ask me something';
    btnMore.hidden = next !== 'answer';
    btnResume.hidden = !(off && (next === 'ask' || next === 'answer'));
    btnHide.textContent = next === 'line' ? 'Hide tour' : 'Close';
    guide.classList.toggle('asking', next === 'ask' || next === 'answer');
    syncAway();
    place = '';
    wake();
  }

  /* ---- lines ---- */
  function speakLine(item) {
    voice.say({
      src: `assets/voice/tour-${item.id}.mp3`,
      kind: 'tour',
      wanted: () => current === item && mode === 'line',
      onStart: () => { if (current === item) { clearTimeout(lineTimer); lineTimer = setTimeout(next, 20000); } },
      onEnd: () => { if (current !== item) return; clearTimeout(lineTimer); lineTimer = setTimeout(next, 900); },
    });
  }

  /* once the visitor starts using the console, she stops narrating it and lets them work */
  const CONSOLE_LINES = ['console', 'counter', 'natures', 'modes', 'starters', 'composer'];
  let consoleQuiet = false;

  function rearm(item) {
    if (consoleQuiet && CONSOLE_LINES.includes(item.id)) return;
    said.delete(item.id);
    io.unobserve(item.el);
    io.observe(item.el);
  }

  function next(latest) {
    clearTimeout(lineTimer);
    if (voice.replyActive) { lineTimer = setTimeout(next, 900); return; }   /* let her finish answering */
    /* mid-jump she would start a line about something the page is racing past, then cut it */
    if (performance.now() < rushUntil) { lostSince = 0; lineTimer = setTimeout(() => next(latest), 380); return; }
    let item = null;
    if (latest === true) {
      /* the visitor jumped ahead: go straight to the newest thing on screen */
      for (let i = queue.length - 1; i >= 0 && !item; i--) if (targetBox(queue[i].el)) item = queue.splice(i, 1)[0];
      queue.splice(0).forEach(rearm);
    }
    while (!item && queue.length) {
      const q = queue.shift();
      if (targetBox(q.el)) { item = q; break; }
      rearm(q);                        /* scrolled past before she got to it: it can come back */
    }
    heldForLine = false;
    lostSince = 0;
    current = item;
    if (!item) { if (mode === 'line') setMode('dock'); return; }
    setText(item.text, true);
    if (mode !== 'line') setMode('line');
    place = '';
    aliveUntil = performance.now() + 1300;   /* entrances are still settling under her */
    if (spotShown) redrawRing();
    lineTimer = setTimeout(next, Math.max(4200, item.text.split(/\s+/).length * 330 + 1500));
    speakLine(item);
    wake();
  }

  function trigger(id) {
    if (off || said.has(id)) return;
    const item = LINES.find((l) => l.id === id);
    if (!item || !item.el) return;
    start();
    said.add(id);
    queue.push(item);
    if (!current && mode !== 'ask' && mode !== 'answer') next();
  }

  function setOff(value) {
    off = value;
    store.set('aura.tour', value ? 'off' : 'on');
    if (value) {
      queue.length = 0;
      clearTimeout(lineTimer);
      clearInterval(typeTimer);
      voice.stopTour();
      if (current) { said.delete(current.id); current = null; }
      setMode(mode === 'line' ? 'dock' : mode);
    } else {
      LINES.forEach((l) => { if (l.el && !said.has(l.id)) { io.unobserve(l.el); io.observe(l.el); } });
      setMode(mode);
    }
  }

  /* ---- asking ---- */
  function openAsk() {
    start();
    clearTimeout(lineTimer);
    voice.stopTour();
    if (current) { rearm(current); current = null; }   /* she explains it again once you are done */
    setText(ASK_PROMPT, false);
    setMode('ask');
    coreBtn.setAttribute('aria-expanded', 'true');
    setTimeout(() => askInput.focus({ preventScroll: true }), 80);
  }

  function closeAsk() {
    coreBtn.setAttribute('aria-expanded', 'false');
    setMode('dock');
    if (!off && queue.length) next();
  }

  /* the bubble holds a short version; the full reply is always in the console */
  function summarize(text) {
    const hadCode = /```/.test(text);
    const flat = text.replace(/```[\s\S]*?(```|$)/g, ' ').replace(/[*_#>`]/g, '').replace(/\s+/g, ' ').trim();
    const parts = flat.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) || [flat];
    let out = '';
    for (const part of parts) { if (out && (out + part).length > 340) break; out += part; }
    out = out.trim() || flat.slice(0, 340);
    if (hadCode) return `${out}${out ? ' ' : ''}The code is in the console.`;
    return out.length < flat.length ? `${out} The rest is in the console.` : out;
  }

  askForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = askInput.value.trim();
    if (!q) return;
    if (demo.busy) { setText("I'm still answering in the console. Give me a second.", false); wake(); return; }
    askInput.value = '';
    setText('Thinking…', false);
    setMode('answer');
    demo.ask(q, {
      onChunk: (text) => { if (mode === 'answer') { setText(summarize(text) || 'Thinking…', false); wake(); } },
      onDone: (d) => { if (mode === 'answer') { setText(summarize(d.text || ''), false); wake(); } },
      onError: (msg) => { if (mode === 'answer') { setText(msg, false); wake(); } },
    });
  });
  askInput.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); closeAsk(); coreBtn.focus(); } });
  bubble.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (mode === 'ask' || mode === 'answer')) { closeAsk(); coreBtn.focus(); }
  });

  btnAsk.addEventListener('click', openAsk);
  btnHide.addEventListener('click', () => { if (mode === 'line') setOff(true); else closeAsk(); });
  btnResume.addEventListener('click', () => { setOff(false); closeAsk(); });
  btnMore.addEventListener('click', () => {
    closeAsk();
    $('#console').scrollIntoView({ behavior: RM.matches ? 'auto' : 'smooth', block: 'start' });
  });

  /* ---- dragging: a press that moves is a drag, a press that does not is a click ---- */
  coreBtn.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !pos) return;
    drag = { id: e.pointerId, sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y, x: pos.x, y: pos.y, moved: false };
    try { coreBtn.setPointerCapture(e.pointerId); } catch { /* capture is a nicety */ }
  });
  coreBtn.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    if (!drag.moved) { drag.moved = true; guide.classList.add('dragging'); }
    const h = coreSize() / 2, v = viewBox();
    drag.x = clamp(drag.ox + dx, v.l + h, v.r - h);
    drag.y = clamp(drag.oy + dy, v.t + h, v.b - h);
    wake();
  });
  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (drag.moved) {
      swallowClick = true;
      dock = { x: drag.x, y: drag.y };
      try { sessionStorage.setItem('aura.guide.dock', JSON.stringify(dock)); } catch { /* private mode */ }
      if (mode === 'line') heldForLine = true;   /* she stays where you put her for the rest of this line */
      guide.classList.remove('dragging');
      setTimeout(() => { swallowClick = false; }, 0);
    }
    drag = null;
    place = '';
    wake();
  };
  coreBtn.addEventListener('pointerup', endDrag);
  coreBtn.addEventListener('pointercancel', endDrag);
  coreBtn.addEventListener('click', () => {
    if (swallowClick) return;
    if (mode === 'ask' || mode === 'answer') closeAsk(); else openAsk();
  });

  /* ---- what wakes her ---- */
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting || off) continue;
      io.unobserve(e.target);
      trigger(e.target.dataset.tour);
    }
  }, { rootMargin: '-34% 0px -34% 0px' });
  LINES.forEach((l) => { if (l.el) io.observe(l.el); });

  /* she appears once the visitor is past the intro, and steps aside if they scroll back up to it */
  new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) start();
  }, { rootMargin: '0px 0px -40% 0px' }).observe(demoSection);
  new IntersectionObserver((entries) => {
    heroInView = entries[0].isIntersecting;
    syncAway();
    wake();
  }, { rootMargin: '-55% 0px 0px 0px' }).observe($('#top'));

  /* a jump (a nav link, "Skip the intro", a hard flick) moves faster than anyone reads */
  let lastY = scrollY, lastScrollAt = 0, rushUntil = 0;
  addEventListener('scroll', () => {
    const now = performance.now(), dt = now - lastScrollAt;
    if (lastScrollAt && dt > 0 && dt < 200 && Math.abs(scrollY - lastY) / dt > 2.5) rushUntil = now + 350;
    lastY = scrollY;
    lastScrollAt = now;
    wake();
  }, { passive: true });
  addEventListener('resize', () => { syncNav(); place = ''; wake(); }, { passive: true });
  consoleInput.addEventListener('focus', wake);
  consoleInput.addEventListener('blur', wake);

  function quietConsole() {
    if (consoleQuiet) return;
    consoleQuiet = true;
    CONSOLE_LINES.forEach((id) => said.add(id));
    for (let i = queue.length - 1; i >= 0; i--) if (CONSOLE_LINES.includes(queue[i].id)) queue.splice(i, 1);
    if (current && CONSOLE_LINES.includes(current.id)) { voice.stopTour(); next(); }
  }
  $('#console').addEventListener('pointerdown', quietConsole);
  consoleInput.addEventListener('focus', quietConsole);

  setMode('dock');

  return {
    trigger,
    speakCurrent() { if (current && mode === 'line') speakLine(current); },
  };
})();

/* voice is on by default, so say hello on phones and with reduced motion too; the scrub hero speaks as its first line settles */
if (voice.on) setTimeout(() => { if (!hero.scrubOn) speakWhatIsOnScreen(); }, 1200);

/* --------------------------------------------------------------------------
   The live console
   -------------------------------------------------------------------------- */
const demo = (() => {
  const API = (() => {
    const meta = $('meta[name="aura-api"]');
    const v = meta ? meta.content.trim() : '';
    if (v) return v.replace(/\/$/, '');
    return location.protocol === 'file:' ? '' : '/web/api';
  })();

  const NATURE_NOTES = {
    auto: "No lock. My tone follows what you're asking.",
    chill: 'Laid-back friend energy, whatever the task.',
    focus: 'All business. Minimal words, results first.',
    savage: 'Roast mode. Merciless, never cruel, still fixes it.',
    professional: 'Complete sentences. No slang, no sarcasm.',
  };
  const MODE_LABELS = { chat: 'Chat', code: 'Code', research: 'Research', discussion: 'Discussion', plan: 'Plan' };
  const SOURCE_LABELS = {
    classifier: 'read by the classifier',
    'director rule': 'set by a director rule',
    'workspace mode': 'pinned by the mode',
    'code request': 'explicit code request',
  };
  const PROVIDERS = { groq: 'Groq', openrouter: 'OpenRouter' };

  const el = {
    console: $('#console'), log: $('#log'), form: $('#composer'), input: $('#input'), send: $('#sendBtn'),
    counter: $('#counter'), status: $('#status'), dial: $('#dial'), note: $('#natureNote'),
    overlayBox: $('#overlayBox'), overlay: $('#overlayText'), modes: $('#modes'),
    newChat: $('#newChat'), trace: $('#trace'), modal: $('#limitModal'),
  };
  const t = {
    intent: $('#tIntent'), mode: $('#tMode'), style: $('#tStyle'), model: $('#tModel'),
    chain: $('#tChain'), guard: $('#tGuard'), time: $('#tTime'),
  };

  const st = {
    session: store.get('aura.site.session'),
    remaining: null, limit: 50,
    nature: store.get('aura.site.nature') || 'auto',
    mode: 'chat', busy: false, offline: false, ready: false,
    overlays: {}, ringAngle: 0, replied: false, offlineShown: false,
  };

  const headers = () => {
    const h = { 'Content-Type': 'application/json' };
    if (st.session) h['X-Aura-Session'] = st.session;
    return h;
  };

  async function post(path, body) {
    return fetch(API + path, { method: 'POST', headers: headers(), body: body ? JSON.stringify(body) : undefined });
  }

  /* ---- session ---- */
  async function handshake() {
    if (!API) throw new Error('no backend on file://');
    const res = await post('/session');
    if (!res.ok) throw new Error(`session ${res.status}`);
    const d = await res.json();
    st.session = d.session;
    store.set('aura.site.session', d.session);
    st.overlays = Object.fromEntries((d.natures || []).map((n) => [n.key, n.overlay]));
    st.ready = true;
    setOffline(false);
    budget(d);
    syncMode(d.mode);
    showOverlay(st.nature);
    return d;
  }

  async function ensureSession() {
    if (st.ready && st.session) return true;
    try { await handshake(); return true; } catch { setOffline(true); return false; }
  }

  function setOffline(on) {
    st.offline = on;
    el.console.classList.toggle('offline', on);
    if (on) {
      el.status.textContent = 'offline';
      if (!st.offlineShown) { st.offlineShown = true; addSystem(MSG_UNREACHABLE); }
    } else if (el.status.textContent === 'offline') {
      el.status.textContent = 'idle';
    }
  }

  /* ---- budget ---- */
  function budget(d) {
    if (!d || typeof d.remaining !== 'number') return;
    st.remaining = d.remaining;
    st.limit = d.limit || st.limit;
    el.counter.innerHTML = `<b>${st.remaining}</b><span class="c-of"> of ${st.limit}</span> left`;
    el.counter.classList.toggle('low', st.remaining <= 5);
    composerState();
  }

  function composerState() {
    const out = st.remaining === 0;
    el.send.disabled = st.busy || out;
    el.input.disabled = out;
    el.input.placeholder = out ? 'That’s the free 50.' : 'Say something to AURA';
    $$('.mode', el.modes).forEach((b) => { b.disabled = st.busy; });
  }

  /* ---- limit modal ---- */
  let lastFocus = null;
  function openLimit() {
    if (!el.modal.hidden) return;
    lastFocus = document.activeElement;
    el.modal.hidden = false;
    requestAnimationFrame(() => el.modal.classList.add('on'));
    setTimeout(() => $('.btn-primary', el.modal).focus(), 60);
  }
  function closeLimit() {
    el.modal.classList.remove('on');
    setTimeout(() => { el.modal.hidden = true; }, RM.matches ? 0 : 450);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  $$('[data-close]', el.modal).forEach((b) => b.addEventListener('click', closeLimit));
  el.modal.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeLimit();
    if (e.key === 'Tab') {
      const f = $$('a, button', $('.modal-card', el.modal));
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  /* ---- natures: the dial ---- */
  const natButtons = $$('.nat', el.dial);
  function typeInto(node, text) {
    if (RM.matches || !text) { node.textContent = text; return; }
    let i = 0;
    clearInterval(node._timer);
    node.textContent = '';
    node._timer = setInterval(() => {
      i = Math.min(text.length, i + 4);
      node.textContent = text.slice(0, i);
      if (i >= text.length) clearInterval(node._timer);
    }, 16);
  }
  function showOverlay(key) {
    const text = st.overlays[key] || '';
    el.overlayBox.hidden = !text;
    if (text) typeInto(el.overlay, text);
  }
  function selectNature(key, { focus = false } = {}) {
    const i = natButtons.findIndex((b) => b.dataset.nature === key);
    if (i < 0) return;
    st.nature = key;
    store.set('aura.site.nature', key);
    natButtons.forEach((b, j) => {
      b.setAttribute('aria-checked', String(j === i));
      b.tabIndex = j === i ? 0 : -1;
    });
    if (focus) natButtons[i].focus();
    const want = -i * 72;
    const delta = ((want - st.ringAngle) % 360 + 540) % 360 - 180;
    st.ringAngle += delta;
    el.dial.style.setProperty('--ring', `${st.ringAngle}deg`);
    document.body.dataset.nature = key;
    el.note.textContent = NATURE_NOTES[key];
    showOverlay(key);
  }
  natButtons.forEach((b, i) => {
    b.addEventListener('click', () => selectNature(b.dataset.nature));
    b.addEventListener('keydown', (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const n = natButtons[(i + step + natButtons.length) % natButtons.length];
      selectNature(n.dataset.nature, { focus: true });
    });
  });

  /* ---- modes ---- */
  function syncMode(mode) {
    st.mode = mode || 'chat';
    $$('.mode', el.modes).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === st.mode)));
  }
  $$('.mode', el.modes).forEach((b) => b.addEventListener('click', async () => {
    const want = b.dataset.mode;
    if (st.busy || want === st.mode) return;
    if (!(await ensureSession())) return;
    try {
      let res = await post('/mode', { mode: want });
      if (res.status === 401) { st.ready = false; await handshake(); res = await post('/mode', { mode: want }); }
      if (!res.ok) throw new Error(`mode ${res.status}`);
      const d = await res.json();
      syncMode(d.mode);
      budget(d);
      if (d.text) addSystem(d.text);
    } catch {
      setOffline(true);
    }
  }));

  /* ---- transcript ---- */
  function nearBottom() { return el.log.scrollHeight - el.log.scrollTop - el.log.clientHeight < 80; }
  function scrollLog(force) { if (force || nearBottom()) el.log.scrollTop = el.log.scrollHeight; }

  /* A short reply keeps the log pinned to the bottom. A long one (a plan, a report)
     is held at its first line so the visitor reads it top-down instead of chasing
     the stream. Scrolling the log by hand mid-reply hands control back to them. */
  let follow = true;
  const letGo = () => { if (st.busy) follow = false; };
  el.log.addEventListener('wheel', letGo, { passive: true });
  el.log.addEventListener('touchmove', letGo, { passive: true });
  function followReply(msg) {
    if (!follow) return;
    const r = msg.getBoundingClientRect();
    if (r.height > el.log.clientHeight - 48) {
      const want = el.log.scrollTop + (r.top - el.log.getBoundingClientRect().top) - 12;
      if (Math.abs(el.log.scrollTop - want) > 2) el.log.scrollTop = want;
    } else {
      el.log.scrollTop = el.log.scrollHeight;
    }
  }

  function addMsg(role, text) {
    const wrap = document.createElement('div');
    wrap.className = `msg ${role}`;
    const who = document.createElement('span');
    who.className = 'who';
    who.textContent = role === 'user' ? 'You' : 'AURA';
    const body = document.createElement('div');
    body.className = 'body';
    if (text) {
      if (role === 'user') body.textContent = text; else render(body, text);
    }
    wrap.append(who, body);
    el.log.append(wrap);
    el.log.classList.add('has-msgs');
    scrollLog(true);
    return body;
  }

  function addSystem(text) {
    const p = document.createElement('p');
    p.className = 'sys';
    p.textContent = text;
    el.log.append(p);
    scrollLog(true);
  }

  /* small, safe markdown: fences, headings, lists, bold, inline code */
  function inline(node, text) {
    const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) node.append(text.slice(last, m.index));
      const tok = m[0];
      const tag = document.createElement(tok[0] === '`' ? 'code' : 'strong');
      tag.textContent = tok[0] === '`' ? tok.slice(1, -1) : tok.slice(2, -2);
      node.append(tag);
      last = m.index + tok.length;
    }
    if (last < text.length) node.append(text.slice(last));
  }
  /* A section name on its own line ("Goal", "Architecture / Approach", "**Risks**"),
     the shape research, discussion and plan replies use for their headings. */
  const isSectionLine = (line, next) => {
    const bare = line.replace(/^\*\*(.+)\*\*:?$/, '$1').trim();
    if (!next || bare.length > 48 || /[.!?,;]$/.test(bare) || !/^[A-Z]/.test(bare)) return false;
    return /^\*\*.+\*\*:?$/.test(line) || bare.split(/\s+/).length <= 5;
  };
  function prose(root, text) {
    let list = null, para = [];
    const flush = () => {
      if (!para.length) return;
      const p = document.createElement('p');
      inline(p, para.join(' '));
      root.append(p);
      para = [];
    };
    const lines = text.replace(/\r/g, '').split('\n');
    const structured = text.length > 400;       /* short chat replies never get headings */
    lines.forEach((raw, i) => {
      const line = raw.trim();
      const next = (lines[i + 1] || '').trim();
      let m;
      if (!line) { flush(); list = null; return; }
      if ((m = line.match(/^#{1,4}\s+(.*)$/)) || (structured && !para.length && isSectionLine(line, next))) {
        flush(); list = null;
        const h = document.createElement('h4');
        inline(h, (m ? m[1] : line).replace(/\*\*/g, '').replace(/:$/, ''));
        root.append(h);
        return;
      }
      if ((m = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/))) {
        flush();
        const ordered = /^\d/.test(line);
        if (!list || list.dataset.ordered !== String(ordered)) {
          list = document.createElement(ordered ? 'ol' : 'ul');
          list.dataset.ordered = String(ordered);
          root.append(list);
        }
        const li = document.createElement('li'); inline(li, m[1]); list.append(li);
        return;
      }
      list = null;
      para.push(line);
    });
    flush();
  }
  function codeBlock(lang, code) {
    const fig = document.createElement('figure');
    fig.className = 'codeblock';
    const bar = document.createElement('div');
    bar.className = 'codeblock-bar';
    const label = document.createElement('span');
    label.textContent = lang || 'code';
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.textContent = 'Copy';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(code); copy.textContent = 'Copied'; }
      catch { copy.textContent = 'Select it'; }
      setTimeout(() => { copy.textContent = 'Copy'; }, 1500);
    });
    bar.append(label, copy);
    const pre = document.createElement('pre');
    const c = document.createElement('code');
    c.textContent = code;
    pre.append(c);
    fig.append(bar, pre);
    return fig;
  }
  function render(root, src) {
    root.textContent = '';
    const parts = src.split(/```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g);
    for (let i = 0; i < parts.length; i += 3) {
      if (parts[i] && parts[i].trim()) prose(root, parts[i]);
      if (i + 2 < parts.length) root.append(codeBlock((parts[i + 1] || '').trim(), (parts[i + 2] || '').replace(/\n$/, '')));
    }
  }

  /* ---- the trace ---- */
  function flash(node) { node.classList.remove('flash'); void node.offsetWidth; node.classList.add('flash'); }
  function setRow(node, main, small) {
    node.textContent = '';
    if (main instanceof Node) node.append(main); else node.append(main);
    if (small) { const s = document.createElement('small'); s.textContent = small; node.append(s); }
    flash(node);
  }
  const trace = {
    reset() {
      el.trace.classList.add('used');
      [t.intent, t.mode, t.style, t.model, t.guard, t.time].forEach((n) => { n.textContent = '…'; });
      t.chain.textContent = '';
    },
    route(d) {
      if (d.lane === 'reply') {
        setRow(t.intent, 'none', 'answered locally');
        setRow(t.mode, MODE_LABELS[d.mode] || d.mode);
        return;
      }
      const corrected = d.classifier && d.classifier !== d.intent && d.source === 'classifier';
      setRow(t.intent, d.intent, corrected ? `classifier said ${d.classifier}, rules corrected it` : SOURCE_LABELS[d.source] || d.source);
      setRow(t.mode, MODE_LABELS[d.mode] || d.mode, d.nature && d.nature !== 'auto' ? `nature: ${d.nature}` : '');
      t.chain.textContent = '';
      (d.candidates || []).forEach((name) => {
        const li = document.createElement('li');
        li.textContent = name;
        li.dataset.name = name;
        t.chain.append(li);
      });
      t.model.textContent = 'routing…';
    },
    fallback(d) {
      const li = $$('li', t.chain).find((n) => n.dataset.name === d.model);
      if (!li) return;
      li.classList.remove('win');
      li.classList.add('fail');
      const em = document.createElement('em');
      em.textContent = ` ${d.reason}`;
      li.append(em);
    },
    model(d) {
      const li = $$('li', t.chain).find((n) => n.dataset.name === d.name);
      if (li) li.classList.add('win');
      const b = document.createElement('b');
      b.textContent = d.name;
      setRow(t.model, b, `${d.id} · ${PROVIDERS[d.provider] || d.provider}`);
    },
    done(d) {
      if (d.lane === 'reply') {
        setRow(t.style, 'none');
        setRow(t.model, 'none', 'no model call');
        t.chain.textContent = '';
      } else {
        const cap = d.cap ? `${d.cap} sentence cap` : 'whole answer';
        setRow(t.style, d.style || '·', cap);
      }
      const notes = (d.notes || []).filter(Boolean);
      if (notes.length) {
        const ul = document.createElement('ul');
        ul.className = 't-guard';
        notes.forEach((n) => { const li = document.createElement('li'); li.textContent = n; ul.append(li); });
        setRow(t.guard, ul);
      } else {
        setRow(t.guard, 'clean pass');
      }
      setRow(t.time, `${((d.ms || 0) / 1000).toFixed(1)} s`);
    },
    error(d) {
      $$('li', t.chain).forEach((li) => { if (!li.classList.contains('fail')) li.classList.add('fail'); });
      setRow(t.model, 'no model answered', d.code === 'RATE_LIMIT' ? 'every model in the chain was rate limited' : 'every model in the chain failed');
      setRow(t.guard, '·');
      setRow(t.style, '·');
      t.time.textContent = '·';
    },
  };

  /* ---- server-sent events ---- */
  async function readSSE(res, onEvent) {
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const frames = buf.split('\n\n');
      buf = frames.pop();
      for (const frame of frames) {
        let ev = 'message', data = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) ev = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (!data) continue;
        try { onEvent(ev, JSON.parse(data)); } catch { /* malformed frame */ }
      }
    }
  }

  /* ---- send ----
     The guide asks through here too, with hooks: onChunk(text), onDone(d),
     onError(message). Her questions land in the console log like any other,
     but leave the composer's draft and focus alone. */
  async function send(raw, hooks = {}) {
    const text = raw.trim();
    if (!text || st.busy) return;
    if (st.remaining === 0) { openLimit(); if (hooks.onError) hooks.onError('That’s the free 50.'); return; }
    if (!(await ensureSession())) { if (hooks.onError) hooks.onError(MSG_UNREACHABLE); return; }

    st.busy = true;
    composerState();
    if (!hooks.fromGuide) { el.input.value = ''; autoGrow(); }
    addMsg('user', text);
    const out = addMsg('aura', '');
    const msg = out.parentElement;
    out.innerHTML = '<span class="typing" aria-label="AURA is thinking"><i></i><i></i><i></i></span>';
    setChatState('thinking');
    el.status.textContent = 'thinking';
    trace.reset();
    voice.stopReply();

    let acc = '', finished = false, painting = false;
    follow = true;
    const fail = (message) => { if (hooks.onError) hooks.onError(message); };
    const paint = () => {
      painting = false;
      if (finished) return;
      render(out, acc);
      followReply(msg);
      if (hooks.onChunk) hooks.onChunk(acc);
    };

    try {
      const body = { text, nature: st.nature };
      let res = await post('/chat', body);
      if (res.status === 401) { st.ready = false; await handshake(); res = await post('/chat', body); }
      if (!res.ok) {
        let d = {};
        try { d = await res.json(); } catch { /* not json */ }
        budget(d);
        if (res.status === 429 && d.code === 'limit') {
          msg.remove();
          openLimit();
          fail('That’s the free 50.');
          return;
        }
        msg.classList.add('err');
        out.textContent = res.status === 429 ? 'Too many requests. Give it a minute.' : (typeof d.detail === 'string' ? d.detail : MSG_UNREACHABLE);
        fail(out.textContent);
        return;
      }

      await readSSE(res, (ev, d) => {
        if (ev === 'state' && d.state) {
          setChatState(d.state);
          el.status.textContent = d.state;
        } else if (ev === 'route') {
          trace.route(d);
          if (d.mode) syncMode(d.mode);
        } else if (ev === 'fallback') {
          trace.fallback(d);
        } else if (ev === 'model') {
          trace.model(d);
        } else if (ev === 'chunk') {
          acc += d.text;
          if (!painting) { painting = true; requestAnimationFrame(paint); }
        } else if (ev === 'reset') {
          acc = '';
          out.innerHTML = '<span class="typing" aria-label="AURA is thinking"><i></i><i></i><i></i></span>';
          if (hooks.onChunk) hooks.onChunk('');
        } else if (ev === 'done') {
          finished = true;
          if (d.lane === 'reply') msg.classList.add('instant');
          render(out, d.text || acc);
          followReply(msg);
          trace.done(d);
          budget(d);
          if (d.mode) syncMode(d.mode);
          afterReply(d);
          if (hooks.onDone) hooks.onDone(d);
        } else if (ev === 'error') {
          finished = true;
          msg.classList.add('err');
          out.textContent = d.message || MSG_UNREACHABLE;
          trace.error(d);
          budget(d);
          fail(out.textContent);
        }
      });
      if (!finished) { msg.classList.add('err'); out.textContent = MSG_UNREACHABLE; fail(MSG_UNREACHABLE); }
    } catch {
      msg.classList.add('err');
      out.textContent = MSG_UNREACHABLE;
      st.ready = false;
      setOffline(true);
      fail(MSG_UNREACHABLE);
    } finally {
      st.busy = false;
      setChatState('idle');
      if (!st.offline) el.status.textContent = presence.voice ? 'speaking' : 'idle';
      composerState();
      if (st.remaining !== 0 && !hooks.fromGuide) el.input.focus({ preventScroll: true });
    }
  }

  /* the live roster, grouped by job, from /session; the HTML list is the fallback */
  function renderRoster(chains) {
    const list = $('#rosterList');
    if (!list || !chains) return;
    const rows = Object.entries(chains).filter(([, models]) => Array.isArray(models) && models.length);
    if (!rows.length) return;
    list.textContent = '';
    for (const [job, models] of rows) {
      const li = document.createElement('li');
      const b = document.createElement('b');
      b.textContent = job;
      const span = document.createElement('span');
      span.textContent = models.join(', ');
      li.append(b, span);
      list.append(li);
    }
  }

  function afterReply(d) {
    if (d.counted && !st.replied) {
      st.replied = true;
      tour.trigger('trace');
    }
    if (voice.on && d.text) voice.say({ text: d.text, kind: 'reply' });
    if (d.remaining === 0) setTimeout(openLimit, 1800);
  }

  async function ttsUrl(text) {
    if (!API || !st.session) return null;
    try {
      const res = await post('/tts', { text });
      if (!res.ok) return null;
      return URL.createObjectURL(await res.blob());
    } catch {
      return null;
    }
  }

  /* ---- composer ---- */
  function autoGrow() {
    el.input.style.height = 'auto';
    el.input.style.height = `${Math.min(el.input.scrollHeight, 152)}px`;
  }
  el.input.addEventListener('input', autoGrow);
  el.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(el.input.value); }
  });
  el.form.addEventListener('submit', (e) => { e.preventDefault(); send(el.input.value); });
  $$('.starter').forEach((b) => b.addEventListener('click', () => {
    el.input.value = b.textContent;
    autoGrow();
    el.input.focus();
  }));

  el.newChat.addEventListener('click', async () => {
    if (st.busy) return;
    voice.stopReply();
    el.log.textContent = '';
    el.log.classList.remove('has-msgs');
    el.trace.classList.remove('used');
    [t.intent, t.mode, t.style, t.model, t.guard, t.time].forEach((n) => { n.textContent = '·'; });
    t.chain.textContent = '';
    if (!(await ensureSession())) return;
    try {
      const res = await post('/reset');
      if (res.ok) { const d = await res.json(); budget(d); syncMode(d.mode); }
    } catch { setOffline(true); }
  });

  /* ---- boot ---- */
  selectNature(st.nature);
  syncMode('chat');
  const boot = () => handshake().then((d) => renderRoster(d && d.chains)).catch(() => setOffline(true));
  if ('requestIdleCallback' in window) requestIdleCallback(boot, { timeout: 2500 }); else setTimeout(boot, 1200);

  return {
    ttsUrl,
    /* the guide's questions: false while an answer is still streaming */
    ask(text, hooks) {
      if (st.busy) return false;
      send(text, { ...hooks, fromGuide: true });
      return true;
    },
    get busy() { return st.busy; },
  };
})();

/* --------------------------------------------------------------------------
   Reduced motion, honoured live in both directions
   -------------------------------------------------------------------------- */
let pipePinned = false;
function pinToFinalStates() {
  document.documentElement.classList.add('rm-pinned');
  $$('.reveal:not(.in)').forEach((el) => { pinnedByRM.add(el); el.classList.add('in', 'settled'); });
  if (pipeline && !pipeline.classList.contains('drawn')) { pipePinned = true; pipeline.classList.add('drawn'); }
}
function unpinFinalStates() {
  document.documentElement.classList.remove('rm-pinned');
  pinnedByRM.forEach((el) => {
    el.classList.remove('in', 'settled');
    revealIO.observe(el);
  });
  pinnedByRM.clear();
  if (pipePinned) { pipePinned = false; pipeline.classList.remove('drawn'); pipeIO.observe(pipeline); }
}
RM.addEventListener('change', (e) => {
  if (e.matches) pinToFinalStates();
  else { unpinFinalStates(); hero.applyMode(); }
});

})();
