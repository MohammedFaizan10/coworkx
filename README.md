# CoWorkX — Decentralized AI Workforce Network

CoWorkX lets anyone rent out their computer as an AI worker node. A user submits a
plain-language task; it runs on a remote machine's GPU using a **local** vision AI
(LLaVA / Gemma via Ollama) driving a real browser — no cloud AI required. Every step
is streamed live and logged, with a mock token economy and proof-of-execution.

Built for HackPrix S3, Hyderabad.

## Architecture

```
 User (browser)              Coordinator (FastAPI + PostgreSQL)         Worker PC
 ┌───────────────┐  HTTP/WS  ┌──────────────────────────────┐  HTTP    ┌──────────────────┐
 │ React frontend │ ───────▶ │ tasks, machines, wallet, proof│ ◀─────── │ daemon + Docker   │
 │ live stream    │ ◀─────── │ Socket.io relay               │          │ agent + Ollama GPU│
 └───────────────┘           └──────────────────────────────┘          └──────────────────┘
```

- **backend/** — FastAPI coordinator + PostgreSQL (tasks, machines, steps, wallet, proof, Socket.io)
- **daemon/** — runs on a worker PC: registers the machine, spawns the Docker agent
- **daemon/agent/** — the in-container AI loop (Playwright + Ollama vision model)
- **daemon-ui/** — worker control panel (start/stop the node, live log)
- **frontend/** — marketplace, live task view, wallet, network dashboard
- **extension/** — VS Code extension to submit a file as a task

## Stack
Python 3.11 · FastAPI · PostgreSQL · React + Vite · Socket.io · Docker · Playwright ·
Ollama (LLaVA / Gemma) · Sarvam AI (Telugu STT + Hindi TTS) · Leaflet

## Quick start

**Coordinator (host):**
```
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:socket_app --host 0.0.0.0 --port 8000
```

**Frontend:**
```
cd frontend
npm install
npm run dev
```

**Worker node:** see `daemon/HOST_SETUP.md`.

## Features
- Local GPU AI agent loop (no cloud inference)
- Live screen stream + real-time step log (Socket.io)
- Mock token economy: credit lock / release / refund + proof-of-execution hashes
- Voice: Telugu/Hindi/English speech-to-text input, Hindi step narration (Sarvam AI)
- VS Code extension for in-editor task submission

> Demo project. API keys and `.env` files are git-ignored — never commit secrets.
