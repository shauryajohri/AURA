"""
Tests for Buddy Lock (core/guard) — AURA only answers her buddy.

The ask: "when AURA opens she checks if it's her buddy. If I'm not in the
camera frame, don't answer. If someone else is using my laptop and I'm there,
or I told her she can help him, give access. Voice is recognised when I speak;
when typing she checks the camera."

Part 1 — the policy, with fake engines and a fake clock (always runs):
  typed/voice decisions, grace + continuity, someone-else takeover, guest
  passes (bound, unclaimed, revoked, expired), PIN + voice sessions, the REST
  gate, the vault, the "you can help him" parser, the guest-lane code filter.
Part 2 — the real engines on real photos/recordings (runs when opencv +
  sherpa-onnx are installed and the samples can be fetched; skipped otherwise):
  same person matches, different people don't, short audio abstains.

Never touches the real vault: everything runs in a temp dir.

Run:  PYTHONPATH=. python test_guard.py
"""

import io
import json
import os
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="aura_guard_test_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")

from core.guard import commands  # noqa: E402
from core.guard.face import Face  # noqa: E402
from core.guard.policy import (  # noqa: E402
    FRESH_S, GRACE_S, LOCK_AFTER_S, PIN_FREE_ATTEMPTS, PIN_SESSION_S, Guard)
from core.guard.vault import Vault  # noqa: E402
from core.guard.voice import VoiceSample  # noqa: E402

passed = failed = skipped = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


# ── fakes ──────────────────────────────────────────────────────────────────
# Embeddings are 3-d unit vectors: OWNER, FRIEND and STRANGER are orthogonal
# (similarity 0), BLURRY_OWNER sits at ~0.39 — "probably the owner".
OWNER = [1.0, 0.0, 0.0]
FRIEND = [0.0, 1.0, 0.0]
STRANGER = [0.0, 0.0, 1.0]
BLURRY_OWNER = [0.39, 0.92, 0.0]
DIM_OWNER = [0.3, -0.954, 0.0]   # the owner in bad light: matches nobody enrolled


class FakeFaces:
    """frame bytes are a JSON list of embeddings, largest face first."""

    def analyze(self, frame: bytes):
        return [Face(box=(0, 0, 200, 200), score=0.99, embedding=e) for e in json.loads(frame)]


class FakeVoices:
    """audio bytes are JSON: {"emb": [...]|null, "s": voiced seconds}."""

    def embed(self, audio: bytes):
        d = json.loads(audio)
        return VoiceSample(d["emb"], d["s"])


def frame(*faces) -> bytes:
    return json.dumps(list(faces)).encode()


def said(emb, s=3.0) -> bytes:
    return json.dumps({"emb": emb, "s": s}).encode()


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def tick(self, s):
        self.t += s


def fresh_guard(enroll=True, voice=True):
    path = os.path.join(_TMP, f"v{fresh_guard.n}.json")
    fresh_guard.n += 1
    v = Vault(path)
    if enroll:
        v.add_faces([OWNER, OWNER])
        if voice:
            v.add_voices([OWNER])
        v.set_pin("2468")
        v.set_enabled(True)
    clock = Clock()
    return Guard(v, FakeFaces(), FakeVoices(), clock=clock), clock


fresh_guard.n = 0

# ════════════════════════════════════════════════════════════════════════════
print("\n[lock off until an owner is enrolled]")
g, c = fresh_guard(enroll=False)
check("not active with nothing enrolled", not g.active)
d = g.authorize("hi", frame=frame(STRANGER))
check("everyone is answered while off", d.allowed and d.reason == "guard_off")
check("role is 'open'", g.role() == "open")

