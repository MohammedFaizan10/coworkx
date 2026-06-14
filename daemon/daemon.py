"""
CoWorkX Daemon v0.0.3 — Day 3: Live Screen Streaming

New in v0.0.3:
  - FFmpeg captures Windows desktop (gdigrab) as JPEG frames
  - Playwright runs on HOST with headless=False (Chrome visible on screen)
  - JPEG frames sent via raw WebSocket to coordinator /ws/stream/{task_id}
  - Coordinator relays frames to browser via Socket.io room

Flow per task:
  1. HTTP polling picks up task (Day 2)
  2. start_streaming() → spawn FFmpeg + open WebSocket to coordinator
  3. frame_sender_loop() runs as background task (reads FFmpeg → sends frames)
  4. run_playwright_task() → launches Chrome on host, executes task visibly
  5. stop_streaming() → kill FFmpeg, close WebSocket
  6. POST /tasks/{id}/complete

IMPORTANT: Do NOT set WindowsSelectorEventLoopPolicy here.
ProactorEventLoop (Windows default) supports asyncio subprocess — needed for FFmpeg.
"""

import asyncio
import platform
import re
import sys

import httpx
import psutil
import websockets

try:
    from playwright.async_api import async_playwright
except Exception as _pw_err:
    # Playwright is only needed for the host-side fallback runner. On a worker
    # PC the task runs inside Docker, so a missing/broken Playwright is fine.
    async_playwright = None
    print(f"⚠️  Playwright not available on host (ok — tasks run in Docker): {_pw_err}")

from config import Config
from docker_manager import DockerManager
from machine_info import get_machine_specs

config = Config()
docker_manager = DockerManager()


