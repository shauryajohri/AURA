import { useEffect, useRef, useState } from "react";
import { guardApi } from "../../guardApi";
import { useGuardStore } from "../../stores/guardStore";
import { cameraError, cameraStream, startCamera } from "../../guard/camera";
import { recordClip } from "../../guard/recorder";

/**
 * Shown whenever Buddy Lock says nobody AURA knows is here — at launch until
 * the owner's face appears, and again after they've been away a while.
 *
 * It mostly just watches: the presence loop is already sending frames, and
 * the moment the owner is seen the brain flips the role and this disappears.
 * The PIN and "use my voice" are for when the camera can't help.
 */
export default function LockScreen() {
  const status = useGuardStore((s) => s.status);
  const seen = useGuardStore((s) => s.seen);
  const camera = useGuardStore((s) => s.camera);
  const apply = useGuardStore((s) => s.apply);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState<"" | "pin" | "voice">("");
  const [level, setLevel] = useState(0);
  const [msg, setMsg] = useState("");

  const owner = status?.owner_name || "my buddy";
  const hasVoice = (status?.vault.voice_samples ?? 0) > 0;
  const corrupt = !!status?.vault.corrupt;

  // Ask for the camera once on mount — not on every camera-state change, or
  // each failure (starting → error) would immediately ask again.
  useEffect(() => { void startCamera(); }, []);

  // Mirror the shared stream into the visible preview.
  useEffect(() => {
    const v = videoRef.current;
    if (v && camera === "on") {
      v.srcObject = cameraStream();
      void v.play().catch(() => undefined);
    }
  }, [camera]);

  const unlockPin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pin) return;
    setBusy("pin");
    setMsg("");
    try {
      const r = await guardApi.unlockPin(pin);
      if (r.ok) apply(r.status);
      else setMsg(r.error || "That didn't work.");
    } catch {
      setMsg("Can't reach AURA's brain.");
    } finally {
      setPin("");
      setBusy("");
    }
  };

  const unlockVoice = async () => {
    setBusy("voice");
    setMsg("Say a full sentence…");
    try {
      const clip = await recordClip(3500, setLevel);
      setMsg("Listening back…");
      const r = await guardApi.unlockVoice(clip);
      if (r.ok) { apply(r.status); setMsg(""); }
      else setMsg(r.error || "That didn't sound like you.");
    } catch {
      setMsg("Couldn't use the microphone.");
    } finally {
      setBusy("");
    }
  };

  let line: string;
  if (corrupt) {
    line = "Buddy Lock's data file is damaged. Delete memory/guard/buddy.json on this machine to set it up again.";
  } else if (camera === "denied" || camera === "error") {
    line = `${cameraError() || "The camera isn't available."} Use your PIN${hasVoice ? " or your voice" : ""} instead.`;
  } else if (seen?.error || status?.camera_error) {
    line = `I can't check faces right now (${seen?.error || status?.camera_error}). Use your PIN.`;
  } else if (camera !== "on" || seen == null) {
    line = "Opening my eyes…";
  } else if (!seen.faces) {
    line = "I don't see anyone yet — sit where the camera can see you.";
  } else {
    line = `I don't recognise you. I only open up for ${owner}.`;
  }

  return (
    <div className="lock" role="dialog" aria-modal="true" aria-label="AURA is locked">
      <div className="lock__card">
        <div className={"lock__eye" + (camera === "on" ? " lock__eye--on" : "")}>
          <video ref={videoRef} muted playsInline className="lock__video" />
          <span className="lock__ring" />
        </div>

        <h1 className="lock__title">AURA</h1>
        <p className="lock__hello">Hey — is that you, {owner}?</p>
        <p className="lock__line" aria-live="polite">{line}</p>

        <form className="lock__pin" onSubmit={unlockPin}>
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            placeholder="PIN"
            value={pin}
            maxLength={12}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            disabled={!!busy || corrupt}
            aria-label="Backup PIN"
          />
          <button type="submit" disabled={!pin || !!busy}>Unlock</button>
        </form>

        {hasVoice && (
          <button className="lock__voice" onClick={unlockVoice} disabled={!!busy}>
            <span>{"🎙"}</span>
            {busy === "voice" ? "Listening…" : "Use my voice"}
            {busy === "voice" && (
              <span className="lock__meter" style={{ "--lvl": level } as React.CSSProperties} />
            )}
          </button>
        )}

        {(camera === "denied" || camera === "error") && !corrupt && (
          <button className="lock__voice" onClick={() => void startCamera(true)} disabled={!!busy}>
            Try the camera again
          </button>
        )}

        {msg && <p className="lock__msg">{msg}</p>}
        <p className="lock__fine">Frames are checked on this machine and never saved.</p>
      </div>
    </div>
  );
}
