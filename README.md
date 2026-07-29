# AURA — AI Desktop Companion & Multi-Agent Coding Environment

AURA is a self-hosted AI companion built to live on your desktop and work alongside you — not a chatbot you summon, but a system that observes, remembers, and steps in when it's actually useful.

It routes every query through a cost-aware, multi-model pipeline, remembers context across sessions instead of starting fresh every time, and pairs voice interaction with real-time awareness of your active workspace.

---

## ✨ Core Features

- **4-stage routing pipeline** — a 550+ entry pattern-matcher, a local Ollama gate, and an intent-based router across 5 free-tier LLMs (via Groq and OpenRouter) bring per-query inference cost to $0, with automatic fallback on rate limits.
- **Persistent memory layer** — 11 SQLite tables covering conversations, facts, tasks, session snapshots, and working memory, enabling durable recall across sessions instead of stateless, forgetful chat.
- **Rule-based Error Intelligence engine** — classifies coding errors into 4 severity levels locally, only escalating to an LLM when it can't resolve the issue itself, keeping common errors fast and free to diagnose.
- **Real-time voice I/O** — wake-word activation ("Aura"), speech in and out, built for hands-free, ambient interaction.
- **Live screen & workspace awareness** — AURA can see your active application/IDE context to give situationally relevant help.
- **AURA Domain — coding workspace** — an integrated development environment inside AURA itself: live git status, file explorer, real terminal, and project switching.
- **Proactive + curiosity engines** — notices when you're stuck, idle, or hit an error, and speaks up without being asked.
- **Slash-command modes** — `/code`, `/research`, `/plan`, `/discussion`, `/prompt` for different working styles without leaving the chat.

---

## 🧠 Philosophy

Most AI assistants wait for a prompt and reply. AURA is built around a different loop:

> Observe before interrupting. Understand before responding. Remember before asking again. Stay silent when silence is better.

---

## 🖥️ Two Interfaces, One Brain

1. **PySide6 desktop app** — the original interface: a floating orb with a cosmic, black-hole-themed visualization.
2. **React + TypeScript + Electron + Three.js frontend** *(active development)* — a cinematic universe-style UI with a "Sanctuary" home (live tasks, quick shortcuts, memory graph, settings) and a full "Domain" workspace (kanban planning, code/markdown editors, project shell). Communicates with the same Python backend over a FastAPI WebSocket bridge.

---

## 🛠️ Tech Stack

**Backend:** Python, PySide6, Groq API, OpenRouter, Ollama, SQLite, edge-tts
**Frontend (new):** React, TypeScript, Vite, Electron, Three.js
**Bridge:** FastAPI (WebSocket)
**Memory search:** FAISS + sentence-transformers

---

## 📌 Project Status

Actively evolving — most core systems (routing, memory, voice, error intelligence, workspace) are live and used daily. A few pieces are built but not yet fully wired in: a deeper session-awareness engine, settings-to-visuals integration, a plan-approval panel, and a packaged installer.

**Roadmap:** relationship engine, study mode, Spotify integration, cross-device context.

---


## 🗺️ Why "AURA"

Built as a real, daily-use tool — not a class assignment — around the idea that an AI companion should feel like a teammate sitting next to you, not a tool you have to open and address every time.