def detect_nvidia_gpu():
    """Return (gpu_name, gpu_vram_gb) using nvidia-smi, or (None, None) if no
    NVIDIA GPU / nvidia-smi is unavailable."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
        first = out.splitlines()[0]
        name, mem = [p.strip() for p in first.split(",")]
        # mem looks like "6144 MiB"
        mib = int(re.search(r"(\d+)", mem).group(1))
        return name, max(1, round(mib / 1024))
    except Exception:
        return None, None

# ─── Global state ────────────────────────────────────────────────────────────
machine_id: str | None = None
is_busy: bool = False

# Streaming state
streaming_active: bool = False
ffmpeg_proc: asyncio.subprocess.Process | None = None
stream_ws = None  # websockets.WebSocketClientProtocol


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

async def register_machine() -> bool:
    global machine_id

    print("\n🔧 Detecting machine specs...")
    specs = get_machine_specs()

    # Detect NVIDIA GPU via nvidia-smi for an accurate name + VRAM (Local AI).
    gpu_name, gpu_vram_gb = detect_nvidia_gpu()
    if gpu_name:
        specs["gpu_model"] = gpu_name
        if gpu_vram_gb:
            specs["gpu_vram_gb"] = gpu_vram_gb
        print(f"   GPU:     {gpu_name} ({gpu_vram_gb or '?'} GB) — Local AI capable")

    print(f"   Name:    {specs.get('display_name', 'Unknown')}")
    print(f"   OS:      {specs.get('os', 'Unknown').upper()}")
    print(f"   CPU:     {specs.get('cpu_model', 'Unknown')} ({specs.get('cpu_cores', '?')} cores)")
    print(f"   RAM:     {specs.get('ram_gb', '?')} GB")
    print(f"   GPU:     {specs.get('gpu_model', 'None detected')}")
    print(f"   Software:{', '.join(specs.get('installed_software', []))}")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{config.COORDINATOR_URL}/machines/register",
                json=specs
            )
        if resp.status_code == 200:
            data = resp.json()
            machine_id = data["id"]
            print(f"✅ Registered!  Machine ID: {machine_id}")
            return True
        else:
            print(f"❌ Registration failed: {resp.status_code} — {resp.text}")
            return False
    except httpx.ConnectError:
        print(f"❌ Cannot reach coordinator at {config.COORDINATOR_URL}")
        print("   Is the backend running? (uvicorn main:socket_app --reload --port 8000)")
        return False
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# HEARTBEAT LOOP
# ═══════════════════════════════════════════════════════════════════════════════

async def heartbeat_loop():
    """POST /machines/{id}/heartbeat every 10 seconds."""
    while True:
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)
        if not machine_id:
            continue

        cpu_pct  = psutil.cpu_percent(interval=0.5)
        ram_pct  = psutil.virtual_memory().percent
        status   = "busy" if is_busy else "online"

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{config.COORDINATOR_URL}/machines/{machine_id}/heartbeat",
                    json={
                        "cpu_pct":        int(cpu_pct),
                        "ram_pct":        int(ram_pct),
                        "status":         status,
                        "daemon_version": "0.0.3",
                    }
                )
            print(f"💓 CPU {cpu_pct:.0f}%  RAM {ram_pct:.0f}%  [{status}]")
        except Exception as e:
            print(f"⚠️  Heartbeat failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TASK POLLING LOOP
# ═══════════════════════════════════════════════════════════════════════════════

async def poll_for_tasks():
    """GET /tasks/pending/{machine_id} every 3 seconds."""
    print("📡 Polling for tasks every 3 seconds...")

    while True:
        await asyncio.sleep(3)

        if not machine_id or is_busy:
            continue

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{config.COORDINATOR_URL}/tasks/pending/{machine_id}"
                )
            if resp.status_code == 200:
                task = resp.json()
                if task:
                    await handle_task(task)
        except Exception as e:
            print(f"⚠️  Poll error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TASK HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_task(task: dict):
    global is_busy

    task_id   = task["id"]
    task_desc = task["task_description"]

    print(f"\n{'='*52}")
    print(f"📋 NEW TASK RECEIVED")
    print(f"   ID:   {task_id}")
    print(f"   Task: {task_desc}")
    print(f"{'='*52}")

    is_busy = True

    # Mark as running
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{config.COORDINATOR_URL}/tasks/{task_id}/start"
            )

        if resp.status_code == 200:
            print("🏃 Task marked as RUNNING")
        else:
            print(f"❌ Start API returned {resp.status_code}: {resp.text[:200]}")

    except Exception as e:
        print(f"⚠️ Could not mark task as running: {e}")

    # ── Step 1: Live view comes from the AGENT's own screenshots now ──────────
    # The agent runs headless inside Docker, so capturing the host desktop with
    # FFmpeg was misleading. The agent POSTs each screenshot to the coordinator
    # (/tasks/{id}/frame), which relays it to the browser canvas. So we skip the
    # FFmpeg desktop capture entirely.
    # stream_ok = await start_streaming(task_id)   # disabled on purpose

    # ── Step 2: Run the task inside a Docker container (Day 4 Gemini agent) ───
    if docker_manager.is_available():
        output = await docker_manager.run_task(task_id, task_desc)
    else:
        print("⚠️  Docker unavailable — falling back to host Playwright runner")
        output = await run_playwright_task(task_desc)

    # ── Step 3: (FFmpeg streaming disabled — nothing to stop) ─────────────────
    # await stop_streaming()

    # ── Step 4: Report completion ─────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{config.COORDINATOR_URL}/tasks/{task_id}/complete",
                json={
                    "output": output,
                    "machine_id": machine_id
                }
            )

        if resp.status_code == 200:
            print(f"📤 Completion reported — status: {resp.json().get('status')}")
        else:
            print(f"❌ Complete API returned {resp.status_code}: {resp.text[:300]}")

    except Exception as e:
        print(f"⚠️ Could not report completion: {e}")

    finally:
        # CRITICAL: free the daemon so it polls for the next task.
        is_busy = False
        print("🟢 Daemon free — ready for the next task")


# ═══════════════════════════════════════════════════════════════════════════════
# STREAMING — FFmpeg + WebSocket
# ═══════════════════════════════════════════════════════════════════════════════

async def start_streaming(task_id: str) -> bool:
    """Spawn FFmpeg gdigrab + open WebSocket to coordinator streaming endpoint."""
    global ffmpeg_proc, stream_ws, streaming_active

    # ── 1. Spawn FFmpeg ───────────────────────────────────────────────────────
    # gdigrab = Windows screen capture driver
    # -framerate 5 = 5 fps (smooth enough for demo, low bandwidth)
    # -vcodec mjpeg = output as JPEG frames
    # -q:v 3 = quality (1=best, 31=worst; 3 is good balance)
    # -f image2pipe pipe:1 = write raw JPEG stream to stdout
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "gdigrab",
        "-framerate", "5",
        "-i", "desktop",
        "-vf", "scale=1280:720",
        "-vcodec", "mjpeg",
        "-q:v", "3",
        "-f", "image2pipe",
        "-loglevel", "error",
        "pipe:1",
    ]

    try:
        ffmpeg_proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        print("🎥 FFmpeg started (gdigrab capturing Windows desktop at 5fps)")
    except FileNotFoundError:
        print("❌ FFmpeg not found in PATH!")
        print("   Download: https://www.gyan.dev/ffmpeg/builds/")
        print("   Extract and add the bin/ folder to Windows PATH")
        return False
    except Exception as e:
        print(f"❌ FFmpeg spawn error: {e}")
        return False

    # Give FFmpeg 500ms to initialize
    await asyncio.sleep(0.5)

    # ── 2. Connect WebSocket to coordinator ───────────────────────────────────
    ws_url = f"ws://localhost:8000/ws/stream/{task_id}"
    try:
        stream_ws = await websockets.connect(
            ws_url,
            max_size=10_000_000,   # 10MB max message
            ping_interval=None,    # Disable auto-ping (we send frames frequently)
        )
        print(f"📡 Stream WebSocket connected → {ws_url}")
    except Exception as e:
        print(f"❌ Stream WebSocket connection failed: {e}")
        if ffmpeg_proc:
            ffmpeg_proc.terminate()
            ffmpeg_proc = None
        return False

    # ── 3. Start background frame sender ─────────────────────────────────────
    streaming_active = True
    asyncio.create_task(frame_sender_loop())
    return True


async def frame_sender_loop():
    """
    Reads raw JPEG frames from FFmpeg stdout by parsing SOI/EOI markers.

    JPEG frame boundaries:
      SOI (Start of Image) = 0xFF 0xD8
      EOI (End of Image)   = 0xFF 0xD9

    We buffer FFmpeg stdout, find complete SOI→EOI frames, and send each
    frame as a binary WebSocket message to the coordinator.
    """
    global streaming_active, stream_ws, ffmpeg_proc

    SOI = b'\xff\xd8'
    EOI = b'\xff\xd9'
    buffer = b''
    frames_sent = 0

    print("📡 Frame sender loop started")

    try:
        while streaming_active and ffmpeg_proc:
            # Read up to 64KB from FFmpeg stdout (async, non-blocking)
            chunk = await ffmpeg_proc.stdout.read(65536)
            if not chunk:
                print("📡 FFmpeg stdout closed")
                break

            buffer += chunk

            # Extract all complete JPEG frames from buffer
            while True:
                # Find start of next frame
                start = buffer.find(SOI)
                if start == -1:
                    buffer = b''   # No JPEG start marker — discard
                    break

                # Find end of frame (search AFTER start + 2 bytes)
                end = buffer.find(EOI, start + 2)
                if end == -1:
                    # Incomplete frame — keep buffer from SOI, wait for more data
                    buffer = buffer[start:]
                    break

                # Complete JPEG frame: start → end+2 (include EOI's 2 bytes)
                frame = buffer[start : end + 2]
                buffer = buffer[end + 2:]   # Remove this frame from buffer

                # Send frame to coordinator
                if stream_ws and frame:
                    try:
                        await stream_ws.send(frame)
                        frames_sent += 1
                        if frames_sent % 25 == 0:   # Log every 5 seconds (at 5fps)
                            print(f"📡 {frames_sent} frames sent — last frame: {len(frame)//1024}KB")
                    except Exception as e:
                        print(f"⚠️  Frame send error: {e}")
                        streaming_active = False
                        break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️  Frame reader exception: {e}")

    print(f"📡 Frame sender done. Total frames sent: {frames_sent}")


async def stop_streaming():
    """Kill FFmpeg process and close the stream WebSocket cleanly."""
    global streaming_active, ffmpeg_proc, stream_ws

    streaming_active = False

    # Kill FFmpeg
    if ffmpeg_proc:
        try:
            ffmpeg_proc.terminate()
            await asyncio.wait_for(ffmpeg_proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            ffmpeg_proc.kill()
        except Exception:
            pass
        ffmpeg_proc = None
        print("🛑 FFmpeg stopped")

    # Close WebSocket
    if stream_ws:
        try:
            await stream_ws.close()
        except Exception:
            pass
        stream_ws = None
        print("🛑 Stream WebSocket closed")


# ═══════════════════════════════════════════════════════════════════════════════
# PLAYWRIGHT TASK RUNNER (HOST — headless=False, browser visible on screen)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_playwright_task(task_description: str) -> str:
    """
    Run Playwright on the HOST machine with headless=False.
    Chrome is visible on the Windows desktop — captured by FFmpeg.
    This is what judges see in the live stream canvas.
    """
    if async_playwright is None:
        return "Host Playwright unavailable — task should run in Docker instead."

    print(f"\n🌐 Launching Chrome on host (headless=False — visible on screen)...")

    output = "Task completed"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    "--window-size=1200,800",
                    "--window-position=60,60",
                    "--no-sandbox",
                ]
            )
            context = await browser.new_context(viewport={"width": 1200, "height": 800})
            page    = await context.new_page()

            task_lower = task_description.lower()

            try:
                # ── Pattern matching for common task types ─────────────────
                if "google" in task_lower and ("search" in task_lower or "find" in task_lower):
                    # "search google for X" or "find X on google"
                    match = re.search(
                        r"(?:search(?:\s+for)?|find)\s+(.+?)(?:\s+on\s+google)?$",
                        task_lower
                    )
                    query = match.group(1).strip() if match else task_description
                    await page.goto("https://www.google.com")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1)
                    await page.fill('textarea[name="q"], input[name="q"]', query)
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(3)
                    title  = await page.title()
                    output = f"Searched Google for '{query}': {title}"

                elif "github" in task_lower:
                    await page.goto("https://github.com")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(3)
                    title  = await page.title()
                    output = f"Opened GitHub: {title}"

                elif "wikipedia" in task_lower:
                    match = re.search(r"(?:about|on|for)\s+(.+)", task_lower)
                    topic  = match.group(1).strip() if match else "Python"
                    url    = f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}"
                    await page.goto(url)
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(3)
                    title  = await page.title()
                    output = f"Opened Wikipedia — {title}"

                elif "youtube" in task_lower:
                    match = re.search(r"(?:search|find|play)\s+(.+?)(?:\s+on\s+youtube)?$", task_lower)
                    query  = match.group(1).strip() if match else "music"
                    await page.goto(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(3)
                    title  = await page.title()
                    output = f"YouTube search '{query}': {title}"

                elif "open" in task_lower or "go to" in task_lower or "visit" in task_lower:
                    # "open google.com" / "go to github.com" / "visit example.com"
                    urls = re.findall(
                        r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/\S*)?)',
                        task_description
                    )
                    if urls:
                        target = urls[0]
                        if not target.startswith("http"):
                            target = "https://" + target
                        await page.goto(target)
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(3)
                        title  = await page.title()
                        output = f"Opened {target} — Page title: '{title}'"
                    else:
                        await page.goto("https://www.google.com")
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)
                        output = "Opened browser (no URL found in task)"

                else:
                    # Default: Google search for the task
                    query  = task_description[:100]
                    await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                    await page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(3)
                    title  = await page.title()
                    output = f"Google search for task: {title}"

            except Exception as e:
                output = f"Task execution error: {e}"
                print(f"⚠️  Playwright task error: {e}")

            # Hold browser open for 2 seconds so judges can see the result
            print("⏳ Holding browser open 2s so stream shows result...")
            await asyncio.sleep(2)
            await browser.close()

    except Exception as e:
        output = f"Playwright launch error: {e}"
        print(f"❌ Playwright error: {e}")
        print("   Run:  playwright install chromium")

    print(f"📤 RESULT: {output}")
    return output


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    print("╔══════════════════════════════════════════╗")
    print("║       CoWorkX Daemon  v0.0.3             ║")
    print("║       HTTP Polling + Live Streaming      ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  OS:          {platform.system()}")
    print(f"║  Coordinator: {config.COORDINATOR_URL}")
    print(f"║  Streaming:   ws://localhost:8000/ws/stream/{{task_id}}")
    print("╚══════════════════════════════════════════╝")

    # Register with coordinator (retry until it works)
    while True:
        success = await register_machine()
        if success:
            break
        print("⏳ Retrying registration in 5s...")
        await asyncio.sleep(5)

    print(f"\n🚀 Daemon ready — polling every 3s, heartbeat every 10s\n")
    print("💡 Tip: Submit a task via http://localhost:8000/docs to see streaming\n")

    # Run heartbeat + task polling concurrently
    await asyncio.gather(
        heartbeat_loop(),
        poll_for_tasks(),
    )


if __name__ == "__main__":
    # NOTE: Do NOT set WindowsSelectorEventLoopPolicy here.
    # Windows ProactorEventLoop (default) is required for asyncio subprocess
    # (used by FFmpeg). It also supports websockets and httpx fine.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Daemon stopped cleanly.")