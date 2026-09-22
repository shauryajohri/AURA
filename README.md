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

### Saved Info — share it, she reads it

Paste a link in chat, or drop a PDF / Word file / image on the dock (📎 works too), and AURA saves it, reads it and files a title, summary, key points and tags (`core/saved_info.py`). Web pages, GitHub repos (README + metadata), YouTube videos, PDF links and uploads are all understood.

- **Just the link** ("save this https://…") → an instant "saved — here's what it is", no model call beyond the summary.
- **A question with it** ("what does this argue? https://…") → answered from the page's actual text.
- **Later** — "what did that pdf say about X?" pulls the saved item back into context; the tool loop can look it up too.
- The **Saved Info** page (sidebar ✦) lists everything: search, filter by kind, **Open original**, **Ask AURA about it** (she explains it in the chat, out loud if voice is on), pin, re-read, delete.

Files live in `memory/saved_files/`, rows in the `saved_info` table.

### Install a planet from a key or a link

Paste an API key in chat — or say "install" with a GitHub, docs or model link — and AURA (`core/integrations.py`):

1. works out the service from the key's prefix or the link (unknown key → she asks which service, as a dropdown);
2. checks it live and lists what it offers, ranking free models first;
3. marks what each model is best at (Coding / Research / Chat / Vision / Background) and pre-ticks her pick;
4. asks you to confirm in a card — which models, which jobs, first pick or backup;
5. test-calls every ticked model; each one that answers **is born at the event horizon and spirals out to its orbit**, and the router uses it for exactly those jobs.

It's configuration, not generated code: almost every LLM API speaks the OpenAI chat-completions dialect, so an install records `{base URL, key, model, jobs}` and `ai_router` reads it. Known services: OpenRouter, Groq, Gemini, Mistral, Cerebras, GitHub Models, Hugging Face, NVIDIA NIM, SambaNova, Together, DeepSeek, OpenAI, Anthropic, xAI, Fireworks, Perplexity, Ollama and LM Studio (local), any OpenAI-compatible URL — plus Tavily / Brave / Serper, which install as **web search** for research questions. A key already in `.env` is reused when you only paste a link.

Keys never reach a model or the chat log: messages with a key are intercepted before the Director, stored masked (`gsk_…Wx9Q`), and the key itself stays in the local database. Retune or remove installed planets under **Models → Installed**.

### The floating orb

When AURA is out of sight — minimized, or another window is on top of her — a small always-on-top orb appears in the corner of the screen (`frontend/electron/orb.cjs`). It's a pocket version of the core: violet when idle, brighter while she thinks, pulsing while she speaks, cyan while the mic is live, and an amber mark if she said something while you were away (hover to read it).

- **Click** — AURA comes back to the front, and the orb steps aside.
- **Drag** — it glides to the nearest screen edge and remembers the spot.
- **Right-click** — size, *Keep the orb on screen*, *Hide until AURA is minimized again*, Quit.

It never takes focus from what you're doing, and it only hides once AURA is really visible — Chromium's occlusion tracking is the judge, not just the focus events.

---

## AURA Domain — the development OS

Enter it from Sanctuary's **Enter Workspace** button (portal transition), or hit any section in the left nav.

| Section | What it does |
|---|---|
| **Overview** | Real progress: buckets, per-feature bars, biggest blocker, recent events, git sync |
| **Sources** | Your GitHub link and document folders, re-read every time AURA opens. Open a repo here and it is cloned, ready to prompt |
| **Projects** | Create empty · import a local folder (reads code + git history) · clone a GitHub repo |
| **Code** | Real filesystem editor (file tree, tabs, quick-open) with **Build with AURA** underneath it |
| **Git** | Status, diff, branches, commit, push |
| **Tasks** | The generated board, grouped by feature. Commits close tasks themselves |
| **Notes** | Quick notes per project |
| **Terminal** | A real shell, scoped to the project folder |
| **Settings** | Nav order, density, accent, surface, connectors |

