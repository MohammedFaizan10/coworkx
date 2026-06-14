"""
Standalone Gemini smoke test (TEST STEP 1 — run OUTSIDE Docker).

Reads GEMINI_API_KEY / GEMINI_MODEL from daemon/.env automatically, so you do
NOT need to set anything in the shell. Just run:

    cd c:\\Users\\mfaiz\\coworkx\\daemon\\agent
    python test_gemini.py

Verifies your key works, the model is vision-capable, and JSON parsing works.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load daemon/.env (one folder up from this file) BEFORE importing agent.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import google.generativeai as genai
from agent import parse_action, SYSTEM_PROMPT, GEMINI_MODEL

API_KEY = os.environ.get("GEMINI_API_KEY", "")

# A 1x1 red PNG (smallest valid image) so we exercise the vision path.
RED_DOT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d7636060f8cf00000301010018dd8db00000000049454e44ae426082"
)


def main():
    if not API_KEY.strip():
        print("❌ No GEMINI_API_KEY found in daemon/.env")
        print("   Open c:\\Users\\mfaiz\\coworkx\\daemon\\.env and add:")
        print("   GEMINI_API_KEY=AIza...your-key...")
        return

    print(f"🔑 Key loaded from .env (starts with: {API_KEY[:6]}...)")
    if not API_KEY.startswith("AIza"):
        print("⚠️  Warning: AI Studio keys usually start with 'AIza'. "
              "Yours doesn't — if you get an auth error, grab the key from "
              "https://aistudio.google.com/apikey")

    print(f"🧠 Asking {GEMINI_MODEL} for one action (with a test image)...")
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)

    resp = model.generate_content([
        "TASK: open github.com\nThe screenshot is a blank test image. "
        "Decide the first action. Reply with ONE raw JSON object only.",
        {"mime_type": "image/png", "data": RED_DOT_PNG},
    ])

    raw = resp.text
    print("\nRAW RESPONSE:\n" + raw)

    action = parse_action(raw)
    print("\n✅ Parsed OK:")
    print(f"   action    = {action['action']}")
    print(f"   params    = {action['params']}")
    print(f"   reasoning = {action['reasoning']}")


if __name__ == "__main__":
    main()
