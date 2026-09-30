# AURA — Full App QA Report

**Date:** 2026-09-11 · **Commit tested:** `3b111a2` (Tool layer) · **Scope:** backend (FastAPI, WebSocket, every REST route), frontend (all Home pages + all 19 Domain sections), test suite, static checks.

**How it was tested:** existing test suite · frontend `tsc --noEmit` · an AST undefined-name scan · a scripted sweep of ~150 API calls (valid, edge, malformed inputs) · scripted WebSocket chat sessions with real LLM calls · click-through in a browser against the Vite UI.
All live testing ran against an **isolated copy** of the repo and database. Your real `memory/*.db`, `*.json` and `.aura_index.pkl` were hash-checked afterwards and are byte-identical.

Legend: **[live]** = reproduced against the running app · **[code]** = confirmed by reading the code path.

---

## Summary

| Severity | Count | Headline |
|---|---|---|
| Critical | 3 | Any website you visit can run shell commands on your PC and read your API keys |
| High | 11 | Code answers say "lost my train of thought"; code never saved to history; reasoning leaks; privacy toggles do nothing; room switches invisible |
| Medium | 15 | Domain tools ignore the open project; junk projects; stale code index; WebSocket crash; render-loop crash |
| Low | 10 | Counters, stale tests, validation gaps, launcher |

Good news: every file compiles, **zero undefined names**, `tsc` is clean, all 19 Domain sections and all Home pages render with **no JS errors**, and every Critical/High item from the July `DEBUG_REPORT.md` has been fixed.

---

## CRITICAL

### C1. Drive-by remote code execution + file theft from any web page [live]
`server.py:83-85` sets `CORSMiddleware(allow_origins=["*"])`, and **no endpoint has any authentication**, including `POST /api/domain/shell/run` (runs arbitrary commands, `core/domain_shell.py:122`) and `/api/domain/fs/read|write|delete`. Starlette's `req.json()` parses a `text/plain` body, so a page can send a CORS "simple request" with no preflight.

Reproduced with a foreign `Origin` header and `Content-Type: text/plain`:
- `shell/run {"command":"echo AURA_POC_COMMAND_EXECUTED"}` returned `200`, `"output":"AURA_POC_COMMAND_EXECUTED"`, `access-control-allow-origin: *`.
- `fs/read?path=…/.env` returned the full file, readable cross-origin: `GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_*, MS_CLIENT_SECRET…` (only key names were printed during the test).

Any site open in your browser while AURA runs can do this. The git `confirm: true` guard doesn't help here, because it's just a flag the client sends.
**Fix:** generate a random token at startup and require it on every `/api/*` route and on `/ws` (Electron passes it through `preload.cjs`). Restrict CORS to `http://localhost:5173` and the `file://` origin. Also reject requests whose `Host` isn't `127.0.0.1:8760`/`localhost:8760` (DNS rebinding).

### C2. Reflected XSS on AURA's own origin [live]
`domain_api.py:407-429`: the OAuth callback interpolates the `error` query param (and `provider`, and exception text) into HTML unescaped.
`GET /api/connectors/callback/github?error=<img src=x onerror=alert(document.domain)>` renders the tag verbatim. Script running on `127.0.0.1:8760` can call every API same-origin, so this still works after C1's CORS fix.
**Fix:** `html.escape()` every interpolated value, or return a static page.

### C3. `fs/delete` will `rmtree` your home folder or a whole drive [code]
`core/domain_fs.py:258-267` + `_PROTECTED` (`:31-34`): only `C:\Windows` and `Program Files` are blocked. `delete("C:\\")` or `delete("C:\\Users\\shaur")` passes the guard and calls `shutil.rmtree`. Combined with C1, that makes it remotely reachable. (Also, the prefix check means `c:\windowsfoo` is treated as protected.)
**Fix:** refuse drive roots, the home directory itself, and any path above a workspace root. Consider sending deletes to the Recycle Bin (`send2trash`).

---

## HIGH

