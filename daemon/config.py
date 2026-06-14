"""
CoWorkX Daemon — Configuration
Reads from .env file or environment variables.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Fixed placeholder emitted in place of the Anthropic API key in any output.
REDACTION_PLACEHOLDER = "***REDACTED***"


class Config:
    # Where is the coordinator running? (used by the daemon ON THE HOST)
    COORDINATOR_URL: str = os.getenv("COORDINATOR_URL", "http://localhost:8000")

    # URL the AGENT (inside Docker) uses to reach the coordinator.
    # On Docker Desktop (Windows/Mac) containers reach the host via
    # host.docker.internal — NOT localhost.
    AGENT_COORDINATOR_URL: str = os.getenv(
        "AGENT_COORDINATOR_URL", "http://host.docker.internal:8000"
    )

    # Google Gemini API credential (legacy cloud-AI path — kept for fallback).
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Local-AI (LLaVA via Ollama) — runs on the host GPU.
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llava:7b")

    # Gemini model the agent uses (vision-capable).
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # Max reasoning steps per task. Free tier is ~20 requests/day per model,
    # so keep this low to make each run count.
    AGENT_MAX_STEPS: int = int(os.getenv("MAX_STEPS", "10"))

    # Set after registration — coordinator gives us this token
    MACHINE_TOKEN: str = os.getenv("MACHINE_TOKEN", "")

    # How often to send heartbeat (seconds)
    HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "10"))

    # Max seconds a task container can run before being killed
    TASK_TIMEOUT: int = int(os.getenv("TASK_TIMEOUT", "120"))

    # Docker image name for the agent
    AGENT_IMAGE: str = os.getenv("AGENT_IMAGE", "coworkx-agent:latest")

    # Container resource limits
    CONTAINER_MEMORY: str  = "512m"
    CONTAINER_CPU_QUOTA: int = 50000   # 50% of one CPU core

    def __repr__(self):
        return f"Config(coordinator={self.COORDINATOR_URL})"


def is_api_key_present(key: Optional[str]) -> bool:
    """Return True only when the API key is a non-empty, non-whitespace string.

    Returns False for None, empty strings, and whitespace-only strings (Req 8.3).
    """
    if key is None:
        return False
    return bool(key.strip())


def redact(text: str, secret: str, placeholder: str = REDACTION_PLACEHOLDER) -> str:
    """Replace every occurrence of ``secret`` in ``text`` with ``placeholder``.

    When ``secret`` is empty (or None) there is nothing to redact, so the text
    is returned unchanged (Req 8.4).
    """
    if not secret:
        return text
    return text.replace(secret, placeholder)