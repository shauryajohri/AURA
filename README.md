# AURA — AI Desktop Companion & Software Development OS

AURA is a self-hosted AI companion that lives on your desktop and works alongside you. Not a chatbot you summon — a system that observes, remembers, and steps in when it's actually useful.

Two halves, one brain:

- **The companion** — voice, screen awareness, durable memory, quests, proactive nudges.
- **AURA Domain** — an AI Software Development Operating System: conversations become features, features become tasks, commits close those tasks, and the whole history stays queryable.

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
leak-sanitised                        notes, recaps, tasks, quests,
     │                                domain graph
     ▼                                       │
  answer ◄─── core/work_recall.py ───────────┘
              (the project brain, in the conversation)
```

**A single chat turn:**

1. `classify_intent` → CASUAL / PERSONAL / CODING / SEARCH / RECALL / SAVE / COMMAND / REMINDER
2. `build_context_prompt` assembles: recent turns (from the *store*, not RAM), durable facts, **project memory** (`work_recall`), screen context, identity, error-intelligence hints, relationship layer
3. `ai_router` picks a model for that intent and streams the reply
4. `sanitize_text` strips any leaked chain-of-thought, `guard_output` is the final gate
5. Everything is written back to SQLite, so the next turn remembers it

### AURA knows what you're working on

Ask *"what project were we doing last time?"* and she answers from the project graph, not a guess. `core/work_recall.py` assembles it:

- **every turn** gets a compact block — recent projects, % done, last event
- **memory questions** ("where did we leave off", "what's left", "what did we decide") get the expanded version: open tasks with status, the current blocker, recent decisions *and their reasons*, session recaps

If nothing is stored, the block is empty on purpose — she says it's fuzzy rather than inventing a project name.

### The chat answers, it doesn't narrate

Reasoning models leak their deliberation as ordinary content ("So answer: …", "The user wants …", "That's one sentence?"). Three layers stop it:

1. prompt-level instruction + `reasoning: {exclude: true}` on OpenRouter
2. `sanitize_text` — two tiers of markers (STRONG stripped anywhere, WEAK only as leading preamble), a density rule, and a **seam cut**: when the model announces its answer, the text after the announcement *is* the answer, so it's recovered rather than discarded
3. `guard_output` before anything is shown or spoken

Fenced code is lifted out before filtering and restored byte-for-byte — a filter that flattens a C++ answer into one line is worse than the leak.

---

## AURA Domain — the development OS

Enter it from Sanctuary's **Enter Workspace** button (portal transition), or hit any section in the left nav.

| Section | What it does |
|---|---|
| **Dashboard** | Real progress: buckets, per-feature bars, biggest blocker, recent events, git sync |
| **Projects** | Create empty · import a local folder (reads code + git history) · clone a GitHub repo |
| **Research** | Pick a project, then just talk. Every sentence becomes a feature, decision, task edit, or note |
| **Tasks** | The generated board, grouped by feature. Commits close tasks themselves |
| **Knowledge Graph** | Nodes + edges, laid out left-to-right as the lifecycle: idea → decision → feature → task → commit → file |
| **Code** | Real filesystem editor (file tree, tabs, quick-open) |
| **Code Review** | AURA's version vs yours, console, and a permission ladder |
| **Documentation / Notes** | Markdown docs and quick notes per project |
| **Terminal** | A real shell, scoped to the project folder |
| **History** | The project's own timeline — commits, decisions, finished tasks, milestones |
| **Settings** | Nav order, density, glass, accent, background, connectors |

Click any node anywhere — graph, board, timeline, a Research receipt — and the **node drawer** answers three questions: *why does this exist* (the causal chain back to the originating idea), *what's connected*, and anything else you type (grounded in the graph only).

### The permission ladder (Code Review)

```
Read Only  →  Sandbox  →  Merge Review  →  Write  →  Push
   │            │             │              │        │
 suggest      run it       see the diff     save    commit
 only                                       to disk & push
```

One rung at a time, and the capabilities above the current rung are genuinely disabled. AURA's suggestion is always read-only — applying it is a click *you* make. Nothing escalates itself.

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
POST /api/voice/transcribe                  WAV → text fallback
GET  /api/v3/snapshot · /session · /mistakes       developer state
POST /api/v3/explain · /api/v3/build              error intelligence
GET  /health · /api/status
```

**Domain — machine**

```
GET  /api/domain/fs/roots · list · tree · read · search
POST /api/domain/fs/write · create · rename · delete
POST /api/domain/shell/open · run · close
GET  /api/domain/git/preview      what a commit would include
POST /api/domain/git/commit · push · publish       (all require confirm)
POST /api/domain/review           AURA reviews a file → findings + revision
GET  /api/domain/office/open · figma/file · github
GET  /api/connectors ...          OAuth (GitHub, OneDrive, Figma)
```

**Domain — the Project Brain**

