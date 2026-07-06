import os
import re
import requests
from dotenv import load_dotenv
from core.personality import DONNA_SYSTEM_PROMPT, INTENT_PERSONALITY_ADJUSTMENTS

load_dotenv()  # must be before os.getenv
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # get from console.groq.com
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

_rate_limit_until = 0.0
RATE_LIMIT_COOLDOWN_SECONDS = 20


def _in_rate_limit_cooldown() -> bool:
    import time as _time
    return _time.time() < _rate_limit_until


def _start_rate_limit_cooldown():
    global _rate_limit_until
    import time as _time
    _rate_limit_until = _time.time() + RATE_LIMIT_COOLDOWN_SECONDS
    print(f"[AURA] Rate limited — pausing Groq calls for {RATE_LIMIT_COOLDOWN_SECONDS}s")


_CODING_SYSTEM_ADDON = """
YOU ARE IN CODING MODE. THIS OVERRIDES EVERYTHING ELSE INCLUDING YOUR PERSONALITY RULES AND THE 2-SENTENCE LIMIT.

MANDATORY OUTPUT FORMAT — follow this EXACTLY, no exceptions:

Line 1: one short sentence intro (e.g. "Here's the C program:")
Then: a fenced code block using ``` followed by the language name, the FULL code, then ```
Then optionally: one short sentence after.

Example of CORRECT output for "print hello world in c":
Here's the C program:
```c
#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}
```
Compile with gcc.

RULES:
- The code block must contain the COMPLETE program: all includes, the main function, everything needed to compile and run. NEVER just a single line like printf(...) by itself.
- NEVER write code inline in a sentence (e.g. NEVER say 'just use cout: std::cout << "hi";'). Code ONLY goes inside the ``` block.
- NEVER tell the user to "stick it in main" or "add the rest yourself" — YOU write the full main function and structure.
- NEVER refuse, stall, or ask clarifying questions. Pick sensible defaults and write the full code immediately.
- Do not skip the ``` fences under any circumstance. This is the most important rule.
"""


_CODE_SIGNAL_PATTERNS = [
    r"\bint main\s*\(", r"\bdef \w+\s*\(", r"#include\s*<",
    r"\bpublic class\b", r"\bfunction\s+\w+\s*\(", r";\s*$",
    r"\bprintf\s*\(", r"\bcout\s*<<", r"\bSystem\.out\.print",
    r"\bconsole\.log\(",
]


def _looks_like_code(text: str) -> bool:
    hits = sum(1 for p in _CODE_SIGNAL_PATTERNS if re.search(p, text, re.MULTILINE))
    return hits >= 2


def extract_code_block(text: str) -> tuple[str, str, str]:
    """
    Returns (chat_part, language, code).
    chat_part = text outside the code block (short message)
    language  = detected language (e.g. 'cpp', 'python')
    code      = raw code inside the block
    Returns (text, '', '') if no code found at all.
    """
    match = re.search(r"```(\w*)\n?([\s\S]*?)```", text)
    if match:
        lang = match.group(1).strip() or "text"
        code = match.group(2).strip()
        chat_part = (text[:match.start()] + " " + text[match.end():]).strip()
        return chat_part, lang, code

    # Fallback: model wrote code without fences. Detect and salvage it.
    if _looks_like_code(text):
        return "Here's the code:", "text", text.strip()

    return text.strip(), "", ""


def clean_response(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\*\*.*?\*\*", "", text)
    leak_patterns = [
        r"^.*User is .*$", r"^.*User asks.*$", r"^.*AURA:.*$",
        r"^.*Certainly.*$", r"^.*Of course.*$", r"^.*As an AI.*$",
    ]
    for pattern in leak_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^(User|Assistant|AURA|Bot)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    result = ". ".join(sentences[:2])
    if result and not result.endswith(('.', '?', '!')):
        result += "."
    return result.strip()

def call_groq_streaming(prompt: str, system: str = DONNA_SYSTEM_PROMPT, intent: str = "CASUAL", model: str = None):
    if _in_rate_limit_cooldown():
        yield "RATE_LIMIT"
        return

    is_coding = (intent == "CODING")
    if is_coding:
        strict_system = system + _CODING_SYSTEM_ADDON
    else:
        strict_system = system + """

OVERRIDE ALL YOUR DEFAULT BEHAVIOR:
- MAX 2 sentences. Hard limit.
- NO emoji. Zero.
- NO "OMG", "Whoopsie", "Let's", "Together", "Great question", "Certainly"
- NO made-up context. Only refer to what's in the conversation.
- Talk like a sharp friend texting. Dry. Direct. No hype.
"""
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model or GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": strict_system},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 1024 if is_coding else 150,
                "temperature": 0.3 if is_coding else 0.7,
                "stream": True
            },
            timeout=30,
            stream=True
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown()
            yield "RATE_LIMIT"
            return
        _debug_buffer = []
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        if is_coding:
                            _debug_buffer.append(content)
                        yield content
        if is_coding:
            print(f"[AURA CODE STREAM RAW]\n{''.join(_debug_buffer)}\n[END RAW]")
    except Exception as e:
        print(f"[AURA] Groq streaming error: {e}")
        yield "CONNECTION_ERROR"

