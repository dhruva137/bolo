"""Environment configuration. Every key is optional: missing keys switch that hop to its
fallback, and with no keys at all Bolo still runs end to end in offline mode (rule-based
understanding, simulator instead of WhatsApp)."""
import os

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OFFLINE = os.environ.get("BOLO_OFFLINE") == "1"
if not OFFLINE:
    load_dotenv(os.path.join(ROOT, ".env"))


def credential(name: str) -> str:
    return "" if OFFLINE else os.environ.get(name, "")


DATA_DIR = os.environ.get("BOLO_DATA_DIR", os.path.join(ROOT, "data"))
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
DB_PATH = os.path.join(DATA_DIR, "bolo.db")
LOCAL_STT_MODEL = os.environ.get("BOLO_STT_MODEL") or os.path.join(ROOT, "data", "models", "whisper-tiny")
for _d in (DATA_DIR, AUDIO_DIR, DOCS_DIR):
    os.makedirs(_d, exist_ok=True)

SARVAM_API_KEY = credential("SARVAM_API_KEY")
GROQ_API_KEY = credential("GROQ_API_KEY")
GEMINI_API_KEY = credential("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
SARVAM_LLM_MODEL = os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b")
GROQ_LLM_MODEL = os.environ.get("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
# Order in which LLM providers are tried; any without a key is skipped.
LLM_ORDER = [p.strip() for p in os.environ.get("LLM_ORDER", "gemini,sarvam,groq").split(",") if p.strip()]

WA_TOKEN = credential("WA_TOKEN")
WA_PHONE_NUMBER_ID = credential("WA_PHONE_NUMBER_ID")
WHATSAPP_LIVE = bool(WA_TOKEN and WA_PHONE_NUMBER_ID)

# Twilio WhatsApp sandbox: fallback channel when the Meta test number isn't available.
TWILIO_SID = credential("TWILIO_SID")
TWILIO_TOKEN = credential("TWILIO_TOKEN")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "whatsapp:+14155238886")
TWILIO_LIVE = bool(TWILIO_SID and TWILIO_TOKEN) and not WHATSAPP_LIVE

BOLNA_API_KEY = credential("BOLNA_API_KEY")
BOLNA_AGENT_ID = credential("BOLNA_AGENT_ID")

SITE_PORT = int(os.environ.get("BOLO_SITE_PORT", "8000"))
CUSTOMER_PORT = int(os.environ.get("BOLO_CUSTOMER_PORT", "8001"))
BUSINESS_PORT = int(os.environ.get("BOLO_BUSINESS_PORT", "8002"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def status() -> dict:
    from voice import local
    return {
        "stt_local": local.stt_ready(),
        "whatsapp": "live" if WHATSAPP_LIVE else ("twilio-sandbox" if TWILIO_LIVE else "simulator"),
        "stt_sarvam": bool(SARVAM_API_KEY),
        "stt_groq": bool(GROQ_API_KEY),
        "stt_gemini": bool(GEMINI_API_KEY),
        "llm": [p for p in LLM_ORDER if {"gemini": GEMINI_API_KEY, "sarvam": SARVAM_API_KEY, "groq": GROQ_API_KEY}.get(p)]
        or ["offline rules"],
        "tts": "sarvam" if SARVAM_API_KEY else ("eSpeak NG" if local.tts_ready() else "off"),
        "translate": "sarvam" if SARVAM_API_KEY else "off",
        "calls": "bolna" if (BOLNA_API_KEY and BOLNA_AGENT_ID) else "off",
    }
