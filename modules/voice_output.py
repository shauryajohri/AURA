import pyttsx3
import re

def clean_text(text: str) -> str:
    text = re.sub(r'\*\*|__|\*|_|~~|`', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[#\[\]{}|<>]', '', text)
    text = re.sub(r'\[You might also.*?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'Anticipated Follow-up Question:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\[You might.*', '', text, flags=re.DOTALL)
    text = re.sub(r'aura:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'User asks:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Screen content:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Recent conversation:.*', '', text, flags=re.DOTALL)
    if len(text) > 300:
        sentences = text.split('.')
        text = '. '.join(sentences[:2]) + '.'
    return text.strip()

def speak(text: str):
    clean = clean_text(text)
    print(f"[AURA] {clean}")
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 175)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'zira' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        engine.say(clean)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print(f"[AURA TTS Error] {e}")