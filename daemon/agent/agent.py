"""
CoWorkX Agent — LOCAL AI edition (LLaVA via Ollama, runs INSIDE Docker)

The "thinking" now happens on the HOST machine's GPU via Ollama running LLaVA.
No cloud AI. The container calls Ollama at http://host.docker.internal:11434.

Every step:
  1. Screenshot the page (Playwright)
  2. Send screenshot + task + history to LLaVA via Ollama /api/generate
  3. LLaVA returns the next action as JSON {action, params, reasoning}
  4. Execute the action, log the step (with GPU inference time) to the coordinator
  5. Repeat until task_complete or MAX_STEPS

Environment variables (injected by the daemon):
  TASK_ID, TASK_DESCRIPTION, COORDINATOR_URL
  OLLAMA_HOST    — default http://host.docker.internal:11434
  OLLAMA_MODEL   — default llava:7b
  MAX_STEPS      — default 20
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import sys

import httpx
import requests
from playwright.async_api import async_playwright, Page, Browser

# ── Configuration from environment ────────────────────────────────────────────
TASK_ID         = os.environ.get("TASK_ID", "test-task")
TASK_DESC       = os.environ.get("TASK_DESCRIPTION", "open google.com")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://host.docker.internal:8000")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llava:7b")
MAX_STEPS       = int(os.environ.get("MAX_STEPS", "20"))

ACTION_TIMEOUT_SECONDS = 10        # browser action timeout
OLLAMA_TIMEOUT_SECONDS = 90        # one LLaVA inference call budget
STEP_DELAY_SECONDS     = 0         # local AI has no rate limit → no delay needed

VALID_TOOLS = {
    "browser_navigate", "browser_click", "browser_type",
    "browser_extract", "browser_screenshot", "task_complete",
}

# ── LLaVA prompt — simpler & more explicit than the Gemini one ────────────────
# LLaVA follows instructions less reliably, so we give a strict format plus a
# worked example, and we also force Ollama to emit JSON via "format": "json".
SYSTEM_PROMPT = """You are a web-browsing robot. You look at a screenshot and choose ONE next action.

You MUST answer with ONLY a JSON object. No words before or after. Use EXACTLY these keys:
  "action"  : one of browser_navigate, browser_click, browser_type, browser_extract, browser_screenshot, task_complete
  "params"  : an object with the parameters for that action
  "reasoning": a short sentence (under 20 words)

Parameters per action:
  browser_navigate  -> {"url": "https://..."}
  browser_click     -> {"selector": "css selector"}
  browser_type      -> {"selector": "css selector", "text": "text to type"}
  browser_extract   -> {"selector": "css selector"}
  browser_screenshot-> {}
  task_complete     -> {"output": "the final answer"}

Rules:
- Answer with JSON only.
- If you already have the answer, use task_complete immediately.
- To search a site, it is often easiest to browser_navigate directly to a results URL.

Example answer:
{"action": "browser_navigate", "params": {"url": "https://news.ycombinator.com"}, "reasoning": "Go to the site to find the story."}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PARSING (robust — LLaVA often wraps or adds prose)
# ═══════════════════════════════════════════════════════════════════════════════

def extract_json_object(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No '{' in response")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
        else:
            if ch == '"': in_str = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start:i + 1]
    raise ValueError("No balanced JSON object found")


def parse_action(raw_text: str) -> dict:
    """Strict parse: JSON with action/params/reasoning, action must be valid."""
    candidate = extract_json_object(raw_text)
    data = json.loads(candidate)
    if not isinstance(data, dict) or "action" not in data:
        raise ValueError("Missing 'action'")
    action = data.get("action")
    params = data.get("params", {})
    reasoning = data.get("reasoning", "")
    if action not in VALID_TOOLS:
        raise ValueError(f"Unknown action '{action}'")
    if not isinstance(params, dict):
        params = {}
    return {"action": action, "params": params, "reasoning": str(reasoning)}


def fallback_parse(text: str) -> dict:
    """Last resort when LLaVA returns natural language instead of JSON.
    Scan the text for a known tool name and obvious params (url/selector)."""
    low = text.lower()
    # find a tool mentioned
    action = None
    for tool in VALID_TOOLS:
        if tool in low:
            action = tool
            break
    # url?
    url_match = re.search(r"https?://[^\s\"'<>]+", text)
    if action is None:
        action = "browser_navigate" if url_match else "task_complete"

    params = {}
    if action == "browser_navigate" and url_match:
        params = {"url": url_match.group(0)}
    elif action == "task_complete":
        params = {"output": text.strip()[:1000]}
    return {"action": action, "params": params,
            "reasoning": "Recovered from non-JSON response."}


# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA CALL (local GPU inference)
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(history: list, current_url: str) -> str:
    lines = []
    for h in history[-10:]:
        lines.append(f"  step {h['step']}: {h['action']} -> {str(h.get('outcome',''))[:120]}")
    hist = "\n".join(lines) if lines else "  (no actions yet)"
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"TASK: {TASK_DESC}\n"
        f"CURRENT URL: {current_url or '(blank)'}\n"
        f"HISTORY:\n{hist}\n\n"
        f"Look at the screenshot and reply with ONE JSON action now."
    )


