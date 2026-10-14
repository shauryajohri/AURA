import { downsample, encodeWavBase64 } from "../hooks/useVoiceInput";

/**
 * Record one short clip from the mic as a 16 kHz WAV (base64). Used for voice
 * enrollment and the lock screen's "use my voice".
 *
 * Same getUserMedia constraints as useVoiceInput on purpose: echo
 * cancellation and noise suppression colour the signal, and a voice enrolled
 * through one chain and checked through another scores lower.
 */
export async function recordClip(
  ms: number,
  onLevel?: (level: number) => void,
): Promise<string> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const Ctx: typeof AudioContext =
    (window as any).AudioContext || (window as any).webkitAudioContext;
  const ctx = new Ctx();
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const sink = ctx.createGain();
  sink.gain.value = 0; // ScriptProcessor only ticks when connected — but silently
  const chunks: Float32Array[] = [];

  proc.onaudioprocess = (ev) => {
    const input = ev.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(input));
    if (onLevel) {
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      onLevel(Math.min(1, Math.sqrt(sum / input.length) * 3.2));
    }
  };
  source.connect(proc);
  proc.connect(sink);
  sink.connect(ctx.destination);

  try {
    await new Promise((r) => setTimeout(r, ms));
  } finally {
    proc.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    onLevel?.(0);
  }
  const rate = ctx.sampleRate;
  await ctx.close().catch(() => undefined);

  const merged = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let off = 0;
  for (const c of chunks) { merged.set(c, off); off += c.length; }
  return encodeWavBase64(downsample(merged, rate, 16000), 16000);
}
