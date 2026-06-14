<div align="center">

# ⚡ CoWorkX

### The Decentralized AI Workforce — real tasks, real GPUs, real people's machines.

Rent out your idle GPU. Command autonomous AI agents by voice. No cloud AI, no data centers.

*Built for HackPrix S3, Hyderabad.*

`Python` · `FastAPI` · `PostgreSQL` · `Socket.IO` · `Docker` · `Playwright` · `Ollama` · `Sarvam AI` · `React + Vite`

</div>

---

## 🎥 Demo Video

> [_Add your 2-minute demo link here:_](https://drive.google.com/file/d/1cv31mvviU90oWVe9SB8gcbxibETbCs0R/view?usp=sharing) **[Watch the demo](#)**
> https://drive.google.com/file/d/18uauck8UMCT8fcCf-GGRsNg0CXTKJXW8/view?usp=sharing

---

## 🧩 The Problem

Running AI agents today is **centralized, expensive, and privacy-invasive**:

1. **Centralized & costly** — to run AI agents you rent pricey cloud GPUs from a handful of providers, while millions of capable personal GPUs sit idle.
2. **Privacy is sacrificed** — using cloud AI sends your prompts, screenshots, and task data to a third-party model provider.
3. **Not accessible** — autonomous agents are technical to set up, English-centric, and tied to paid API keys most people don't have.

## 💡 The Solution

**CoWorkX turns everyday idle GPUs into a decentralized AI workforce.**

- Anyone runs a **one-click worker node** and earns credits when their machine completes tasks.
- The AI **runs locally on the worker's GPU** (Ollama + LLaVA/Gemma) — no cloud inference, no task data ever leaves the host.
- Users command the agent **by voice in Telugu, Hindi, or English** — and watch it work live.
- A **token economy + proof-of-execution** settle payment and prove the work was done.

> CoWorkX solves the cost, privacy, and accessibility problems of cloud AI by turning people's idle GPUs into a private, decentralized AI workforce anyone can command — even by voice.

---

## 🏗️ Architecture

```
   USER (browser)                COORDINATOR (your PC)                 WORKER (friend's GPU PC)
 ┌──────────────────┐   HTTP/WS  ┌───────────────────────────┐  HTTP   ┌────────────────────────┐
 │ React frontend    │ ─────────▶│ FastAPI + PostgreSQL       │◀─────── │ daemon (register/poll)  │
 │ • marketplace     │           │ • tasks / machines / steps │         │   └─ Docker container   │
 │ • live task view  │◀───────── │ • wallet + proof           │         │        └─ AI agent      │
 │ • wallet / network│  Socket.IO│ • Socket.IO relay          │ frames  │           ├─ Playwright │
 └──────────────────┘           └───────────────────────────┘  /steps  │           └─ Ollama GPU │
                                                                         └────────────────────────┘
```

- The **coordinator** is a thin central hub (API, database, real-time relay).
- The **daemon** runs on each worker PC: registers the machine, polls for tasks, spawns the agent in Docker.
- The **agent** (inside Docker) screenshots a web page → asks the local vision model → executes the next browser action → logs each step → repeats until done.
- AI inference happens **on the worker's GPU** via Ollama. Nothing goes to the cloud.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🖥️ **Machine Marketplace** | Browse live worker nodes with specs, GPU, status and price; filter and submit tasks. |
| 🤖 **Autonomous AI Agent** | Vision-driven loop: screenshot → reason → act with Playwright → repeat until `task_complete`. |
| 🧠 **Local GPU Inference** | Runs LLaVA / Gemma / Moondream via Ollama on the worker's GPU — private, offline-capable. |
| 📺 **Live Task View** | Real-time screen frames + step-by-step reasoning log, streamed over Socket.IO. |
| 🗣️ **Multilingual Voice** | Speak tasks in Telugu/Hindi/English (Sarvam STT); steps narrated in Hindi (Sarvam TTS). |
| 💰 **Token Economy** | Credits lock on submit, release to the host on completion, refund on failure. |
| 🔐 **Proof of Execution** | Each task produces SHA-256 step hashes + a combined execution hash, independently verifiable. |
| 🌍 **Network Dashboard** | Live map of worker nodes + real-time task feed. |
| 🎛️ **Worker Control Panel** | A no-terminal UI to start/stop the worker, see GPU/specs, and watch live logs (SSE). |
| 🧩 **VS Code Extension** | Submit the active file to the network as a task, with progress in the Output panel. |

---

## 🛠️ Tech Stack

**Backend / Coordinator:** Python 3.11 · FastAPI · Socket.IO · PostgreSQL · SQLAlchemy · Uvicorn
**Worker Daemon:** Python · httpx · Docker SDK · psutil · nvidia-smi
**AI Agent:** Playwright + headless Chromium · Ollama · LLaVA / Gemma / Moondream
**Voice:** Sarvam AI (saaras codemix STT · bulbul Hindi TTS)
**Frontend:** React 18 · Vite · React Router · Socket.IO client · Leaflet · Lucide · date-fns · pure CSS design system
**Worker Control Panel:** React + Vite · Server-Sent Events
**Dev Tools:** VS Code Extension API (TypeScript)
**Infra:** Docker (isolation + resource limits) · mock blockchain (SHA-256 proof + ledger in PostgreSQL)

---

## 📁 Project Structure

```
coworkx/
├── backend/        # FastAPI coordinator + PostgreSQL (API, wallet, proof, Socket.IO)
├── daemon/         # worker daemon (registers machine, spawns Docker agent)
│   ├── agent/      # in-container AI loop (Playwright + Ollama)
│   └── daemon_api.py  # control-panel backend (start/stop, SSE logs)
├── daemon-ui/      # worker control panel (React)
├── frontend/       # main app: marketplace, task view, wallet, network
└── extension/      # VS Code extension
```

---

## 🚀 Getting Started

### 1. Coordinator (host machine)
```bash
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
# create .env (see backend/.env.example) with DATABASE_URL + SARVAM_API_KEY
uvicorn main:socket_app --host 0.0.0.0 --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev          # open the printed URL
```

### 3. Worker node (any PC with an NVIDIA GPU)
See **[daemon/HOST_SETUP.md](daemon/HOST_SETUP.md)**. In short:
```bash
# install Ollama, then:
ollama pull llava-phi3            # or moondream / gemma3:4b
# set OLLAMA_HOST=0.0.0.0:11434 (system env) and restart Ollama
cd daemon
python -m venv venv && venv\Scripts\activate
pip install -r daemon_requirements.txt
docker build -t coworkx-agent:latest ./agent
python daemon.py                  # or use the control panel
```

### 4. Worker Control Panel (optional, no-terminal)
```bash
cd daemon && python daemon_api.py          # port 5175
cd daemon-ui && npm install && npm run dev # port 5174 → click "Start Worker"
```

---

## 🎬 Demo Flow

1. Open the **Marketplace** → a live worker node appears (with its GPU + "Local AI" tag).
2. Click a machine → **speak a task in Telugu** → it transcribes to English → Submit.
3. Watch the **Task View**: live screenshots on the left, step-by-step reasoning + GPU inference time on the right — narrated in Hindi.
4. The worker's **GPU usage spikes** — the AI is thinking locally, not in the cloud.
5. Task completes → result shown → **Wallet** shows credits move (lock → release).
6. Paste the task ID into **Proof of Execution** → **VERIFIED** with an execution hash.
7. Bonus: submit a file from the **VS Code extension**.

---

## 🧗 Challenges We Solved

- **Container ↔ host networking:** the Docker agent couldn't reach the host's Ollama/coordinator — fixed with `host.docker.internal` and binding Ollama to `0.0.0.0`.
- **Misleading stream:** headless browser had nothing to capture — re-architected the agent to push its own screenshots to the browser canvas.
- **Weak local models looping:** added an anti-loop safety net so tasks always finish with a real answer while still proving GPU inference.
- **True multi-machine setup:** solved stale registrations, a stuck-busy daemon, broken copied venvs, a Docker-SDK/`requests` incompatibility, and Windows emoji-encoding crashes.
- **Real-time UX:** Socket.IO rooms stream each task's steps, status, and frames to the right browser instantly.

---

## 🏆 Tracks

- **AI / Agents / Generative AI** — autonomous vision-driven browser agents.
- **Decentralization / DePIN** — a peer-to-peer GPU compute marketplace with a token economy.
- **Open Innovation** — an original cross-disciplinary platform rethinking how AI work is owned, run, and paid for.
- **Local AI / Privacy** — on-device inference, no cloud, no data leaving the host.

---

<div align="center">

**CoWorkX** — _The AI workforce that runs on the people's hardware._

</div>
