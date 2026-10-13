# AURA — AI Desktop Companion

AURA is a self-hosted AI companion that lives on your desktop and works alongside you. Not a chatbot you summon — a system that observes, remembers, and steps in when it's actually useful.

Voice, screen awareness, durable memory, quests, proactive nudges — and **you decide who she is to you**: a buddy, an assistant, a mentor, or a role you describe yourself (Settings → Relationship).

> AURA Domain (the coding workspace / Project Brain) was removed so AURA can be a companion rather than a tool you have to learn. The full Domain code is still in git history at commit `c752187` (the last commit before it was removed).

---

## Quick start

```bash
# 1. Python deps (once)
pip install -r requirements.txt          # full companion (voice, screen, TTS)
pip install -r requirements-web.txt      # backend/API only

# 2. Frontend deps (once)
cd frontend && npm install && cd ..

# 3. Keys — create .env in the repo root (see "Environment" below)

# 4. Run it
python server.py                         # backend on 127.0.0.1:8760
cd frontend && npm run dev               # Vite + Electron, hot reload
```

**Or just double-click `AURA.bat`** (or `AURA.vbs` for no console window). It builds the frontend on first run, then launches Electron, which boots `server.py` itself. `CREATE_DESKTOP_SHORTCUT.bat` puts it on your desktop with the generated black-hole icon.

| What you want | Command |
|---|---|
| Backend only | `python server.py` |
| Frontend dev (hot reload) | `cd frontend && npm run dev` |
| Frontend only, no Electron | `cd frontend && npm run dev:vite` → http://localhost:5173 |
| Production build | `cd frontend && npm run build` |
| Typecheck without building | `cd frontend && npx tsc --noEmit` |
| One-click launch | `AURA.bat` |
| Health check | `curl http://127.0.0.1:8760/health` |

---

## How it works

```
                        You
                         │
              voice · text · your screen
                         │
                         ▼
            ┌────────────────────────┐
            │   core/brain.py        │  intent → context → route → guard
            └────────────────────────┘
                 │            │
     ┌───────────┘            └──────────────┐
     ▼                                       ▼
core/ai_router.py                     memory/store.py
5 models, cost-aware,                 SQLite: conversations, facts,
leak-sanitised                        notes, recaps, tasks, quests
     │                                       │
     ▼                                       │
  answer ◄─── core/work_recall.py ───────────┘
              (session memory, in the conversation)
```

**A single chat turn:**

1. `classify_intent` → CASUAL / PERSONAL / CODING / SEARCH / RECALL / SAVE / COMMAND / REMINDER
2. `build_context_prompt` assembles: recent turns (from the *store*, not RAM), durable facts, **session memory** (`work_recall`), screen context, the chosen **relationship** (`persona`) and identity, error-intelligence hints, relationship layer
3. `ai_router` picks a model for that intent and streams the reply
4. `sanitize_text` strips any leaked chain-of-thought, `guard_output` is the final gate
5. Everything is written back to SQLite, so the next turn remembers it

### Who AURA is to you

`core/persona.py` builds the top of every system prompt from Settings → Relationship:

| Mode | AURA is… |
|---|---|
| **Buddy** (default) | a sharp, close friend — the original Donna-style AURA |
| **Assistant** | a capable chief of staff — warm, efficient, a step ahead |
| **Mentor** | wants you to get better — hints first, honest feedback |
| **Custom** | whatever you describe in your own words |

You can also tell her what to call you. The **nature** lock (Chill / Focus / Savage / Professional) still sits on top and controls tone inside any role.

### She remembers where you left off

Ask *"what were we doing last time?"* and `core/work_recall.py` answers from the last session summary and earlier recaps, not a guess. It's only added to the prompt when you're actually asking about past work, and it's empty on purpose when nothing is stored — she says it's fuzzy rather than inventing something.

### She learns your routine

`core/habits.py` reads the foreground app every 5 seconds (process name + window title only, no screenshots) and keeps per-hour totals: which apps and tools you use, how long, and when. Browsers count as the site when it's a well-known one (YouTube, GitHub, Gmail…), otherwise just as the browser.

- **Private by design** — only app names are stored, never window titles; AFK time, sleep gaps and AURA's own window are never counted.
- **Yours to control** — Memory → **Habits** shows it all; pause it, hide an app forever, or forget everything. The same switch lives in Settings → Privacy.
- **In the chat** — ordinary turns get one background line ("right now: Excel for 40m; usually VS Code, YouTube"); ask *"how much time did I spend on YouTube?"* or *"what are my habits?"* and she gets the full picture.

### The chat answers, it doesn't narrate

Reasoning models leak their deliberation as ordinary content ("So answer: …", "The user wants …", "That's one sentence?"). Three layers stop it:

