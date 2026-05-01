import re
import ollama
from core.personality import DONNA_SYSTEM_PROMPT


def clean_response(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)   # strip code blocks
    text = re.sub(r"\*\*.*?\*\*", "", text)
    text = re.sub(r"Note:.*", "", text, flags=re.DOTALL)
    text = re.sub(r"Instructions:.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"User:.*", "", text, flags=re.DOTALL)
    text = re.sub(r"AURA:.*", "", text, flags=re.DOTALL)
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    result = ". ".join(sentences[:2])
    if result and not result.endswith("."):
        result += "."
    return result.strip()


def call_ollama(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    try:
        strict_system = system + """
CRITICAL OUTPUT RULES:
- Max 2 short sentences. That's it.
- No bullet points. No markdown. No headers.
- No meta text. No "User:" or "AURA:" prefixes.
- Talk like a friend texting — casual and direct.
- Never start your reply with a quote mark.
"""
        response = ollama.chat(
            model="phi3",
            messages=[
                {"role": "system", "content": strict_system},
                {"role": "user",   "content": prompt}
            ]
        )
        raw = response["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA] Ollama error: {e}")
        return "CONNECTION_ERROR"


def call_claude(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    return call_ollama(prompt, system)


def route(intent: str, prompt: str) -> str:
    # all routes use Ollama for now
    # Phase 3 will add Claude for CODING/SEARCH
    return call_ollama(prompt)