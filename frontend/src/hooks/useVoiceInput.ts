import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

/**
 * Always-listening voice input for AURA.
 *
 * Two engines, one interface:
 *   1. Web Speech API  — the browser/Electron's own recognizer. Free, instant,
 *      streams interim text as you speak. Preferred whenever it exists.
 *   2. Backend fallback — captures raw PCM, encodes a WAV in the browser and
 *      POSTs it to /api/voice/transcribe (speech_recognition on the Python
 *      side). Used when Web Speech is missing or its network path dies.
 *
 * WAV is encoded here on purpose: speech_recognition reads WAV natively, so
 * the backend needs no ffmpeg/pydub to decode a webm/opus blob.
 *
 * The mic stream is opened ONCE and shared: the recognizer listens to it and
 * an AnalyserNode reads RMS off the same stream, so the level meter is real
 * regardless of which engine is transcribing.
 */

// ── tuning ──────────────────────────────────────────────────────────────────
const TARGET_RATE = 16000;   // what speech_recognition likes
const SILENCE_RMS = 0.012;   // below this counts as "not talking"
const SILENCE_MS = 900;      // hold that long to end an utterance
const MIN_UTTER_MS = 350;    // ignore blips shorter than this
const MAX_UTTER_MS = 15000;  // hard cut so one long ramble still gets sent

export type VoiceEngine = "webspeech" | "backend" | "none";

export interface VoiceInput {
  /** Mic is open and we're actively transcribing. */
  listening: boolean;
  /** Words heard but not yet finalised — render these greyed in the composer. */
  interim: string;
  /** Live mic loudness, 0..1. Drives meters and the glow. */
  level: number;
  /** Which engine is actually doing the work right now. */
  engine: VoiceEngine;
  /** Human-readable problem, or "" when healthy. */
  error: string;
  /** Mic permission as last observed. */
  permission: "unknown" | "granted" | "denied";
  /** True while an utterance is being transcribed by the backend. */
  transcribing: boolean;
  start: () => void;
  stop: () => void;
  toggle: () => void;
}

interface Options {
  /** Called with each finished sentence. This is what gets sent to AURA. */
  onFinal: (text: string) => void;
  /**
   * Freeze capture without dropping the mic — used while AURA is speaking so
   * she never transcribes her own voice back into the chat.
   */
  muted?: boolean;
}

// ── WAV encoding (fallback path) ────────────────────────────────────────────

