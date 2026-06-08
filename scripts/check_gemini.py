"""Validate the configured Gemini key with one live call.

Resolves the key exactly like the backend does (root .env first, then operator's
.env as a fallback), then makes a tiny request and prints a clear verdict.

Run:  python scripts/check_gemini.py
"""

import os
import sys
import warnings

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OPERATOR_ENV = "/Users/manushresthkrishnan/projects/operator/backend/.env"


def _read_env_file(path):
    if not os.path.exists(path):
        return None
    for line in open(path):
        if line.strip().startswith("GEMINI_API_KEY="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return val or None
    return None


def resolve_key():
    # 1. real shell env, 2. this project's .env, 3. operator fallback
    return (os.environ.get("GEMINI_API_KEY")
            or _read_env_file(os.path.join(ROOT, ".env"))
            or _read_env_file(OPERATOR_ENV))


def main():
    key = resolve_key()
    if not key:
        print("✗ No GEMINI_API_KEY found. Paste one into .env (project root).")
        print("  → app runs in deterministic mode (no AI narratives).")
        sys.exit(1)
    print(f"• key: {key[:6]}…{key[-4:]}  (len {len(key)})")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        r = genai.GenerativeModel(model).generate_content(
            "Reply with exactly: OK",
            generation_config=genai.types.GenerationConfig(temperature=0, max_output_tokens=10),
        )
        print(f"✓ {model} works → {repr((r.text or '').strip())}")
        print("  Restart the backend and you'll see the green 'Gemini' badge.")
    except Exception as e:
        name = type(e).__name__
        msg = str(e)
        hint = ""
        if "API_KEY_SERVICE_BLOCKED" in msg or "PERMISSION_DENIED" in msg or name == "PermissionDenied":
            hint = "→ key is blocked from the Gemini API. Use an AI Studio key (https://aistudio.google.com/apikey) or enable 'Generative Language API' + clear API restrictions in Google Cloud."
        elif "RESOURCE_EXHAUSTED" in msg or name == "ResourceExhausted":
            hint = "→ key authenticates but is out of quota/credit. Top up billing or use a free AI Studio key."
        elif "API_KEY_INVALID" in msg or "API key not valid" in msg:
            hint = "→ key is malformed or wrong. Recopy it from https://aistudio.google.com/apikey."
        print(f"✗ {name}: {msg[:160]}")
        if hint:
            print(f"  {hint}")
        sys.exit(2)


if __name__ == "__main__":
    main()