print("\n[typing checks the camera]")
g, c = fresh_guard()
check("active once enrolled + enabled", g.active)
check("locked at launch until the owner is seen", g.role() == "locked")
d = g.authorize("hey", frame=frame(OWNER))
check("owner in frame → answered as owner", d.allowed and d.role == "owner" and d.reason == "face")
check("…and the UI unlocks", g.role() == "owner")
g.lock_now()
d = g.authorize("hey", frame=frame(STRANGER))
check("stranger in frame → not answered", not d.allowed and d.reason == "stranger")
check("…with a reason to show", "only talk to" in d.message)
g.lock_now()
d = g.authorize("hey", frame=frame())
check("nobody in frame → not answered", not d.allowed and d.reason == "nobody")
g.lock_now()
d = g.authorize("hey")
check("no camera at all → not answered", not d.allowed and d.reason == "no_camera")

print("\n[detection misses vs. positive stranger evidence]")
g, c = fresh_guard()
sock = {}  # one WebSocket connection's evidence
g.authorize("hi", frame=frame(OWNER), session=sock)
c.tick(GRACE_S - 2)
d = g.authorize("still me, looking down", frame=frame(), session=sock)
check(f"empty frame within {GRACE_S}s of a clear sighting on the same socket → owner",
      d.allowed and d.reason == "face_recent")
c.tick(5)
d = g.authorize("still me?", frame=frame(), session=sock)
check("empty frame after the grace → not answered", not d.allowed)
g, c = fresh_guard()
g.authorize("hi", frame=frame(OWNER), session=sock)
c.tick(1)
d = g.authorize("hi", frame=frame(STRANGER), session=sock)
check("a stranger 1s after the owner is NOT excused by the grace", not d.allowed)

print("\n[a message never borrows evidence from another connection]")
g, c = fresh_guard()
g.observe(frame(OWNER))              # the UI's presence loop: owner at the camera
check("owner is present (UI unlocked)", g.role() == "owner")
d = g.authorize("open cmd", session={})
check("frameless message from another socket → not answered", not d.allowed and d.reason == "no_camera")
d = g.authorize("open cmd", frame=frame(), session={})
check("blank frame from another socket → not answered", not d.allowed and d.reason == "nobody")
mine = {}
g.authorize("hi", frame=frame(OWNER), session=mine)
c.tick(3)
d = g.authorize("one more", frame=frame(), session={})
check("…even right after the owner's own socket was verified", not d.allowed)
d = g.authorize("one more", frame=frame(), session=mine)
check("the owner's own socket keeps its grace", d.allowed and d.reason == "face_recent")

print("\n[continuity: 'probably the owner' only right after a clear sighting]")
g, c = fresh_guard()
g.authorize("hi", frame=frame(OWNER))
c.tick(30)
d = g.authorize("hi", frame=frame(BLURRY_OWNER))
check("0.39 match within the window → owner", d.allowed and d.reason == "face_continuity")
g2, c2 = fresh_guard()
d = g2.authorize("hi", frame=frame(BLURRY_OWNER))
check("0.39 match cold → not enough", not d.allowed)

print("\n[someone else sits down]")
g, c = fresh_guard()
g.observe(frame(OWNER))
c.tick(3)
g.observe(frame(STRANGER))
check("one stranger frame doesn't flash the lock", g.role() == "owner")
c.tick(3)
g.observe(frame())
check("an empty frame doesn't count either way", g.role() == "owner")
c.tick(3)
g.observe(frame(STRANGER))
check("two stranger frames → owner counts as gone", g.role() == "locked")
g.observe(frame(OWNER))
check("owner back → unlocked again", g.role() == "owner")
c.tick(LOCK_AFTER_S + 1)
check(f"owner unseen for {LOCK_AFTER_S}s → locked", g.role() == "locked")

