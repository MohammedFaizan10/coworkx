"""
CoWorkX Coordinator — main.py v0.3.0

Day 3 additions over v0.2.0:
  - FastAPI WebSocket endpoint: /ws/stream/{task_id}
    Receives binary JPEG frames from daemon and broadcasts
    them to browser clients via Socket.io room.
  - Socket.io event: join_task_room — browser joins room for a task
  - Socket.io event: task_completed — notifies browser when task done
  - stream_connections dict tracks active daemon stream WebSockets
"""

import hashlib
import base64
import os
import tempfile
import uuid
from datetime import datetime
from typing import Optional

import socketio
from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from database import SessionLocal, engine

# ─── Create DB tables ────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="CoWorkX Coordinator",
    description="P2P AI Agent Network — Coordinator Server",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Socket.io server ────────────────────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# ─── Active stream WebSocket connections: task_id → WebSocket ───────────────
stream_connections: dict[str, WebSocket] = {}


async def emit_task_update(task_id: str, payload: dict):
    """Broadcast a task_update event to the browser room for this task."""
    try:
        await sio.emit("task_update", payload, room=f"task_{task_id}")
    except Exception as e:
        print(f"⚠️  socket emit failed for task {task_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE DEPENDENCY
# ═══════════════════════════════════════════════════════════════════════════════

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET / MOCK BLOCKCHAIN HELPERS (Day 6)
# ═══════════════════════════════════════════════════════════════════════════════

# Single demo user for the hackathon (no auth). All tasks are submitted by them.
DEMO_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CURRENCY = "CWX"
DEFAULT_TASK_COST = 5.0   # fallback cost if a machine has no price


def make_tx_hash(task_id, amount) -> str:
    """Fake-but-realistic transaction hash: sha256(task_id + timestamp + amount)."""
    raw = f"{task_id}{datetime.utcnow().isoformat()}{amount}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_create_wallet(db: Session, owner_id):
    """Return the wallet for an owner, creating it with 100 credits if missing."""
    wallet = db.query(models.Wallet).filter(models.Wallet.owner_id == owner_id).first()
    if not wallet:
        wallet = models.Wallet(id=uuid.uuid4(), owner_id=owner_id, balance=100.0)
        db.add(wallet)
        db.flush()
    return wallet


def record_tx(db: Session, tx_type, amount, task_id, from_owner, to_owner, description):
    """Insert a wallet_transactions ledger row. Caller commits."""
    tx = models.WalletTransaction(
        id=uuid.uuid4(),
        from_owner=from_owner,
        to_owner=to_owner,
        task_id=task_id,
        amount=amount,
        type=tx_type,
        tx_hash=make_tx_hash(task_id, amount),
        description=description,
    )
    db.add(tx)
    return tx


def wallet_tx_to_dict(t):
    return {
        "id":          str(t.id),
        "type":        t.type,
        "amount":      float(t.amount),
        "task_id":     str(t.task_id) if t.task_id else None,
        "tx_hash":     t.tx_hash,
        "description": t.description,
        "created_at":  t.created_at.isoformat() if t.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def task_to_dict(t):
    return {
        "id":               str(t.id),
        "user_id":          str(t.user_id) if t.user_id else None,
        "machine_id":       str(t.machine_id),
        "task_description": t.task_description,
        "task_type":        t.task_type,
        "status":           t.status.value if hasattr(t.status, "value") else str(t.status),
        "output_url":       t.output_url,
        "started_at":       t.started_at.isoformat() if t.started_at else None,
        "completed_at":     t.completed_at.isoformat() if t.completed_at else None,
        "duration_seconds": t.duration_seconds,
        "error_message":    t.error_message,
        "created_at":       t.created_at.isoformat() if t.created_at else None,
    }

def step_to_dict(s):
    return {
        "id":              str(s.id),
        "task_id":         str(s.task_id),
        "step_number":     s.step_number,
        "action_type":     s.action_type,
        "action_params":   s.action_params or {},
        "reasoning":       s.reasoning,
        "screenshot_hash": s.screenshot_hash,
        "result_hash":     s.result_hash,
        "executed_at":     s.executed_at.isoformat() if s.executed_at else None,
    }

def machine_to_dict(m):
    return {
        "id":                     str(m.id),
        "owner_id":               str(m.owner_id) if m.owner_id else None,
        "display_name":           m.display_name,
        "os":                     m.os,
        "cpu_model":              m.cpu_model,
        "cpu_cores":              m.cpu_cores,
        "ram_gb":                 m.ram_gb,
        "gpu_model":              m.gpu_model,
        "gpu_vram_gb":            m.gpu_vram_gb,
        "installed_software":     m.installed_software or [],
        "supported_tasks":        m.supported_tasks or [],
        "price_per_hour":         float(m.price_per_hour) if m.price_per_hour else 0.0,
        "latitude":               float(m.latitude) if m.latitude else None,
        "longitude":              float(m.longitude) if m.longitude else None,
        "status":                 m.status.value if hasattr(m.status, "value") else str(m.status),
        "cpu_usage_pct":          m.cpu_usage_pct,
        "ram_usage_pct":          m.ram_usage_pct,
        "last_heartbeat":         m.last_heartbeat.isoformat() if m.last_heartbeat else None,
        "total_tasks_completed":  m.total_tasks_completed or 0,
        "rating":                 float(m.rating) if m.rating else 5.0,
        "registered_at":          m.registered_at.isoformat() if m.registered_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SOCKET.IO EVENTS (browser ↔ coordinator)
# ═══════════════════════════════════════════════════════════════════════════════

@sio.event
async def connect(sid, environ):
    print(f"🔌 Browser connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"🔌 Browser disconnected: {sid}")


@sio.event
async def join_task_room(sid, data):
    """
    Browser emits this to start receiving stream frames for a task.
    data = { "task_id": "some-uuid" }
    """
    task_id   = data.get("task_id")
    room_name = f"task_{task_id}"
    await sio.enter_room(sid, room_name)
    print(f"👁️  Browser {sid} joined stream room: {room_name}")
    await sio.emit("room_joined", {"task_id": task_id, "room": room_name}, to=sid)


@sio.event
async def leave_task_room(sid, data):
    task_id   = data.get("task_id")
    room_name = f"task_{task_id}"
    await sio.leave_room(sid, room_name)
    print(f"👋 Browser {sid} left room: {room_name}")


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET STREAMING ENDPOINT (daemon → coordinator)
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/stream/{task_id}")
async def websocket_stream(websocket: WebSocket, task_id: str):
    """
    Daemon connects here when a task starts streaming.
    Receives binary JPEG frames and broadcasts them to the browser
    room via Socket.io 'stream_frame' event.
    """
    await websocket.accept()
    stream_connections[task_id] = websocket
    room_name  = f"task_{task_id}"
    frames_rcv = 0

    print(f"📡 Daemon stream WebSocket opened — task {task_id}")

    try:
        while True:
            # Receive binary JPEG frame from daemon
            frame_bytes = await websocket.receive_bytes()
            frames_rcv += 1

            # Relay binary frame to all browsers watching this task
            await sio.emit("stream_frame", frame_bytes, room=room_name)

            if frames_rcv % 25 == 0:
                print(f"📡 Relayed {frames_rcv} frames for task {task_id}")

    except WebSocketDisconnect:
        print(f"📡 Daemon stream disconnected — task {task_id} ({frames_rcv} frames total)")
    except Exception as e:
        print(f"⚠️  Stream error for task {task_id}: {e}")
    finally:
        stream_connections.pop(task_id, None)
        # Notify browser that stream ended
        await sio.emit("stream_ended", {"task_id": task_id}, room=room_name)


# ═══════════════════════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root(db: Session = Depends(get_db)):
    machine_count = db.query(models.Machine).count()
    task_count    = db.query(models.Task).count()
    return {
        "service":  "CoWorkX Coordinator v0.3.0",
        "machines": machine_count,
        "tasks":    task_count,
        "streaming_active": len(stream_connections),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MACHINE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class MachineRegisterRequest(BaseModel):
    display_name:      str
    os:                str
    cpu_model:         Optional[str] = None
    cpu_cores:         Optional[int] = None
    ram_gb:            Optional[int] = None
    gpu_model:         Optional[str] = None
    gpu_vram_gb:       Optional[int] = None
    storage_gb:        Optional[int] = 100
    installed_software: Optional[list] = []
    supported_tasks:   Optional[list] = ["browsing", "file", "coding", "research"]
    price_per_hour:    Optional[float] = 1.0
    latitude:          Optional[float] = None
    longitude:         Optional[float] = None
    daemon_version:    Optional[str] = "0.0.3"


@app.post("/machines/register")
def register_machine(req: MachineRegisterRequest, db: Session = Depends(get_db)):
    machine = models.Machine(
        id = uuid.uuid4(),

        owner_id = uuid.uuid4(),   # ADD THIS LINE

        display_name = req.display_name,
        os = req.os,
        cpu_model = req.cpu_model,
        cpu_cores = req.cpu_cores,
        ram_gb = req.ram_gb,
        gpu_model = req.gpu_model,
        gpu_vram_gb = req.gpu_vram_gb,
        storage_gb          = req.storage_gb or 100,
        installed_software = req.installed_software or [],
        supported_tasks = req.supported_tasks or [],
        price_per_hour = req.price_per_hour,
        latitude = req.latitude,
        longitude = req.longitude,
        status = models.MachineStatus.online,
        daemon_version = req.daemon_version,
        registered_at = datetime.utcnow(),
        last_heartbeat = datetime.utcnow(),
        total_tasks_completed = 0,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    print(f"✅ Machine registered: {machine.display_name} ({machine.id})")
    return machine_to_dict(machine)


@app.get("/machines")
def list_machines(db: Session = Depends(get_db)):
    machines = db.query(models.Machine).all()
    # Attach each machine owner's wallet balance (their earnings) so the UI can
    # show the host side of the economy.
    owner_ids = [m.owner_id for m in machines]
    wallets = {}
    if owner_ids:
        for w in db.query(models.Wallet).filter(models.Wallet.owner_id.in_(owner_ids)).all():
            wallets[w.owner_id] = float(w.balance)
    result = []
    for m in machines:
        d = machine_to_dict(m)
        d["owner_earnings"] = wallets.get(m.owner_id, 0.0)
        result.append(d)
    return result


@app.get("/machines/{machine_id}")
def get_machine(machine_id: str, db: Session = Depends(get_db)):
    machine = db.query(models.Machine).filter(
        models.Machine.id == uuid.UUID(machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, "Machine not found")
    return machine_to_dict(machine)


@app.post("/machines/{machine_id}/heartbeat")
def machine_heartbeat(machine_id: str, data: dict, db: Session = Depends(get_db)):
    machine = db.query(models.Machine).filter(
        models.Machine.id == uuid.UUID(machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, "Machine not found")

    machine.cpu_usage_pct  = data.get("cpu_pct", 0)
    machine.ram_usage_pct  = data.get("ram_pct", 0)
    machine.last_heartbeat = datetime.utcnow()
    machine.daemon_version = data.get("daemon_version", machine.daemon_version)

    status_str = data.get("status", "online")
    if status_str == "online":
        machine.status = models.MachineStatus.online
    elif status_str == "busy":
        machine.status = models.MachineStatus.busy
    else:
        machine.status = models.MachineStatus.offline

    db.commit()
    return {"ack": True}


# ═══════════════════════════════════════════════════════════════════════════════
# TASK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TaskSubmitRequest(BaseModel):
    machine_id:       Optional[str] = None
    task_description: str
    task_type:        Optional[str] = "browsing"


@app.post("/tasks")
def submit_task(req: TaskSubmitRequest, db: Session = Depends(get_db)):
    # Resolve the machine: use the provided one, else auto-pick the first online
    # machine (lets the VS Code extension submit without choosing a machine).
    if req.machine_id:
        machine = db.query(models.Machine).filter(
            models.Machine.id == uuid.UUID(req.machine_id)
        ).first()
        if not machine:
            raise HTTPException(404, "Machine not found")
        if machine.status == models.MachineStatus.offline:
            raise HTTPException(400, "Machine is offline")
    else:
        machine = db.query(models.Machine).filter(
            models.Machine.status == models.MachineStatus.online
        ).order_by(models.Machine.last_heartbeat.desc().nullslast()).first()
        if not machine:
            raise HTTPException(400, "No online machine available")

    # ── Mock blockchain: lock (deduct) credits from the demo user ────────────
    cost = float(machine.price_per_hour or DEFAULT_TASK_COST)
    user_wallet = get_or_create_wallet(db, DEMO_USER_ID)
    if float(user_wallet.balance) < cost:
        raise HTTPException(400, f"Insufficient credits: need {cost} {CURRENCY}, "
                                 f"have {float(user_wallet.balance)} {CURRENCY}")

    task = models.Task(
        id               = uuid.uuid4(),
        user_id          = DEMO_USER_ID,
        machine_id       = machine.id,
        task_description = req.task_description,
        task_type        = req.task_type,
        status           = models.TaskStatus.queued,
        credits_charged  = cost,
        created_at       = datetime.utcnow(),
    )
    db.add(task)

    user_wallet.balance = float(user_wallet.balance) - cost
    record_tx(db, "lock", cost, task.id, DEMO_USER_ID, machine.owner_id,
              f"Locked {cost} {CURRENCY} for task")

    db.commit()
    db.refresh(task)
    print(f"📥 Task queued: {task.id} — locked {cost} {CURRENCY} "
          f"(machine {machine.display_name})")
    return task_to_dict(task)


@app.get("/tasks")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(models.Task).order_by(models.Task.created_at.desc()).limit(50).all()
    return [task_to_dict(t) for t in tasks]


@app.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(
        models.Task.id == uuid.UUID(task_id)
    ).first()
    if not task:
        raise HTTPException(404, "Task not found")

    steps = db.query(models.TaskStep).filter(
        models.TaskStep.task_id == task.id
    ).order_by(models.TaskStep.step_number.asc()).all()

    data = task_to_dict(task)
    data["steps"] = [step_to_dict(s) for s in steps]
    return data


@app.get("/tasks/{task_id}/steps")
def list_task_steps(task_id: str, db: Session = Depends(get_db)):
    """Return all logged steps for a task, ordered by step number."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(422, "Invalid task identifier")
    steps = db.query(models.TaskStep).filter(
        models.TaskStep.task_id == task_uuid
    ).order_by(models.TaskStep.step_number.asc()).all()
    return [step_to_dict(s) for s in steps]


@app.delete("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(
        models.Task.id == uuid.UUID(task_id)
    ).first()
    if not task:
        raise HTTPException(404, "Task not found")
    task.status = models.TaskStatus.cancelled
    db.commit()
    return task_to_dict(task)


# ─────────────────────────────────────────────────────────────────────────────
# DAEMON HTTP POLLING ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tasks/pending/{machine_id}")
def get_pending_task(machine_id: str, db: Session = Depends(get_db)):
    """Called by daemon every 3s. Returns one queued task or null."""
    task = db.query(models.Task).filter(
        models.Task.machine_id == uuid.UUID(machine_id),
        models.Task.status     == models.TaskStatus.queued
    ).order_by(models.Task.created_at.asc()).first()

    if not task:
        return None
    return task_to_dict(task)


@app.post("/tasks/{task_id}/start")
async def start_task(task_id: str, db: Session = Depends(get_db)):
    """Called by daemon when task execution begins."""
    task = db.query(models.Task).filter(
        models.Task.id == uuid.UUID(task_id)
    ).first()
    if not task:
        raise HTTPException(404, "Task not found")

    task.status     = models.TaskStatus.running
    task.started_at = datetime.utcnow()
    db.commit()
    print(f"🏃 Task running: {task_id}")

    await emit_task_update(task_id, {
        "task_id": task_id,
        "type":    "status",
        "status":  "running",
    })
    return task_to_dict(task)


# ─────────────────────────────────────────────────────────────────────────────
# STEP LOGGING ENDPOINT (agent → coordinator)
# ─────────────────────────────────────────────────────────────────────────────

class StepCreateRequest(BaseModel):
    step_number:     int                 = Field(ge=1, le=2147483647)
    action_type:     str                 = Field(min_length=1, max_length=50)
    action_params:   dict                = {}
    screenshot_hash: Optional[str]       = Field(default=None, max_length=64)
    result_hash:     Optional[str]       = Field(default=None, max_length=64)
    reasoning:       Optional[str]       = None


# ─────────────────────────────────────────────────────────────────────────────
# LIVE FRAME RELAY (agent screenshot → browser canvas)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/tasks/{task_id}/frame")
async def push_frame(task_id: str, request: Request):
    """The in-container agent POSTs a raw JPEG/PNG screenshot here each step.
    We relay it to the browser room as a 'stream_frame' so the canvas shows
    the agent's ACTUAL page (the headless browser has no capturable window)."""
    body = await request.body()
    if body:
        await sio.emit("stream_frame", body, room=f"task_{task_id}")
    return {"ok": True, "bytes": len(body)}


@app.post("/tasks/{task_id}/steps")
async def create_step(task_id: str, req: StepCreateRequest, db: Session = Depends(get_db)):
    """
    Insert one row into task_steps for an executed agent step.

      - 422 if task_id is not a valid UUID (handled here + by Pydantic for the body)
      - 404 if the UUID is valid but no matching task exists
      - 200 + persisted step UUID on success

    task_id is taken from the path; executed_at is set to the UTC insertion time.
    """
    # Parse the path task_id as a UUID first — a non-UUID maps to HTTP 422.
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(422, "Invalid task identifier: not a valid UUID")

    # Valid UUID but unknown task → 404, without inserting a row.
    task = db.query(models.Task).filter(
        models.Task.id == task_uuid
    ).first()
    if not task:
        raise HTTPException(404, "Task not found")

    step = models.TaskStep(
        id              = uuid.uuid4(),
        task_id         = task_uuid,
        step_number     = req.step_number,
        action_type     = req.action_type,
        action_params   = req.action_params,
        screenshot_hash = req.screenshot_hash,
        result_hash     = req.result_hash,
        reasoning       = req.reasoning,
        executed_at     = datetime.utcnow(),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    print(f"📝 Step logged: task {task_id} step #{req.step_number} ({req.action_type})")

    await emit_task_update(task_id, {
        "task_id": task_id,
        "type":    "step",
        "step":    step_to_dict(step),
    })
    return {"id": str(step.id)}


@app.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    data: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Called by the daemon when a task finishes. Marks it completed, stores
    the agent's final output, frees the machine, and records step count."""
    try:
        print("COMPLETE REQUEST DATA:", data)

        task = db.query(models.Task).filter(
            models.Task.id == uuid.UUID(task_id)
        ).first()
        if not task:
            raise HTTPException(404, "Task not found")

        now = datetime.utcnow()
        task.status       = models.TaskStatus.completed
        task.completed_at = now
        task.output_url   = data.get("output")

        # Duration: started_at from the DB may be timezone-aware while
        # utcnow() is naive — subtracting those raises. Guard it.
        try:
            if task.started_at:
                started = task.started_at
                end = datetime.now(started.tzinfo) if started.tzinfo else now
                task.duration_seconds = int((end - started).total_seconds())
        except Exception as e:
            print(f"⚠️  duration calc skipped: {e}")

        # Count how many steps the agent logged for this task
        task.steps_count = db.query(models.TaskStep).filter(
            models.TaskStep.task_id == task.id
        ).count()

        # Free the machine and bump its completed counter
        machine = db.query(models.Machine).filter(
            models.Machine.id == task.machine_id
        ).first()
        if machine:
            machine.status = models.MachineStatus.online
            machine.total_tasks_completed = (machine.total_tasks_completed or 0) + 1

        # ── Mock blockchain: release locked credits to the machine owner ─────
        amount = float(task.credits_charged or DEFAULT_TASK_COST)
        if machine:
            host_wallet = get_or_create_wallet(db, machine.owner_id)
            host_wallet.balance = float(host_wallet.balance) + amount
            task.credits_earned = amount
            record_tx(db, "release", amount, task.id,
                      task.user_id, machine.owner_id,
                      f"Released {amount} {CURRENCY} to host on completion")

        db.commit()
        db.refresh(task)
        print(f"✅ Task completed: {task_id} ({task.steps_count} steps)")

        await emit_task_update(task_id, {
            "task_id": task_id,
            "type":    "status",
            "status":  "completed",
            "output":  task.output_url,
        })
        return task_to_dict(task)

    except HTTPException:
        raise
    except Exception as e:
        print("COMPLETE ERROR:", repr(e))
        raise


@app.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, data: dict = Body(default={}), db: Session = Depends(get_db)):
    """Called by daemon if execution fails or times out."""
    task = db.query(models.Task).filter(
        models.Task.id == uuid.UUID(task_id)
    ).first()
    if not task:
        raise HTTPException(404, "Task not found")

    task.status        = models.TaskStatus.failed
    task.completed_at  = datetime.utcnow()
    task.error_message = data.get("error", "Unknown error")

    machine = db.query(models.Machine).filter(
        models.Machine.id == task.machine_id
    ).first()
    if machine:
        machine.status = models.MachineStatus.online

    # ── Mock blockchain: refund the locked credits to the user ───────────────
    refund = float(task.credits_charged or 0)
    if refund > 0 and task.user_id:
        user_wallet = get_or_create_wallet(db, task.user_id)
        user_wallet.balance = float(user_wallet.balance) + refund
        record_tx(db, "refund", refund, task.id,
                  task.machine_id, task.user_id,
                  f"Refunded {refund} {CURRENCY} (task failed)")

    db.commit()
    print(f"❌ Task failed: {task_id}")

    await emit_task_update(task_id, {
        "task_id": task_id,
        "type":    "status",
        "status":  "failed",
        "error":   task.error_message,
    })
    return task_to_dict(task)


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET / PROOF ENDPOINTS (Day 6 — mock blockchain)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/wallet/balance")
def wallet_balance(db: Session = Depends(get_db)):
    """Return the demo user's wallet balance."""
    wallet = get_or_create_wallet(db, DEMO_USER_ID)
    db.commit()
    return {"balance": float(wallet.balance), "currency": CURRENCY}


@app.get("/wallet/transactions")
def wallet_transactions(db: Session = Depends(get_db)):
    """Return the full ledger, newest first."""
    txs = db.query(models.WalletTransaction).order_by(
        models.WalletTransaction.created_at.desc()
    ).limit(100).all()
    return [wallet_tx_to_dict(t) for t in txs]


@app.post("/wallet/seed")
def wallet_seed(db: Session = Depends(get_db)):
    """DEMO ONLY — reset the demo user's wallet to 100 credits."""
    wallet = get_or_create_wallet(db, DEMO_USER_ID)
    wallet.balance = 100.0
    db.commit()
    return {"balance": float(wallet.balance), "currency": CURRENCY, "reset": True}


@app.get("/tasks/{task_id}/proof")
def task_proof(task_id: str, db: Session = Depends(get_db)):
    """Return a verifiable proof-of-execution for a task: per-step hashes plus a
    combined execution hash over all step content."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(422, "Invalid task identifier")

    task = db.query(models.Task).filter(models.Task.id == task_uuid).first()
    if not task:
        raise HTTPException(404, "Task not found")

    steps = db.query(models.TaskStep).filter(
        models.TaskStep.task_id == task_uuid
    ).order_by(models.TaskStep.step_number.asc()).all()

    step_hashes = []
    for s in steps:
        raw = f"{s.step_number}{s.action_type}{s.action_params}{s.reasoning}"
        step_hashes.append(hashlib.sha256(raw.encode()).hexdigest())

    execution_hash = hashlib.sha256("".join(step_hashes).encode()).hexdigest()

    return {
        "task_id":        task_id,
        "steps_count":    len(steps),
        "step_hashes":    step_hashes,
        "execution_hash": execution_hash,
        "verified":       len(steps) > 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SARVAM AI — Voice (STT saaras:v3 + TTS bulbul:v3). Fail-silent for demos.
# ═══════════════════════════════════════════════════════════════════════════════

class TranscribeRequest(BaseModel):
    audio_base64: str
    language:     Optional[str] = "te-IN"

class SpeakRequest(BaseModel):
    text:     str
    language: Optional[str] = "hi-IN"


def _new_client(key: str):
    """Create a Sarvam client across SDK versions (constructor arg name varies)."""
    from sarvamai import SarvamAI
    for kwargs in ({"api_subscription_key": key}, {"api_key": key}):
        try:
            return SarvamAI(**kwargs)
        except TypeError:
            continue
    return SarvamAI(key)   # positional fallback


def _sarvam_client():
    """Create a Sarvam client, or None if the SDK/key is unavailable."""
    try:
        from sarvamai import SarvamAI  # noqa: F401
    except Exception as e:
        print(f"⚠️  Sarvam SDK not installed: {e}")
        return None
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key.strip():
        print("⚠️  SARVAM_API_KEY is missing/empty (add to backend/.env, restart uvicorn).")
        return None
    try:
        return _new_client(key)
    except Exception as e:
        print(f"⚠️  Could not init Sarvam client: {e}")
        return None


@app.post("/sarvam/transcribe")
def sarvam_transcribe(req: TranscribeRequest):
    """Speech-to-text via Sarvam saaras:v3 (codemix). Never crashes."""
    client = _sarvam_client()
    if client is None:
        return {"transcript": "", "error": "Sarvam not configured"}

    tmp_path = None
    try:
        # Strip a possible data-URI prefix, then decode.
        b64 = req.audio_base64.split(",", 1)[-1]
        audio_bytes = base64.b64decode(b64)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            resp = client.speech_to_text.transcribe(
                file=f,
                model="saaras:v3",
                language_code=req.language or "te-IN",
                mode="codemix",
            )
        transcript = getattr(resp, "transcript", "") or ""
        detected = getattr(resp, "language_code", req.language) or req.language
        return {"transcript": transcript, "detected_language": detected}
    except Exception as e:
        print(f"⚠️  Sarvam STT failed: {e}")
        return {"transcript": "", "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass


@app.post("/sarvam/speak")
def sarvam_speak(req: SpeakRequest):
    """Text-to-speech via Sarvam bulbul:v3 (speaker 'neel'). Never crashes.
    Returns a debug 'error' field so failures are visible in /docs."""
    # 1. SDK present?
    try:
        from sarvamai import SarvamAI
    except Exception as e:
        return {"audio_base64": "", "error": f"SDK not installed: {e}"}
    # 2. Key present?
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key.strip():
        return {"audio_base64": "", "error": "SARVAM_API_KEY missing in backend/.env (restart uvicorn after adding)"}
    # 3. Call the API
    try:
        client = _new_client(key)
        text = (req.text or "")[:500]
        if not text.strip():
            return {"audio_base64": "", "error": "empty text"}
        resp = client.text_to_speech.convert(
            text=text,
            target_language_code=req.language or "hi-IN",
            speaker="vijay",
            model="bulbul:v3",
            enable_preprocessing=True,
        )
        audios = getattr(resp, "audios", None) or []
        if not audios:
            return {"audio_base64": "", "error": f"no audio in response: {resp!r}"[:300]}
        first = audios[0]
        audio_b64 = first if isinstance(first, str) else base64.b64encode(first).decode()
        return {"audio_base64": audio_b64}
    except Exception as e:
        print(f"⚠️  Sarvam TTS failed: {type(e).__name__}: {e}")
        return {"audio_base64": "", "error": f"{type(e).__name__}: {e}"}


# ═══════════════════════════════════════════════════════════════════════════════
# ASGI APP — Socket.io wraps FastAPI
# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTANT: socket_app wraps app. FastAPI WebSocket endpoints (/ws/stream/...)
# are passed through to FastAPI by socketio.ASGIApp correctly.
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)