### H1. Nearly every code answer says "Hmm — lost my train of thought. Say that again?" above the code [live]
`core/brain.py:1193` defaults the chat line to `"Here's the code:"`. Then `core/response_composer.py:236-237` (coding style) strips any leading `Here's the …:` / `Here is a …`, leaves an empty string, and `:288-289` swaps in the fallback line. Verified directly: `compose_text("Here's the code:", "CODING", …)` and `compose_text("Sure! Here is a function that reverses a string.", …)` both return the fallback. Live result for "write a python function that reverses a string": `Hmm — lost my train of thought. Say that again?` followed by correct code.
**Fix:** in `compose_text`, if shaping empties a non-empty input, keep the original; and don't compose the placeholder at all.

### H2. Code blocks are never saved: reopen a chat and the code is gone [live]
`core/brain.py:1202-1203` saves only `chat_msg`; the code goes to the socket via `on_code` and nowhere else. After reload, the coding turn shows only "Hmm — lost my train of thought…".
**Fix:** save `chat_msg + fenced code` (the same string `server.py` sends in `done`).

### H3. Chat history shows the internal compiled prompt as *your* message [live]
Explicit code requests take the **PLAN → BUILD** lane. `server.py:1308` calls `process_streaming(res.prompt, …)`, and the brain saves `query` (now the compiled prompt) as the user turn (`brain.py:1202/1264`). Reopening the chat shows `YOU: Task: … Execution Plan: □ 1. Analyze … Requirements: …`. The comment at `server.py:1290` says users should never see it. It also pollutes `_history` and the chat title.
**Fix:** pass the original text through and save that as the user turn (e.g. a `display_query` parameter).

### H4. Chain-of-thought reaches the user [live]
Two leaks in about 7 real chat turns, both from **Nemotron 3 Super (free)**:
- *Streamed:* for "what is the kanji for water…" the live bubble streamed deliberation (`" That would be mentioning activity? … The background says 'You are in the Japanese Study room'…"`). Then `done` replaced it with "Lost my train of thought there — say that again?", so the question was never answered. Cause: `brain.py:1217-1219` forwards raw chunks before sanitizing.
- *Persisted:* "what is 2 plus 2? answer with just the number" was saved as `answer with just the number". So we should output just "4". That's one "sentence"? … Probably not.` The log reported `reasoning leak repaired`, so the final sanitizer approved leaked text.

Also worth noting: the room brief conflicts with the "never mention the user's activity" rule, and that's what the model was deliberating over.
**Fix:** lock or deprioritize Nemotron for chat. Buffer the first N characters before streaming. Add both transcripts to `test_reasoning_leak.py`.

### H5. Failed turns disappear from history [live]
Every early return in `process_streaming` (`brain.py:1222-1225` rate limit/connection, `:1241-1245` leak discard) happens **before** `store.save_conversation`. The kanji question and its reply exist nowhere in the DB, so after a reload your question is gone.
**Fix:** save the user turn first (or in a `finally`), then save whatever reply was shown.

### H6. Privacy toggles (and 14 other settings) do nothing [code]
`privacy.screen_reading` and `privacy.store_conversations` are defined (`frontend/src/stores/settingsStore.ts:52-53`) and editable (`SettingsOverlay.tsx:50`), but **no backend or frontend code reads them**. Turning off "Screen Reading" doesn't stop screen OCR from being sent to cloud models, and turning off "Store Conversations" doesn't stop storage. The panel also renders both as `0`.
The same is true (zero consumers) for `behavior.proactive`, `behavior.interrupt_work`, `dev.verbose_logs`, `dev.show_intents`, `experimental.plugins`, `experimental.cloud_sync`, `voice.sensitivity`, `voice.wake_word`, `voice.noise_suppression`, `anim.enabled`, `anim.intensity`, `anim.reduced_motion`, `wallpaper.video`, `wallpaper.dim`.
**Fix:** wire the two privacy keys first (gate `screen_reader`/proactive observation and `save_conversation`). Hide the rest until they're implemented.

### H7. Room auto-switches are invisible, and the composer pill goes stale [live]
The server broadcasts `{"type":"room", …, "note":"Switching us to Japanese Study — I'll keep this thread there."}`, but `frontend/src/hooks/useAuraSocket.ts:123-168` has no `room` case, and `types.ts` doesn't declare it. Live: after a Japanese question the backend was in **Japanese Study** while the pill still said **Coding**. No note was shown, and the dock kept the old chat's transcript while the backend wrote to a different chat. The rooms commit says an invisible context change is the one thing that must not happen.
**Fix:** handle `room`. Push the note as a bubble, reload that chat's turns (`loadTurns`), and refresh the pill.

