# core/quest_presets.py
"""
Keyword packs for quest matching.

The whole point of a quest is that AURA verifies it rather than taking your
word for it — so the matcher has to recognise a subject from whatever is on
screen. That means covering BOTH modes of study, because they look completely
different to a screen watcher:

    learning  — a YouTube/Udemy video, a textbook PDF, a blog post
    doing     — LeetCode, Anki, a compiler, a notebook

A DSA quest has to count "watching a recursion lecture" as well as "solving a
problem", which is exactly what shaurya asked for. So each pack carries both.

Keywords are matched against app name + window title + visible screen text.
Window titles are the workhorse here: a YouTube video's title lands in the
browser's title bar, which is how a lecture gets recognised at all.

Every entry is lowercase and matched on word boundaries, so short tokens can't
fire on fragments ("go" inside "google"). Anything under 3 characters is
dropped by the matcher for the same reason.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "japanese": {
        "label": "Japanese",
        "icon": "あ",
        "color": "#ff6b8a",
        "keywords": [
            # tools
            "anki", "wanikani", "bunpro", "jisho", "genki", "tae kim",
            "duolingo", "renshuu", "kanji study", "migaku", "yomichan",
            "satori reader", "japanesepod", "tofugu", "imabi", "marumori",
            # concepts
            "japanese", "kanji", "hiragana", "katakana", "furigana",
            "jlpt", "n5", "n4", "n3", "n2", "n1", "grammar point",
            "particle wa", "keigo", "godan", "ichidan", "counters",
            # native text on screen
            "日本語", "漢字", "ひらがな", "カタカナ", "文法",
        ],
    },
    "dsa": {
        "label": "DSA",
        "icon": "◈",
        "color": "#38e1ff",
        "keywords": [
            # doing
            "leetcode", "hackerrank", "codeforces", "codechef", "atcoder",
            "geeksforgeeks", "interviewbit", "neetcode", "striver",
            "algoexpert", "codingninjas", "hackerearth", "spoj", "usaco",
            # learning
            "data structure", "algorithm", "big o", "time complexity",
            "space complexity", "recursion", "dynamic programming",
            "backtracking", "binary search", "linked list", "binary tree",
            "graph traversal", "dijkstra", "bfs", "dfs", "sliding window",
            "two pointer", "heap", "trie", "segment tree", "union find",
            "memoization", "greedy algorithm", "sorting algorithm",
        ],
    },
    "coding": {
        "label": "Coding",
        "icon": "⌘",
        "color": "#8b5cff",
        "keywords": [
            "visual studio code", "vscode", "pycharm", "intellij", "webstorm",
            "sublime text", "neovim", "android studio", "xcode",
            "github", "gitlab", "stack overflow", "localhost", "terminal",
            "npm run", "pytest", "docker", "compiler", "debugger",
            "pull request", "merge conflict", "refactor",
        ],
    },
    "reading": {
        "label": "Reading",
        "icon": "❋",
        "color": "#f5a623",
        "keywords": [
            "kindle", "epub", "goodreads", "libby", "pocket", "instapaper",
            "chapter", "paperback", "audiobook", "blinkist", "readwise",
        ],
    },
    "math": {
        "label": "Math",
        "icon": "∑",
        "color": "#4ade80",
        "keywords": [
            "khan academy", "wolfram", "desmos", "geogebra", "3blue1brown",
            "calculus", "linear algebra", "probability", "statistics",
            "differential equation", "matrix", "eigenvalue", "integral",
            "derivative", "theorem", "proof",
        ],
    },
    "fitness": {
        "label": "Fitness",
        "icon": "⚡",
        "color": "#ff9f45",
        "keywords": [
            "strava", "myfitnesspal", "hevy", "strong app", "workout",
            "gym", "running", "yoga", "stretching", "cardio", "reps",
        ],
    },
    "design": {
        "label": "Design",
        "icon": "◐",
        "color": "#b18bff",
        "keywords": [
            "figma", "sketch app", "adobe xd", "photoshop", "illustrator",
            "blender", "canva", "dribbble", "behance", "wireframe",
            "prototype", "typography", "color palette",
        ],
    },
    "writing": {
        "label": "Writing",
        "icon": "✎",
        "color": "#7dd3fc",
        "keywords": [
            "notion", "obsidian", "google docs", "scrivener", "ulysses",
            "substack", "medium", "draft", "outline", "manuscript",
            "word count", "blog post",
        ],
    },
    "custom": {
        "label": "Custom",
        "icon": "◆",
        "color": "#8b5cff",
        "keywords": [],
    },
}


def preset_keywords(preset: str) -> list[str]:
    return list(PRESETS.get(preset or "custom", PRESETS["custom"])["keywords"])


def preset_list() -> list[dict]:
    """For the 'new quest' picker in the UI."""
    return [
        {"id": pid, "label": p["label"], "icon": p["icon"],
         "color": p["color"], "keyword_count": len(p["keywords"])}
        for pid, p in PRESETS.items()
    ]


# ── Container apps ──────────────────────────────────────────────────────────
# Apps whose NAME proves nothing about what you're doing. A browser, an LLM
# chat, a general editor or a terminal can hold literally any subject, so for
# these the app name is discarded as evidence and only the window title and
# the on-screen content decide.
#
# This is what makes "I'm in Claude, but the conversation is about AURA" count
# toward an AURA quest while "I'm in Claude asking about pasta" does not.
CONTAINER_APPS = {
    # browsers
    "chrome", "google chrome", "firefox", "edge", "msedge", "brave", "arc",
    "safari", "opera", "vivaldi", "chromium", "zen browser",
    # LLM chats — the subject lives entirely in the content
    "claude", "chatgpt", "openai", "gemini", "perplexity", "copilot",
    "poe", "mistral", "deepseek", "grok", "claude.ai", "t3.chat",
    # general-purpose editors / IDEs (could be ANY project)
    "visual studio code", "vscode", "code", "cursor", "windsurf", "zed",
    "sublime text", "neovim", "vim", "emacs", "notepad++", "intellij idea",
    "pycharm", "webstorm", "android studio", "visual studio",
    # note / doc surfaces
    "notion", "obsidian", "logseq", "onenote", "google docs", "word",
    "notepad", "typora",
    # shells
    "terminal", "windows terminal", "powershell", "cmd", "wsl", "iterm",
    "iterm2", "alacritty", "kitty", "hyper", "warp",
}


def is_container_app(app: str) -> bool:
    """True when the app name shouldn't count as evidence on its own."""
    a = (app or "").strip().lower()
    if not a:
        return True
    return any(c == a or c in a for c in CONTAINER_APPS)


