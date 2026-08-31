/* ===========================================================================
   AURA — public site behaviour
   Zero dependencies. Talks to /web/api/* when the backend is up; falls back to
   a scripted "offline preview" when it isn't (so the page still demos from a
   file:// open or a static host).
   =========================================================================== */
(() => {
'use strict';

const API = '/web/api';
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ───────────────────────── starfield ───────────────────────── */
(function stars(){
  const c = $('#stars');
  if (!c || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx = c.getContext('2d');
  let w, h, pts = [];
  const resize = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    w = c.width = innerWidth * dpr; h = c.height = innerHeight * dpr;
    c.style.width = innerWidth + 'px'; c.style.height = innerHeight + 'px';
    const n = Math.min(190, Math.round(innerWidth * innerHeight / 11000));
    pts = Array.from({length: n}, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: (Math.random() * 1.25 + .25) * dpr,
      a: Math.random() * .55 + .12,
      s: (Math.random() * .12 + .02) * dpr,
      t: Math.random() * Math.PI * 2
    }));
  };
  const tick = () => {
    ctx.clearRect(0, 0, w, h);
    for (const p of pts) {
      p.y -= p.s; p.t += .012;
      if (p.y < -4) { p.y = h + 4; p.x = Math.random() * w; }
      const a = p.a * (0.65 + 0.35 * Math.sin(p.t));
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.284);
      ctx.fillStyle = `rgba(200,214,255,${a})`; ctx.fill();
    }
    requestAnimationFrame(tick);
  };
  addEventListener('resize', resize, {passive: true});
  resize(); tick();
})();

/* ───────────────────────── chrome ───────────────────────── */
addEventListener('scroll', () => $('#nav').classList.toggle('stuck', scrollY > 8), {passive: true});

const io = new IntersectionObserver((es) => {
  es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
}, {threshold: .12});
$$('.reveal').forEach((el, i) => { el.style.transitionDelay = `${Math.min(i % 6, 5) * 55}ms`; io.observe(el); });

$$('.copy').forEach(b => b.addEventListener('click', async () => {
  const pre = $('#' + b.dataset.copy + '-code');
  try { await navigator.clipboard.writeText(pre.innerText); b.textContent = 'Copied'; }
  catch { b.textContent = 'Select it'; }
  setTimeout(() => b.textContent = 'Copy', 1600);
}));

/* ───────────────────────── demo shell ───────────────────────── */
const state = {
  session: localStorage.getItem('aura.web.session') || null,
  remaining: null,
  offline: false,
  busy: false,
  facts: [],
  notes: [],
};

const setSession = (id) => {
  if (!id || id === state.session) return;
  state.session = id;
  try { localStorage.setItem('aura.web.session', id); } catch {}
};

const headers = () => {
  const h = {'Content-Type': 'application/json'};
  if (state.session) h['X-Aura-Session'] = state.session;
  return h;
};

async function api(path, opts = {}) {
  const res = await fetch(API + path, {headers: headers(), ...opts});
  const sid = res.headers.get('X-Aura-Session');
  if (sid) setSession(sid);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return res.json();
}

function goOffline() {
  if (state.offline) return;
  state.offline = true;
  $('#modelPill').textContent = 'offline preview';
  $('#quotaPill').textContent = 'scripted';
  $('#quotaNote').textContent = 'backend not reachable — showing scripted replies';
}

$$('.tab').forEach(t => t.addEventListener('click', () => {
  $$('.tab').forEach(x => x.classList.toggle('is-on', x === t));
  $$('.pane').forEach(p => p.classList.toggle('is-on', p.dataset.pane === t.dataset.tab));
  if (t.dataset.tab === 'brain') loadProjects();
  if (t.dataset.tab === 'memory') renderMemory();
}));

function quota(info) {
  if (info && typeof info.remaining === 'number') {
    state.remaining = info.remaining;
    $('#quotaPill').textContent = `${info.remaining} left`;
    $('#quotaNote').textContent = `${info.remaining} of ${info.limit} turns left in this session`;
    $('#sendBtn').disabled = info.remaining <= 0 || state.busy;
  }
}

/* ───────────────────────── chat ───────────────────────── */
const log = $('#chatLog');

function bubble(role, text, cls) {
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + role;
  const who = document.createElement('div');
  who.className = 'who'; who.textContent = role === 'user' ? 'You' : 'AURA';
  const b = document.createElement('div');
  b.className = 'bubble' + (cls ? ' ' + cls : '');
  if (text) b.textContent = text;
  wrap.append(who, b); log.append(wrap);
  log.scrollTop = log.scrollHeight;
  return b;
}