print("\n[voice: recognised when the owner speaks]")
g, c = fresh_guard()
d = g.authorize("open my notes", via="voice", audio=said(OWNER), frame=frame(STRANGER))
check("owner's voice → owner, even with a bad camera read", d.allowed and d.reason == "voice")
g.lock_now()
d = g.authorize("open my notes", via="voice", audio=said(STRANGER), frame=frame(STRANGER))
check("someone else's voice + stranger in frame → not answered", not d.allowed)
g.lock_now()
d = g.authorize("yes", via="voice", audio=said(None, 0.4), frame=frame(OWNER))
check("too short to judge → camera decides (owner in frame)", d.allowed and d.reason == "face")
g.lock_now()
d = g.authorize("yes", via="voice", audio=said(None, 0.4), frame=frame(STRANGER))
check("too short to judge → camera decides (stranger)", not d.allowed)
g.lock_now()
d = g.authorize("hello", via="voice", audio=said(STRANGER), frame=frame(OWNER))
check("voice mismatch but owner alone in frame → owner (voice false-reject)",
      d.allowed and d.role == "owner")
g.lock_now()
d = g.authorize("hello", via="voice", audio=said(STRANGER), frame=frame(FRIEND, OWNER))
check("someone else talking while the owner is there → guest",
      d.allowed and d.role == "guest" and d.reason == "owner_present")
g3, _ = fresh_guard(voice=False)
d = g3.authorize("hi", via="voice", audio=said(OWNER), frame=frame(STRANGER))
check("no voice enrolled → voice ignored, camera decides", not d.allowed)

print("\n[\"you can help him\" — guest passes]")
g, c = fresh_guard()
d = g.authorize("aura you can help him", frame=frame(OWNER, FRIEND))
check("owner's command is handled locally", d.allowed and d.handled and "help" in d.message)
check("pass is bound to the friend in frame", g.status()["guest"]["claimed"])
c.tick(LOCK_AFTER_S + 5)
d = g.authorize("can you explain recursion?", frame=frame(FRIEND))
check("friend alone later → guest", d.allowed and d.role == "guest" and d.reason == "guest_pass")
check("…and the UI serves a guest", g.role() == "guest")
d = g.authorize("hi", frame=frame(STRANGER))
check("a third person is NOT covered by the friend's pass", not d.allowed)
d = g.authorize("you can help me", frame=frame(FRIEND))
check("a guest can't grant passes (it's just chat)", d.allowed and d.role == "guest" and not d.handled)
d = g.authorize("stop helping him", frame=frame(OWNER))
check("owner revokes", d.handled and g.status()["guest"] is None)
d = g.authorize("hello?", frame=frame(FRIEND))
check("friend after revoke → not answered", not d.allowed)

g, c = fresh_guard()
g.authorize("you can help my friend for an hour", frame=frame(OWNER))
st = g.status()["guest"]
check("granted with nobody else in frame → unclaimed", st and not st["claimed"])
check("…for the hour asked", 3590 <= st["expires_in"] <= 3600)
c.tick(LOCK_AFTER_S + 5)
d = g.authorize("hi", frame=frame(FRIEND))
check("first new face claims it", d.allowed and d.role == "guest" and g.status()["guest"]["claimed"])
d = g.authorize("hi", frame=frame(STRANGER))
check("…and only them", not d.allowed)
c.tick(3600)
d = g.authorize("hi", frame=frame(FRIEND))
check("pass expires", not d.allowed and g.status()["guest"] is None)

g, c = fresh_guard()
g.authorize("you can help him", frame=frame(OWNER))
c.tick(LOCK_AFTER_S + 5)
d = g.authorize("hi")
check("a pass needs a face: frameless message isn't covered", not d.allowed)

print("\n[PIN and voice sessions]")
g, c = fresh_guard()
ok, _ = g.unlock_pin("0000")
check("wrong PIN refused", not ok)
for _ in range(5):
    g.unlock_pin("0000")