```
GET    /api/domain/projects
POST   /api/domain/projects                 create empty
POST   /api/domain/projects/import          from a local folder
DELETE /api/domain/project/{pid}
GET    /api/domain/project/{pid}            dashboard vitals
GET    /api/domain/project/{pid}/nodes · graph · timeline · progress
POST   /api/domain/project/{pid}/capture    talk → structured knowledge
POST   /api/domain/project/{pid}/plan       text → feature + tasks
POST   /api/domain/project/{pid}/rescan     fold in new commits
POST   /api/domain/task/{tid}/status · expand
GET    /api/domain/node/{nid}/why · related
POST   /api/domain/node/{nid}/ask           grounded Q&A about any node
GET    /api/domain/github/status · repos
POST   /api/domain/github/import            clone + build the graph
```

---

## Layout

```
server.py              FastAPI app + WebSocket bridge + companion REST
domain_api.py          Domain REST (filesystem, shell, git, review, brain, connectors)
core/
  brain.py             the turn: intent → context → route → guard
  ai_router.py         5 models, cost-aware routing, leak sanitiser
  work_recall.py       project memory injected into every chat turn
  response_composer.py persona layer + 5 reply styles
  engagement.py        when to speak, when to shut up
  quest_verify.py      screenshot verification (vision model)
  git_ops.py           safe commit/push (preview → confirm)
  domain_fs.py         sandboxed filesystem
  domain_shell.py      persistent shell sessions
  identity.py          who AURA is
  domain/              THE PROJECT BRAIN
    brain_store.py     SQLite knowledge graph (nodes + typed edges)
    project_brain.py   high-level API: record, import, why(), timeline()
    idea_capture.py    conversation → feature / decision / edit / note
    planning.py        text → feature + tasks (LLM + offline heuristic)
    analyzer.py        static analysis of a folder
    git_scan.py        local git, no auth
    progress.py        buckets, per-feature rollup, biggest blocker
    github_import.py   clone a repo into a project
modules/               error_intelligence, developer_state, screen_reader,
                       relationship_engine, decision_engine, forex_report
memory/store.py        SQLite: conversations, facts, notes, recaps, tasks, quests
frontend/src/
  App.tsx              Sanctuary ⇄ Domain, portal transition
  api.ts               companion REST client
  domainApi.ts         Domain machine-half client
  brainApi.ts          Project Brain client
  stores/              domainStore · brainStore · settingsStore · planetStore
  views/               Memory · Tasks · Quests · Models · Intelligence · Skills
  components/Domain/   shell, nav, header, chat
    brain/             Projects · Research · Dashboard · Tasks · Graph ·
                       Timeline · NodeDrawer
    views/             CodePane · CodeReviewView · Terminal · Docs · Notes
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
GITHUB_CLIENT_ID=...            # only for Domain → GitHub import
GITHUB_CLIENT_SECRET=...
```

OAuth callbacks come back to `http://127.0.0.1:8760/api/connectors/callback/<provider>` — nothing public needed. Everything degrades: no OpenRouter key means Groq only; no keys at all still gives you the offline heuristic paths (planning, idea capture, error classification) and the whole filesystem/git/terminal side.

---

## Tests

All standalone — no pytest, no fixtures, just run them.

```bash
set PYTHONPATH=.                      # Windows;  export PYTHONPATH=. on Unix

python test_work_recall.py            # project memory in the chat
python test_reasoning_leak.py         # chain-of-thought never reaches the user
python test_memory.py                 # durable facts + context
python test_engine.py                 # routing + intent
python test_quests.py                 # quests, verification, pressure
python test_engagement.py             # when she speaks
python test_error_intelligence.py     # error KB (35 asserts)
python test_developer_state.py        # session awareness (26 asserts)
python test_screen_reading.py         # OCR, language detection
python tests/test_domain_foundation.py    # brain e2e on this repo
python tests/test_domain_api_contract.py  # every endpoint shape the UI reads
python tests/test_idea_capture.py          # conversation → knowledge

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
| "Project Brain unreachable" in Domain | `server.py` isn't running |
| Frontend loads, nothing responds | Backend on a different port — check `8760` |
| `npm run dev` can't find electron | `npm install` inside `frontend/` |
| Models all locked / no replies | No API key in `.env`, or every model rate-limited |
| GitHub import says not connected | Set `GITHUB_CLIENT_ID`/`SECRET`, then authorise in Domain → Settings → Connectors |
| Blank Domain background | `frontend/public/domain.mp4` missing — it falls back to a gradient |
| She talks about the wrong project | The brain has no project yet: Domain → Projects → import your folder |

---

## Status

Live and used daily: routing, memory, voice, screen awareness, error intelligence, quests, the Project Brain (backend + UI), Code Review, Research capture.

Not yet built: documentation generator, roadmap view, release management, and a project-grounded Domain chat rail (the per-node ask exists; the right rail is still generic).

---

## Why "AURA"

Built as a real, daily-use tool — around the idea that an AI companion should feel like a teammate sitting next to you, not something you have to open and address every time.

> Observe before interrupting. Understand before responding. Remember before asking again. Stay silent when silence is better.
