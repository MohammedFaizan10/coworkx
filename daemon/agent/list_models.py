"""
List the Gemini models YOUR key can use for generateContent (vision loop).

Run (Windows CMD), from daemon/agent/:
    set GEMINI_API_KEY=your-key-here
    python list_models.py

Pick any name from the printed list and put it in daemon/.env as:
    GEMINI_MODEL=<that-name-without-the-"models/"-prefix>
"""

import os
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")


def main():
    if not API_KEY.strip():
        print("❌ Set GEMINI_API_KEY first:  set GEMINI_API_KEY=your-key-here")
        return

    genai.configure(api_key=API_KEY)

    print("Models on your key that support generateContent:\n")
    for m in genai.list_models():
        if "generateContent" in getattr(m, "supported_generation_methods", []):
            # strip the "models/" prefix for use in GEMINI_MODEL
            short = m.name.replace("models/", "")
            print(f"  {short}")


if __name__ == "__main__":
    main()
