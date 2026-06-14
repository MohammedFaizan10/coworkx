# CoWorkX — Host (Worker) Setup

You are running a **worker machine** for CoWorkX. Your PC runs the AI locally on
your GPU (LLaVA via Ollama) and executes browser tasks in Docker. You do NOT run
the backend or frontend — those run on the coordinator's PC.

You need: **Windows + NVIDIA GPU + Docker Desktop + Python 3.11**.

Ask the coordinator for their **IP address** (e.g. `10.0.50.69`).

---

## 1. Check your GPU
```
nvidia-smi
```
You should see your NVIDIA GPU. If not, install the latest NVIDIA driver.

## 2. Install Ollama
Download from https://ollama.com/download and run the installer.

## 3. Let Docker reach Ollama (important)
- Windows Search → "Edit the system environment variables" → Environment Variables
- System variables → New: name `OLLAMA_HOST`, value `0.0.0.0:11434`
- OK, then quit Ollama from the tray and reopen it (or reboot).

## 4. Pull the model
```
ollama pull llava:7b
```

## 5. Test it (optional)
```
ollama run llava:7b "say hi"
```
Run `nvidia-smi` in another terminal while it answers — GPU usage should rise.

## 6. Create `daemon/.env`
Create a file named `.env` in this folder (use the coordinator's IP):
```
COORDINATOR_URL=http://COORDINATOR_IP:8000
AGENT_COORDINATOR_URL=http://COORDINATOR_IP:8000
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=llava:7b
MAX_STEPS=15
```

## 7. Python deps
```
python -m venv venv
venv\Scripts\activate
pip install -r daemon_requirements.txt
pip install pywin32
```

## 8. Build the agent image (Docker Desktop must be running)
```
docker build -t coworkx-agent:latest ./agent
```

## 9. Start the daemon
```
python daemon.py
```
Look for `✅ Docker connected`, your GPU name, and `✅ Registered!`.

Your machine now appears in the coordinator's marketplace. Leave this running.
