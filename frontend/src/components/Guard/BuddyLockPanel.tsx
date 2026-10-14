import { useEffect, useRef, useState } from "react";
import { guardApi, type GuardResult, type Proof } from "../../guardApi";
import { useGuardStore } from "../../stores/guardStore";
import { cameraReady, cameraStream, grabFrame } from "../../guard/camera";
import { recordClip } from "../../guard/recorder";
import "./guard.css";

/**
 * Settings → Security → Buddy Lock.
 *
 * Off: a short setup — name, face, (optional) voice, backup PIN — then on.
 * On:  guest passes, re-enrolling, PIN, and switching it off. Anything that
 *      weakens the lock sends a fresh camera frame as proof; the PIN field is
 *      the fallback when the camera can't vouch for you.
 */

type Step = "intro" | "face" | "voice" | "pin";

const POSES = [
  "Look straight at the camera",
  "Turn a little to your left",
  "Now a little to your right",
  "Tilt your chin up slightly",
  "Natural — like you're reading the screen",
];

const LINES = [
  "Hey AURA, it's me — let's get some real work done today.",
  "The quick brown fox jumps over the lazy dog by the riverbank.",
  "I'm teaching you my voice, so you always know it's really me.",
];

const CLIP_MS = 4500;

function Preview() {
  const ref = useRef<HTMLVideoElement>(null);
  const camera = useGuardStore((s) => s.camera);
  useEffect(() => {
    const v = ref.current;
    if (v && camera === "on") {
      v.srcObject = cameraStream();
      void v.play().catch(() => undefined);
    }
  }, [camera]);
  return (
    <div className="bl__preview">
      <video ref={ref} muted playsInline />
      {camera !== "on" && <span className="bl__previewnote">{camera === "starting" ? "Starting camera…" : "Camera off"}</span>}
    </div>
  );
}

