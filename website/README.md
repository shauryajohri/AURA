# The AURA site

AURA introduces herself over her own portal descent, then hands the visitor a
live console running her real pipeline, then the facts and the repo. As the page
scrolls, her core walks the visitor through each part and draws a lens around
what she is explaining. The design decisions and every line of copy are in
[`docs/WEBSITE_DESIGN.md`](../docs/WEBSITE_DESIGN.md).

No framework, no build step.

```
website/
  index.html              the page and all of its copy
  assets/site.css         the design system
  assets/site.js          hero scrub, AURA's tour, the live console
  assets/hero-scrub.mp4   the portal descent, re-encoded for scrubbing
  assets/hero-*.jpg       first frame, settled frame (static hero), og card
  assets/voice/*.mp3      her intro and tour lines, pre-rendered in her voice
  assets/shots/*.jpg      real screenshots of the desktop app
```

## Run it

```bash
python web_api.py
```

Then open <http://127.0.0.1:8770>. `WEB.bat` does the same on Windows. One
process serves the page and the demo API, so nothing else is needed.

Double-clicking `index.html` also works, but only as a preview of the static
state: browsers block `fetch` on `file://`, so the hero shows its still image and
the console reports that it cannot reach her.

## The demo backend

`web_api.py` is the public, sandboxed face of AURA. It runs the same pipeline as
the desktop app (the ConversationDirector, the intent classifier and its rules,
the five natures, the four workspace modes, the model chain with fallback, the
reasoning-leak guard and the persona layer) and never imports `server.py`,
`core/brain.py` or `memory/store.py`. Nothing personal is reachable from it.

What it adds for the open internet:

| Guard | Default | Env |
|---|---|---|
| Messages per visitor (session and IP, rolling 24h) | 50 | `AURA_WEB_MSG_LIMIT`, `AURA_WEB_IP_DAILY` |
| Requests per IP per minute | 20 | `AURA_WEB_IP_PER_MIN` |
| Model messages per day, everyone | 3000 | `AURA_WEB_DAILY_CAP` |
| Voice clips per IP per day | 200 | `AURA_WEB_TTS_DAILY` |
| Allowed CORS origins | localhost | `AURA_WEB_ORIGINS` |

Instant replies (mode switches, `/help`, her clarifying questions) do not count
against the 50. A failed turn is refunded. Starting a new chat does not reset the
budget.

The leak gate: replies from the free OpenRouter reasoning models are held back
until their opening reads like an answer. One that recites its instructions is
re-routed to the next model in the chain, and the console's trace shows it.

## Deploying

Two pieces, and only one of them is static.

1. **The site.** Upload the contents of `website/` (`index.html` and `assets/`)
   to any static host.
2. **The backend.** Run `web_api.py` on anything that runs Python 3.10+, with the
   packages from `requirements.txt` and `requirements-web.txt` and a
   `GROQ_API_KEY` (plus `OPENROUTER_API_KEY` for the OpenRouter lanes).

Then connect them:

- In `index.html`, set `<meta name="aura-api" content="https://your-backend/web/api">`.
- On the backend, set `AURA_WEB_ORIGINS=https://your-site` and, behind a reverse
  proxy, `AURA_WEB_TRUST_PROXY=1` so the per-IP limits see real addresses.
- Patch `og:url` and `og:image` in `index.html` with the live absolute URL.

Never expose `server.py`. It is the private desktop bridge and has no auth
(see `QA_REPORT.md`, C1).

## Editing

- **Copy** lives in `index.html`. AURA's tour lines and the nature notes live at
  the top of the tour and console sections in `assets/site.js`.
- **Hero timing** is `data-a` and `data-b` on each `.band`: scroll progress from
  0 to 1 through the intro.
- **Changed a spoken line?** Re-render its clip so her voice matches the text.
  The script reads the words from `index.html` and `site.js` and speaks them in
  the web voice (`en-US-AvaNeural`):

  ```bash
  python tools/render_site_voice.py tour-code
  ```

  With no names it renders every clip and removes ones no line uses any more.

- **Re-encoding the hero** (from `frontend/public/transition_1440_backup.mp4`):

  ```bash
  ffmpeg -i transition_1440_backup.mp4 -vf scale=1600:-2 -c:v libx264 -crf 22 -preset slow -g 8 -keyint_min 8 -pix_fmt yuv420p -movflags +faststart -an website/assets/hero-scrub.mp4
  ```

  The short keyframe interval is what makes scrubbing smooth. Update
  `VIDEO_BYTES` in `site.js` if the size changes.
