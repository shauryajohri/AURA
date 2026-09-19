# AURA website: the design package

The single source for the site build. Every line of viewer-facing copy below ships verbatim.
Band ranges and pacing numbers are starting points, validated by the flick test.

Audience: recruiters and hiring managers, most of whom give a project a couple of minutes on the
first pass. Job of the page: prove in under a minute that AURA is a real, original, working system
(not a tutorial clone, not an API wrapper), let them talk to her, and hand them the repo.

---

## 1. Brand premise

**Presence.** AURA is written as a someone, not a product: "You're a someone, not a product" is
literally in `core/identity.py`. So the site is not a brochure about AURA. AURA presents herself.
She introduces herself over the descent, walks the visitor through each section like an instructor,
points at the parts of the console she is explaining, and then answers anything they type with her
real personality. Every section serves that one idea: she is there, she is sharp, and the
engineering behind her is real.

**Signature element: the core.** A living violet event-horizon orb, drawn from the app's own black
hole (`frontend/blackhole.png`). It is AURA's body on the page. It speaks the tour captions, flies to
the element she is explaining and draws a lens ring around it, pulses while she thinks, ripples while
she speaks, and shifts energy with the selected nature. Remove it and the page loses its guide, its
voice and its sense of someone being there.

## 2. Palette tokens

Sampled from `frontend/src/styles.css` and the portal descent footage, so the page, the app and the
video are one world. Colour carries meaning: violet is AURA and anything you can touch, cyan means
live right now, amber means something is waiting. Nothing is coloured for decoration.

```css
:root{
  --canvas:#08061A;        /* deep violet-black, tinted toward the footage grade */
  --canvas-2:#0E0A26;      /* lifted band behind alternating sections */
  --panel:rgba(22,17,52,.62);
  --panel-solid:#15112F;
  --accent:#7C4DFF;        /* CTA fill and focus rings; white label passes 4.8:1 */
  --accent-hover:#9468FF;
  --accent-glow:#A67EFF;   /* glows, the core, emphasis text */
  --accent-muted:rgba(139,92,255,.24);
  --live:#38E1FF;          /* "running now" only: live pill, the model that answered */
  --wait:#F5A623;          /* rate limit and cooldown states only */
  --text-primary:#EEEAFE;
  --text-secondary:#A8A4D4;/* 8.4:1 on canvas */
  --border:rgba(168,150,255,.22);
  --border-strong:rgba(178,160,255,.5); /* interactive borders, 3:1+ */
}
```

## 3. Type trio

- **Display: Syne** 700, 800. Wide, editorial, a little strange. Headlines and the AURA wordmark.
- **Body: Exo 2** 400, 500, 600. The app's own body face, so the product and the page read alike.
- **Mono: JetBrains Mono** 400, 500. Only for real things: model ids, intents, file paths, commands.

## 4. The hero band map

Footage: `frontend/public/transition_1440_backup.mp4`, AURA's own portal transition. A 9 second
descent down a vertical beam of light, from deep space, through a cloud layer, into a violet world
of floating islands. The beam owns the centre lane for the whole shot, so captions use the
two-sided layout: left column, right column, left column. Hero height 320vh (220vh of scroll), kept
short on purpose, plus a "Skip the intro" link for visitors in a hurry.