function typing(el) {
  el.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
}

/* very small markdown: fenced code blocks + inline code */
function render(el, text) {
  el.textContent = '';
  const parts = text.split(/```(?:[a-zA-Z0-9_+-]*)\n?/);
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = part.replace(/\n$/, '');
      pre.append(code); el.append(pre);
    } else if (part) {
      const frag = document.createDocumentFragment();
      part.split(/`([^`\n]+)`/).forEach((seg, j) => {
        if (j % 2 === 1) { const c = document.createElement('code'); c.textContent = seg; frag.append(c); }
        else if (seg) frag.append(document.createTextNode(seg));
      });
      el.append(frag);
    }
  });
}

const CANNED = [
  "That one needs the desktop app — the browser build has no screen or file access. Ask me something I can actually answer here.",
  "Short version: I keep state. Most assistants start from zero every time; I read back what you told me, what you shipped, and what broke, then answer from that.",
  "Fine. The pattern you want is a decorator that catches, sleeps `base * 2 ** attempt` with jitter, and re-raises on the last try. Keep the sleep outside the try.",
  "Noted. I'll hold that for this session — close the tab and it's gone, which is the honest trade for a demo you didn't install."
];
let cannedIdx = 0;

async function send(text) {
  if (state.busy || !text.trim()) return;
  state.busy = true;
  $('#sendBtn').disabled = true;
  bubble('user', text);
  const out = bubble('aura', '');
  typing(out);

  if (state.offline) {
    await new Promise(r => setTimeout(r, 550));
    render(out, CANNED[cannedIdx++ % CANNED.length]);
    state.busy = false; $('#sendBtn').disabled = false;
    return;
  }

  let acc = '';
  try {
    const res = await fetch(API + '/chat', {
      method: 'POST', headers: headers(), body: JSON.stringify({text})
    });
    const sid = res.headers.get('X-Aura-Session');
    if (sid) setSession(sid);
    if (!res.ok || !res.body) {
      let msg = 'The demo is busy or out of turns. Try again in a minute.';
      try { msg = (await res.json()).detail || msg; } catch {}
      out.classList.add('err'); out.textContent = msg;
      throw new Error(msg);
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const frames = buf.split('\n\n');
      buf = frames.pop();
      for (const frame of frames) {
        let ev = 'message', data = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) ev = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (!data) continue;
        let payload; try { payload = JSON.parse(data); } catch { continue; }

        if (ev === 'chunk') { acc += payload.text; render(out, acc); log.scrollTop = log.scrollHeight; }
        else if (ev === 'done') { render(out, payload.text || acc); quota(payload); if (payload.model) $('#modelPill').textContent = payload.model; }
        else if (ev === 'error') { out.classList.add('err'); out.textContent = payload.message; }
        else if (ev === 'state' && payload.model) $('#modelPill').textContent = payload.model;
      }
    }
    if (!acc && !out.textContent) { out.classList.add('err'); out.textContent = 'Empty reply. Try rephrasing.'; }
  } catch (e) {
    if (!out.textContent || out.querySelector('.typing')) {
      out.classList.add('err');
      out.textContent = 'Could not reach AURA. Is the backend running?';
      goOffline();
    }
  } finally {
    state.busy = false;
    $('#sendBtn').disabled = state.remaining === 0;
    log.scrollTop = log.scrollHeight;
  }
}

$('#chatForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const i = $('#chatInput');
  const v = i.value; i.value = '';
  send(v);
});

$$('#chips .chip').forEach(c => c.addEventListener('click', () => send(c.textContent)));

$('#resetBtn').addEventListener('click', async () => {
  log.innerHTML = '';
  bubble('aura', 'Clean slate. Nothing kept.');
  state.facts = []; state.notes = []; renderMemory();
  if (state.offline) return;
  try { quota(await api('/reset', {method: 'POST'})); } catch { goOffline(); }
});

