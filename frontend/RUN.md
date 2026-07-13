# AURA — React/Electron Face (Milestone 1)

The new "face" for AURA. React + Electron talks to your existing Python brain
over a WebSocket. **Nothing in `main.py` or the PySide6 app was changed** — this
runs alongside it.

```
React (Electron)  ──WebSocket──►  server.py (FastAPI)  ──►  core.brain.process_streaming
```

## One-time setup

**1. Python side (from the AURA repo root, in your existing venv):**

```powershell
pip install -r requirements-web.txt
```

**2. Frontend side:**

```powershell
cd frontend
npm install
```

## Running it (two terminals)

**Terminal 1 — the brain bridge:**

```powershell
# from AURA repo root, venv active
python server.py
```

You should see uvicorn come up on `http://127.0.0.1:8760`.
Sanity check: open `http://127.0.0.1:8760/health` → `{"status":"ok",...}`.

**Terminal 2 — the face:**

```powershell
cd frontend
npm run dev
```

This starts Vite (port 5173) and launches the Electron window automatically.
The status dot goes green ("Prime Core Online") once it connects to the bridge.
Type a message → it streams back from the real AURA brain, token by token.

> If you start the face before the bridge, that's fine — it auto-reconnects
> every 1.5s and turns green as soon as `server.py` is up.

## What's wired

- **Message contract** lives in `src/types.ts` and mirrors `server.py`. Keep the
  two in lockstep — one schema, both sides.
- The **orb** in the left stage is a CSS placeholder that already reacts to
  state (`idle` / `thinking` / `speaking`). That's the seam the Three.js black
  hole will drop into next — the backend already drives it, no backend changes
  needed for the visual.

## Next milestones

1. Replace the CSS orb with the react-three-fiber black hole (cosmic web, bloom,
   gravitational lens) driven by the same `auraState`.
2. Model constellation + tasks/events panels (port from the PySide6 UI).
3. Voice mode (mic → existing voice_input, TTS state → `speaking`).
4. Packaging: electron-builder + PyInstaller sidecar so `server.py` launches
   with the app.