# Words too generic to identify a subject, even inside a quest title.
# "Aura Code Base" must key on "aura" — "code" and "base" describe half the
# windows on a developer's machine and would make the quest match everything.
GENERIC_TERMS = {
    "code", "codebase", "base", "project", "projects", "work", "working",
    "app", "application", "dev", "development", "stuff", "thing", "things",
    "main", "file", "files", "folder", "repo", "repository", "src", "source",
    "test", "tests", "build", "run", "task", "tasks", "todo", "notes", "note",
    "session", "time", "daily", "quest", "quests", "my", "the", "and", "for",
    "data", "system", "tool", "tools", "update", "updates", "fix", "fixes",
    "setup", "config", "doc", "docs", "chat", "ai", "llm",
}


# Directory and module names shared by basically every codebase. Harvested
# from a project folder they're real terms, but they identify NOTHING — a
# conversation mentioning "core" and "api" isn't necessarily about your
# project. They stay as supporting evidence but never count as anchors.
COMMON_CODE_TERMS = {
    "core", "logs", "public", "static", "assets", "frontend", "backend",
    "memory", "modules", "module", "components", "component", "utils", "util",
    "lib", "libs", "api", "apis", "server", "client", "styles", "style",
    "views", "view", "hooks", "stores", "store", "scripts", "script",
    "templates", "template", "helpers", "common", "shared", "types", "model",
    "models", "routes", "router", "controller", "controllers", "services",
    "service", "database", "schema", "migrations", "electron", "dist",
    "index", "readme", "license", "package", "requirements", "settings",
    "main", "app", "apps", "pages", "layout", "layouts", "images", "fonts",
}


def is_identifying(term: str) -> bool:
    """Is this term specific enough to prove which project you're in?"""
    t = (term or "").lower()
    return bool(t) and t not in COMMON_CODE_TERMS and t not in GENERIC_TERMS


def is_specific(term: str) -> bool:
    """Near-unique identifiers — long names and snake_case code symbols.

    "response_composer" or "error_intelligence" appearing even once is decisive:
    nobody says those words by accident.
    """
    t = (term or "").lower()
    return len(t) >= 10 or "_" in t


# Words that appear in almost any window title and would match everything.
STOPWORDS = {
    "the", "and", "for", "you", "your", "with", "from", "how", "what", "why",
    "app", "web", "new", "tab", "google", "chrome", "firefox", "edge", "search",
    "home", "page", "video", "watch", "youtube", "part", "full", "free", "best",
    "top", "day", "days", "hour", "hours", "min", "mins", "guide", "tutorial",
    "learn", "learning", "study", "course", "lesson", "practice", "beginner",
}


def guess_preset(title: str) -> str:
    """Best-guess preset for a quest named in plain language ('2h japanese')."""
    low = (title or "").lower()
    for pid, p in PRESETS.items():
        if pid == "custom":
            continue
        if pid in low or p["label"].lower() in low:
            return pid
    for pid, p in PRESETS.items():
        if pid == "custom":
            continue
        for kw in p["keywords"][:12]:
            if kw in low:
                return pid
    return "custom"
