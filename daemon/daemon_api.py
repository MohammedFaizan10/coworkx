"""
CoWorkX Daemon Control API — runs on the worker PC (port 5175).

The daemon-ui (port 5174) talks to this. It manages daemon.py as a subprocess
so the friend never needs a terminal: open the control panel, click "Start Worker".

Endpoints:
  GET  /status      -> {connected, running, machine_id, uptime, heartbeat_count}
  GET  /specs       -> {gpu, ram, cpu, os, model, disk_free}
  GET  /tasks       -> [{task_id, status}]  (parsed from daemon output)
  POST /start       -> start daemon.py
  POST /stop        -> stop daemon.py
  GET  /stream/log  -> SSE stream of daemon stdout lines

Run:  python daemon_api.py
"""

import asyncio
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import Config

config = Config()
HERE = Path(__file__).parent

app = FastAPI(title="CoWorkX Daemon Control")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"], allow_headers=["*"], allow_credentials=True,
)

# ── Daemon process state ──────────────────────────────────────────────────────
class DaemonState:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.start_time: float | None = None
        self.machine_id: str | None = None
        self.heartbeats: int = 0
        self.registered: bool = False
        self.tasks: dict[str, str] = {}        # task_id -> status
        self.log: list[str] = []               # all log lines
        self.lock = threading.Lock()

    def reset_runtime(self):
        self.start_time = time.time()
        self.machine_id = None
        self.heartbeats = 0
        self.registered = False
        self.tasks = {}

state = DaemonState()


def _reader(proc: subprocess.Popen):
    """Background thread: read daemon stdout, store + parse markers."""
    for raw in iter(proc.stdout.readline, ""):
        line = raw.rstrip("\n")
        if not line:
            continue
        with state.lock:
            state.log.append(line)
            if len(state.log) > 2000:
                state.log = state.log[-2000:]
            if "Registered!" in line:
                state.registered = True
                m = re.search(r"Machine ID:\s*([0-9a-fA-F-]+)", line)
                if m:
                    state.machine_id = m.group(1)
            elif "💓" in line or "[online]" in line or "[busy]" in line:
                state.heartbeats += 1
            elif "NEW TASK RECEIVED" in line:
                pass
            else:
                m = re.search(r"ID:\s*([0-9a-fA-F-]{8}-[0-9a-fA-F-]+)", line)
                if m:
                    state.tasks[m.group(1)] = "running"
    # process ended
    with state.lock:
        state.registered = False


def start_daemon() -> bool:
    if state.process and state.process.poll() is None:
        return True  # already running
    state.reset_runtime()
    # Force UTF-8 stdout so emoji prints don't crash on Windows cp1252 consoles.
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    state.process = subprocess.Popen(
        [sys.executable, "daemon.py"],
        cwd=str(HERE),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        env=env,
    )
    threading.Thread(target=_reader, args=(state.process,), daemon=True).start()
    return True


def stop_daemon() -> bool:
    if state.process and state.process.poll() is None:
        state.process.terminate()
        try:
            state.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state.process.kill()
    state.process = None
    state.registered = False
    return True


def detect_gpu() -> str:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=8).decode().strip()
        return out.splitlines()[0] if out else "No NVIDIA GPU"
    except Exception:
        return "No NVIDIA GPU"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/status")
def status():
    running = bool(state.process and state.process.poll() is None)
    uptime = int(time.time() - state.start_time) if (running and state.start_time) else 0
    return {
        "running": running,
        "connected": running and state.registered,
        "machine_id": state.machine_id,
        "uptime": uptime,
        "heartbeat_count": state.heartbeats,
    }


@app.get("/specs")
def specs():
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
    return {
        "gpu": detect_gpu(),
        "cpu": platform.processor() or "Unknown CPU",
        "ram_total_gb": round(vm.total / 1e9, 1),
        "ram_free_gb": round(vm.available / 1e9, 1),
        "os": f"{platform.system()} {platform.release()}",
        "disk_free_gb": round(du.free / 1e9),
        "model": config.OLLAMA_MODEL,
        "coordinator_url": config.COORDINATOR_URL,
    }


@app.get("/tasks")
def tasks():
    """Real tasks for THIS machine, fetched from the coordinator."""
    if not state.machine_id:
        return []
    try:
        import requests
        r = requests.get(f"{config.COORDINATOR_URL}/tasks", timeout=5)
        all_tasks = r.json() if r.status_code == 200 else []
        mine = [t for t in all_tasks if str(t.get("machine_id")) == str(state.machine_id)]
        mine.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return [{"task_id": t["id"], "status": t.get("status", "?")} for t in mine[:10]]
    except Exception as e:
        print(f"⚠️  tasks fetch failed: {e}")
        return []


@app.post("/start")
def start():
    start_daemon()
    return {"ok": True}


@app.post("/stop")
def stop():
    stop_daemon()
    return {"ok": True}


@app.get("/stream/log")
async def stream_log():
    async def gen():
        idx = 0
        # send a small backlog first
        with state.lock:
            idx = max(0, len(state.log) - 50)
        while True:
            with state.lock:
                lines = state.log[idx:]
                idx = len(state.log)
            for line in lines:
                yield f"data: {line}\n\n"
            await asyncio.sleep(0.6)
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    print("🎛️  CoWorkX Daemon Control API on http://localhost:5175")
    uvicorn.run(app, host="127.0.0.1", port=5175)
