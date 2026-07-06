# AURA — Debug & Flaw Report

Audit date: 2026-07-06. Scope: all first-party Python (`core/`, `modules/`, `memory/`, `ui/`, `config/`, entry points). Excludes `venv/`, `.venv/`, `.codex_pycache/`. Every file compiles (no syntax errors); the flaws below are runtime crashes, broken features, wrong logic, concurrency issues, and hygiene problems.

Good news up front: `.env` was **never committed to git history** — no secret leak.

---

## CRITICAL — crashes at runtime or destroys data

### C1. `call_groq_with_search` does not exist → crash on every SEARCH query
`core/ai_router.py:225`. `route()` calls `call_groq_with_search(prompt, system)` when `intent == "SEARCH"`, but that function is never defined anywhere → `NameError`. This path is hit constantly: `brain.py` sets `intent = "SEARCH"` for any message containing a URL (line 434) and the classifier routes news/weather/prices/"facts you don't know" to SEARCH. So any "search-like" question crashes the response.
Fix: route SEARCH to `call_groq` (or implement a real search call). One-line change.

### C2. Startup greeting **deletes all session memory** every launch
`modules/session_memory.py:52-54`. `get_greeting_with_memory()` reads the last session, then runs `DELETE FROM session_snapshots` and commits. It's called at import time in `main.py`. So the "remembers what you were doing last time" feature wipes its own table on every startup — you only ever see the single most-recent snapshot once, then it's gone. Also uses a hardcoded relative path `memory/aura_memory.db` (only works if cwd is the project root), inconsistent with `store.DB_PATH`.
Fix: remove the DELETE block; read only.

### C3. Wake word can never initialize — real key overwritten by placeholder
`modules/wake_word.py:5-7`. Line 5 sets `ACCESS_KEY = PICOVOICE_KEY` (from env), then line 7 immediately does `ACCESS_KEY = "your_picovoice_key_here"`, clobbering it with a dummy string. `pvporcupine.create()` then always fails auth → wake word ("Jarvis") never works.
Fix: delete line 7.

---

## HIGH — feature silently broken or logically wrong

### H1. Quick forex price lookup almost always fails (reversed substring test)
`modules/forex_report.py:102`. `if pair.lower() in name.lower()` checks whether the *whole user query* is a substring of `"EUR/USD"`. It's backwards — the long query is never inside the short pair name, so `get_quick_price` nearly always returns "Couldn't fetch data." Should test the pair token against the query, e.g. normalize (`"eurusd"`) and check membership the other way.

### H2. Model selection is decorative — every call goes to Groq llama anyway
`ui/app.py:283` `_process_approved_plan()` receives `model_id` and never uses it; `process_streaming` always calls Groq `llama-3.3-70b`. The approval panel shows "Claude / MiniMax / Qwen3-Coder" and dollar cost estimates (`$0.03–$0.08`, etc.) that have nothing to do with what actually runs. For a tool you'll use for real, this is misleading UI theater. Either wire real multi-model dispatch or relabel the panel honestly.

### H3. `model_router` routing table is mis-ordered — domain rules unreachable
`core/model_router.py:25-50`. Entries are "first match where `complexity < max_c`." The generic `(70, None, ...)` MiniMax entry catches everything below complexity 70, so the domain-specific `RESEARCH`/`CODING` → Claude entries only ever fire at complexity ≥ 70. The comment "Research tasks always go to Claude regardless of complexity" is false. (Compounded by H2, this never affects real output — but the logic is wrong.)

### H4. VoiceGate can drop the winning speaker (race condition)
`core/voice_gate.py:124-143`. After the collection window, whichever thread grabs the lock first computes `winner`, decides `won` **for itself only**, then clears `_round_bids`. If a *non-winner* runs first, it returns `False` (correct for itself) but wipes the round; the actual highest-priority bidder then sees an empty `_round_bids` and also returns `False`. Result: under near-simultaneous bids, the intended speech can be silently suppressed. The winner should be computed once and cached for all bidders in the round.

---

## MEDIUM — reliability, robustness, maintainability

### M1. `voice_input.py` initializes the mic at import time
`modules/voice_input.py:5-9`. `sr.Microphone()` + `adjust_for_ambient_noise()` run at module top level. On any machine without a working mic / PortAudio, merely *importing* the module throws and takes down whatever imported it. Move into a lazy init function.

