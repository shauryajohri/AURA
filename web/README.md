# AURA on the web

The public face of AURA: a landing page plus a **sandboxed** in-browser demo of
the basics, so someone can try AURA without downloading it.

```
web/
  index.html          landing page + demo shell (no build step, no CDN)
  styles.css
  app.js
  demo_project.json   the sample Project Brain the preview serves
../web_api.py         the /web/api/* backend + the static mount
```

## Run it

Nothing extra to install — `server.py` serves both.

```bash
python server.py
# landing page   → http://127.0.0.1:8760/
# demo API       → http://127.0.0.1:8760/web/api/session
```

The Electron app is unaffected: it only ever calls `/ws` and `/api/*`.

## What the demo can and cannot do

`/ws` is AURA's *private* bridge — real ConversationDirector, real SQLite,
screen access, the coding permission gate. None of that is exposed here.
`/web/api/*` is a separate surface that:

- **never writes to `memory/store.py`** — a visitor's turns live in a RAM
  session object that expires after `AURA_WEB_TTL_MIN` minutes,
- **never reads your personal memory** — the demo's facts and notes are the
  visitor's own; the Project Brain preview serves `demo_project.json`,
- **has no tools** — no filesystem, shell, git, screen or voice,
- **is budgeted** — per-session message cap, per-IP rate limit, and the small
  model by default, so a demo tab can't eat the quota the desktop app needs.

The page degrades gracefully: if the backend is unreachable (opened as a static
file, or the server is down) the demo switches to an offline preview with
scripted replies rather than showing errors.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `AURA_WEB_MODEL` | `openai/gpt-oss-20b` | model id for demo chat |
| `AURA_WEB_MSG_LIMIT` | `20` | messages per visitor session |
| `AURA_WEB_IP_PER_MIN` | `30` | requests per IP per minute |
| `AURA_WEB_TTL_MIN` | `45` | idle session lifetime |
| `AURA_WEB_LIVE_DOMAIN` | unset | `1` serves the **real** Project Brain — self-host only |
| `AURA_WEB_SITE` | `1` | `0` skips mounting the static site |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/web/api/session` | handshake: session id, limits, model, capabilities |
| POST | `/web/api/chat` | SSE stream — `state` → `chunk`* → `done` \| `error` |
| POST | `/web/api/reset` | wipe this session |
| GET | `/web/api/memory` | session facts + notes |
| POST | `/web/api/memory/facts` | remember a fact |
| DELETE | `/web/api/memory/facts/{id}` | forget one |
| POST | `/web/api/memory/notes` | save a note |
| GET | `/web/api/domain/projects` | Project Brain preview: project list |
| GET | `/web/api/domain/project/{id}` | overview, features, blocker, timeline, graph |

Sessions are identified by the `X-Aura-Session` header, which the server
returns on `/session` and `/chat`.

## Deploying it publicly

`server.py` binds `127.0.0.1` on purpose. If you put this on the internet:

1. Put it behind a reverse proxy with TLS, and disable proxy buffering so SSE
   streams (`proxy_buffering off;` in nginx).
2. Keep `AURA_WEB_LIVE_DOMAIN` unset — the sample graph is what strangers
   should see.
3. Run a **separate** process from your personal instance, with its own API key
   and its own (empty) `memory/` directory. The demo doesn't read that database,
   but a second process means a bug can't reach it either.
4. Tighten CORS: `server.py` currently allows `*` because the Electron shell
   loads from `file://`.