ok, why = g.unlock_pin("2468")
check("brute force backs off (even the right PIN waits)", not ok and "try again" in why)
c.tick(3600)
ok, _ = g.unlock_pin("2468")
check("right PIN after the backoff → unlocked", ok and g.role() == "owner")
d = g.authorize("hi", frame=frame(STRANGER))
check("PIN session: camera isn't consulted", d.allowed and d.reason == "pin")
c.tick(PIN_SESSION_S + LOCK_AFTER_S)
check("PIN session ends", g.role() == "locked")

g, c = fresh_guard()
g.observe(frame(DIM_OWNER))          # camera can't place the owner (bad light)…
ok, _ = g.unlock_pin("2468")         # …so they use the PIN
for _ in range(4):
    c.tick(3)
    g.observe(frame(DIM_OWNER))
check("PIN session stays with the person who unlocked it", g.role() == "owner")
c.tick(3)
g.observe(frame(STRANGER))
check("one frame of someone else doesn't end it", g.role() == "owner")
c.tick(3)
g.observe(frame(STRANGER))
check("someone else taking the seat ends the PIN session", g.role() == "locked")

g, c = fresh_guard()
for _ in range(PIN_FREE_ATTEMPTS):
    g.unlock_pin("0000")
g2 = Guard(g.vault.__class__(g.vault.path), FakeFaces(), FakeVoices(), clock=c)
ok, why = g2.unlock_pin("2468")
check("PIN lockout survives a restart", not ok and "try again" in why)

g, c = fresh_guard()
check("verify_owner_now with the PIN → yes", g.verify_owner_now(pin="2468"))
check("…but it opens NO session (no inheriting the owner)", g.role() == "locked")
check("verify_owner_now with a stranger frame → no", not g.verify_owner_now(frame=frame(STRANGER)))
check("verify_owner_now with the owner in frame → yes", g.verify_owner_now(frame=frame(OWNER)))

g, c = fresh_guard()
check("voice unlock: too short", g.unlock_voice(said(None, 0.5)) == (False, "short"))
check("voice unlock: someone else", g.unlock_voice(said(STRANGER)) == (False, "mismatch"))
check("voice unlock: the owner", g.unlock_voice(said(OWNER))[0])
for _ in range(3):
    c.tick(2)
    g.observe(frame(STRANGER))
check("voice session survives a camera that can't place them", g.role() == "owner")

print("\n[the REST gate]")
import guard_api  # noqa: E402

g, c = fresh_guard()
guard_api.get_guard = lambda: g
check("non-API paths pass (site, /ws, /health)", guard_api.rest_verdict("GET", "/") is None
      and guard_api.rest_verdict("GET", "/health") is None)
check("guard endpoints always reachable", guard_api.rest_verdict("POST", "/api/guard/unlock/pin") is None)
v = guard_api.rest_verdict("GET", "/api/facts")
check("locked → 423 for the owner's data", v and v[0] == 423)
g.observe(frame(OWNER))
check("owner → everything", guard_api.rest_verdict("DELETE", "/api/facts/3") is None)
g.grant(30)
g.lock_now()
check("guest can load what the chat needs", guard_api.rest_verdict("GET", "/api/settings") is None)
v = guard_api.rest_verdict("GET", "/api/facts")
check("guest can't read the owner's memory → 403", v and v[0] == 403)
v = guard_api.rest_verdict("POST", "/api/domain/shell/run")
check("guest can't touch the terminal → 403", v and v[0] == 403)


def broken():
    raise RuntimeError("boom")


guard_api.get_guard = broken
v = guard_api.rest_verdict("GET", "/api/tasks")
check("a broken guard fails CLOSED", v and v[0] == 423)

print("\n[the vault]")
p = os.path.join(_TMP, "vault_t.json")
v = Vault(p)
v.add_faces([OWNER])
v.set_pin("1234")
raw = open(p).read()
check("PIN is not stored in clear", "1234" not in raw and v.check_pin("1234") and not v.check_pin("4321"))
check("only embeddings on disk — no images", set(json.loads(raw)) <= {
    "version", "enabled", "owner_name", "face", "voice", "pin", "tuning", "updated_at"})
