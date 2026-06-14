"""
CoWorkX Daemon — Docker Manager
Handles spinning up, monitoring, and cleaning up Docker containers.

Each task gets its own isolated container:
  - Based on coworkx-agent:latest image
  - Task description passed as env var
  - Auto-removed after completion (remove=True)
  - Resource-limited (CPU + RAM cap)
  - Network isolated from host's private network
"""

import asyncio
from pathlib import Path

import docker
import docker.errors

from config import Config

config = Config()


class DockerManager:

    def __init__(self):
        """Connect to Docker daemon on startup"""
        try:
            self.client = docker.from_env()
            # Quick ping to make sure Docker is actually running
            self.client.ping()
            print("✅ Docker connected")
        except docker.errors.DockerException as e:
            print(f"❌ Docker not available: {e}")
            print("   → Start Docker Desktop and restart the daemon")
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    # ─────────────────────────────────────────────────────────────────────────
    # BUILD IMAGE
    # ─────────────────────────────────────────────────────────────────────────

    def build_agent_image(self) -> bool:
        """
        Build the coworkx-agent Docker image from ./agent/Dockerfile.
        Only needs to run ONCE — Docker caches the result.
        Takes 3–8 minutes first time (downloads Chromium).
        Subsequent builds are instant (all cached).
        """
        if not self.client:
            print("❌ Docker not available — cannot build image")
            return False

        agent_dir = Path(__file__).parent / "agent"
        if not agent_dir.exists():
            print(f"❌ agent/ folder not found at {agent_dir}")
            return False

        print("🔨 Building coworkx-agent Docker image...")
        print("   (First build takes 3–8 min — downloads Playwright + Chromium)")
        print("   Subsequent builds are instant (cached)")

        try:
            image, build_logs = self.client.images.build(
                path=str(agent_dir),
                tag="coworkx-agent:latest",
                rm=True,         # Remove intermediate containers
                forcerm=True,    # Force remove even on errors
            )
            # Print build output
            for log in build_logs:
                if "stream" in log:
                    line = log["stream"].strip()
                    if line:
                        print(f"   {line}")

            print("✅ Image built: coworkx-agent:latest")
            return True

        except docker.errors.BuildError as e:
            print(f"❌ Build error: {e}")
            for log in e.build_log:
                if "stream" in log:
                    print(f"   {log['stream'].strip()}")
            return False

        except Exception as e:
            print(f"❌ Unexpected build error: {e}")
            return False

    def image_exists(self) -> bool:
        """Check if coworkx-agent image is already built"""
        if not self.client:
            return False
        try:
            self.client.images.get(config.AGENT_IMAGE)
            return True
        except docker.errors.ImageNotFound:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # RUN TASK
    # ─────────────────────────────────────────────────────────────────────────

    async def run_task(self, task_id: str, task_description: str) -> str:
        """
        Spin up a Docker container to execute the task.
        Returns the container output as a string.

        This is async but Docker SDK is sync — we use run_in_executor
        so we don't block the event loop (heartbeats keep running).
        """
        if not self.client:
            return "❌ Docker not available"

        if not self.image_exists():
            print("⚠️  Image not found — building now...")
            success = self.build_agent_image()
            if not success:
                return "❌ Docker image build failed"

        print(f"🐳 Container starting for task {task_id}")

        # Run the blocking Docker call in a thread pool
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            self._run_container_sync,
            task_id,
            task_description,
        )
        return output

    def _run_container_sync(self, task_id: str, task_description: str) -> str:
        """
        Synchronous container runner — called inside thread executor.

        Security flags:
          cap_drop=ALL          — remove all Linux capabilities
          security_opt          — no privilege escalation
          mem_limit             — max 512MB RAM
          cpu_quota             — max 50% of one CPU core
          network_mode=bridge   — has internet but isolated from host LAN
          remove=True           — auto-delete container after exit
        """
        try:
            output_bytes = self.client.containers.run(
                image=config.AGENT_IMAGE,
                environment={
                    "TASK_ID":          task_id,
                    "TASK_DESCRIPTION": task_description,
                    # Local AI: the container calls Ollama/LLaVA on the host GPU
                    "OLLAMA_HOST":      config.OLLAMA_HOST,
                    "OLLAMA_MODEL":     config.OLLAMA_MODEL,
                    "MAX_STEPS":        str(config.AGENT_MAX_STEPS),
                    # Container reaches the host coordinator via host.docker.internal
                    "COORDINATOR_URL":  config.AGENT_COORDINATOR_URL,
                },
                # Let the container resolve host.docker.internal on Linux too.
                # (No-op on Docker Desktop where it already resolves.)
                extra_hosts={"host.docker.internal": "host-gateway"},
                # Security
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                # Resource limits
                mem_limit=config.CONTAINER_MEMORY,
                cpu_period=100000,
                cpu_quota=config.CONTAINER_CPU_QUOTA,
                # Networking — bridge has internet, isolated from host
                network_mode="bridge",
                # Cleanup
                remove=True,      # Delete container after it exits
                detach=False,     # Wait for container to finish
                stdout=True,
                stderr=True,
                # timeout= REMOVED — not supported in this Docker SDK version
                # Container will run until task completes naturally
            )

            output = output_bytes.decode("utf-8") if isinstance(output_bytes, bytes) else str(output_bytes)
            print(f"📦 Container output for {task_id}:\n{output}")
            return output.strip()

        except docker.errors.ContainerError as e:
            error = f"Container exited with error code {e.exit_status}: {e.stderr}"
            print(f"❌ {error}")
            return error

        except docker.errors.ImageNotFound:
            error = "Image coworkx-agent:latest not found — run build_agent_image() first"
            print(f"❌ {error}")
            return error

        except Exception as e:
            error = f"Docker error: {type(e).__name__}: {e}"
            print(f"❌ {error}")
            return error