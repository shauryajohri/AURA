import os
import re
import requests
from core.personality import DONNA_SYSTEM_PROMPT, INTENT_PERSONALITY_ADJUSTMENTS

GROQ_API_KEY = "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"  # get from console.groq.com
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


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


def call_groq(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    strict_system = system + """

OVERRIDE ALL YOUR DEFAULT BEHAVIOR:
- MAX 2 sentences. Hard limit.
- NO emoji. Zero.
- NO "OMG", "Whoopsie", "Let's", "Together", "Great question", "Certainly"
- NO made-up context. Only refer to what's in the conversation.
- Talk like a sharp friend texting. Dry. Direct. No hype.
- If you don't know something, say so in one line.
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
                "max_tokens": 150,
                "temperature": 0.7,
                "stream": False
            },
            timeout=15
        )
        data = response.json()
        print(f"[AURA Groq Debug] Status: {response.status_code} | Response: {data}")  # add this
        raw = data["choices"][0]["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA] Groq error: {e}")
        return "CONNECTION_ERROR"

def call_groq_streaming(prompt: str, system: str = DONNA_SYSTEM_PROMPT):
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
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": strict_system},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": 150,
                "temperature": 0.7,
                "stream": True
            },
            timeout=15,
            stream=True
        )
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
    except Exception as e:
        print(f"[AURA] Groq streaming error: {e}")
        yield "CONNECTION_ERROR"


def call_claude(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    return call_groq(prompt, system)


def route(intent: str, prompt: str) -> str:
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    system = DONNA_SYSTEM_PROMPT + extra
    return call_groq(prompt, system)


def route_streaming(intent: str, prompt: str):
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    system = DONNA_SYSTEM_PROMPT + extra
    for chunk in call_groq_streaming(prompt, system):
        yield chunk