### M2. SQLite has no thread-safety guards under many background loops
`memory/store.py`. Every helper opens a fresh `sqlite3.connect(DB_PATH)` with no `timeout=` and no WAL mode. Multiple daemon threads (proactive, curiosity, attention, error_detector) write concurrently → intermittent `database is locked` errors. Set `timeout=`, enable `PRAGMA journal_mode=WAL`, or serialize access.

### M3. Dead / duplicated code in `call_classifier`
`core/ai_router.py:205-213` calls `response.json()` twice and has an unreachable 429 re-check; a *classifier* meant to emit one word can return `"RATE_LIMIT"`/`"CONNECTION_ERROR"` strings that then get treated as an intent. Also `GROQ_API_KEY` is assigned twice (lines 8-9).

### M4. `brain.py` duplicate import + large copy-paste between `process` and `process_streaming`
Duplicate `from core.thinking import think, post_think` (lines 6 and 13). The two entry points duplicate ~150 lines of tier routing that have already drifted apart (streaming has AFK + observation-followup handling; the non-streaming `process()` does not). Extract the shared routing into one helper.

### M5. 10 bare `except:` clauses swallow everything
`thinking.py`, `session_memory.py`, `knowledge.py`, `store.py`, `brain.should_respond`, etc. Bare `except:` also catches `KeyboardInterrupt`/`SystemExit` and hides real bugs. Use `except Exception as e:` and log.

### M6. `csv_handler.py` bogus import + possible IndexError
`from urllib import response` (line 6) is meaningless and immediately shadowed. In `_process`, `random.choice(text_entries)` will `IndexError` if a trigger has only action-type entries and no text fallback.

### M7. `should_respond` silently depends on a local Ollama `phi3` model
`brain.py:507`. If Ollama isn't running, the bare `except` returns `True` for everything — so the gate is effectively a no-op on most machines. Fine as a fallback, but it's undocumented and inconsistent with the Groq-based rest of the app.

---

## LOW — hygiene, dead code, project setup

- **L1. Junk files in repo root:** `e -i HEAD~3` (a `git log` dump) and `ession memory, proactive upgrade, groq integration` (a `less` pager help dump). Both are accidental shell redirections. Delete them.
- **L2. No dependency manifest.** ~15 third-party deps (PySide6, requests, edge_tts, pygame, speech_recognition, pvporcupine, pvrecorder, yfinance, ta, pandas, pyperclip, ollama, python-dotenv, keyboard) and no `requirements.txt`/`pyproject.toml`. Not reproducible on another machine.
- **L3. Two virtualenvs on disk** (`venv/` and `.venv/`) plus a `.codex_pycache/` tree and an 858 KB `.aura_index.pkl`. Clutter; pick one venv.
- **L4. Dead config.** `config/settings.py` exposes `ANTHROPIC_API_KEY`/`GEMINI_API_KEY`/`PICOVOICE_KEY`, none used by the live Groq path; `.env` also carries `ELEVENLABS_*` keys though TTS actually uses free `edge_tts`. Remove or wire up.
- **L5. `core/context.py` is an empty 0-byte file.** Remove.
- **L6. ~40 unused imports** across `ui/*` and `modules/*` (ruff F401), unused locals (`casual_ratio` in store.py:97, `tags` in knowledge.py:61), and f-strings without placeholders (store.py:406, test_engine.py:28). Cosmetic but noisy.
- **L7. `main.py` runs work at import.** The greeting is computed/printed at top-level (module import), and a `QTimer` firing a no-op every 200 ms is used just to keep Python's SIGINT handler responsive — works, but hacky. Move into `if __name__ == "__main__"`.

---

## Suggested fix order

1. C1, C2, C3 — three tiny edits that fix a guaranteed crash, a data-loss bug, and a dead feature.
2. H1, H4 — broken forex lookup and the voice-gate race.
3. H2/H3 — decide: make model routing real, or relabel the panel so it's honest.
4. M1–M6 — robustness pass.
5. L1–L7 — cleanup + add `requirements.txt`.

Nothing here requires a rewrite; most criticals are one- or few-line fixes. Ready to apply them on your say-so.