def call_ollama(screenshot_b64: str, history: list, current_url: str):
    """Call LLaVA via Ollama. Returns (action_dict, gpu_ms). Retries once on timeout."""
    prompt = build_prompt(history, current_url)
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "images": [screenshot_b64],
        "stream": False,
        "format": "json",                 # ask Ollama to emit valid JSON
        "options": {"temperature": 0.1},  # low temp = more consistent format
    }
    url = f"{OLLAMA_HOST}/api/generate"

    for attempt in range(2):  # initial + one retry on timeout
        try:
            resp = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "")
            # eval_duration is in nanoseconds → milliseconds
            gpu_ms = int(data.get("eval_duration", 0) / 1_000_000)
            print(f"   🧠 LLaVA ({OLLAMA_MODEL}) {gpu_ms}ms raw: {raw[:200]}")
            try:
                return parse_action(raw), gpu_ms
            except Exception:
                return fallback_parse(raw), gpu_ms
        except requests.exceptions.Timeout:
            print(f"   ⏳ Ollama timed out (attempt {attempt + 1}) — retrying…")
            continue
        except Exception as e:
            print(f"   ⚠️  Ollama call failed: {type(e).__name__}: {e}")
            raise
    raise TimeoutError(f"Ollama did not respond within {OLLAMA_TIMEOUT_SECONDS}s")


# ═══════════════════════════════════════════════════════════════════════════════
# BROWSER ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def take_screenshot(page: Page) -> bytes:
    return await page.screenshot(type="png")


async def execute_action(page: Page, action: str, params: dict) -> str:
    if action == "browser_navigate":
        url = params.get("url")
        if not url:
            return "ERROR: missing 'url'"
        await page.goto(url, wait_until="domcontentloaded")
        return f"navigated to {url}; title='{await page.title()}'"

    if action == "browser_click":
        selector = params.get("selector")
        if not selector:
            return "ERROR: missing 'selector'"
        await page.wait_for_selector(selector, timeout=ACTION_TIMEOUT_SECONDS * 1000)
        await page.click(selector)
        return f"clicked '{selector}'"

    if action == "browser_type":
        selector = params.get("selector")
        text = params.get("text", "")
        if not selector:
            return "ERROR: missing 'selector'"
        await page.wait_for_selector(selector, timeout=ACTION_TIMEOUT_SECONDS * 1000)
        await page.fill(selector, text)
        await page.press(selector, "Enter")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        return f"typed '{text}' into '{selector}' and pressed Enter"

    if action == "browser_extract":
        selector = params.get("selector")
        if not selector:
            return "ERROR: missing 'selector'"
        await page.wait_for_selector(selector, timeout=ACTION_TIMEOUT_SECONDS * 1000)
        text = await page.inner_text(selector)
        return f"extracted from '{selector}': {text[:1000]}"

    if action == "browser_screenshot":
        return "screenshot captured"

    if action == "task_complete":
        return params.get("output", "(no output)")

    return f"ERROR: unknown action '{action}'"


# ═══════════════════════════════════════════════════════════════════════════════
# COORDINATOR REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

async def send_frame(client: httpx.AsyncClient, screenshot_bytes: bytes) -> None:
    if not screenshot_bytes:
        return
    try:
        await client.post(f"{COORDINATOR_URL}/tasks/{TASK_ID}/frame",
                          content=screenshot_bytes,
                          headers={"Content-Type": "image/png"}, timeout=10)
    except Exception as e:
        print(f"   ⚠️  frame send failed: {e}")


