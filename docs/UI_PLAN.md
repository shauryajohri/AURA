# AURA UI Rebuild Plan — Main App Window

> "The orb is AURA's body. The windows are just tools she opens when she needs them."

**Stack:** PySide6 (existing app, upgraded in place)
**Milestone 1:** Full main app window, mock data, debug state-switcher
**Backend wiring:** after visuals approved (event_bus → UI signals)

## Layout (3-column, frameless, custom titlebar)

```
┌──────────┬─────────────────────────────┬──────────────┐
│ Sidebar  │  Greeting + time/focus chips│  AURA Chat   │
│  logo    │  ┌───────────────────────┐  │   bubbles    │
│  nav     │  │  COSMOS PANEL         │  │   plan card  │
│          │  │  black hole core      │  │   focus card │
│  orb     │  │  5 model planets      │  │              │
│  mini    │  │  routing waveform     │  │   input+mic  │
│  panel   │  └───────────────────────┘  │──────────────│
│  voice   │  shortcuts row              │ reminder     │
│  mode    │  music player               │ toast        │
├──────────┴─────────────────────────────┴──────────────┤
│ encouragement │ focus time │ tasks │ productivity     │
└────────────────────────────────────────────────────────┘
```

## State system

`AuraState` enum, single source of truth. One change propagates to orb,
cosmos core, sidebar chip, status text. Transitions 200–500 ms, no instant cuts.

| State     | Visual                          | Color        |
|-----------|---------------------------------|--------------|
| idle      | black hole, very slow pulse     | black/purple |
| listening | colorful orb, ring, expansion   | blue/purple  |
| thinking  | white hole, breathing, ring     | white/silver |
| speaking  | white, pulse follows speech     | white/blue   |
| focus     | stable, minimal energy          | green        |
| alert     | strong glow, fast orbit         | orange (never full red) |

## Phases

1. **Tokens + skeleton** — extend `theme.py` (THINKING_SILVER, FOCUS_GREEN,
   ALERT_ORANGE, SPEAKING_WHITE); 3-column layout; frameless + titlebar.
2. **Cosmos panel** (`ui/cosmos_panel.py`) — QPainter black hole (dark core,
   accretion gradient ring, orbiting particles), 5 model planets
   (GPT/Claude/Gemini/Grok/Local) with ACTIVE/STANDBY chips, routing
   waveform bar. ~60 fps QTimer, paused when window hidden.
3. **Chat panel** (`ui/chat_panel.py`) — bubbles, plan checklist card,
   focus-session card, input row + mic, reminder toast.
4. **Sidebar + widgets** — nav, orb mini-panel w/ waveform, Voice Mode
   button, stats bar, shortcuts row, music player. All mock data.
5. **State system + mock driver** (`ui/state.py`, `ui/mock_driver.py`) —
   hotkeys 1–6 switch states; scripted demo chat.
6. **Polish + verify** — hover states, transition timing, CPU check,
   offscreen screenshot review.

## Rules (from design philosophy)

- Orb = emotion. Window = information.
- No feature requires opening the full app.
- All animations 200–500 ms, fluid.
- Notifications via orb glow only — never OS toasts.
- Critical errors: small red accent, never a full red orb.

## Later milestones

- M2: Standalone desktop orb (transparent, always-on-top, drag/snap,
  right-click menu, hover tooltip, quick panel) — reuse same state system.
- M3: Backend wiring (event_bus, brain, voice), window auto-expand on
  typing / auto-minimize after conversation.
- M4: AFK roaming, relationship-mode micro-expressions, split windows.