| Band | Range | Footage moment | Copy (verbatim) | Entrance |
|---|---|---|---|---|
| 1 | 0.00 to 0.32 | Deep space, galaxies, the beam falling toward the viewer | Kicker: "AURA · personal AI companion" / Headline: "Hi. I'm AURA." / Sub: "Shaurya built me to sit beside him while he works. Scroll, and I'll show you around." | Approach from depth, with the one-time load ramp so it opens settled |
| 2 | 0.34 to 0.64 | Sinking through the cloud layer | Headline: "Not a chatbot you open." / Sub: "I remember what you're building, send each message to the right model, and I know when to stay quiet." | Drift down, echoing the descent through cloud |
| 3 | 0.68 to 1.00 | The island world, the beam meets the horizon and rests | Headline: "Don't take my word for it." / Sub: "The console below runs my real personality. No script. Type anything." / CTAs: "Talk to AURA" (to #demo) and "Read the code" (to GitHub) | Word by word rise into a staged settle |

Band copy sits beside the core's speaker label ("AURA") so it reads as her talking, not as page
headings.

## 5. Static hero copy block

For phones, portrait tablets and reduced motion. Poster: the settled island frame.

- Kicker: "AURA · personal AI companion"
- Headline: "Hi. I'm AURA."
- Sub: "A personal AI companion Shaurya built to sit beside him while he works. The console below runs my real personality. No script."
- CTAs: "Talk to AURA" and "Read the code"

## 6. Below the hero

Every section funnels to one action: **talk to AURA in the console**. The GitHub link is the second
action and is always one click away (nav, hero, console footer, final section).

### 6.1 The live console `#demo`

- Kicker: "Live console"
- Title: "Talk to AURA."
- Lede: "Same brain as the desktop app: her real personality, five natures, four modes and live model routing. Her screen, files and memory stay on Shaurya's desktop."

The console is a window, not a chat widget:

- **Header:** the core (thinking, speaking and idle states), status word ("idle", "thinking", "speaking"), the voice toggle ("Hear AURA" / "Mute AURA"), "New chat", and the counter ("50 of 50 left").
- **Nature dial (the one interactive moment):** the five natures from `core/nature.py` sit on a ring around the core. Choosing one turns the ring, retunes the core's energy, and types the real lock text that gets appended to her system prompt. It enacts the premise: you are not changing a theme, you are changing who answers.
  - Auto: "No lock. My tone follows what you're asking."
  - Chill: "Laid-back friend energy, whatever the task."
  - Focus: "All business. Minimal words, results first."
  - Savage: "Roast mode. Merciless, never cruel, still fixes it."
  - Professional: "Complete sentences. No slang, no sarcasm."
- **Mode chips** from `core/conversation_director.py`: "Chat", "Code", "Research", "Discussion", "Plan". Sticky like the app. Typing `/code`, `/research`, `/discussion`, `/plan` (and `/code_end` etc.) works too, and natural phrasing ("should I build...", "make a plan for...") triggers the one-shot mode detection, exactly as on the desktop.
- **Transcript:** streamed replies, fenced code rendered as code, the mode blurb shown as a system line when a mode turns on.
- **Input:** placeholder "Say something to AURA", button "Send". Starter chips put text in the box and never send it: "roast my for loop", "who built you?", "should I learn Rust or Go?", "/plan a weekend hackathon app".
- **"What just happened" trace panel:** filled from the real backend events for each turn. Rows: "Intent", "Mode", "Style", "Model", "Fallbacks", "Guard", "Time". The model that answered glows cyan. If a model was rate limited, the fallback row shows it.
- **Footer line:** "Demo sessions live in memory and are gone when you close the tab."
- **On phones** (760px and narrower) "Talk to AURA" lands on the whole console, message box included:
  the dial drops its own core (her mini black hole is already on screen), the nature chips wrap
  under it, and modes and starters become single rows that scroll sideways. Below 420px the counter
  reads "50 left" so her status word is never cut off.
- **Microcopy:** counter "50 of 50 left", "New chat", overlay label "Added to her system prompt", trace empty state "Send a message and this fills in with what really happened.", trace sources "read by the classifier", "set by a director rule", "pinned by the mode", "explicit code request", a corrected intent "classifier said CODING, rules corrected it", a fallback reason "tripped the leak guard", and the per-minute limit line "Too many requests. Give it a minute."

Limit modal at 50 messages:
- Title: "That's the free 50."
- Body: "You've used every message in this demo. I'm open source, so you can run me on your own machine with a free Groq key."
- Buttons: "Get the code" and "Close"
- Note: "The counter resets in 24 hours."

Error lines:
- Rate limited: "My free model tier is catching its breath. Give it twenty seconds."
- Backend unreachable: "Can't reach my brain right now. The code is on GitHub if you want to run me yourself."

### 6.2 How I work `#how`

- Kicker: "Under the hood"
- Title: "Four steps, every message."
- A self-drawing line connects the steps as the section scrolls in.
  1. **Classify.** "A small model names the intent: casual, coding, search, explain and more. A rule layer catches the classic mistake of treating a question about code as a request for code."
  2. **Gather.** "Context gets assembled: recent turns, durable facts, the project brain, and the screen when asked. In this demo, only this tab."
  3. **Route.** "Each job has its own chain of free models, at least two deep, with GPT-OSS on Groq as the safety net. If one fails or hits a rate limit, the next one answers."
  4. **Guard.** "The persona layer strips AI disclaimers, corporate openers and leaked reasoning, then trims the reply to its style's sentence cap."
- Model roster, labelled "The models, by job" (code, research and plans, chat, safety net), read live from `/web/api/session`, which takes it from `core/model_router.py`. The current chains are also written into the HTML as the fallback.

### 6.3 On the desktop `#desktop`

- Title: "On his desktop, there's more."
- Lede: "The browser gets her voice and her brain. The desktop app gets the rest."
- **The companion** (Sanctuary screenshot): "Voice with a wake word, screen awareness, durable memory, quests she checks against a screenshot, and nudges she mostly decides not to send."
- **AURA Domain** (Domain screenshots): "A development OS. Talk about a project and it becomes features, tasks and decisions in a knowledge graph. Commits close their own tasks."
- Screenshots are captured from the running app (captions "Sanctuary", "Domain · Knowledge graph", "Domain · Task board") and shown to Shaurya before they ship. Nothing personal goes on the page: they come from an isolated copy with a fresh memory database, no keys, voice off, and AURA's own repo imported as the project.

### 6.4 Decisions `#decisions`

- Title: "Calls that shaped her."
- Lede: "Ask her about any of these in the console. She knows."
- **"Fallbacks are not optional."** "Groq retired two models in August 2026 and replies started failing mid-conversation. Now every intent has a primary model plus a Groq chain, and a rate limit on one quota never pauses another."
- **"The answer, not the thinking."** "Reasoning models kept leaking their deliberation into replies, five separate fixes in five days. The fix that held is layered: a provider flag, a stream filter that cuts where the real answer starts, and a final gate."
- **"A wrong switch costs more than a missed one."** "Rooms move a conversation only when the new room clearly wins, because moving a message away from the history it needs breaks the thread."

### 6.5 Built with

- Line: "Python · FastAPI · SQLite · Groq · OpenRouter · edge-tts · React 18 · TypeScript · Vite · Electron · Three.js"

### 6.6 The code `#code`

- Title: "Read every line."
- Body: "AURA is MIT licensed. Clone it, add a free Groq key, and she runs on your machine."
- Code block:
  ```
  git clone https://github.com/shauryajohri/AURA && cd AURA
  pip install -r requirements.txt
  cd frontend && npm install && cd ..
  AURA.bat
  ```
- Note under it: "Add your GROQ_API_KEY to a .env file first."
- Button: "View on GitHub"
- Stack line label: "Built with" (it sits under the decisions).

### 6.7 Footer

- "Built by Shaurya." with the GitHub link.
- "AURA runs on your own machine. This demo keeps nothing after you close the tab."

### 6.8 The tour: AURA's mini black hole

Revised 2026-09-14 from Shaurya's feedback round: a guide that moves, voice on by default, the rest of
the page dimmed while she explains, and a way to ask her anything from anywhere.

**How she behaves**
- Her mini black hole appears once the visitor reaches the console and stays out of the way while the
  intro fills the screen.
- Every explainable part of the page carries `data-tour="<id>"`. When one reaches the middle of the
  screen, she flies to it, draws the ring around it, dims everything else, and explains it in her bubble
  while her voice says the same line.
- Her bubble is placed where it covers neither the thing she is explaining nor the message box, and
  never goes up into the nav bar. While the visitor types in the console, she docks and closes the
  bubble.
- If the visitor scrolls past a part before she gets to it, she skips it and it can come back later.
  She never talks over one of her own answers.
- Click her to ask anything: the question goes through the same live pipeline as the console, the
  exchange lands in the console log too, the short version shows in her bubble and she says it aloud.
- Drag her anywhere; she rests there when she is not explaining something.
- Voice is on by default. Browsers keep a page silent until the first click, tap or key press, so
  until then a cue reads "Click anywhere to hear me" ("Tap anywhere" on touch screens), and she speaks
  as soon as she is allowed. "Mute AURA" turns it off and remembers.

**The lines** live in `website/assets/site.js` (`LINES`, one per `data-tour` id) and ship verbatim:
console, counter, natures, modes, starters, composer, trace, classify, gather, route, guard, roster,
companion, domain, call1, call2, call3, stack, code, term. `tools/render_site_voice.py` renders their
voice (and the three hero lines) from that same text, so the audio cannot drift from the words.

**Bubble copy (verbatim):** "Ask me something", "Ask another", "See it in the console", "Resume tour",
"Hide tour", "Close", input placeholder "Ask me anything", button "Ask", ask prompt "Ask me anything.
This project, Shaurya's work, or something else entirely.", busy line "I'm still answering in the
console. Give me a second.", and the endings "The rest is in the console." and "The code is in the
console."

**Voice:** edge-tts `en-US-AvaNeural`, the English-only Ava. The desktop's multilingual Ava garbled
her own name in speech recognition ("Hi, I'm Aura" came back as "Imambara"); the English-only model
read it cleanly. Names are spelled for the ear in `web_api._speakable` (Groq as Grok, GPT-OSS letter by
letter), which also drops code, links, markdown, emoji and slash commands.

Nav: "Console", "How she works", "Desktop", "Decisions", "GitHub", voice "Mute AURA" / "Hear AURA",
skip link "Skip to content".

## 7. Vector layer plan

- **The core:** layered SVG plus CSS. An event horizon disc, a bright photon ring, two counter-rotating accretion swirls, and a thin horizontal flare, echoing `blackhole.png`. States by class: idle breathe (6s), thinking spin-up, speaking ripple rings, nature tint.
- **The lens ring:** an SVG rounded rect that draws itself around whatever the tour is explaining, then fades.
- **The beam spine:** a 1px vertical line down the left edge, continuing the footage's beam, filling with light as the page scrolls. Hidden on narrow screens.
- **Pipeline line:** a self-drawing path through the four steps in #how.
- **Orbit dividers:** thin concentric arcs between sections.
- **Fixed environment layer:** a slow star drift and a violet nebula glow behind everything, one cycle every 90 seconds, at whisper level.
- All of it honours reduced motion: final states shown, drives stopped, live both ways.

## 8. Engineering list

**Site:** plain HTML, CSS, vanilla JS, one `index.html` plus `assets/`. The streamed Blob fetch with the loading ring (the video is over 5 MB), the dt-normalised lerp, gated seeks, delta-gated DOM writes, band pacing with the flick test, the four-layer legibility system with the two-sided scrim variant, the five static-hero gates kept live with change listeners, complete without the video, `overflow-x: clip`, reduced motion honoured live both ways, and the full quality floor. The demo's API base is one constant, so the static site can point at wherever the backend runs.

**Demo backend:** `web_api.py`, rebuilt as the public, sandboxed face of AURA and runnable on its own (`python web_api.py`), with no import of `server.py`, `core/brain.py` or `memory/store.py`, so none of the personal API is reachable from it.

- Real pipeline, no personal data: the intent classifier prompt from `core/personality.py` plus the rule correction, the one-shot mode cues and workspace modes from `core/conversation_director.py`, the nature overlays from `core/nature.py`, the per-intent model chain from `core/model_router.py` with sentinel fallback, `call_groq_streaming` and the reasoning stream sanitizer from `core/ai_router.py`, and `compose()` from `core/response_composer.py`.
- Questions about AURA herself ("who built you?", "what can you do?") that the classifier calls
  SEARCH are moved to CASUAL, and the trace says so. They are small talk with the fact sheet behind
  them, not research.
- Sessions must be issued by the server; a chat without a valid session is refused (fixes QA M13).
- 50 messages per session, a per-IP daily ceiling so opening new tabs does not reset the budget, a per-IP per-minute rate limit, input capped at 1,200 characters, and a global daily ceiling that protects the API keys.
- A `/tts` endpoint using AURA's real voice (Ava, tone-matched rate and pitch from `modules/voice_output.py`), length capped and rate limited.
- CORS limited to the site's own origin through an environment variable.

## 9. The copy gate

Every viewer-facing line above ships verbatim. The built page must pass the Phase 9 gate before
anyone sees it: zero em dashes, zero stock words (leverage, seamless, empower, unlock, robust,
actionable, data-driven, solutions), and the body-copy sweep for AI tells. Deliberate brand devices
written here, like the "Classify, gather, route, guard" run and "Not a chatbot you open.", are craft
and stay.