/* ───────────────────────── memory ───────────────────────── */
function renderMemory() {
  const fl = $('#factList'), nl = $('#noteList');
  $('#factCount').textContent = state.facts.length;
  $('#noteCount').textContent = state.notes.length;

  fl.innerHTML = '';
  if (!state.facts.length) fl.innerHTML = '<p class="empty">Nothing yet. Tell it something.</p>';
  state.facts.forEach(f => {
    const li = document.createElement('li');
    const cat = document.createElement('span'); cat.className = 'cat'; cat.textContent = f.category;
    const txt = document.createElement('span'); txt.textContent = f.fact;
    const x = document.createElement('button'); x.className = 'x'; x.textContent = '×'; x.title = 'Forget';
    x.addEventListener('click', async () => {
      state.facts = state.facts.filter(v => v.id !== f.id); renderMemory();
      if (!state.offline) { try { await api('/memory/facts/' + f.id, {method: 'DELETE'}); } catch {} }
    });
    li.append(cat, txt, x); fl.append(li);
  });

  nl.innerHTML = '';
  if (!state.notes.length) nl.innerHTML = '<p class="empty">No notes saved.</p>';
  state.notes.forEach(n => {
    const li = document.createElement('li');
    const txt = document.createElement('span'); txt.textContent = n.text;
    const when = document.createElement('span'); when.className = 'cat'; when.textContent = 'note';
    li.append(when, txt); nl.append(li);
  });
}

$('#factForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#factInput'), cat = $('#factCat').value;
  const fact = input.value.trim(); if (!fact) return;
  input.value = '';
  const local = {id: 'l' + Math.random().toString(36).slice(2, 8), fact, category: cat};
  state.facts.push(local); renderMemory();
  if (state.offline) return;
  try {
    const r = await api('/memory/facts', {method: 'POST', body: JSON.stringify({fact, category: cat})});
    state.facts = r.facts; quota(r); renderMemory();
  } catch (err) {
    if (err.status === 429) { state.facts.pop(); renderMemory(); alert(err.message); }
    else goOffline();
  }
});

$('#noteForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#noteInput');
  const text = input.value.trim(); if (!text) return;
  input.value = '';
  state.notes.push({id: 'l' + Math.random().toString(36).slice(2, 8), text}); renderMemory();
  if (state.offline) return;
  try {
    const r = await api('/memory/notes', {method: 'POST', body: JSON.stringify({text})});
    state.notes = r.notes; quota(r); renderMemory();
  } catch { goOffline(); }
});

/* ───────────────────────── project brain ───────────────────────── */
const FALLBACK_PROJECT = {
  project: {id: 'aura', name: 'AURA', summary: 'Offline preview — the backend serves the real snapshot.'},
  overall: {done: 41, total: 58, pct: 71},
  counts: {features: 12, tasks: 58, decisions: 19, commits: 214},
  blocker: {title: 'Two response paths have drifted apart',
    detail: 'brain.process() and brain.process_streaming() duplicate context assembly.',
    feature: 'Conversation core', age_days: 11},
  features: [
    {name: 'Conversation core', status: 'in_progress', done: 9, total: 12},
    {name: 'Voice I/O', status: 'done', done: 6, total: 6},
    {name: 'Durable memory', status: 'done', done: 7, total: 7},
    {name: 'Project Brain (Domain)', status: 'in_progress', done: 8, total: 14},
  ],
  timeline: [{date: '2026-08-20', kind: 'milestone', title: 'Named chat sessions', detail: 'Switchable chats; context follows the switch.'}],
  graph: {nodes: [], edges: []}
};

let projectsLoaded = false;

async function loadProjects() {
  if (projectsLoaded) return;
  projectsLoaded = true;
  const sel = $('#projSelect');
  try {
    const r = await api('/domain/projects');
    $('#sourcePill').textContent = r.source === 'live' ? 'live graph' : 'sample data';
    sel.innerHTML = '';
    (r.projects || []).forEach(p => {
      const o = document.createElement('option'); o.value = p.id; o.textContent = p.name; sel.append(o);
    });
    sel.addEventListener('change', () => loadProject(sel.value));
    if (sel.options.length) loadProject(sel.value);
    else drawProject(FALLBACK_PROJECT);
  } catch {
    goOffline();
    $('#sourcePill').textContent = 'offline preview';
    sel.innerHTML = '<option>AURA</option>';
    drawProject(FALLBACK_PROJECT);
  }
}

