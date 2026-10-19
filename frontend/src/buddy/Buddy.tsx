import { useCallback, useEffect, useRef, useState } from "react";
import type { AuraState, BuddyBridge, BuddyWork, ConnStatus, Presence } from "../types";
import { GRID, drawBuddy, type Pose } from "./sprite";
import { WIN_H, WIN_W } from "./win";

const WALK_SPEED = 34; // px per second along the taskbar
const SNAP = 90;       // dropped this close to the floor → falls onto it
const SAVE_KEY = "aura.buddy";

interface Saved { x?: number; y?: number; perched?: boolean; wander?: boolean }

function loadSaved(): Saved {
  try {
    return JSON.parse(localStorage.getItem(SAVE_KEY) || "{}") ?? {};
  } catch {
    return {};
  }
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const floorOf = (w: BuddyWork) => w.y + w.height - WIN_H;

/** Squeeze a chat reply into something a speech bubble can hold. */
function bubbleText(raw: string): string {
  const t = raw
    .replace(/```[\s\S]*?(```|$)/g, " [code: open AURA to see it] ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return t.length > 260 ? t.slice(0, 257).trimEnd() + "…" : t;
}

/** Everything the 30 fps loop reads and writes, kept out of React state. */
interface Sim {
  x: number; y: number;          // window top-left, screen DIPs
  work: BuddyWork | null;        // work area of the display it's on
  perched: boolean;              // dropped somewhere off the floor: sits there
  wander: boolean;
  napping: boolean;
  dir: 1 | -1;
  walking: boolean;
  targetX: number;
  nextMoveAt: number;
  sitting: boolean;
  falling: boolean;
  vy: number;
  dragging: boolean;
  blinkAt: number; blinkUntil: number;
  look: -1 | 1; lookUntil: number;
  happyUntil: number;
  landUntil: number;
  aura: AuraState;
  presence: Presence;
  busy: boolean;                 // thinking/speaking, chatting, or showing a bubble
}

const asleep = (s: Sim) => s.napping || (s.presence === "afk" && !s.busy);

function poseFor(s: Sim, now: number): Pose {
  const t = now / 1000;
  const flick = (period: number) => (Math.floor(t / period) % 2) as 0 | 1;
  const sleeping = asleep(s);
  const thinking = s.aura === "thinking" && !sleeping;
  const speaking = s.aura === "speaking";
  const airborne = s.dragging || s.falling;
  const landing = now < s.landUntil;
  const sit = !airborne && !s.walking &&
    (sleeping || s.perched || landing || (s.sitting && !s.busy));
  return {
    feet: airborne ? "dangle" : s.walking ? (flick(0.16) ? "walkA" : "walkB") : sit ? "sit" : "stand",
    eyes: sleeping ? "shut" : airborne ? "wide" : now < s.blinkUntil ? "blink"
      : now < s.happyUntil ? "happy" : "open",
    look: s.walking ? s.dir : thinking ? (flick(1.1) ? 1 : -1) : now < s.lookUntil ? s.look : 0,
    up: thinking,
    mouth: airborne ? "open" : speaking ? (flick(0.14) ? "open" : "small") : "none",
    bob: airborne || landing ? 0 : s.walking ? flick(0.16) : sleeping ? flick(1.4)
      : thinking ? flick(0.3) : flick(0.9),
    flip: s.dir < 0,
    dots: thinking ? 1 + (Math.floor(t / 0.3) % 3) : 0,
    z: sleeping ? Math.floor(t * 4) : -1,
  };
}

/**
 * AURA's desktop body. Strolls along the taskbar edge, naps when you're away,
 * thinks and talks when the brain does. Drag it anywhere (high up, it sits
 * there; near the floor, it drops back down), click it to chat, right-click
 * for its menu. Lives in electron/main.cjs's buddy window.
 */
export default function Buddy({ bridge }: { bridge: BuddyBridge }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [aura, setAura] = useState<AuraState>("idle");
  const [presence, setPresence] = useState<Presence>("idle");
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const [bubble, setBubble] = useState<string | null>(null);
  const [holdBubble, setHoldBubble] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [dragging, setDragging] = useState(false);
  const [cssSize, setCssSize] = useState(100);

  const sim = useRef<Sim>({
    x: 0, y: 0, work: null, perched: false, wander: true, napping: false,
    dir: 1, walking: false, targetX: 0, nextMoveAt: 0, sitting: false,
    falling: false, vy: 0, dragging: false,
    blinkAt: 0, blinkUntil: 0, look: 1, lookUntil: 0, happyUntil: 0, landUntil: 0,
    aura: "idle", presence: "idle", busy: false,
  });
  const chatOpenRef = useRef(chatOpen);
  chatOpenRef.current = chatOpen;

  const busy = aura !== "idle" || chatOpen || bubble !== null;
  useEffect(() => { Object.assign(sim.current, { aura, presence, busy }); }, [aura, presence, busy]);

  const persist = useCallback(() => {
    const s = sim.current;
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify({
        x: Math.round(s.x), y: Math.round(s.y), perched: s.perched, wander: s.wander,
      }));
    } catch { /* storage off: the position just won't stick */ }
  }, []);

  // ---- click-through: only the sprite and bubbles catch the mouse ---------
  const passing = useRef(true);
  const passThrough = useCallback((pass: boolean) => {
    if (passing.current === pass) return;
    passing.current = pass;
    bridge.setIgnoreMouse(pass);
  }, [bridge]);
  useEffect(() => {
    passing.current = true;
    bridge.setIgnoreMouse(true);
    // While ignoring, Electron still forwards mouse moves, so this sees the
    // pointer arrive over the sprite and starts catching clicks.
    const onMove = (e: MouseEvent) => {
      if (sim.current.dragging) return;
      passThrough(!(e.target instanceof Element && e.target.closest(".hit")));
    };
    document.addEventListener("mousemove", onMove);
    return () => document.removeEventListener("mousemove", onMove);
  }, [bridge, passThrough]);

  // ---- chat ---------------------------------------------------------------
  const openChat = useCallback(() => {
    sim.current.napping = false;
    setChatOpen(true);
    bridge.focus();
  }, [bridge]);
  const closeChat = useCallback(() => {
    setChatOpen(false);
    setDraft("");
    setBubble(null);
    setHoldBubble(false);
  }, []);
  useEffect(() => { if (chatOpen) inputRef.current?.focus(); }, [chatOpen]);

  // Click away with nothing typed → the chat box folds up.
  useEffect(() => {
    if (!chatOpen) return;
    const onBlur = () => { if (!draft.trim()) closeChat(); };
    window.addEventListener("blur", onBlur);
    return () => window.removeEventListener("blur", onBlur);
  }, [chatOpen, draft, closeChat]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    if (status !== "open") {
      setBubble("I can't reach my brain right now. Is AURA's server running?");
      return;
    }
    bridge.chat(text);
    setDraft("");
    setBubble(null);
  };

  // Bubbles fade on their own, longer for longer lines; hovering holds one.
  useEffect(() => {
    if (bubble === null || chatOpen || holdBubble) return;
    const t = setTimeout(() => setBubble(null), Math.min(16000, 4500 + bubble.length * 45));
    return () => clearTimeout(t);
  }, [bubble, chatOpen, holdBubble]);

  // ---- what the main window relays ---------------------------------------
  useEffect(() => bridge.onUpdate((m) => {
    if (m.kind === "state") setAura(m.state);
    else if (m.kind === "presence") setPresence(m.presence);
    else if (m.kind === "status") setStatus(m.status);
    else if (m.kind === "say") {
      const text = bubbleText(m.text);
      if (!text) return;
      setBubble(text);
      sim.current.happyUntil = performance.now() + 700;
    }
  }), [bridge]);

  useEffect(() => bridge.onCommand((cmd) => {
    const s = sim.current;
    if (cmd === "chat") openChat();
    else if (cmd === "toggle-wander") { s.wander = !s.wander; s.walking = false; persist(); }
    else if (cmd === "toggle-nap") s.napping = !s.napping;
    else if (cmd === "hidden") { passing.current = true; closeChat(); }
  }), [bridge, openChat, closeChat, persist]);

  // ---- the loop: wander, fall, animate ------------------------------------
  useEffect(() => {
    const cv = canvasRef.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const cell = Math.max(1, Math.round(5 * dpr)); // device px per sprite pixel
    cv.width = cv.height = GRID * cell;
    setCssSize((GRID * cell) / dpr);

    const s = sim.current;
    const saved = loadSaved();
    s.wander = saved.wander ?? true;
    let alive = true;
    bridge.place(saved.x, saved.y).then((p) => {
      if (!alive || !p) return;
      s.x = p.x; s.y = p.y; s.work = p.work;
      s.perched = !!saved.perched && floorOf(p.work) - p.y > SNAP;
      s.nextMoveAt = performance.now() + rand(2000, 5000);
    });

    const pickTarget = () => {
      s.nextMoveAt = Infinity; // until the display check answers
      bridge.geom().then((w) => {
        if (!alive) return;
        if (w) s.work = w;
        const work = s.work!;
        const lo = work.x, hi = work.x + work.width - WIN_W;
        const span = rand(80, 380) * (Math.random() < 0.5 ? -1 : 1);
        const tx = s.x + span < lo || s.x + span > hi ? s.x - span : s.x + span;
        s.targetX = Math.min(hi, Math.max(lo, tx));
        s.dir = s.targetX >= s.x ? 1 : -1;
        s.sitting = false;
        s.walking = Math.abs(s.targetX - s.x) > 4;
        s.nextMoveAt = s.walking ? 0 : performance.now() + 3000;
      });
    };

    const tick = (now: number, dt: number) => {
      if (!s.work || s.dragging) return;
      if (now > s.blinkAt) { s.blinkUntil = now + 140; s.blinkAt = now + rand(2500, 6500); }

      // Off the floor and not perched (just dropped, or the taskbar moved): fall.
      const floor = floorOf(s.work);
      if (!s.perched && !s.falling && s.y !== floor) {
        if (s.y < floor) { s.falling = true; s.vy = 0; }
        else { s.y = floor; bridge.move(s.x, s.y); }
      }
      if (s.falling) {
        s.vy = Math.min(1600, s.vy + 2800 * dt);
        s.y = Math.min(floor, s.y + s.vy * dt);
        if (s.y >= floor) { s.falling = false; s.landUntil = now + 260; persist(); }
        bridge.move(s.x, s.y);
        return;
      }

      if (s.perched || s.busy || !s.wander || asleep(s)) { s.walking = false; return; }
      if (s.walking) {
        const dx = s.targetX - s.x, step = WALK_SPEED * dt;
        if (Math.abs(dx) <= step) {
          s.x = s.targetX;
          s.walking = false;
          s.sitting = Math.random() < 0.35;
          s.nextMoveAt = now + rand(4000, 11000);
          persist();
        } else {
          s.x += Math.sign(dx) * step;
        }
        bridge.move(s.x, s.y);
        return;
      }
      // Standing around: glance about now and then, then stroll somewhere.
      if (now > s.lookUntil + 1500 && Math.random() < dt * 0.3) {
        s.look = Math.random() < 0.5 ? -1 : 1;
        s.lookUntil = now + rand(700, 1600);
      }
      if (now > s.nextMoveAt) pickTarget();
    };

    let last = performance.now();
    let lastKey = "";
    const id = window.setInterval(() => {
      const now = performance.now();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      tick(now, dt);
      const pose = poseFor(s, now);
      const key = JSON.stringify(pose); // redraw only when the frame changes
      if (key !== lastKey) { lastKey = key; drawBuddy(ctx, pose, cell); }
    }, 33);
    return () => { alive = false; clearInterval(id); };
  }, [bridge, persist]);

  // ---- drag / click / right-click ----------------------------------------
  const drag = useRef<{ sx: number; sy: number; wx: number; wy: number; moved: boolean } | null>(null);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const s = sim.current;
    drag.current = { sx: e.screenX, sy: e.screenY, wx: s.x, wy: s.y, moved: false };
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.screenX - d.sx, dy = e.screenY - d.sy;
    const s = sim.current;
    if (!d.moved) {
      if (Math.hypot(dx, dy) < 4) return;
      d.moved = true;
      Object.assign(s, { dragging: true, walking: false, falling: false, sitting: false, napping: false });
      setDragging(true);
    }
    s.x = d.wx + dx;
    s.y = d.wy + dy;
    bridge.move(s.x, s.y);
  };

  const endDrag = (asClick: boolean) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (!d.moved) {
      if (asClick) (chatOpenRef.current ? closeChat : openChat)();
      return;
    }
    const s = sim.current;
    setDragging(false);
    bridge.place(s.x, s.y).then((p) => {
      s.dragging = false;
      if (!p) return;
      s.x = p.x; s.y = p.y; s.work = p.work;
      // Dropped up high, it sits right there; near the floor, the loop drops it.
      s.perched = floorOf(p.work) - p.y > SNAP;
      s.vy = 0;
      if (s.perched) s.landUntil = performance.now() + 260;
      s.nextMoveAt = performance.now() + rand(3000, 6000);
      persist();
    });
  };

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    bridge.menu({ wander: sim.current.wander, napping: sim.current.napping });
  };

  return (
    <div className={"buddy" + (dragging ? " buddy--dragging" : "")}>
      {chatOpen ? (
        <div className="bubble bubble--chat hit">
          {(bubble !== null || aura === "thinking") && (
            <div className={"bubble__text" + (bubble === null ? " bubble__text--muted" : "")}>
              {bubble ?? "thinking…"}
            </div>
          )}
          <form className="chat" onSubmit={submit}>
            <input
              ref={inputRef}
              className="chat__input"
              value={draft}
              maxLength={2000}
              placeholder="Ask AURA…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") closeChat(); }}
            />
            <button type="button" className="chat__btn" title="Open AURA" onClick={() => bridge.openMain()}>
              ↗
            </button>
          </form>
        </div>
      ) : bubble !== null && (
        <div
          className="bubble bubble--say hit"
          title="Open AURA"
          onClick={() => bridge.openMain()}
          onMouseEnter={() => setHoldBubble(true)}
          onMouseLeave={() => setHoldBubble(false)}
        >
          <div className="bubble__text">{bubble}</div>
        </div>
      )}

      <div className="buddy__body" style={{ width: cssSize, height: cssSize }}>
        <canvas ref={canvasRef} className="buddy__canvas" />
        <div
          className="buddy__hit hit"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={() => endDrag(true)}
          onPointerCancel={() => endDrag(false)}
          onContextMenu={onContextMenu}
        />
      </div>
    </div>
  );
}