with open(p, "w") as f:
    f.write("{not json")
v2 = Vault(p)
check("a corrupt vault stays LOCKED, it doesn't fall open", v2.enabled and v2.corrupt)
g = Guard(v2, FakeFaces(), FakeVoices())
check("…and the guard enforces it", g.active and g.role() == "locked")

print("\n[the \"you can help him\" parser]")
for text, want in [
    ("aura you can help him", "grant"),
    ("You can help Rahul.", "grant"),
    ("let her use you for an hour", "grant"),
    ("he's with me", "grant"),
    ("give my friend access", "grant"),
    ("you can help me with this bug", None),
    ("you can help fix this", None),
    ("let me use you", None),
    ("can you help me", None),
    ("stop helping him", "revoke"),
    ("revoke guest access", "revoke"),
    ("don't let him use you", "revoke"),
    ("only talk to me", "revoke"),
]:
    got = commands.parse(text)
    check(f"{text!r} → {want}", (got or {}).get("action") == want)
check("'for 2 hours' → 120 min", commands.parse_minutes("you can help him for 2 hours") == 120)
check("'half an hour' → 30 min", commands.parse_minutes("help him out for half an hour") == 30)
check("'for the day' → capped", commands.parse_minutes("let him use you for the day") == commands.MAX_MINUTES)

print("\n[guest lane never falls back to the raw monologue]")
import core.ai_router as _router  # noqa: E402
from core.guard import guest_lane  # noqa: E402

_real_route, _real_sanitize = _router.route_streaming, _router.sanitize_text
_router.route_streaming = lambda *a, **k: iter(["The user is asking about the owner. ",
                                                "We need to avoid sharing Shaurya's facts."])
_router.sanitize_text = lambda text, query="": ""
try:
    reply = guest_lane.answer("hi", "Shaurya")
finally:
    _router.route_streaming, _router.sanitize_text = _real_route, _real_sanitize
check("all-deliberation reply → a fallback line, not the monologue",
      reply == guest_lane._LOST and "Shaurya" not in reply)
guest_lane.reset()

print("\n[guest lane never streams code twice]")
from core.guard.guest_lane import _ProseOnly  # noqa: E402

out = []
p = _ProseOnly(out.append)
for chunk in ["Here:\n`", "``py", "thon\nprint(1)\n``", "`\nDone `x`."]:
    p.feed(chunk)
p.flush()
check("fenced code held back, inline code kept", "".join(out) == "Here:\n\nDone `x`.")

print("\n[voice VAD on synthetic audio]")
try:
    import numpy as np
    from core.guard.voice import decode_wav, speech_only

    def wav(samples, rate=16000):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return buf.getvalue()

    t = np.arange(16000 * 2) / 16000
    burst = 0.3 * np.sin(2 * np.pi * 220 * t)
    clip = np.concatenate([np.zeros(16000), burst, np.zeros(16000)])
    voiced = len(speech_only(decode_wav(wav(clip)))) / 16000
    check(f"1s silence + 2s sound + 1s silence → ~2s voiced ({voiced:.2f}s)", 1.9 <= voiced <= 2.2)
    check("pure silence → nothing voiced", len(speech_only(decode_wav(wav(np.zeros(32000))))) == 0)
    one_sec_44k = 0.3 * np.sin(2 * np.pi * 220 * np.arange(44100) / 44100)
    a = decode_wav(wav(one_sec_44k, rate=44100))
    check(f"1s at 44.1 kHz → 16000 samples at 16 kHz ({len(a)})", abs(len(a) - 16000) <= 2)
except ImportError:
    skipped += 1
    print("  - numpy missing: skipped")