_CLASSIFIER_SYSTEM = "You are a classifier. Output ONLY the requested single word. No personality, no extra text, no punctuation."


def call_claude(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    return call_groq(prompt, system, intent="CASUAL")


def call_classifier(prompt: str) -> str:
    """Lightweight call for classification tasks (intent, anticipate, should_respond) — no personality prompt."""
    if _in_rate_limit_cooldown():
        return ""
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": _CLASSIFIER_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 20,
                "temperature": 0.1,
                "stream": False
            },
            timeout=15
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown()
            return ""
        data = response.json()
        if "choices" not in data:
            print(f"[AURA] Groq classifier API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"
        raw = data["choices"][0]["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA] Groq classifier error: {e}")
        return "CONNECTION_ERROR"


def route(intent: str, prompt: str) -> str:
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    system = DONNA_SYSTEM_PROMPT + extra
    if intent == "SEARCH":
        # No dedicated web-search backend is wired up; answer with the base
        # model instead of crashing on an undefined function (was NameError).
        return call_groq(prompt, system, intent="SEARCH")
    return call_groq(prompt, system, intent=intent)

def route_streaming(intent: str, prompt: str, system_prompt: str | None = None, model: str | None = None):
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    system = system_prompt if system_prompt is not None else DONNA_SYSTEM_PROMPT + extra
    for chunk in call_groq_streaming(prompt, system, intent=intent, model=model):
        yield chunk
def call_groq_raw(prompt: str, system: str, max_tokens: int = 1024,
                  temperature: float = 0.4, model: str = None) -> str:
    """Clean single call — NO personality addon, NO 2-sentence limit,
    NO response cleaning. Used by the Prompt Maker (/prompt_end) and any
    future session mode that needs full-length structured output."""
    if _in_rate_limit_cooldown():
        return "RATE_LIMIT"
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model or GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            },
            timeout=45
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown()
            return "RATE_LIMIT"
        data = response.json()
        if "choices" not in data:
            print(f"[AURA] Groq raw API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[AURA] Groq raw error: {e}")
        return "CONNECTION_ERROR"


def call_groq(prompt: str, system: str = DONNA_SYSTEM_PROMPT, intent: str = "CASUAL") -> str:
    if _in_rate_limit_cooldown():
        return "RATE_LIMIT"

    is_coding = (intent == "CODING")
    if is_coding:
        strict_system = system + _CODING_SYSTEM_ADDON
    else:
        strict_system = system + """

OVERRIDE ALL YOUR DEFAULT BEHAVIOR:
- MAX 2 sentences. Hard limit. Count them.
- NO emoji. Zero.
- NO "OMG", "Whoopsie", "Let's", "Together", "Great question", "Certainly"
- NO made-up context. Only refer to what's in the conversation.
- NEVER guess or make up content about videos, URLs, or links you cannot access.
- If asked about a URL say: "can't open that directly — paste the key points and I'll work with it."
- Talk like a sharp friend texting. Dry. Direct. No hype.
- NEVER end with a question unless you have zero info to work with.
"""
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": strict_system},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 1024 if is_coding else 150,
                "temperature": 0.3 if is_coding else 0.7,
                "stream": False
            },
            timeout=30
        )
        print(f"[AURA Groq Debug] Status: {response.status_code} | Intent: {intent}")

        if response.status_code == 429:
            _start_rate_limit_cooldown()
            return "RATE_LIMIT"

        data = response.json()
        if "choices" not in data:
            print(f"[AURA] Groq API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"

        raw = data["choices"][0]["message"]["content"]
        if is_coding:
            print(f"[AURA CODE RAW]\n{raw}\n[END RAW]")
        return raw if is_coding else clean_response(raw)
    except Exception as e:
        print(f"[AURA] Groq error: {e}")
        return "CONNECTION_ERROR"