async function loadProject(pid) {
  $('#brainBody').innerHTML = '<p class="hint">Loading…</p>';
  try { drawProject(await api('/domain/project/' + encodeURIComponent(pid))); }
  catch { drawProject(FALLBACK_PROJECT); }
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function drawProject(p) {
  const body = $('#brainBody');
  body.innerHTML = '';
  const o = p.overall || {pct: 0, done: 0, total: 0};
  const c = p.counts || {};

  /* header */
  const top = el('div', 'brain-top');
  const ring = el('div', 'ring');
  ring.style.setProperty('--pct', o.pct || 0);
  ring.append(el('span', '', (o.pct || 0) + '%'));
  const sum = el('div', 'brain-sum');
  sum.append(el('h3', '', (p.project && p.project.name) || p.name || 'Project'));
  sum.append(el('p', '', (p.project && p.project.summary) || p.summary ||
    `${o.done} of ${o.total} tasks closed.`));
  const counts = el('div', 'counts');
  [['features', 'features'], ['tasks', 'tasks'], ['decisions', 'decisions'], ['commits', 'commits']]
    .forEach(([k, label]) => {
      if (c[k] == null) return;
      const d = el('div'); d.append(el('b', '', String(c[k])), document.createTextNode(label)); counts.append(d);
    });
  sum.append(counts);
  top.append(ring, sum);
  body.append(top);

  /* blocker */
  if (p.blocker && p.blocker.title) {
    const b = el('div', 'blocker');
    b.append(el('h4', '', 'Biggest blocker'));
    b.append(el('strong', '', p.blocker.title));
    if (p.blocker.detail) b.append(el('p', '', p.blocker.detail));
    const bits = [p.blocker.feature, p.blocker.age_days != null ? `open ${p.blocker.age_days} days` : null]
      .filter(Boolean).join(' · ');
    if (bits) b.append(el('span', 'age', bits));
    body.append(b);
  }

  /* columns */
  const cols = el('div', 'brain-cols');

  const fp = el('div', 'panel');
  fp.append(el('h4', '', 'Features'));
  (p.features || []).forEach(f => {
    const total = f.total || 1, done = f.done || 0;
    const w = Math.round(done / total * 100);
    const box = el('div', 'feat');
    const t = el('div', 'feat-top');
    t.append(el('b', '', f.name));
    t.append(el('span', 'st ' + (f.status || ''), (f.status || '').replace('_', ' ')));
    const bar = el('div', 'bar'); const i = el('i'); bar.append(i);
    box.append(t, bar);
    if (f.note) box.append(el('small', '', f.note));
    fp.append(box);
    requestAnimationFrame(() => { i.style.width = w + '%'; });
  });
  if (!(p.features || []).length) fp.append(el('p', 'empty', 'No features in this graph yet.'));
  cols.append(fp);

  const right = el('div', 'panel');
  right.append(el('h4', '', 'Timeline'));
  const tl = el('ul', 'tl');
  (p.timeline || []).slice().reverse().forEach(t => {
    const li = el('li', t.kind || 'milestone');
    li.append(el('span', 'when', t.date || ''));
    li.append(el('b', '', t.title || ''));
    if (t.detail) li.append(el('p', '', t.detail));
    tl.append(li);
  });
  if (!(p.timeline || []).length) tl.append(el('li', '', 'Nothing recorded.'));
  right.append(tl);

  const g = p.graph || {};
  if ((g.nodes || []).length) {
    right.append(el('h4', '', 'Graph'));
    const gr = el('div', 'graph');
    g.nodes.forEach(n => {
      const nd = el('div', 'node ' + (n.type || ''));
      nd.append(el('span', 'k', n.type || 'node'));
      nd.append(document.createTextNode(n.title || ''));
      gr.append(nd);
    });
    right.append(gr);
    const byId = Object.fromEntries(g.nodes.map(n => [n.id, n.title]));
    const ed = el('div', 'edges');
    (g.edges || []).slice(0, 6).forEach(e => {
      const line = el('div');
      line.append(el('span', '', byId[e.src] || e.src));
      line.append(document.createTextNode(`  —${e.type}→  `));
      line.append(el('span', '', byId[e.dst] || e.dst));
      ed.append(line);
    });
    right.append(ed);
  }
  cols.append(right);
  body.append(cols);
}

/* ───────────────────────── boot ───────────────────────── */
(async function boot(){
  try {
    const s = await api('/session');
    setSession(s.session);
    $('#modelPill').textContent = s.model || 'model —';
    quota(s);
    const m = await api('/memory');
    state.facts = m.facts || []; state.notes = m.notes || [];
    renderMemory();
  } catch {
    goOffline();
    renderMemory();
  }
})();

})();
