import os

from dotenv import load_dotenv

load_dotenv()

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def _auto_pick_gemini_model():
    if not GEMINI_API_KEY:
        return "gemini-1.5-flash"
    try:
        from google import genai
        c = genai.Client(api_key=GEMINI_API_KEY)
        bad = ("image", "tts", "live", "audio", "embedding")
        names = []
        for m in c.models.list():
            n = m.name.replace("models/", "")
            if "generateContent" in (m.supported_actions or []) and "flash" in n and not any(b in n for b in bad):
                names.append(n)
        names.sort()
        pick = next((n for n in names if n.endswith("flash-latest")), names[0] if names else "")
        print(f"Auto-picked Gemini model: {pick}")
        return pick
    except Exception as e:
        print(f"Failed to auto-pick model: {e}")
        return "gemini-1.5-flash"

MODEL_NAME = os.getenv("MODEL_NAME")
if not MODEL_NAME:
    MODEL_NAME = _auto_pick_gemini_model()


# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Sandbox Limits
SANDBOX_MEM_LIMIT = "512m"
SANDBOX_CPU_LIMIT = "1.0"
SANDBOX_TIMEOUT_SEC = 120

# Execution Limits
MAX_ATTEMPTS = 5
MAX_TIME_MINUTES = 10
