/**
 * Interface sounds — synthesized on the fly with Web Audio, so there are no
 * files to ship and every sound can be tuned in code. All of them sit well
 * under AURA's voice; they are texture, not alerts.
 *
 * Off switch: Settings → This device → "Interface sounds". Default on.
 */

import { usePrefs } from "../stores/prefsStore";

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let lastTick = 0;

const sfxEnabled = () => usePrefs.getState().sfx;

function audio(): AudioContext | null {
  if (!sfxEnabled()) return null;
  if (!ctx) {
    try {
      ctx = new AudioContext();
      master = ctx.createGain();
      master.gain.value = 0.9;
      master.connect(ctx.destination);
    } catch { return null; }
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

// Browsers keep audio locked until the first gesture; unlock on it.
if (typeof window !== "undefined") {
  const unlock = () => { if (ctx?.state === "suspended") void ctx.resume(); };
  window.addEventListener("pointerdown", unlock, { passive: true });
  window.addEventListener("keydown", unlock, { passive: true });
}

function tone(freq: number, dur: number, gain: number, type: OscillatorType = "sine", to?: number, delay = 0) {
  const a = audio();
  if (!a || !master) return;
  const t = a.currentTime + delay;
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t);
  if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + Math.min(0.012, dur / 4));
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(master);
  o.start(t);
  o.stop(t + dur + 0.02);
}

function noise(dur: number, gain: number, from: number, to: number, q = 1.2) {
  const a = audio();
  if (!a || !master) return;
  const t = a.currentTime;
  const len = Math.ceil(a.sampleRate * dur);
  const buf = a.createBuffer(1, len, a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const src = a.createBufferSource();
  src.buffer = buf;
  const f = a.createBiquadFilter();
  f.type = "bandpass";
  f.Q.value = q;
  f.frequency.setValueAtTime(from, t);
  f.frequency.exponentialRampToValueAtTime(to, t + dur);
  const g = a.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + dur * 0.25);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(f).connect(g).connect(master);
  src.start(t);
}

export const sfx = {
  /** Pointer lands on something clickable. */
  hover() {
    const now = performance.now();
    if (now - lastTick < 60) return;
    lastTick = now;
    tone(2100, 0.035, 0.006);
  },
  /** A click. */
  tap() { tone(560, 0.09, 0.022, "triangle", 360); },
  /** A keystroke in the composer — pitch wanders so it never drones. */
  key() { tone(900 + Math.random() * 500, 0.03, 0.004); },
  /** A message leaves: air rushing toward the core. */
  send() {
    noise(0.55, 0.05, 2600, 180);
    tone(190, 0.5, 0.03, "sine", 55);
  },
  /** A reply starts arriving. */
  chime() {
    tone(660, 1.1, 0.014);
    tone(990, 1.3, 0.01, "sine", undefined, 0.07);
  },
  /** The core is struck. */
  shock() {
    tone(80, 0.7, 0.05, "sine", 32);
    noise(0.4, 0.025, 900, 90, 0.8);
  },
  /** The startup swell. */
  boot() {
    tone(55, 3.2, 0.035, "sine", 110);
    tone(220, 2.6, 0.008, "sine", 440, 1.2);
    tone(660, 2.2, 0.006, "sine", 990, 2.2);
  },
};
