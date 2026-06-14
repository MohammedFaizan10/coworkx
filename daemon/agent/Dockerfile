# CoWorkX Agent Container
# Base image: Python 3.12 slim (small size)
# Installs: Playwright + Chromium browser
# This image is built ONCE, then reused for every task

FROM python:3.12-slim

# ── System dependencies needed by Chromium ────────────────────────────────────
# These are the exact packages Playwright requires on Debian/Ubuntu
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2t64 \
    libatk-bridge2.0-0t64 \
    libatk1.0-0t64 \
    libcups2t64 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0t64 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    xdg-utils \
    fonts-unifont \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory inside container ────────────────────────────────────────
WORKDIR /agent

# ── Install Python packages ───────────────────────────────────────────────────
COPY agent_requirements.txt .
RUN pip install --no-cache-dir -r agent_requirements.txt

# ── Install Playwright + download Chromium browser ────────────────────────────
# We pre-installed OS deps above, so no --with-deps needed
RUN playwright install chromium

# ── Copy the agent script ─────────────────────────────────────────────────────
COPY agent.py .

# ── Environment defaults ──────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV TASK_ID=test
ENV TASK_DESCRIPTION="open google.com"
# Local-AI defaults (overridden by the daemon at run time)
ENV OLLAMA_HOST="http://host.docker.internal:11434"
ENV OLLAMA_MODEL="llava:7b"

# ── Run the agent ─────────────────────────────────────────────────────────────
CMD ["python", "agent.py"]