### H8. Messages sent from the Chats page never appear there [live]
`frontend/src/views/ChatsPage.tsx:153-158` sends through the shared socket, but the transcript only reloads when `activeChat` changes (`:59-66`). Live: I sent "what is 2 plus 2?", the backend answered and saved it, and the page still said "4 messages".
**Fix:** refetch on the socket's `done`, or render from the socket's `turns` while the page is open.

### H9. Slash commands go through the room router [live]
`server.py:1248` runs `_route_room(text)` before the Director handles the text. `/code_end` matched the Coding room's keywords, so the chat was moved and history reset.
**Fix:** skip routing when `text.startswith("/")`.

### H10. The code-search index is 21% stale backup code and never refreshes mid-session [live]
- `modules/project_context.py:40` `SKIP_DIRS` doesn't exclude `_backup_20260827_194650/`, `_to_delete/`, `frontend/memory/`. Your real `.aura_index.pkl` has **307 of 1,480 chunks** from old copies of `brain.py`, `proactive.py`, `store.py`, etc., so AURA can answer from outdated code.
- `_ensure_index()` (`:174-176`) builds once per process. Edits made during a session are never re-indexed.
- The first code question pays for the model load and indexing inside the chat turn. One turn took **92s**, 78s of it in `search_code`. That was on a fresh copy, so this is the worst case, but some load cost happens in every session. The answer also described the wrong file (`tool_loop.py` "defines run_tool"; it only calls it).
**Fix:** exclude those dirs, re-check mtimes on each search (it's cheap), and prewarm the embedding model at startup on a thread.

### H11. The chat dock is blank on launch while AURA remembers the hidden chat [live/code]
`useAuraSocket.ts:60` starts `turns` empty, and nothing loads the active chat on mount. The backend still feeds that chat into AURA's context. After a restart you see "Say something to begin", but she answers with context you can't see.
**Fix:** on connect, `getChats()` → `getChatMessages(active)` → `loadTurns`.

---

## MEDIUM

| # | Issue | Where | Evidence |
|---|---|---|---|
| M1 | Curiosity loop ignores **Auto-chat off**. Only `proactive.py` reads `autochat.enabled` | `core/curiosity_engine.py:313-351` | [code] |
| M2 | Domain Git/Build/Terminal/Code ignore the open project. They default to your **home folder**, so Git shows "not a git repository" with AURA open. Each `useWorkspaceRoot()` caller also has its own state (no sync) | `frontend/src/components/Domain/useWorkspaceRoot.ts:16-34` | [live] |
| M3 | Planning board and AI Agents show **hardcoded seed data** ("Relationship surfacing…", "active thought: Implement Domain workspace shell") no matter which project is open. They're a separate localStorage store from the Project Brain | `frontend/src/stores/domainStore.ts:334` | [live] |
| M4 | Wrong planet lights up. `openai/gpt-oss-120b`/`-20b` hit `includes("gpt")` and light **GPT-4o** (display-only) instead of GPT-OSS | `useAuraSocket.ts:31-44` | [code] |
| M5 | Importing a **nonexistent folder** returns `ok:true` and creates a junk project (visible as "nope" in Projects) | `domain_api.py:533-549` | [live] |
| M6 | `plan`/`capture` into a **nonexistent project id** returns `ok:true` and writes orphan nodes. `progress` for a missing project also returns `ok:true` | `domain_api.py:585-632` | [live] |
| M7 | WebSocket drops the whole connection on a malformed frame. `{"text":123}` makes `.strip()` raise and the outer `except` closes the socket. Any unexpected exception in `_dispatch` does the same | `server.py:1345`, `:1354` | [live] |
| M8 | Black-hole render loop dies permanently. `slotR()` goes negative when the window reports 0×0 (minimized/hidden), `arc()` throws `IndexSizeError`, and since `requestAnimationFrame` is scheduled at the end of `draw` it never reschedules | `BlackHole.tsx:152, 590-591, 799` | [live] |
| M9 | `error` frame handler runs `pushMessage` before `finishStream`, so a partially streamed bubble keeps its blinking caret forever | `useAuraSocket.ts:164-166` | [code] |
| M10 | 500 errors on bad input: non-numeric `target_minutes` (quests, promote), `minutes` (adjust), `timeout` (shell/run), malformed/empty JSON (tasks), top-level list (settings) | `server.py:279,325,575,900,988`, `domain_api.py:130` | [live] |
| M11 | Deleting every room **resurrects the 3 defaults** with new ids (reseeds whenever the table is empty) | `memory/store.py:1711` | [live] |
| M12 | Quest time can't be removed. `add_quest_seconds` ignores `seconds <= 0`, so `/adjust` "remove minutes" silently does nothing, and the UI only has `+15m`, so misclicks are permanent | `memory/store.py:1443-1444` | [live] |
| M13 | Web demo's 20-message budget is bypassable. Any request without `X-Aura-Session` gets a fresh session. It's mounted on the same server as the personal API, so exposing the demo publicly also exposes C1 | `web_api.py:132-144` | [code] |
| M14 | Tool-loop echoes args as a Python dict repr (`{'query': 'x'}`). If the model copies it, `json.loads` fails and the literal text becomes the search query | `core/tool_loop.py:101` | [code] |
| M15 | Room router files coding questions into the wrong room. After a Japanese question, "in the AURA codebase, what does core/tool_loop.py do?" stayed in Japanese Study and got titled there | `core/room_router.py` | [live] |

---

## LOW

- **L1.** `PUT /api/links/{id}` stores `javascript:` URLs and blank name/url unvalidated. `POST` normalizes them. Mostly neutralized by Electron's http(s)-only `openExternal`, but not in the browser dev UI. `memory/store.py:987`.
- **L2.** `PATCH /api/rooms/{id}` accepts a blank name (create rejects it), and it renders as "—". `memory/store.py:1799`.
- **L3.** Invalid `priority`/`bucket` are accepted. Home then shows "ultra-mega priority", and a bad bucket can hide a task from both columns.
- **L4.** Models page "Used N×" is wrong. It only increments when the model **changes**, resets on every page switch, and only counts while the page is open. `frontend/src/views/ModelSpecs.tsx:31-34`.
- **L5.** `AURA.bat:11` only builds when `dist\index.html` is **missing**, despite the "or after UI changes" comment. `dist` is fresh right now, so your next UI edit won't show up via AURA.bat until you rebuild.
- **L6.** `server.py` is imported twice at startup (`uvicorn.run("server:app")` re-imports the module), so all module-level init runs twice. Pass `app` directly.
- **L7.** Project cards show a stale git head (`7323987` from July vs HEAD `3b111a2`) until a manual rescan.
- **L8.** Bare `cd` in the Domain terminal goes to HOME. On Windows `cmd`, bare `cd` prints the cwd. A bad `cwd` creates a broken session (`WinError 267`) instead of an error.
- **L9.** Missing-resource calls return `ok:true`: complete/delete missing task, rename missing chat, file a missing chat into a missing room, toggle-lock an unknown model name (writes junk to the lock store).
- **L10.** Test suite: 3 failures, all test-side:
  - `test_quests.py:196-206` builds "past days" from the calendar instead of `quest_day()`, so it **fails every night 00:00–04:00** (4am rollover).
  - `test_work_recall.py:157-158` is stale. It expects the compact block on casual turns, but that was deliberately gated on 2026-08-20 (`brain.py:576`).
  - Importing `modules/relationship_engine` rewrites the **real** `memory/relationship_state.json` (daily reset at import). No isolation, so tests touch live data.

---

## Suggested fix order

1. **C1–C3.** A startup token plus a CORS allowlist closes most of the exposure; escape the callback page; harden `delete`.
2. **H1–H3, H5.** Four small edits that make coding chats correct and history trustworthy.
3. **H6.** Wire the privacy toggles, or hide them.
4. **H4.** Take Nemotron out of the chat lane and buffer the stream start.
5. **H7–H9, H11.** Room/chat sync in the UI.
6. **H10, M1–M8.** Then the rest.

Test scripts used for the sweep (API, WebSocket, undefined-name scan) can be rerun on request.