async def log_step(client: httpx.AsyncClient, step_number: int, action: str,
                   params: dict, reasoning: str, screenshot_bytes: bytes,
                   gpu_ms: int) -> None:
    screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest() if screenshot_bytes else None
    # Prefix reasoning with the local-GPU inference time so the UI shows it.
    tagged = f"[🧠 {OLLAMA_MODEL} · {gpu_ms}ms] {reasoning}"
    payload = {
        "step_number":     step_number,
        "action_type":     action[:50],
        "action_params":   params,
        "reasoning":       tagged,
        "screenshot_hash": screenshot_hash,
    }
    try:
        resp = await client.post(f"{COORDINATOR_URL}/tasks/{TASK_ID}/steps",
                                 json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"   📝 step #{step_number} logged ({action}, {gpu_ms}ms GPU)")
        else:
            print(f"   ⚠️  step log {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"   ⚠️  step log failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

async def run_agent_loop(page: Page, client: httpx.AsyncClient) -> str:
    history: list = []
    final_output = "Task ended without task_complete"
    last_sig = None
    repeat_count = 0

    for step_number in range(1, MAX_STEPS + 1):
        print(f"\n──── STEP {step_number}/{MAX_STEPS} ────")
        if step_number > 1:
            await asyncio.sleep(STEP_DELAY_SECONDS)

        try:
            screenshot_bytes = await asyncio.wait_for(
                take_screenshot(page), timeout=ACTION_TIMEOUT_SECONDS)
        except Exception as e:
            print(f"   ⚠️  screenshot failed: {e}")
            screenshot_bytes = b""

        await send_frame(client, screenshot_bytes)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode() if screenshot_bytes else ""

        try:
            current_url = page.url
        except Exception:
            current_url = ""

        # Ask LLaVA (local GPU) for the next action
        try:
            decision, gpu_ms = call_ollama(screenshot_b64, history, current_url)
        except Exception as e:
            outcome = f"LLaVA failed: {type(e).__name__}: {e}"
            print(f"   ❌ {outcome}")
            history.append({"step": step_number, "action": "ai_error",
                            "params": {}, "outcome": outcome})
            await log_step(client, step_number, "ai_error", {}, outcome, screenshot_bytes, 0)
            continue

        action    = decision["action"]
        params    = decision["params"]
        reasoning = decision["reasoning"]
        print(f"   ➡️  action={action}  params={params}")

        if action == "task_complete":
            final_output = params.get("output", "(no output)")
            await log_step(client, step_number, action, params, reasoning,
                           screenshot_bytes, gpu_ms)
            print(f"   ✅ task_complete: {final_output[:120]}")
            return final_output

        # ── Anti-loop safety net for weak models (e.g. moondream) ────────────
        # If the model proposes the same action repeatedly, it's stuck. Read the
        # current page ourselves and complete the task with a real answer.
        sig = f"{action}:{json.dumps(params, sort_keys=True)}"
        if sig == last_sig:
            repeat_count += 1
        else:
            repeat_count = 0
            last_sig = sig

        if repeat_count >= 2:
            print("   🔁 Stuck (repeated action) — auto-extracting page and completing.")
            recovered = await auto_complete_from_page(page)
            await log_step(client, step_number, "task_complete",
                           {"output": recovered}, "Auto-completed after loop detection.",
                           screenshot_bytes, gpu_ms)
            print(f"   ✅ auto task_complete: {recovered[:120]}")
            return recovered

        try:
            outcome = await asyncio.wait_for(
                execute_action(page, action, params),
                timeout=ACTION_TIMEOUT_SECONDS + 20)
        except asyncio.TimeoutError:
            outcome = f"ERROR: action '{action}' hard-timed out"
        except Exception as e:
            outcome = f"ERROR: {type(e).__name__}: {e}"
        print(f"   📤 outcome: {outcome[:200]}")

        # Post a frame AFTER the action so the canvas shows the resulting page.
        try:
            after_shot = await asyncio.wait_for(take_screenshot(page), timeout=ACTION_TIMEOUT_SECONDS)
            await send_frame(client, after_shot)
        except Exception:
            pass

        history.append({"step": step_number, "action": action,
                        "params": params, "outcome": outcome})
        await log_step(client, step_number, action, params, reasoning,
                       screenshot_bytes, gpu_ms)

    print(f"\n⛔ Reached MAX_STEPS={MAX_STEPS}")
    # On budget exhaustion, still try to return something useful from the page.
    try:
        return await auto_complete_from_page(page)
    except Exception:
        return final_output


async def auto_complete_from_page(page: Page) -> str:
    """Read a sensible answer from the current page (title + main text).
    Used when a weak model loops so the task still finishes with real output."""
    try:
        title = await page.title()
    except Exception:
        title = ""
    snippet = ""
    for sel in ["main", "article", "h1", "body"]:
        try:
            txt = (await page.inner_text(sel)).strip()
            if txt:
                snippet = txt[:300]
                break
        except Exception:
            continue
    url = ""
    try:
        url = page.url
    except Exception:
        pass
    return f"Page: {title} ({url})\n{snippet}".strip()


async def main():
    print("=" * 56)
    print("🤖 CoWorkX Agent (LOCAL AI — LLaVA via Ollama)")
    print(f"   Task ID:     {TASK_ID}")
    print(f"   Task:        {TASK_DESC}")
    print(f"   Ollama:      {OLLAMA_HOST}")
    print(f"   Model:       {OLLAMA_MODEL}")
    print(f"   Coordinator: {COORDINATOR_URL}")
    print("=" * 56)

    # Verify Ollama is reachable before launching the browser
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        r.raise_for_status()
        print(f"✅ Ollama reachable. Models: "
              f"{[m.get('name') for m in r.json().get('models', [])]}")
    except Exception as e:
        print(f"❌ Cannot reach Ollama at {OLLAMA_HOST}: {e}")
        print("   Is `ollama serve` running on the host? Is the model pulled?")
        sys.exit(1)

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded")
        except Exception:
            pass

        print("\n🌐 Browser launched. Starting LOCAL reasoning loop...\n")
        async with httpx.AsyncClient() as client:
            try:
                result = await run_agent_loop(page, client)
            except Exception as e:
                result = f"❌ Agent crashed: {type(e).__name__}: {e}"
                print(result)
            finally:
                await browser.close()

    print("\n" + "=" * 56)
    print("📤 FINAL RESULT:")
    print(result)
    print("=" * 56)


if __name__ == "__main__":
    asyncio.run(main())
