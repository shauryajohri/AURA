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
    
def clean_response(text: str) -> str:
    # remove meta text
    import re
    text = re.sub(r'\*\*.*?\*\*', '', text, flags=re.DOTALL)
    text = re.sub(r'Note:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Instructions:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\[.*?\]', '', text, flags=re.DOTALL)
    
    # keep only first 2 sentences
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    result = '. '.join(sentences[:2])
    if result and not result.endswith('.'):
        result += '.'
    return result.strip()

def call_ollama(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    try:
        strict_system = system + """
        CRITICAL: Reply in maximum 2 short sentences. 
        No bullet points. No explanations. No meta text.
        Talk like a friend texting — casual and direct.
        """
        response = ollama.chat(
            model="phi3",
            messages=[
                {"role": "system", "content": strict_system},
                {"role": "user", "content": prompt}
            ]
        )
        raw = response['message']['content']
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA DEBUG] Ollama error: {str(e)}")
        return f"ERROR: {str(e)}"