# ════════════════════════════════════════════════════════════════════════════
print("\n[real engines on real faces and voices]")
SAMPLES = os.path.join(_TMP, "samples")
_FILES = {
    "obama.jpg": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama.jpg",
    "obama2.jpg": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama2.jpg",
    "biden.jpg": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/biden.jpg",
    "two_people.jpg": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/two_people.jpg",
    **{f"{n}.wav": f"https://raw.githubusercontent.com/csukuangfj/sr-data/main/{d}/{n}.wav" for d, n in [
        ("enroll", "fangjun-sr-1"), ("enroll", "fangjun-sr-2"), ("enroll", "fangjun-sr-3"),
        ("test", "fangjun-test-sr-1"), ("test", "leijun-test-sr-1"), ("test", "liudehua-test-sr-1")]},
}


def _fetch_samples() -> bool:
    import urllib.request
    os.makedirs(SAMPLES, exist_ok=True)
    try:
        for name, url in _FILES.items():
            with urllib.request.urlopen(url, timeout=20) as r, open(os.path.join(SAMPLES, name), "wb") as f:
                f.write(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  - couldn't fetch samples ({e}): skipped")
        return False


def _read(name):
    with open(os.path.join(SAMPLES, name), "rb") as f:
        return f.read()


from core.guard import face as face_mod, voice as voice_mod  # noqa: E402
from core.guard.face import best_match, cosine  # noqa: E402

f_ok, f_err = face_mod.ENGINE.available()
v_ok, v_err = voice_mod.ENGINE.available()
if not (f_ok or v_ok):
    skipped += 1
    print(f"  - engines unavailable (face: {f_err}; voice: {v_err}): skipped")
elif _fetch_samples():
    if f_ok:
        owner = [face_mod.ENGINE.analyze(_read("obama.jpg"))[0].embedding]
        same = best_match(face_mod.ENGINE.analyze(_read("obama2.jpg"))[0].embedding, owner)
        other = best_match(face_mod.ENGINE.analyze(_read("biden.jpg"))[0].embedding, owner)
        both = face_mod.ENGINE.analyze(_read("two_people.jpg"))
        check(f"face: same person, different photo matches ({same:.2f} ≥ 0.42)", same >= 0.42)
        check(f"face: a different person doesn't ({other:.2f} < 0.363)", other < 0.363)
        check("face: finds both people in a group photo", len(both) == 2)
        check("face: owner found in the group even when not the biggest face",
              max(best_match(f.embedding, owner) for f in both) >= 0.42)
    else:
        skipped += 1
        print(f"  - face engine unavailable ({f_err}): skipped")
    if v_ok:
        import numpy as np
        enrolled = [voice_mod.ENGINE.embed(_read(f"fangjun-sr-{i}.wav")).embedding for i in (1, 2, 3)]
        centroid = np.mean(np.asarray(enrolled), axis=0)
        s_same = cosine(voice_mod.ENGINE.embed(_read("fangjun-test-sr-1.wav")).embedding, centroid)
        s_a = cosine(voice_mod.ENGINE.embed(_read("leijun-test-sr-1.wav")).embedding, centroid)
        s_b = cosine(voice_mod.ENGINE.embed(_read("liudehua-test-sr-1.wav")).embedding, centroid)
        check(f"voice: the enrolled speaker matches ({s_same:.2f} ≥ 0.55)", s_same >= 0.55)
        check(f"voice: two other speakers don't ({s_a:.2f}, {s_b:.2f} < 0.55)", s_a < 0.55 and s_b < 0.55)
        pcm = decode_wav(_read("fangjun-test-sr-1.wav"))[:12000]
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((pcm * 32767).astype("<i2").tobytes())
        check("voice: a 0.75s clip abstains instead of guessing",
              voice_mod.ENGINE.embed(buf.getvalue()).embedding is None)
    else:
        skipped += 1
        print(f"  - voice engine unavailable ({v_err}): skipped")
else:
    skipped += 1

print(f"\n{passed} passed, {failed} failed" + (f", {skipped} section(s) skipped" if skipped else ""))
sys.exit(1 if failed else 0)