Nine sections, down from eighteen. The ones that went were either panels of
invented data or the same act split across two places — Build, Preview and
Review were all "do something to the code you have open", which is what Code
does now that you can talk to it.

Click any node anywhere — graph, board, timeline, a Research receipt — and the **node drawer** answers three questions: *why does this exist* (the causal chain back to the originating idea), *what's connected*, and anything else you type (grounded in the graph only).

### Build with AURA (the prompt bar under the editor)

Say what you want changed in the repo you're in. AURA works out which files it
touches, reads them, rewrites them, and stops — showing you the diff. Nothing
reaches disk until you approve it, and anything applied can be rolled back
whole.

```
you ask  →  AURA picks the files  →  reads them + what they import
         →  rewrites them  →  you read the diff  →  approve  →  written
                                                 └─ roll back any time
```

### Upgrading AURA itself

The same engine, pointed at AURA's own source. From the **Upgrade** page in the
sidebar, or just say it:

```
"upgrade yourself so the sidebar remembers my last page"
   → AURA reads its own code and writes the change
"what upgrades are pending?"       → the list
"apply it"                         → applied, restart to load it
"roll it back"                     → exactly as it was
```

Rails, because this one edits the thing that is running:

- **Nothing is written without an explicit yes.** A request produces a proposal, never an edit.
- **Backed up before it is applied**, so rollback restores the real bytes.
- **Refused if it would break.** Python is compiled, JSON is parsed, and a rewrite that keeps less than a third of a file is rejected as a truncated reply rather than applied — that check runs again at apply time, not just when the proposal is written.
- **Out of bounds:** `.env`, keys, the database, `.git/`, `node_modules/`, `venv/`, and anything outside the repo. A path that tries to escape the tree is dropped.

The old Code Review screen and its permission ladder are gone. They were
describing the same rule the proposal flow now enforces directly: what AURA
writes is a suggestion until you apply it, and applying it is a click you
make. Nothing escalates itself.

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
GET  /api/saved · /api/saved/{id} · /api/saved/{id}/file     Saved Info
POST /api/saved (link) · /api/saved/upload (base64) · /{id}/rescan
PATCH/DELETE /api/saved/{id}
GET  /api/integrations · /api/planets                       installed planets
POST /api/integrations/proposals/{uid}/identify · confirm · dismiss
PATCH/DELETE /api/integrations/models/{id} · DELETE /api/integrations/{id}
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

**Upgrades, reset and sources** (`system_api.py`)

```
GET    /api/upgrade/proposals            list (?scope=self|project&root=…)
GET    /api/upgrade/proposals/{id}       one, with every file's before/after
POST   /api/upgrade/propose              ask for a change — writes nothing
POST   /api/upgrade/proposals/{id}/approve · reject · rollback
DELETE /api/upgrade/proposals/{id}
GET    /api/upgrade/files · /api/upgrade/file      what AURA may read

GET    /api/system/reset                 the scopes you can clear
POST   /api/system/reset                 {scopes: [...], confirm: "RESET"}

GET    /api/sources                      what AURA keeps in step with
POST   /api/sources                      connect a GitHub link, folder or page
PATCH  /api/sources/{id}                 rename, or file it in a room
DELETE /api/sources/{id}
POST   /api/sources/{id}/sync · /api/sources/sync    one, or all of them
GET    /api/sources/repos                every repo across every GitHub source
POST   /api/sources/{id}/clone           bring a repo down to work on
```

---

## Layout

```
server.py              FastAPI app + WebSocket bridge + companion REST
domain_api.py          Domain REST (filesystem, shell, git, review, brain, connectors)
system_api.py          upgrades, reset, connected sources
core/
  patcher.py           AI-authored code changes: propose → approve → roll back
  sources.py           GitHub / document sync, and the context a room gets
  system_reset.py      scoped wipes, database backed up first
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