export default function BuddyLockPanel() {
  const status = useGuardStore((s) => s.status);
  const offline = useGuardStore((s) => s.offline);
  const apply = useGuardStore((s) => s.apply);
  const holdCamera = useGuardStore((s) => s.holdCamera);

  const [step, setStep] = useState<Step | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [voiceReady, setVoiceReady] = useState(false);
  const [pose, setPose] = useState("");
  const [clips, setClips] = useState<string[]>([]);
  const [recIdx, setRecIdx] = useState(-1);
  const [level, setLevel] = useState(0);
  const [pin1, setPin1] = useState("");
  const [pin2, setPin2] = useState("");
  const [proofPin, setProofPin] = useState("");
  const [guestMin, setGuestMin] = useState(30);
  const [changingPin, setChangingPin] = useState(false);

  useEffect(() => {
    if (status && !name) setName(status.owner_name || "");
  }, [status, name]);

  // The wizard needs the camera even though the lock isn't on yet.
  useEffect(() => {
    if (!step || step === "intro") return;
    return holdCamera();
  }, [step, holdCamera]);

  if (offline && !status) return <p className="bl__note">Brain offline — start server.py to set up Buddy Lock.</p>;
  if (!status) return <p className="bl__note">Loading…</p>;

  const proof = (): Proof => ({ frame: grabFrame(), pin: proofPin || undefined });
  const say = (r: GuardResult, ok?: string) => {
    if (r.ok) { setMsg(ok ?? ""); if (r.status) apply(r.status); }
    else setMsg(r.error || "That didn't work.");
    return r.ok;
  };
  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setMsg("");
    setProblems([]);
    try { await fn(); } catch { setMsg("Can't reach AURA's brain."); } finally { setBusy(""); setLevel(0); }
  };

  // ── wizard actions ───────────────────────────────────────────────────────
  const begin = () => run("prepare", async () => {
    setMsg("Getting the face & voice models ready — the first time downloads ~80 MB…");
    const r = await guardApi.prepare();
    if (!r.face.ready) { setMsg(`Face recognition isn't available: ${r.face.error}`); return; }
    setVoiceReady(r.voice.ready);
    setMsg(r.voice.ready ? "" : `Voice ID unavailable (${r.voice.error}) — you can still use face + PIN.`);
    setStep("face");
  });

  const captureFace = () => run("face", async () => {
    if (!(await cameraReady())) { setMsg("I can't open the camera — check it isn't blocked or in use."); return; }
    await new Promise((r) => setTimeout(r, 600)); // let exposure settle
    const frames: string[] = [];
    for (const p of POSES) {
      setPose(p);
      await new Promise((r) => setTimeout(r, 1300));
      const f = grabFrame();
      if (f) frames.push(f);
    }
    setPose("");
    const r = await guardApi.enrollFace(frames, name.trim(), proof());
    setProblems(r.problems ?? []);
    if (say(r)) {
      if (status.active) { setStep(null); setMsg("Got your face again — all set."); }
      else setStep(voiceReady ? "voice" : "pin");
    }
  });

  const recordLine = (i: number) => run("voice", async () => {
    setRecIdx(i);
    try {
      const clip = await recordClip(CLIP_MS, setLevel);
      setClips((prev) => { const next = [...prev]; next[i] = clip; return next; });
    } finally {
      setRecIdx(-1);
    }
  });

  const saveVoice = () => run("voice-save", async () => {
    const r = await guardApi.enrollVoice(clips.filter(Boolean), proof());
    setProblems(r.problems ?? []);
    if (say(r)) {
      setClips([]);
      if (status.active) { setStep(null); setMsg("I'll know your voice now."); }
      else setStep("pin");
    }
  });

  const savePin = () => run("pin", async () => {
    if (!/^\d{4,12}$/.test(pin1)) { setMsg("Use 4–12 digits."); return; }
    if (pin1 !== pin2) { setMsg("Those PINs don't match."); return; }
    const r = await guardApi.setPin(pin1, proof());
    if (!say(r)) return;
    setPin1(""); setPin2("");
    if (status.active) { setChangingPin(false); setMsg("PIN changed."); return; }
    // Turn it on with a frame of the owner, so they start unlocked.
    if (say(await guardApi.enable({ frame: grabFrame() }),
            `Buddy Lock is on. I'll only answer ${name.trim() || "you"} now.`)) setStep(null);
  });

  // ── managing an active lock ──────────────────────────────────────────────
  const act = (label: string, fn: () => Promise<GuardResult>, ok: string) =>
    run(label, async () => { say(await fn(), ok); });

  const g = status.guest;
  const owner = status.owner_name || "you";

  // ── render ───────────────────────────────────────────────────────────────
  const wizard = step && (
    <div className="bl__wizard">
      {step === "intro" && (
        <>
          <p>Once this is on, AURA only answers <b>you</b>:</p>
          <ul className="bl__bullets">
            <li><b>Typing</b> — she checks the camera that it's you at the keyboard.</li>
            <li><b>Talking</b> — she knows your voice (short phrases fall back to the camera).</li>
            <li><b>Friends</b> — they get help when you're sitting there too, or after you say
              <i> "AURA, you can help him"</i>. They never see your memory, chats or projects.</li>
            <li><b>Walk away</b> — after {Math.round(status.lock_after_s)}s without seeing you, she locks.</li>
          </ul>
          <label className="bl__field">What should she call you?
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Your name" />
          </label>
          <div className="bl__row">
            <button className="bl__btn bl__btn--primary" onClick={begin} disabled={!!busy || !name.trim()}>
              {busy === "prepare" ? "Getting ready…" : "Start setup"}
            </button>
            <button className="bl__btn" onClick={() => setStep(null)} disabled={!!busy}>Cancel</button>
          </div>
        </>
      )}

      {step === "face" && (
        <>
          <h4>1 · Your face</h4>
          <Preview />
          <p className="bl__pose">{pose || "Sit where you normally sit, alone in frame, with light on your face."}</p>
          <div className="bl__row">
            <button className="bl__btn bl__btn--primary" onClick={captureFace} disabled={!!busy}>
              {busy === "face" ? "Hold still…" : "Capture my face"}
            </button>
            <button className="bl__btn" onClick={() => setStep(null)} disabled={!!busy}>Cancel</button>
          </div>
        </>
      )}

      {step === "voice" && (
        <>
          <h4>2 · Your voice <span className="bl__opt">optional</span></h4>
          <p className="bl__note">Read each line in your normal voice. Three lines, about 5 seconds each.</p>
          {LINES.map((line, i) => (
            <div key={i} className="bl__line">
              <span className="bl__linetext">“{line}”</span>
              <button className="bl__btn" onClick={() => recordLine(i)} disabled={!!busy}>
                {recIdx === i ? "Recording…" : clips[i] ? "Redo" : "Record"}
              </button>
              {clips[i] && <span className="bl__tick">✓</span>}
            </div>
          ))}
          {busy === "voice" && <div className="bl__meter"><span style={{ width: `${level * 100}%` }} /></div>}
          <div className="bl__row">
            <button className="bl__btn bl__btn--primary" onClick={saveVoice}
                    disabled={!!busy || clips.filter(Boolean).length < 2}>
              {busy === "voice-save" ? "Learning your voice…" : "Save my voice"}
            </button>
            <button className="bl__btn" onClick={() => { setClips([]); setStep(status.active ? null : "pin"); }}
                    disabled={!!busy}>{status.active ? "Cancel" : "Skip"}</button>
          </div>
        </>
      )}

      {step === "pin" && (
        <>
          <h4>3 · Backup PIN</h4>
          <p className="bl__note">For when the camera can't see you — bad light, no webcam, a new haircut.</p>
          <div className="bl__row">
            <input className="bl__pininput" type="password" inputMode="numeric" placeholder="PIN (4–12 digits)"
                   value={pin1} onChange={(e) => setPin1(e.target.value.replace(/\D/g, ""))} maxLength={12} />
            <input className="bl__pininput" type="password" inputMode="numeric" placeholder="Again"
                   value={pin2} onChange={(e) => setPin2(e.target.value.replace(/\D/g, ""))} maxLength={12} />
          </div>
          <div className="bl__row">
            <button className="bl__btn bl__btn--primary" onClick={savePin} disabled={!!busy || !pin1 || !pin2}>
              {busy === "pin" ? "Saving…" : "Save PIN & turn on"}
            </button>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="bl">
      <div className="bl__head">
        <span className={"bl__state" + (status.active ? " bl__state--on" : "")}>
          {status.active ? "ON" : "OFF"}
        </span>
        <div>
          <div className="bl__title">Buddy Lock</div>
          <div className="bl__sub">
            {status.active
              ? `AURA answers only ${owner}${status.role === "guest" ? " — a guest is using her now" : ""}.`
              : "AURA answers whoever is at the laptop."}
          </div>
        </div>
      </div>

      {wizard}

      {!step && !status.active && (
        <div className="bl__row">
          {status.vault.face_samples >= 3 && status.vault.has_pin ? (
            <>
              <button className="bl__btn bl__btn--primary" disabled={!!busy}
                      onClick={() => act("enable", () => guardApi.enable({ frame: grabFrame() }), "Buddy Lock is back on.")}>
                Turn back on
              </button>
              <button className="bl__btn" onClick={() => setStep("intro")} disabled={!!busy}>Set up again</button>
            </>
          ) : (
            <button className="bl__btn bl__btn--primary" onClick={() => setStep("intro")}>Set up Buddy Lock</button>
          )}
        </div>
      )}

      {!step && status.active && (
        <div className="bl__manage">
          <div className="bl__item">
            <div>
              <div className="bl__label">Guest access</div>
              <div className="bl__note">
                {g
                  ? `${g.claimed ? "Your friend has it" : "Waiting for them to sit down"} · ${Math.ceil(g.expires_in / 60)} min left`
                  : <>Off. Or just say <i>"AURA, you can help him"</i> with them next to you.</>}
              </div>
            </div>
            {g ? (
              <button className="bl__btn" disabled={!!busy}
                      onClick={() => act("guest", () => guardApi.revokeGuest(), "Guest access ended.")}>End</button>
            ) : (
              <div className="bl__row bl__row--tight">
                <select value={guestMin} onChange={(e) => setGuestMin(Number(e.target.value))} className="bl__select">
                  <option value={15}>15 min</option>
                  <option value={30}>30 min</option>
                  <option value={60}>1 hour</option>
                  <option value={120}>2 hours</option>
                </select>
                <button className="bl__btn" disabled={!!busy}
                        onClick={() => run("guest", async () => {
                          const r = await guardApi.grantGuest(guestMin, proof());
                          say(r, r.message || "Guest access on.");
                        })}>Allow</button>
              </div>
            )}
          </div>

          <div className="bl__item">
            <div>
              <div className="bl__label">Face</div>
              <div className="bl__note">{status.vault.face_samples} samples</div>
            </div>
            <button className="bl__btn" onClick={() => setStep("face")} disabled={!!busy}>Re-enroll</button>
          </div>

          <div className="bl__item">
            <div>
              <div className="bl__label">Voice</div>
              <div className="bl__note">
                {status.vault.voice_samples ? `${status.vault.voice_samples} recordings` : "Not set up — voice messages are checked by camera"}
              </div>
            </div>
            <div className="bl__row bl__row--tight">
              <button className="bl__btn" disabled={!!busy}
                      onClick={() => run("prepare", async () => {
                        const r = await guardApi.prepare();
                        if (!r.voice.ready) { setMsg(`Voice ID unavailable: ${r.voice.error}`); return; }
                        setVoiceReady(true);
                        setStep("voice");
                      })}>
                {status.vault.voice_samples ? "Re-record" : "Add my voice"}
              </button>
              {status.vault.voice_samples > 0 && (
                <button className="bl__btn" disabled={!!busy}
                        onClick={() => act("voice", () => guardApi.forgetVoice(proof()), "Voice forgotten.")}>Remove</button>
              )}
            </div>
          </div>

          <div className="bl__item">
            <div>
              <div className="bl__label">Backup PIN</div>
              <div className="bl__note">{status.pin_session ? "Unlocked by PIN or voice right now" : "Set"}</div>
            </div>
            {changingPin ? (
              <div className="bl__row bl__row--tight">
                <input className="bl__pininput" type="password" inputMode="numeric" placeholder="New PIN"
                       value={pin1} onChange={(e) => setPin1(e.target.value.replace(/\D/g, ""))} maxLength={12} />
                <input className="bl__pininput" type="password" inputMode="numeric" placeholder="Again"
                       value={pin2} onChange={(e) => setPin2(e.target.value.replace(/\D/g, ""))} maxLength={12} />
                <button className="bl__btn" onClick={savePin} disabled={!!busy}>Save</button>
              </div>
            ) : (
              <button className="bl__btn" onClick={() => setChangingPin(true)} disabled={!!busy}>Change</button>
            )}
          </div>

          <div className="bl__item bl__item--danger">
            <div>
              <div className="bl__label">Turn off or forget me</div>
              <div className="bl__note">Needs your face in the camera — or your current PIN here:
                <input className="bl__pininput bl__pininput--small" type="password" inputMode="numeric"
                       placeholder="PIN" value={proofPin} maxLength={12}
                       onChange={(e) => setProofPin(e.target.value.replace(/\D/g, ""))} />
              </div>
            </div>
            <div className="bl__row bl__row--tight">
              <button className="bl__btn" disabled={!!busy}
                      onClick={() => act("off", () => guardApi.disable(proof()), "Buddy Lock is off.")}>Turn off</button>
              <button className="bl__btn bl__btn--danger" disabled={!!busy}
                      onClick={() => {
                        if (window.confirm("Forget your face, voice and PIN, and turn Buddy Lock off?")) {
                          void act("reset", () => guardApi.reset(proof()), "Forgotten. Buddy Lock is off.");
                        }
                      }}>Forget me</button>
            </div>
          </div>
        </div>
      )}

      {msg && <p className="bl__msg">{msg}</p>}
      {problems.length > 0 && (
        <ul className="bl__problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
      )}
    </div>
  );
}