1. prompt-level instruction + `reasoning: {exclude: true}` on OpenRouter
2. `sanitize_text` — two tiers of markers (STRONG stripped anywhere, WEAK only as leading preamble), a density rule, and a **seam cut**: when the model announces its answer, the text after the announcement *is* the answer, so it's recovered rather than discarded
3. `guard_output` before anything is shown or spoken

Fenced code is lifted out before filtering and restored byte-for-byte — a filter that flattens a C++ answer into one line is worse than the leak.

---

## API

All on `http://127.0.0.1:8760`. WebSocket chat at `/ws`.

**Companion**

```
GET/POST/PUT/DELETE  /api/tasks             tasks (now/later/done, promote to quest)
GET  /api/facts · POST · PUT · DELETE       what AURA knows about you
GET  /api/notes  · DELETE /api/notes/{id}   knowledge she extracted (read + prune)
GET  /api/recaps · DELETE /api/recaps/{id}  session snapshots
GET/POST/PUT/DELETE  /api/quests            daily commitments + screen verification
GET  /api/models · POST /api/models/{n}/toggle    model lock
GET  /api/links · /api/stats · /api/nature · /api/settings
GET  /api/habits?days=7 · DELETE /api/habits[?app_name=]   habits (read / forget)
POST /api/voice/transcribe                  WAV → text fallback
GET  /api/v3/snapshot · /session · /mistakes       developer state
POST /api/v3/explain · /api/v3/build              error intelligence
GET  /health · /api/status
```

---

## Layout

```
server.py              FastAPI app + WebSocket bridge + companion REST
core/
  brain.py             the turn: intent → context → route → guard
  ai_router.py         5 models, cost-aware routing, leak sanitiser
  work_recall.py       session memory for "where did we leave off"
  persona.py           relationship modes: buddy / assistant / mentor / custom
  habits.py            which apps/tools you use and when (foreground sampler)
  response_composer.py persona layer + 5 reply styles
  engagement.py        when to speak, when to shut up
  quest_verify.py      screenshot verification (vision model)
  identity.py          who AURA is
modules/               error_intelligence, developer_state, screen_reader,
                       relationship_engine, decision_engine, forex_report
memory/store.py        SQLite: conversations, facts, notes, recaps, tasks, quests, habits
frontend/src/
  App.tsx              the shell: Home + sidebar pages
  api.ts               companion REST client
  stores/              settingsStore · planetStore · coreStore
  views/               Memory · Tasks · Quests · Models · Settings · Skills
```

---

## Environment

`.env` in the repo root:

```ini
GROQ_API_KEY=...                # console.groq.com — the main path
OPENROUTER_API_KEY=...          # fallback + specialist models
OPENROUTER_KEY_CODING=...       # optional per-lane keys
OPENROUTER_KEY_RESEARCH=...
OPENROUTER_KEY_CHAT=...
```

Everything degrades: no OpenRouter key means Groq only; no keys at all still gives you the offline heuristic paths (error classification, quick responses).

---

## Tests

All standalone — no pytest, no fixtures, just run them.

```bash
set PYTHONPATH=.                      # Windows;  export PYTHONPATH=. on Unix

python test_work_recall.py            # session memory in the chat
python test_persona.py                # relationship modes
python test_habits.py                 # habit tracker: naming, crediting, privacy
python test_reasoning_leak.py         # chain-of-thought never reaches the user
python test_memory.py                 # durable facts + context
python test_engine.py                 # routing + intent
python test_quests.py                 # quests, verification, pressure
python test_engagement.py             # when she speaks
python test_error_intelligence.py     # error KB (35 asserts)
python test_developer_state.py        # session awareness (26 asserts)
python test_screen_reading.py         # OCR, language detection

cd frontend && npx tsc --noEmit       # frontend typecheck
```

---

## Tech

**Backend** Python · FastAPI · SQLite · Groq · OpenRouter · Ollama · edge-tts · FAISS + sentence-transformers
**Frontend** React 18 · TypeScript · Vite · Electron · zustand · Three.js
**Bridge** FastAPI WebSocket on 127.0.0.1:8760

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Brain offline" in Settings | `server.py` isn't running |
| Frontend loads, nothing responds | Backend on a different port — check `8760` |
| `npm run dev` can't find electron | `npm install` inside `frontend/` |
| Models all locked / no replies | No API key in `.env`, or every model rate-limited |
| She doesn't sound like the mode you picked | A **nature** lock is on — set it back to Auto |

---

## Status

Live and used daily: routing, memory, voice, screen awareness, error intelligence, quests, relationship modes, habit tracking.

Next: letting AURA do tasks on your screen when you tell her to.

---

## Why "AURA"

Built as a real, daily-use tool — around the idea that an AI companion should feel like a teammate sitting next to you, not something you have to open and address every time.

> Observe before interrupting. Understand before responding. Remember before asking again. Stay silent when silence is better.
