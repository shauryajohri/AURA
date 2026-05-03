import re
import ollama
from core.personality import DONNA_SYSTEM_PROMPT


def clean_response(text: str) -> str:
    # 1. Strip code blocks and markdown
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\*\*.*?\*\*", "", text)
    text = re.sub(r"\[.*?\]\(.*?\)", "", text)  # markdown links

    # 2. Remove entire lines that are meta-leaks
    leak_patterns = [
        r"^.*User is .*$",
        r"^.*User asks.*$",
        r"^.*AURA:.*$",
        r"^.*Screen content.*$",
        r"^.*Current app.*$",
        r"^.*Note:.*$",
        r"^.*Instructions:.*$",
        r"^.*Certainly.*$",
        r"^.*Of course.*$",
        r"^.*As an AI.*$",
        r"^.*I notice you.*$",
        r"^.*You seem to be.*$",
    ]
    for pattern in leak_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

    # 3. Strip "Also —" or "Also -" follow-ups that came from anticipate
    text = re.sub(r"Also\s*[-—]\s*.*$", "", text, flags=re.IGNORECASE)

    # 4. Remove role prefixes like "User says:", "Assistant:"
    text = re.sub(r"^(User|Assistant|AI|AURA|Bot)\s*:\s*", "", text, flags=re.IGNORECASE)

    # 5. Remove surrounding quotes
    text = text.strip().strip('"').strip("'").strip()

    # 6. Collapse multiple lines and spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 7. Split into sentences, keep max 2
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    result = ". ".join(sentences[:2])
    if result and not result.endswith(('.', '?', '!')):
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