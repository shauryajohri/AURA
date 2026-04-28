import pyperclip
from memory import store
from core.ai_router import call_ollama
import json

def auto_tag_and_save(content: str, source: str = "user") -> str:
    if not content or len(content.strip()) < 5:
        return "Nothing to save — try copying something first."

    # ask Ollama to generate title + tags + summary
    meta_prompt = f"""
Given this content, return ONLY a JSON object with these fields:
- title (max 5 words, descriptive)
- tags (comma separated, max 3 tags)
- summary (max 15 words)

Content: {content[:500]}

Return ONLY the JSON, no extra text.
Example: {{"title": "Binary search notes", "tags": "coding,algorithms,DSA", "summary": "Notes about binary search implementation and complexity"}}
"""
    try:
        raw = call_ollama(meta_prompt)
        # extract JSON from response
        import re
        json_match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            title = parsed.get("title", "Saved note")
            tags = parsed.get("tags", "general")
            summary = parsed.get("summary", "")
        else:
            title = content[:30] + "..."
            tags = "general"
            summary = ""
    except:
        title = content[:30] + "..."
        tags = "general"
        summary = ""

    store.save_entry(title, content, summary, tags, source)
    return f"Saved as '{title}' under {tags}."

def save_from_clipboard() -> str:
    content = pyperclip.paste()
    if not content:
        return "Clipboard is empty. Copy something first."
    return auto_tag_and_save(content, source="clipboard")

def save_from_text(text: str) -> str:
    return auto_tag_and_save(text, source="voice")

def recall(query: str) -> str:
    results = store.search_entries(query)
    if not results:
        return f"I couldn't find anything saved about {query}."

    top = results[0]
    title = top[0]
    summary = top[1]
    tags = top[2]
    date = top[3][:10]  # just the date part
    content = top[4]

    response = f"Found '{title}' saved on {date}. "
    if summary:
        response += summary
    else:
        response += content[:150]

    return response

def list_saved() -> str:
    results = store.get_recent(5)
    if not results:
        return "Nothing saved yet."

    response = "Here's what I have saved recently: "
    for item in results:
        response += f"{item[0]}, "
    return response.rstrip(", ") + "."