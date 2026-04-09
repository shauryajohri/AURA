import ollama
from core.personality import DONNA_SYSTEM_PROMPT

def call_ollama(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    try:
        response = ollama.chat(
            model="phi3",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        )
        return response['message']['content']
    except Exception as e:
        print(f"[AURA DEBUG] Ollama error: {str(e)}")
        return f"ERROR: {str(e)}"

# keep this name so brain.py doesn't break
def call_claude(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    return call_ollama(prompt, system)

def route(intent: str, prompt: str) -> str:
    if intent == "SEARCH":
        return call_ollama(prompt)
    elif intent == "CODING":
        return call_ollama(prompt)
    elif intent in ["CASUAL", "REMINDER", "SAVE", "RECALL", "COMMAND"]:
        return call_ollama(prompt)
    else:
        return call_ollama(prompt)