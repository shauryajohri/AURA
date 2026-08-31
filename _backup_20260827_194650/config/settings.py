import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PICOVOICE_KEY = os.getenv("PICOVOICE_KEY", "")
AURA_NAME = "Aura"
WAKE_WORD = "aura"
TTS_RATE = 175
TTS_VOLUME = 1.08