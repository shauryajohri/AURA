import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Microphone diagnostic. Answers four questions, in order of how often they're
 * the actual problem: is a mic there, is it allowed, is it hearing you, and is
 * the room quiet enough for AURA to make sense of it.
 *
 * Two shapes:
 *   variant="full"    — settings. Meter + noise verdict + record & play back.
 *   variant="compact" — the strip shown in chat the first time you hit the mic.
 *
 * Independent of useVoiceInput on purpose: this has to work *before* voice
 * mode is trusted, including when the recognizer itself is the broken part.
 */

const BARS = 24;
const NOISE_SAMPLE_MS = 1200;   // how long the quiet reading takes
const MAX_RECORD_MS = 5000;

interface Props {
  variant?: "full" | "compact";
  /** Compact strip only: "looks good, go live". */
  onReady?: () => void;
  /** Compact strip only: dismiss without starting. */
  onDismiss?: () => void;
}

type Phase = "idle" | "checking" | "live" | "recording" | "playing";

export default function MicCheck({ variant = "full", onReady, onDismiss }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [noiseFloor, setNoiseFloor] = useState<number | null>(null);
  const [heardVoice, setHeardVoice] = useState(false);
  const [deviceLabel, setDeviceLabel] = useState("");
  const [recordMs, setRecordMs] = useState(0);
  const [hasClip, setHasClip] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const clipUrlRef = useRef("");
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const noiseSamplesRef = useRef<number[]>([]);
  const noiseUntilRef = useRef(0);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    if (stopTimerRef.current) { clearTimeout(stopTimerRef.current); stopTimerRef.current = null; }
    try { recorderRef.current?.state === "recording" && recorderRef.current.stop(); } catch { /* noop */ }
    recorderRef.current = null;
    try { ctxRef.current?.close(); } catch { /* noop */ }
    ctxRef.current = null;
    analyserRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setLevel(0);
  }, []);

  useEffect(() => () => {
    cleanup();
    if (clipUrlRef.current) URL.revokeObjectURL(clipUrlRef.current);
  }, [cleanup]);

  // ── open the mic and start metering ───────────────────────────────────────
  const startCheck = useCallback(async () => {
    setError("");
    setHeardVoice(false);
    setPeak(0);
    setNoiseFloor(null);
    setPhase("checking");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e: any) {
      setPhase("idle");
      setError(
        e?.name === "NotFoundError"
          ? "No microphone found. Plug one in, then check again."
          : "Microphone blocked. Allow mic access for AURA and check again.",
      );
      return;
    }

    streamRef.current = stream;
    setDeviceLabel(stream.getAudioTracks()[0]?.label || "Default microphone");

    const Ctx: typeof AudioContext =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctx();
    ctxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.7;
    ctx.createMediaStreamSource(stream).connect(analyser);
    analyserRef.current = analyser;

    // First stretch is the quiet reading — the user hasn't started talking yet,
    // so whatever we hear now is the room.
    noiseSamplesRef.current = [];
    noiseUntilRef.current = performance.now() + NOISE_SAMPLE_MS;

    const bins = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      const a = analyserRef.current;
      if (!a) return;
      rafRef.current = requestAnimationFrame(tick);
      a.getByteTimeDomainData(bins);
      let sum = 0;
      for (let i = 0; i < bins.length; i++) {
        const v = (bins[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.min(1, Math.sqrt(sum / bins.length) * 3.2);
      setLevel(rms);
      setPeak((p) => Math.max(p * 0.995, rms));

      const now = performance.now();
      if (now < noiseUntilRef.current) {
        noiseSamplesRef.current.push(rms);
      } else if (noiseSamplesRef.current.length) {
        const s = noiseSamplesRef.current;
        setNoiseFloor(s.reduce((x, y) => x + y, 0) / s.length);
        noiseSamplesRef.current = [];
        setPhase((p) => (p === "checking" ? "live" : p));
      }
      if (rms > 0.18) setHeardVoice(true);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const stopCheck = useCallback(() => {
    cleanup();
    setPhase("idle");
  }, [cleanup]);

  // ── test recording ────────────────────────────────────────────────────────
  const startRecording = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    if (clipUrlRef.current) { URL.revokeObjectURL(clipUrlRef.current); clipUrlRef.current = ""; }
    setHasClip(false);
    setRecordMs(0);

    let rec: MediaRecorder;
    try {
      rec = new MediaRecorder(stream);
    } catch {
      setError("This browser can't record audio for playback.");
      return;
    }
    const parts: BlobPart[] = [];
    rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
    rec.onstop = () => {
      const blob = new Blob(parts, { type: rec.mimeType || "audio/webm" });
      clipUrlRef.current = URL.createObjectURL(blob);
      setHasClip(true);
      setPhase("live");
    };

    recorderRef.current = rec;
    rec.start();
    setPhase("recording");

    const startedAt = performance.now();
    const poll = () => {
      if (recorderRef.current?.state !== "recording") return;
      setRecordMs(performance.now() - startedAt);
      stopTimerRef.current = setTimeout(poll, 100);
    };
    poll();
    setTimeout(() => {
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    }, MAX_RECORD_MS);
  }, []);

  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const playClip = useCallback(() => {
    if (!clipUrlRef.current) return;
    const el = audioElRef.current ?? new Audio();
    audioElRef.current = el;
    el.src = clipUrlRef.current;
    el.onended = () => setPhase("live");
    setPhase("playing");
    el.play().catch(() => setPhase("live"));
  }, []);

  // ── verdict ───────────────────────────────────────────────────────────────
  const verdict = (): { tone: "good" | "warn" | "bad"; text: string } => {
    if (error) return { tone: "bad", text: error };
    if (phase === "idle") return { tone: "warn", text: "Not checked yet." };
    if (phase === "checking") return { tone: "warn", text: "Reading the room — stay quiet a moment…" };
    if (noiseFloor !== null && noiseFloor > 0.16) {
      return { tone: "warn", text: "Background noise is high — AURA may mishear you." };
    }
    if (!heardVoice) return { tone: "warn", text: "Mic is open. Say something to test it." };
    return { tone: "good", text: "Sounds good — AURA can hear you clearly." };
  };

  const v = verdict();
  const active = phase !== "idle";
  const bars = Array.from({ length: BARS }, (_, i) => {
    const threshold = (i + 1) / BARS;
    const on = level >= threshold * 0.92;
    const tone = threshold > 0.8 ? "hot" : threshold > 0.45 ? "mid" : "low";
    return { on, tone, key: i };
  });

  const meter = (
    <div className={"miccheck__meter" + (active ? " miccheck__meter--on" : "")}>
      {bars.map((b) => (
        <span key={b.key} className={"miccheck__bar miccheck__bar--" + b.tone + (b.on ? " is-on" : "")} />
      ))}
      {peak > 0.02 && (
        <span className="miccheck__peak" style={{ left: `${Math.min(99, peak * 100)}%` }} />
      )}
    </div>
  );

  if (variant === "compact") {
    return (
      <div className="miccheck miccheck--compact">
        <div className="miccheck__row">
          <span className="miccheck__title">Quick mic check</span>
          <span className={"miccheck__verdict miccheck__verdict--" + v.tone}>{v.text}</span>
        </div>
        {meter}
        <div className="miccheck__actions">
          {!active ? (
            <button className="miccheck__btn miccheck__btn--primary" onClick={startCheck}>
              Check mic
            </button>
          ) : (
            <button
              className="miccheck__btn miccheck__btn--primary"
              onClick={() => { stopCheck(); onReady?.(); }}
            >
              Start talking
            </button>
          )}
          <button className="miccheck__btn" onClick={() => { stopCheck(); onDismiss?.(); }}>
            Skip
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="miccheck">
      <div className="miccheck__row">
        <span className="miccheck__title">Microphone</span>
        <span className={"miccheck__verdict miccheck__verdict--" + v.tone}>{v.text}</span>
      </div>

      {meter}

      <div className="miccheck__stats">
        <span title="The device currently feeding AURA">
          {active ? deviceLabel : "—"}
        </span>
        <span title="How loud the room is when you're not speaking">
          Room: {noiseFloor === null ? "—" : `${Math.round(noiseFloor * 100)}%`}
        </span>
        <span title="Loudest level seen this session">
          Peak: {Math.round(peak * 100)}%
        </span>
      </div>

      <div className="miccheck__actions">
        {!active ? (
          <button className="miccheck__btn miccheck__btn--primary" onClick={startCheck}>
            Check mic
          </button>
        ) : (
          <button className="miccheck__btn" onClick={stopCheck}>Stop</button>
        )}

        {phase === "recording" ? (
          <button className="miccheck__btn miccheck__btn--rec" onClick={stopRecording}>
            Stop recording · {(recordMs / 1000).toFixed(1)}s
          </button>
        ) : (
          <button
            className="miccheck__btn"
            onClick={startRecording}
            disabled={!active || phase === "playing"}
            title={active ? "Record up to 5s and play it back" : "Check the mic first"}
          >
            Record test
          </button>
        )}

        <button
          className="miccheck__btn"
          onClick={playClip}
          disabled={!hasClip || phase === "recording" || phase === "playing"}
        >
          {phase === "playing" ? "Playing…" : "Play back"}
        </button>
      </div>
    </div>
  );
}