/** Naive but adequate linear resample down to TARGET_RATE. */
function downsample(input: Float32Array, from: number, to: number): Float32Array {
  if (to >= from) return input;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

/** Float32 mono → 16-bit PCM WAV → base64 (no data: prefix). */
function encodeWavBase64(samples: Float32Array, rate: number): string {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const str = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };

  str(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  view.setUint32(16, 16, true);       // PCM chunk size
  view.setUint16(20, 1, true);        // format = PCM
  view.setUint16(22, 1, true);        // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // byte rate
  view.setUint16(32, 2, true);        // block align
  view.setUint16(34, 16, true);       // bits per sample
  str(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  // Chunked so a long utterance can't blow the argument limit on fromCharCode.
  const bytes = new Uint8Array(buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

// ── hook ────────────────────────────────────────────────────────────────────

export function useVoiceInput({ onFinal, muted = false }: Options): VoiceInput {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [level, setLevel] = useState(0);
  const [engine, setEngine] = useState<VoiceEngine>("none");
  const [error, setError] = useState("");
  const [permission, setPermission] = useState<"unknown" | "granted" | "denied">("unknown");
  const [transcribing, setTranscribing] = useState(false);

  // Everything the audio graph needs, kept off React state so the rAF meter
  // loop and the recognizer callbacks never trigger re-renders.
  const activeRef = useRef(false);
  const mutedRef = useRef(muted);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const rafRef = useRef(0);
  const recogRef = useRef<any>(null);
  const onFinalRef = useRef(onFinal);

  // Fallback capture state
  const chunksRef = useRef<Float32Array[]>([]);
  const speakingRef = useRef(false);
  const silenceSinceRef = useRef(0);
  const utterStartRef = useRef(0);

  // Dedupe: Chrome occasionally repeats a final result verbatim.
  const lastSentRef = useRef("");
  const lastSentAtRef = useRef(0);

  useEffect(() => { onFinalRef.current = onFinal; }, [onFinal]);
  useEffect(() => { mutedRef.current = muted; }, [muted]);

  const emit = useCallback((text: string) => {
    const t = text.trim();
    if (!t) return;
    const now = Date.now();
    if (t === lastSentRef.current && now - lastSentAtRef.current < 2500) return;
    lastSentRef.current = t;
    lastSentAtRef.current = now;
    setInterim("");
    onFinalRef.current(t);
  }, []);

  // ── fallback: ship one utterance to the backend ───────────────────────────
  const flushUtterance = useCallback(async () => {
    const chunks = chunksRef.current;
    chunksRef.current = [];
    speakingRef.current = false;
    if (!chunks.length) return;

    const total = chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(total);
    let off = 0;
    for (const c of chunks) { merged.set(c, off); off += c.length; }

    const rate = ctxRef.current?.sampleRate ?? 44100;
    if ((merged.length / rate) * 1000 < MIN_UTTER_MS) return;

    setTranscribing(true);
    try {
      const b64 = encodeWavBase64(downsample(merged, rate, TARGET_RATE), TARGET_RATE);
      const res = await api.transcribe(b64);
      if (res.text) emit(res.text);
      else if (res.error) setError(res.error);
      else setError("");
    } catch {
      setError("Brain offline — can't transcribe. Start server.py.");
    } finally {
      setTranscribing(false);
    }
  }, [emit]);

  // ── teardown ──────────────────────────────────────────────────────────────
  const teardown = useCallback(() => {
    activeRef.current = false;
    cancelAnimationFrame(rafRef.current);

    try { recogRef.current?.abort?.(); } catch { /* already dead */ }
    recogRef.current = null;

    try { procRef.current?.disconnect(); } catch { /* noop */ }
    procRef.current = null;
    analyserRef.current = null;

    try { ctxRef.current?.close(); } catch { /* noop */ }
    ctxRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    chunksRef.current = [];
    speakingRef.current = false;
    setLevel(0);
    setInterim("");
    setListening(false);
    setEngine("none");
  }, []);

  // ── start ─────────────────────────────────────────────────────────────────
  const start = useCallback(async () => {
    if (activeRef.current) return;
    activeRef.current = true;
    setError("");

    // 1. Mic + shared audio graph (both engines read from this).
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      activeRef.current = false;
      setPermission("denied");
      setError("Microphone blocked. Allow mic access and try again.");
      return;
    }
    if (!activeRef.current) { stream.getTracks().forEach((t) => t.stop()); return; }

    setPermission("granted");
    streamRef.current = stream;

    const Ctx: typeof AudioContext =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctx();
    ctxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.75;
    source.connect(analyser);
    analyserRef.current = analyser;

    // 2. Pick the engine.
    const SR: any =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const useWebSpeech = typeof SR === "function";
    setEngine(useWebSpeech ? "webspeech" : "backend");
    setListening(true);

    if (useWebSpeech) {
      const recog = new SR();
      recog.continuous = true;
      recog.interimResults = true;
      recog.lang = "en-US";

      recog.onresult = (ev: any) => {
        if (mutedRef.current) return;
        let live = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i];
          if (r.isFinal) emit(r[0].transcript);
          else live += r[0].transcript;
        }
        setInterim(live);
      };

      recog.onerror = (ev: any) => {
        const err = ev?.error;
        if (err === "not-allowed" || err === "service-not-allowed") {
          setPermission("denied");
          setError("Microphone blocked. Allow mic access and try again.");
          teardown();
          return;
        }
        if (err === "network") {
          // Browser recognizer can't reach its service — hand over to Python.
          setEngine("backend");
          setError("");
          try { recog.abort(); } catch { /* noop */ }
          recogRef.current = null;
        }
        // "no-speech" / "aborted" are normal in always-on mode: onend restarts.
      };

      // Chrome ends the session on its own after a silence; in always-listening
      // mode that's not a stop, it's a hiccup — start it straight back up.
      recog.onend = () => {
        if (!activeRef.current || recogRef.current !== recog) return;
        try { recog.start(); } catch { /* already restarting */ }
      };

      recogRef.current = recog;
      try { recog.start(); } catch { /* fires onerror if it can't */ }
    }

    // 3. Fallback capture — only records when Web Speech isn't the active
    //    engine, but the node is always wired so a mid-session switch to
    //    "backend" needs no re-plumbing.
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (ev) => {
      if (!activeRef.current) return;
      if (recogRef.current || mutedRef.current) return; // Web Speech owns it

      const input = ev.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);
      const now = performance.now();

      if (rms > SILENCE_RMS) {
        if (!speakingRef.current) { speakingRef.current = true; utterStartRef.current = now; }
        silenceSinceRef.current = 0;
        chunksRef.current.push(new Float32Array(input));
      } else if (speakingRef.current) {
        chunksRef.current.push(new Float32Array(input)); // keep the tail
        if (!silenceSinceRef.current) silenceSinceRef.current = now;
        if (now - silenceSinceRef.current > SILENCE_MS) {
          silenceSinceRef.current = 0;
          void flushUtterance();
        }
      }

      if (speakingRef.current && now - utterStartRef.current > MAX_UTTER_MS) {
        silenceSinceRef.current = 0;
        void flushUtterance();
      }
    };
    source.connect(proc);
    // Zero-gain sink: ScriptProcessor only ticks when connected to the
    // destination, but we must not play the mic back through the speakers.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    proc.connect(mute);
    mute.connect(ctx.destination);
    procRef.current = proc;

    // 4. Level meter — one rAF loop for the whole session.
    const bins = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      if (!activeRef.current || !analyserRef.current) return;
      rafRef.current = requestAnimationFrame(tick);
      analyserRef.current.getByteTimeDomainData(bins);
      let sum = 0;
      for (let i = 0; i < bins.length; i++) {
        const v = (bins[i] - 128) / 128;
        sum += v * v;
      }
      // ×3.2 so normal speech fills most of the meter instead of a stub.
      setLevel(Math.min(1, Math.sqrt(sum / bins.length) * 3.2));
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [emit, flushUtterance, teardown]);

  const stop = useCallback(() => { teardown(); }, [teardown]);
  const toggle = useCallback(() => {
    if (activeRef.current) teardown();
    else void start();
  }, [start, teardown]);

  // Drop the interim line the moment we're muted, so a half-heard fragment
  // doesn't sit frozen in the composer while AURA talks.
  useEffect(() => { if (muted) setInterim(""); }, [muted]);

  useEffect(() => () => teardown(), [teardown]);

  return {
    listening, interim, level, engine, error, permission, transcribing,
    start: () => void start(),
    stop,
    toggle,
  };
}
