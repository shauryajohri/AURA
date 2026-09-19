"""
Integrations — paste an API key or a link in chat, and AURA installs it.

    you:   install this gsk_…                      (or a GitHub / docs / model link)
    AURA:  works out which service it is, checks the key live, lists what it
           offers and what each model is best at, and asks — as checkboxes —
           which ones should become planets and for which jobs.
    you:   tick, Install.
    AURA:  test-calls every ticked model, and each one that answers becomes a
           planet orbiting the core. The router uses it for the jobs it was
           ticked for (Coding, Research, Chat, Vision, Background), in front of
           or behind the built-in models.

Why this is data, not generated code
------------------------------------
Almost every LLM API today speaks the OpenAI chat-completions dialect, and the
few search APIs worth having are three small request shapes. So "coding
itself in" means recording {base URL, key, model, jobs} and teaching
ai_router to read it — not writing Python at runtime, which would turn a
pasted link into arbitrary code running on this machine.

Keys never reach a model or the chat log: the server intercepts any message
with a key in it before the Director sees it, the stored conversation gets a
masked copy, and the API only ever returns masked keys. They live in the local
SQLite database, like the connector credentials do.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from memory import store

load_dotenv()   # keys already in .env (OPENROUTER_API_KEY, GROQ_API_KEY…) are reused

JOBS = ["Coding", "Research", "Chat", "Vision", "Background"]
FREEISH = {"free", "free tier", "free credits", "local"}

# ── the services AURA knows how to talk to ─────────────────────────────────
# style: how requests are shaped — "openrouter" and "groq" reuse ai_router's
# provider-specific reasoning flags, "compat" is plain OpenAI chat-completions.
PROVIDERS: dict[str, dict] = {
    "openrouter": {"label": "OpenRouter", "kind": "llm", "style": "openrouter",
                   "base": "https://openrouter.ai/api/v1", "prefixes": ("sk-or-",),
                   "hosts": ("openrouter.ai",), "env": ("OPENROUTER_API_KEY",),
                   "cost": "per model", "about": "one key for hundreds of models, many of them free"},
    "groq": {"label": "Groq", "kind": "llm", "style": "groq",
             "base": "https://api.groq.com/openai/v1", "prefixes": ("gsk_",),
             "hosts": ("groq.com", "console.groq.com"), "env": ("GROQ_API_KEY",),
             "cost": "free tier", "about": "very fast open models, free tier"},
    "gemini": {"label": "Google Gemini", "kind": "llm", "style": "compat",
               "base": "https://generativelanguage.googleapis.com/v1beta/openai", "prefixes": ("AIza",),
               "hosts": ("aistudio.google.com", "ai.google.dev", "generativelanguage.googleapis.com",
                         "makersuite.google.com"), "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
               "cost": "free tier", "about": "Gemini models, free tier with daily limits"},
    "mistral": {"label": "Mistral", "kind": "llm", "style": "compat",
                "base": "https://api.mistral.ai/v1", "hosts": ("mistral.ai", "console.mistral.ai",
                                                              "docs.mistral.ai"),
                "env": ("MISTRAL_API_KEY",), "cost": "free tier", "about": "Mistral and Codestral models"},
    "cerebras": {"label": "Cerebras", "kind": "llm", "style": "compat",
                 "base": "https://api.cerebras.ai/v1", "prefixes": ("csk-",),
                 "hosts": ("cerebras.ai", "cloud.cerebras.ai", "inference-docs.cerebras.ai"),
                 "env": ("CEREBRAS_API_KEY",), "cost": "free tier", "about": "extremely fast inference, free tier"},
    "github": {"label": "GitHub Models", "kind": "llm", "style": "compat",
               "base": "https://models.github.ai/inference",
               "prefixes": ("github_pat_", "ghp_", "gho_", "ghu_", "ghs_"),
               "hosts": ("models.github.ai", "github.com/marketplace/models"),
               "env": ("GITHUB_TOKEN",), "cost": "free tier",
               "about": "GPT, Llama, Phi and more through a GitHub token, rate-limited free tier"},
    "huggingface": {"label": "Hugging Face", "kind": "llm", "style": "compat",
                    "base": "https://router.huggingface.co/v1", "prefixes": ("hf_",),
                    "hosts": ("huggingface.co", "hf.co"), "env": ("HF_TOKEN",),
                    "cost": "free credits", "about": "open models via the HF router, small free monthly credit"},
    "nvidia": {"label": "NVIDIA NIM", "kind": "llm", "style": "compat",
               "base": "https://integrate.api.nvidia.com/v1", "prefixes": ("nvapi-",),
               "hosts": ("build.nvidia.com",), "env": ("NVIDIA_API_KEY",),
               "cost": "free credits", "about": "NVIDIA-hosted open models"},
    "sambanova": {"label": "SambaNova", "kind": "llm", "style": "compat",
                  "base": "https://api.sambanova.ai/v1", "hosts": ("sambanova.ai", "cloud.sambanova.ai"),
                  "env": ("SAMBANOVA_API_KEY",), "cost": "free tier", "about": "fast Llama/DeepSeek hosting"},
    "together": {"label": "Together AI", "kind": "llm", "style": "compat",
                 "base": "https://api.together.xyz/v1", "prefixes": ("tgp_",),
                 "hosts": ("together.ai", "together.xyz", "api.together.xyz"),
                 "env": ("TOGETHER_API_KEY",), "cost": "paid", "about": "open models, mostly paid"},
    "deepseek": {"label": "DeepSeek", "kind": "llm", "style": "compat",
                 "base": "https://api.deepseek.com/v1",
                 "hosts": ("deepseek.com", "platform.deepseek.com", "api-docs.deepseek.com"),
                 "env": ("DEEPSEEK_API_KEY",), "cost": "paid", "about": "DeepSeek chat and reasoner"},
    "openai": {"label": "OpenAI", "kind": "llm", "style": "compat",
               "base": "https://api.openai.com/v1", "prefixes": ("sk-proj-", "sk-svcacct-"),
               "hosts": ("openai.com", "platform.openai.com"), "env": ("OPENAI_API_KEY",),
               "cost": "paid", "about": "GPT models (paid)"},
    "anthropic": {"label": "Anthropic", "kind": "llm", "style": "anthropic",
                  "base": "https://api.anthropic.com/v1", "prefixes": ("sk-ant-",),
                  "hosts": ("anthropic.com", "console.anthropic.com", "docs.anthropic.com",
                            "platform.claude.com"),
                  "env": ("ANTHROPIC_API_KEY",), "cost": "paid", "about": "Claude models (paid)"},
    "xai": {"label": "xAI", "kind": "llm", "style": "compat", "base": "https://api.x.ai/v1",
            "prefixes": ("xai-",), "hosts": ("x.ai", "console.x.ai", "docs.x.ai"),
            "env": ("XAI_API_KEY",), "cost": "paid", "about": "Grok models (paid)"},
    "fireworks": {"label": "Fireworks", "kind": "llm", "style": "compat",
                  "base": "https://api.fireworks.ai/inference/v1", "prefixes": ("fw_",),
                  "hosts": ("fireworks.ai",), "env": ("FIREWORKS_API_KEY",), "cost": "paid",
                  "about": "fast open-model hosting (paid)"},
    "perplexity": {"label": "Perplexity", "kind": "llm", "style": "compat",
                   "base": "https://api.perplexity.ai", "prefixes": ("pplx-",),
                   "hosts": ("perplexity.ai", "docs.perplexity.ai"), "env": ("PERPLEXITY_API_KEY",),
                   "cost": "paid", "about": "Sonar models that search the web (paid)",
                   "static_models": ["sonar", "sonar-pro", "sonar-reasoning-pro"]},
    "ollama": {"label": "Ollama (this PC)", "kind": "llm", "style": "compat",
               "base": "http://localhost:11434/v1", "needs_key": False,
               "hosts": ("ollama.com", "ollama.ai", "github.com/ollama/ollama"),
               "cost": "local", "about": "models running on your own machine"},
    "lmstudio": {"label": "LM Studio (this PC)", "kind": "llm", "style": "compat",
                 "base": "http://localhost:1234/v1", "needs_key": False,
                 "hosts": ("lmstudio.ai", "github.com/lmstudio-ai"),
                 "cost": "local", "about": "models running in LM Studio on your machine"},
    "custom": {"label": "Other (OpenAI-compatible)", "kind": "llm", "style": "compat",
               "base": "", "cost": "unknown", "about": "any server that speaks the OpenAI API"},
    # ── web search: a tool planet, not a model ─────────────────────────────
    "tavily": {"label": "Tavily", "kind": "search", "prefixes": ("tvly-",),
               "hosts": ("tavily.com", "app.tavily.com", "docs.tavily.com"),
               "env": ("TAVILY_API_KEY",), "cost": "free tier",
               "about": "web search built for AI, 1,000 free searches a month"},
    "brave": {"label": "Brave Search", "kind": "search", "prefixes": ("BSA",),
              "hosts": ("brave.com/search/api", "api-dashboard.search.brave.com", "api.search.brave.com"),
              "env": ("BRAVE_API_KEY",), "cost": "free tier", "about": "independent web search index"},
    "serper": {"label": "Serper", "kind": "search", "hosts": ("serper.dev",),
               "env": ("SERPER_API_KEY",), "cost": "free tier", "about": "Google results as JSON"},
}
# Provider names people type ("install ollama", "add my mistral key").
_NAMES = {
    "openrouter": "openrouter", "groq": "groq", "gemini": "gemini", "google ai studio": "gemini",
    "mistral": "mistral", "codestral": "mistral", "cerebras": "cerebras", "github models": "github",
    "hugging face": "huggingface", "huggingface": "huggingface", "nvidia": "nvidia", "nim": "nvidia",
    "sambanova": "sambanova", "together": "together", "deepseek": "deepseek", "openai": "openai",
    "anthropic": "anthropic", "claude api": "anthropic", "xai": "xai", "grok": "xai",
    "fireworks": "fireworks", "perplexity": "perplexity", "ollama": "ollama",
    "lm studio": "lmstudio", "lmstudio": "lmstudio", "tavily": "tavily", "brave search": "brave",
    "serper": "serper",
}

# ── spotting keys ───────────────────────────────────────────────────────────
_KEY_PATTERNS: list[tuple[str, re.Pattern]] = [(p, re.compile(rx)) for p, rx in [
    ("openrouter", r"sk-or-(?:v1-)?[A-Za-z0-9]{20,}"),
    ("anthropic", r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("openai", r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}"),
    ("deepseek", r"(?<![A-Za-z0-9])sk-[a-f0-9]{32}(?![A-Za-z0-9])"),
    ("openai", r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{32,}"),
    ("groq", r"gsk_[A-Za-z0-9]{20,}"),
    ("gemini", r"AIza[0-9A-Za-z_\-]{30,}"),
    ("huggingface", r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{20,}"),
    ("cerebras", r"csk-[A-Za-z0-9]{20,}"),
    ("xai", r"xai-[A-Za-z0-9]{20,}"),
    ("fireworks", r"(?<![A-Za-z0-9])fw_[A-Za-z0-9]{16,}"),
    ("nvidia", r"nvapi-[A-Za-z0-9_\-]{20,}"),
    ("github", r"github_pat_[A-Za-z0-9_]{30,}|(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    ("tavily", r"tvly-[A-Za-z0-9_\-]{16,}"),
    ("together", r"tgp_v1_[A-Za-z0-9_\-]{20,}"),
    ("perplexity", r"pplx-[A-Za-z0-9]{20,}"),
    ("brave", r"(?<![A-Za-z0-9])BSA[A-Za-z0-9_\-]{20,}"),
]]
_GENERIC_KEY = re.compile(r"(?<![A-Za-z0-9/._\-])[A-Za-z0-9][A-Za-z0-9_\-]{27,119}(?![A-Za-z0-9/._\-])")
_KEY_WORDS = re.compile(r"(?i)\b(api[\s_-]?key|key|token|secret|install|integrate|credential)\b")
_INSTALL_RE = re.compile(
    r"(?i)\b(install|integrate|hook (?:it|this|that) up|plug (?:it|this|that) in|"
    r"add (?:this|it|that|my|the|a new|new)?\s*(?:api|key|model|provider|service|planet|integration)s?|"
    r"set (?:it|this|that) up|connect (?:this|it|that)|use this (?:api|key|model|provider)|"
    r"make (?:it|this|that) a planet|new planet|register (?:this|it))\b")
_QUESTION_RE = re.compile(r"(?i)^\s*(how|what|why|where|when|which|should|can i|do i|is it|does)\b")
# With only a service name to go on ("install ollama"), it has to be an order,
# not narration ("i need to install ollama later" is a task, not a request).
_COMMAND_RE = re.compile(
    r"(?i)^\W*(?:(?:hey|ok|okay|yo)\W+)?(?:aura\W+)?(?:(?:please|pls|can you|could you|go|just|now)\W+)*"
    r"(install|integrate|add|connect|set up|setup|hook up|plug in|use)\b")


def find_keys(text: str) -> list[tuple[Optional[str], str]]:
    """[(provider or None, key)] in the order they appear. URLs are stripped
    first so a long path segment is never mistaken for a key."""
    from core.saved_info import _URL_RE
    body = _URL_RE.sub(" ", text or "")
    found: list[tuple[int, Optional[str], str]] = []
    taken: list[tuple[int, int]] = []
    for prov, rx in _KEY_PATTERNS:
        for m in rx.finditer(body):
            if any(s <= m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), prov, m.group(0)))
    if _KEY_WORDS.search(body):
        for m in _GENERIC_KEY.finditer(body):
            tok = m.group(0)
            if any(s <= m.start() < e for s, e in taken):
                continue
            if not (re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok)):
                continue
            if re.fullmatch(r"[a-z_\-]+\d?", tok):   # snake_case words, not keys
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), None, tok))
    found.sort()
    return [(p, k) for _, p, k in found]


def mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "…"
    return f"{key[:4]}…{key[-4:]}"


def mask_text(text: str) -> str:
    out = text or ""
    for _, key in find_keys(out):
        out = out.replace(key, mask(key))
    return out


def detect_request(text: str) -> dict | None:
    """Is this message an install request (or does it carry a key)? Returns
    {keys, urls, provider_hint, masked_text} or None for ordinary chat."""
    from core.saved_info import extract_urls
    keys = find_keys(text)
    urls = extract_urls(text)
    named = _named_provider(text)
    cmd = _COMMAND_RE.search(text or "")
    if cmd and cmd.group(1).lower() in ("add", "use") and not re.search(
            r"(?i)\b(api|key|model|models|planet|provider|integration)\b", text or ""):
        cmd = None      # "add groq to my notes" is a to-do, not an install
    wants = bool(_INSTALL_RE.search(text or "")) or bool(named and cmd)
    if not keys:
        if not wants:
            return None
        if not urls and not named:
            return None
        if not urls and (_QUESTION_RE.search(text or "") or not _COMMAND_RE.search(text or "")):
            return None     # "how do I install ollama?" is a question, not an order
    return {"keys": keys, "urls": urls, "named": named, "masked_text": mask_text(text)}


def _named_provider(text: str) -> str | None:
    low = (text or "").lower()
    for name in sorted(_NAMES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            return _NAMES[name]
    return None


def _provider_for_url(url: str) -> tuple[str | None, str | None]:
    """(provider, model hint) for a link to a service, console or model page."""
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.")
    path = u.path.rstrip("/")
    full = host + path
    for pid, p in PROVIDERS.items():
        for h in p.get("hosts", ()):
            if "/" in h:
                if full.startswith(h):
                    return pid, None
            elif host == h or host.endswith("." + h):
                model = None
                parts = [x for x in path.split("/") if x]
                if pid == "openrouter" and len(parts) >= 2 and parts[0] not in (
                        "docs", "keys", "settings", "models", "api", "chat", "rankings", "apps", "provider"):
                    model = "/".join(parts[:2])
                if pid == "huggingface" and len(parts) >= 2 and parts[0] not in (
                        "docs", "settings", "spaces", "datasets", "models", "blog", "papers", "learn", "join", "login"):
                    model = "/".join(parts[:2])
                return pid, model
    return None, None


# ── storage ─────────────────────────────────────────────────────────────────
_DDL = [
    """CREATE TABLE IF NOT EXISTS integrations (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        uid          TEXT UNIQUE,
        provider     TEXT NOT NULL,
        label        TEXT NOT NULL,
        kind         TEXT NOT NULL DEFAULT 'llm',
        base_url     TEXT DEFAULT '',
        secret       TEXT DEFAULT '',
        key_source   TEXT DEFAULT '',
        status       TEXT DEFAULT 'pending',
        position     TEXT DEFAULT 'backup',
        proposal     TEXT DEFAULT '{}',
        source_url   TEXT DEFAULT '',
        created_at   TEXT,
        installed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS integration_models (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        integration_id INTEGER NOT NULL,
        model_id       TEXT NOT NULL,
        name           TEXT NOT NULL,
        jobs           TEXT DEFAULT '',
        position       TEXT DEFAULT 'backup',
        vision         INTEGER DEFAULT 0,
        cost           TEXT DEFAULT '',
        context        TEXT DEFAULT '',
        color          TEXT DEFAULT '#00E5C7',
        role           TEXT DEFAULT '',
        nature         TEXT DEFAULT '',
        best_for       TEXT DEFAULT '',
        status         TEXT DEFAULT 'ok',
        error          TEXT DEFAULT '',
        latency_ms     INTEGER DEFAULT 0,
        style          TEXT DEFAULT '',
        created_at     TEXT
    )""",
]
_ready = False
_lock = threading.RLock()
_sink: Optional[Callable[[dict], None]] = None


def set_sink(fn: Callable[[dict], None]) -> None:
    global _sink
    _sink = fn


def _publish(payload: dict) -> None:
    if _sink:
        try:
            _sink(payload)
        except Exception:  # noqa: BLE001
            pass


def _activity(text: str, kind: str = "info") -> None:
    try:
        from core import activity
        activity.emit(text, kind)
    except Exception:  # noqa: BLE001
        pass


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _conn():
    global _ready
    conn = store._connect()
    if not _ready:
        for ddl in _DDL:
            conn.execute(ddl)
        conn.commit()
        _ready = True
    return conn


# ── the routing cache ai_router reads on every call ─────────────────────────
_cache: dict = {"at": 0.0, "models": []}
_CACHE_TTL = 15.0


def invalidate() -> None:
    with _lock:
        _cache["at"] = 0.0


def _models_cached() -> list[dict]:
    with _lock:
        if time.time() - _cache["at"] < _CACHE_TTL:
            return _cache["models"]
        try:
            conn = _conn()
            try:
                rows = conn.execute(
                    "SELECT m.id, m.model_id, m.name, m.jobs, m.position, m.vision, m.cost, m.context, "
                    "m.color, m.role, m.nature, m.best_for, m.status, m.error, m.latency_ms, m.created_at, "
                    "i.id, i.provider, i.label, i.base_url, i.secret, i.key_source, m.style "
                    "FROM integration_models m JOIN integrations i ON i.id = m.integration_id "
                    "WHERE i.status = 'installed' ORDER BY m.id").fetchall()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 — routing must survive a broken table
            print(f"[AURA integrations] cache load failed: {e}")
            rows = []
        out = []
        for r in rows:
            prov = PROVIDERS.get(r[17], PROVIDERS["custom"])
            out.append({
                "row_id": r[0], "wire": r[1], "name": r[2],
                "jobs": [j for j in (r[3] or "").split(",") if j],
                "position": r[4] or "backup", "vision": bool(r[5]), "cost": r[6] or "",
                "context": r[7] or "", "color": r[8] or "#00E5C7", "role": r[9] or "",
                "nature": r[10] or "", "best_for": [j for j in (r[11] or "").split(",") if j],
                "status": r[12] or "ok", "error": r[13] or "", "latency_ms": r[14] or 0,
                "created_at": r[15], "integration_id": r[16], "provider": r[17],
                "label": r[18], "base": (r[19] or prov.get("base") or "").rstrip("/"),
                "key": _resolve_key(r[20], r[21], prov),
                # the style its live test passed with beats the provider default
                "style": r[22] or prov.get("style", "compat"),
                "id": f"ext:{r[0]}", "planet_id": f"x{r[0]}",
            })
        _cache["models"], _cache["at"] = out, time.time()
        return out


def _resolve_key(secret: str, key_source: str, prov: dict) -> str:
    if prov.get("needs_key") is False:
        return "no-key"   # local servers ignore auth, but the header must be non-empty
    if secret:
        return secret
    if key_source and key_source.startswith("env:"):
        return os.getenv(key_source[4:], "") or ""
    return ""


def is_ext(model_id: str) -> bool:
    return bool(model_id) and model_id.startswith("ext:")


def _by_id(model_id: str) -> dict | None:
    for m in _models_cached():
        if m["id"] == model_id:
            return m
    return None


def endpoint(model_id: str) -> tuple[str, str, str] | None:
    """(style, chat-completions url, key) for an installed model."""
    m = _by_id(model_id)
    if not m or not m["base"]:
        return None
    return m["style"], m["base"] + "/chat/completions", m["key"]


def wire_id(model_id: str) -> str:
    m = _by_id(model_id)
    return m["wire"] if m else model_id


def name_for(model_id: str) -> str | None:
    m = _by_id(model_id)
    return m["name"] if m else None


def routed(job: str) -> list[tuple[str, str, str]]:
    """[(name, ext id, position)] installed models ticked for `job`."""
    return [(m["name"], m["id"], m["position"]) for m in _models_cached()
            if job in m["jobs"] and m["status"] != "failed"]


def installed_models() -> list[dict]:
    return list(_models_cached())


# ── search tool (installed search integrations) ─────────────────────────────

def search_provider() -> dict | None:
    conn = _conn()
    try:
        r = conn.execute("SELECT provider, secret, key_source FROM integrations "
                         "WHERE kind='search' AND status='installed' ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    if not r:
        return None
    key = _resolve_key(r[1], r[2], PROVIDERS.get(r[0], {}))
    return {"provider": r[0], "key": key} if key else None


def web_search(query: str, n: int = 5, provider: str | None = None, key: str | None = None) -> list[dict]:
    """[{title, url, snippet}] from the installed search API. Raises on failure."""
    if provider is None:
        sp = search_provider()
        if not sp:
            raise RuntimeError("no web search installed")
        provider, key = sp["provider"], sp["key"]
    q = (query or "").strip()[:300]
    if provider == "tavily":
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": key, "query": q, "max_results": n}, timeout=20)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")}
                for x in r.json().get("results", [])][:n]
    if provider == "brave":
        r = requests.get("https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": n},
                         headers={"X-Subscription-Token": key, "Accept": "application/json"}, timeout=20)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("description", "")}
                for x in (r.json().get("web") or {}).get("results", [])][:n]
    if provider == "serper":
        r = requests.post("https://google.serper.dev/search", json={"q": q, "num": n},
                          headers={"X-API-KEY": key}, timeout=20)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("link", ""), "snippet": x.get("snippet", "")}
                for x in r.json().get("organic", [])][:n]
    raise RuntimeError(f"unknown search provider {provider}")


# ── model catalogue + "what is it best for" ─────────────────────────────────
_SKIP_MODEL = re.compile(
    r"(?i)(whisper|tts|speech|audio|transcri|embed|rerank|moderation|guard|dall-e|gpt-image|"
    r"imagen|image-gen|stable-diffusion|sdxl|flux|playai|orpheus|realtime|davinci|babbage|"
    r"text-similarity|search-preview|computer-use|veo|lyria|aqa)")


def _params_b(s: str) -> float:
    """Largest '<n>b' parameter count in a model id — 0 if none."""
    best = 0.0
    for m in re.finditer(r"(?<![a-z])(\d+(?:\.\d+)?)\s*b\b", s.lower()):
        try:
            best = max(best, float(m.group(1)))
        except ValueError:
            pass
    return best


def classify(model_id: str, name: str = "", desc: str = "", vision: bool = False) -> list[str]:
    """Jobs a model is best at, strongest first — the pre-ticked boxes."""
    s = f"{model_id} {name} {desc}".lower()
    size = _params_b(model_id + " " + name)
    code = bool(re.search(r"cod(e|er|ing|estral)|devstral|starcoder|swe|qwen3?-coder|kimi-k2|gpt-oss|"
                          r"deepseek-v3|glm-4\.\d|agentic", s))
    reason = bool(re.search(r"\br1\b|reason|think|qwq|nemotron|\bo[134]\b|o[134]-|deepseek-r|magistral|"
                            r"opus|\bpro\b|-pro|large|research|gpt-5|gemini-2\.5|sonar", s)) or size >= 60
    vis = vision or bool(re.search(r"\bvl\b|-vl|vision|omni|llava|pixtral|4o|gemini|gemma-3|gemma-4|"
                                   r"llama-4|maverick|scout|multimodal|image input", s))
    small = (0 < size <= 9) or bool(re.search(r"mini|nano|lite|instant|tiny|small|haiku|flash-8b|\b8b\b|\b7b\b|\b3b\b|\b1b\b", s))
    code_only = bool(re.search(r"codestral|starcoder|coder(?!.*instruct)", s)) and not reason
    jobs: list[str] = []
    if code:
        jobs.append("Coding")
    if reason:
        jobs.append("Research")
    if not code_only:
        jobs.append("Chat")
    if vis:
        jobs.append("Vision")
    if small:
        jobs.append("Background")
    return jobs or ["Chat"]


def _pretty(model_id: str, name: str = "") -> str:
    if name:
        n = re.sub(r"^[^:]{1,30}:\s*", "", name)          # "Meta: Llama 3.3" → "Llama 3.3"
        n = re.sub(r"\s*\((free|beta|preview)\)\s*$", "", n, flags=re.I)
        return n.strip()[:40] or model_id
    base = model_id.split("/")[-1].split(":")[0]
    base = re.sub(r"[-_]+", " ", base)
    words = []
    for w in base.split():
        lw = w.lower()
        if re.fullmatch(r"\d+(\.\d+)?[bkm]", w, re.I) or re.fullmatch(r"a\d+b", lw):
            words.append(w.upper())
        elif lw in _ACRONYMS:
            words.append(_ACRONYMS[lw])
        else:
            words.append(w[:1].upper() + w[1:])
    out = " ".join(words).replace("GPT OSS", "GPT-OSS")
    return out[:40] or model_id


_ACRONYMS = {"gpt": "GPT", "oss": "OSS", "vl": "VL", "ai": "AI", "it": "IT", "moe": "MoE",
             "llm": "LLM", "r1": "R1", "v3": "V3", "v2": "V2", "qwq": "QwQ", "glm": "GLM",
             "phi": "Phi", "nim": "NIM", "hd": "HD"}


def _ctx_label(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f"{round(n / 1_000_000, 1):g}M" if n >= 1_000_000 else f"{round(n / 1000):d}K"


class _ProbeError(Exception):
    pass


def _headers(style: str, key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if key and key != "no-key":
        h["Authorization"] = f"Bearer {key}"
    if style == "openrouter":
        h["HTTP-Referer"] = "https://aura.local"
        h["X-Title"] = "AURA"
    if style == "anthropic":
        h["x-api-key"] = key
        h["anthropic-version"] = "2023-06-01"
    return h


def _explain_http(r: requests.Response, label: str) -> str:
    msg = ""
    try:
        j = r.json()
        err = j.get("error") if isinstance(j, dict) else None
        if isinstance(err, dict):
            msg = err.get("message") or ""
        elif isinstance(err, str):
            msg = err
        if not msg and isinstance(j, dict):
            msg = j.get("message") or j.get("detail") or ""
        if isinstance(j, list) and j and isinstance(j[0], dict):
            msg = (j[0].get("error") or {}).get("message", "")
    except Exception:  # noqa: BLE001
        msg = r.text[:160]
    msg = re.sub(r"\s+", " ", str(msg)).strip()[:180]
    if r.status_code in (401, 403):
        return f"{label} rejected the key ({r.status_code}{': ' + msg if msg else ''})"
    return f"{label} answered {r.status_code}{': ' + msg if msg else ''}"


def list_models(provider: str, key: str, base: str) -> list[dict]:
    """Live catalogue: [{id, name, cost, context, vision, desc}]. Raises
    _ProbeError with a sentence a person can act on."""
    p = PROVIDERS.get(provider, PROVIDERS["custom"])
    label = p["label"]
    style = p.get("style", "compat")
    try:
        if provider == "openrouter":
            if key:
                kr = requests.get("https://openrouter.ai/api/v1/key", headers=_headers(style, key), timeout=15)
                if kr.status_code >= 400:
                    raise _ProbeError(_explain_http(kr, label))
            r = requests.get("https://openrouter.ai/api/v1/models", timeout=20)
            r.raise_for_status()
            out = []
            for m in r.json().get("data", []):
                pr = m.get("pricing") or {}
                free = str(m["id"]).endswith(":free") or (
                    str(pr.get("prompt", "1")) in ("0", "0.0") and str(pr.get("completion", "1")) in ("0", "0.0"))
                mods = ((m.get("architecture") or {}).get("input_modalities") or [])
                outs = ((m.get("architecture") or {}).get("output_modalities") or ["text"])
                if "text" not in outs:
                    continue
                out.append({"id": m["id"], "name": m.get("name") or "", "cost": "free" if free else "paid",
                            "context": _ctx_label(m.get("context_length")), "vision": "image" in mods,
                            "desc": (m.get("description") or "")[:300], "created": m.get("created") or 0})
            return out
        if p.get("static_models"):
            return [{"id": mid, "name": "", "cost": p["cost"], "context": "", "vision": False, "desc": ""}
                    for mid in p["static_models"]]
        if provider == "github":
            r = requests.get("https://models.github.ai/catalog/models", headers=_headers(style, key), timeout=20)
            if r.status_code >= 400:
                raise _ProbeError(_explain_http(r, label))
            out = []
            for m in r.json():
                if "chat-completion" not in str(m.get("task", "chat-completion")) and \
                        "text" not in (m.get("supported_output_modalities") or ["text"]):
                    continue
                out.append({"id": m.get("id", ""), "name": m.get("name") or "", "cost": "free tier",
                            "context": _ctx_label((m.get("limits") or {}).get("max_input_tokens")),
                            "vision": "image" in (m.get("supported_input_modalities") or []),
                            "desc": (m.get("summary") or "")[:300], "created": 0})
            return [m for m in out if m["id"]]
        if not base:
            raise _ProbeError("I need the service's base URL to reach it")
        r = requests.get(base.rstrip("/") + "/models", headers=_headers(style, key), timeout=20)
        if r.status_code >= 400:
            raise _ProbeError(_explain_http(r, label))
        j = r.json()
        rows = j if isinstance(j, list) else (j.get("data") or j.get("models") or [])
        out = []
        for m in rows:
            mid = str(m.get("id") or m.get("name") or "")
            if provider == "gemini":
                mid = mid.removeprefix("models/")
            if not mid:
                continue
            mods = m.get("input_modalities") or (m.get("architecture") or {}).get("input_modalities") or []
            cost = p["cost"]
            if provider == "together":
                cost = "free" if mid.lower().endswith("-free") else "paid"
            out.append({"id": mid, "name": str(m.get("display_name") or m.get("displayName") or ""),
                        "cost": cost,
                        "context": _ctx_label(m.get("context_window") or m.get("context_length")
                                              or m.get("max_context_length") or m.get("inputTokenLimit")),
                        "vision": "image" in mods, "desc": str(m.get("description") or "")[:300],
                        "created": m.get("created") or 0})
        return out
    except _ProbeError:
        raise
    except requests.ConnectionError as e:
        if provider in ("ollama", "lmstudio"):
            raise _ProbeError(f"{label} isn't running — start it and ask me again") from e
        raise _ProbeError(f"couldn't reach {label} ({base or 'no address'})") from e
    except requests.Timeout as e:
        raise _ProbeError(f"{label} took too long to answer") from e
    except Exception as e:  # noqa: BLE001
        raise _ProbeError(f"{label} sent something I couldn't read ({type(e).__name__})") from e


def _existing_wires(provider: str) -> set[str]:
    """Models this provider already serves as planets — built-in or installed."""
    wires: set[str] = set()
    try:
        from core import model_router
        from core.ai_router import GROQ_MODEL_IDS
        if provider == "openrouter":
            wires |= {mid for mid in model_router.MODELS.values() if mid not in GROQ_MODEL_IDS}
        if provider == "groq":
            wires |= set(GROQ_MODEL_IDS)
    except Exception:  # noqa: BLE001
        pass
    wires |= {m["wire"] for m in _models_cached() if m["provider"] == provider}
    return wires


def _rank(models: list[dict], hint: str | None) -> list[dict]:
    """Best-first: the linked model, then free before paid, bigger and newer
    before smaller — and a spread of jobs rather than ten near-twins."""
    def score(m: dict) -> float:
        s = 0.0
        if hint and m["id"].lower().startswith(hint.lower()):
            s += 10_000
        if m["cost"] in FREEISH:
            s += 1000
        size = _params_b(m["id"] + " " + m["name"])
        s += min(size, 700) ** 0.5 * 10
        s += math.log10(max(1, int(m.get("created") or 0))) if m.get("created") else 0
        if re.search(r"instruct|chat|it\b|-it", m["id"].lower()):
            s += 15
        if re.search(r"preview|beta|exp|test|legacy|deprecated", m["id"].lower()):
            s -= 40
        if re.search(r"mini|nano|tiny|lite", m["id"].lower()):
            s -= 20
        ctx = m.get("context") or ""
        num = float(re.sub(r"[^\d.]", "", ctx) or 0) * (1_000_000 if ctx.endswith("M") else 1000)
        if 0 < num < 16_000:
            s -= 200        # a 4K window can't hold AURA's context block
        return s
    return sorted(models, key=score, reverse=True)


def _assess(provider: str, key: str, base: str, hint: str | None) -> dict:
    """Catalogue + classification for the card. {ok, error, models}."""
    try:
        cat = list_models(provider, key, base)
    except _ProbeError as e:
        return {"ok": False, "error": str(e), "models": [], "total": 0}
    cat = [m for m in cat if not _SKIP_MODEL.search(m["id"] + " " + m["name"])]
    existing = _existing_wires(provider)
    ranked = _rank(cat, hint)
    shown = ranked[:14]
    if hint:
        linked = [m for m in ranked if m["id"].lower() == hint.lower() or m["id"].lower().startswith(hint.lower())]
        for m in linked[:1]:
            if m not in shown:
                shown.insert(0, m)
    out = []
    lead_jobs: list[str] = []
    for m in shown:
        best = classify(m["id"], m["name"], m["desc"], m["vision"])
        already = m["id"] in existing
        linked = bool(hint and m["id"].lower().startswith(hint.lower()))
        pick = False
        if not already:
            if hint:
                pick = linked and not lead_jobs
            elif m["cost"] in FREEISH and len(lead_jobs) < 2 and best[0] not in lead_jobs:
                pick = True     # two picks that lead different jobs beat two twins
        if pick:
            lead_jobs.append(best[0])
        # pre-tick its two strongest jobs (and Vision if it can see) — the rest
        # are one click away, but a model shouldn't land in every lane unasked
        ticked = best[:2] + (["Vision"] if "Vision" in best[2:] else [])
        out.append({"id": m["id"], "name": _pretty(m["id"], m["name"]), "cost": m["cost"],
                    "context": m["context"], "vision": m["vision"], "best_for": best,
                    "jobs": ticked if pick else best[:1], "selected": pick, "existing": already,
                    "linked": linked, "desc": m["desc"][:200]})
    free = sum(1 for m in cat if m["cost"] in FREEISH)
    return {"ok": True, "error": "", "models": out, "total": len(cat), "free": free}


# ── reading a GitHub repo / docs page someone asked to install ──────────────
_PAGE_SYS = """You decide whether a project or web page gives AURA an API she can call. Answer with ONE JSON object and nothing else:
{"what": "one sentence: what this is",
 "type": "llm_api" | "search_api" | "local_llm_server" | "library" | "app" | "other",
 "openai_compatible": true or false,
 "base_url": "the HTTP base URL of its OpenAI-compatible API if the text states one (ending in /v1 or similar), else null",
 "needs_key": true or false,
 "service": "the hosted service it is for, if any (e.g. Groq, Mistral, Ollama), else null",
 "best_for": ["Coding" | "Research" | "Chat" | "Vision" | "Background" | "Search"]}
Use only facts in the text."""


def _read_page(url: str) -> tuple[dict | None, dict]:
    """Save the page to Saved Info (it's worth keeping either way) and ask a
    small model what it is. (verdict or None, saved item)."""
    from core import saved_info
    items = saved_info.capture([url], wait=30, origin="install")
    item = items[0] if items else {}
    full = saved_info.get_item(item["id"], with_content=True) if item else None
    text = (full or {}).get("content") or ""
    if not text:
        return None, item
    try:
        from core.ai_router import GROQ_MODEL_LIGHT, call_groq_raw
        from core.saved_info import _parse_json
        reply = call_groq_raw(f"URL: {url}\nTITLE: {full.get('title')}\n\n{text[:7000]}",
                              _PAGE_SYS, max_tokens=500, temperature=0.1, model=GROQ_MODEL_LIGHT)
        return _parse_json(reply), item
    except Exception as e:  # noqa: BLE001
        print(f"[AURA integrations] page read failed: {e}")
        return None, item


# ── proposals ───────────────────────────────────────────────────────────────

def _provider_menu() -> list[dict]:
    return [{"id": pid, "label": p["label"], "kind": p["kind"], "cost": p.get("cost", "")}
            for pid, p in PROVIDERS.items()]


def _env_key(provider: str) -> tuple[str, str]:
    """(key, 'env:NAME') if the key for this provider is already in .env."""
    for name in PROVIDERS.get(provider, {}).get("env", ()):
        val = os.getenv(name, "")
        if val and "your-" not in val and "your_" not in val:
            return val, f"env:{name}"
    return "", ""


def _save_proposal(prop: dict, secret: str = "", key_source: str = "") -> dict:
    conn = _conn()
    try:
        pub = {k: v for k, v in prop.items() if k != "id"}
        if prop.get("id"):
            conn.execute(
                "UPDATE integrations SET provider=?, label=?, kind=?, base_url=?, secret=?, key_source=?, "
                "proposal=?, source_url=? WHERE uid=?",
                (prop["provider"] or "custom", prop["label"], prop["kind"], prop.get("base_url", ""),
                 secret, key_source, json.dumps(pub), prop.get("source_url", ""), prop["id"]))
        else:
            prop["id"] = "p" + secrets.token_hex(6)
            conn.execute(
                "INSERT INTO integrations (uid, provider, label, kind, base_url, secret, key_source, status, "
                "proposal, source_url, created_at) VALUES (?,?,?,?,?,?,?, 'pending', ?, ?, ?)",
                (prop["id"], prop["provider"] or "custom", prop["label"], prop["kind"],
                 prop.get("base_url", ""), secret, key_source, json.dumps(pub),
                 prop.get("source_url", ""), _now()))
        conn.commit()
    finally:
        conn.close()
    return prop


def _load(uid: str) -> tuple[dict, str, str, int, str] | None:
    """(proposal, secret, key_source, row id, status)."""
    conn = _conn()
    try:
        r = conn.execute("SELECT proposal, secret, key_source, id, status FROM integrations WHERE uid=?",
                         (uid,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    prop = json.loads(r[0] or "{}")
    prop["id"] = uid
    return prop, r[1] or "", r[2] or "", r[3], r[4]


def _blank(provider: str | None, source_url: str = "", masked_key: str = "") -> dict:
    p = PROVIDERS.get(provider or "custom", PROVIDERS["custom"])
    return {
        "id": "", "provider": provider or "", "label": p["label"] if provider else "Unknown service",
        "kind": p["kind"], "about": p.get("about", ""), "cost": p.get("cost", ""),
        "base_url": p.get("base", ""), "key_masked": masked_key, "key_from": "",
        "stage": "choose", "error": "", "note": "", "models": [], "total_models": 0,
        "position": "backup", "search_jobs": ["Research", "Search"], "source_url": source_url,
        "providers": _provider_menu(), "results": [], "status": "pending", "created_at": _now(),
        "hint_model": "",
    }


def propose(req: dict) -> dict:
    """Turn a detected install request into a proposal card + a chat line."""
    keys, urls, named = req.get("keys") or [], req.get("urls") or [], req.get("named")
    key_prov, key = (keys[0] if keys else (None, ""))
    url = urls[0] if urls else ""
    url_prov, hint = _provider_for_url(url) if url else (None, None)
    provider = key_prov or url_prov or named
    note = ""
    if len(keys) > 1:
        note = "You pasted more than one key — I'm setting up the first. Send the others one at a time."

    # A link to something that isn't a known service: read it and decide.
    verdict = None
    if url and not provider:
        _activity("Reading the link to see what it is…", "memory")
        verdict, item = _read_page(url)
        if verdict:
            svc = _NAMES.get(str(verdict.get("service") or "").strip().lower())
            if svc:
                provider = svc
            elif verdict.get("openai_compatible") and str(verdict.get("base_url") or "").startswith("http"):
                provider = "custom"
            elif verdict.get("type") == "local_llm_server" and "ollama" in json.dumps(verdict).lower():
                provider = "ollama"
        if not provider and not key:
            what = (verdict or {}).get("what") or (item or {}).get("summary") or "a page I couldn't classify"
            typ = (verdict or {}).get("type") or "other"
            prop = _blank(None, url)
            prop.update(stage="not_installable", label=(item or {}).get("title") or url,
                        note=f"{what}", error="")
            _save_proposal(prop)
            kind = {"library": "a code library", "app": "an app", "other": "not an API"}.get(typ, "not an API")
            prop["message"] = (f"I read it — {what.rstrip('.')}. It's {kind}, not an API I can call, so "
                               "there's nothing to turn into a planet. I saved it to **Saved Info**. "
                               "If it has a hosted API, paste the key and I'll wire it in.")
            return prop

    prop = _blank(provider, url, mask(key))
    prop["note"] = note
    if hint:
        prop["hint_model"] = hint
    if verdict and provider == "custom":
        prop["base_url"] = str(verdict.get("base_url") or "").rstrip("/")
        prop["about"] = verdict.get("what") or ""

    secret, key_source = key, "chat" if key else ""
    if not provider:
        prop.update(stage="need_provider", label="Unknown key")
        _save_proposal(prop, secret, key_source)
        prop["message"] = ("That looks like an API key, but I can't tell which service it's for. "
                           "Pick it below and I'll check it.")
        return prop

    p = PROVIDERS[provider]
    if not key and p.get("needs_key", True) and provider != "custom":
        env_key, src = _env_key(provider)
        if env_key:
            secret, key_source = "", src
            prop["key_from"] = src[4:]
            prop["key_masked"] = mask(env_key)
        else:
            prop["stage"] = "need_key"
            _save_proposal(prop, "", "")
            prop["message"] = (f"That's **{p['label']}** — {p.get('about', '')}. I need an API key for it: "
                               "paste it in the card below (it stays on this PC and never goes into the chat).")
            return prop
    return _finish(prop, secret, key_source)


def _finish(prop: dict, secret: str, key_source: str) -> dict:
    """Probe the service and fill in models / the search offer."""
    provider = prop["provider"]
    p = PROVIDERS.get(provider, PROVIDERS["custom"])
    key = secret or _resolve_key("", key_source, p)
    if p["kind"] == "search":
        prop["stage"] = "choose"
        _save_proposal(prop, secret, key_source)
        prop["message"] = (f"That's a **{p['label']}** key — web search ({p.get('cost', '')}). Install it and "
                           "I'll search the web when you ask research or look-up questions. "
                           "I'll run one test search when you hit Install.")
        return prop
    if provider == "custom" and not prop.get("base_url"):
        prop["stage"] = "need_base_url"
        _save_proposal(prop, secret, key_source)
        prop["message"] = ("It speaks the OpenAI API, but I need its base URL (something ending in /v1). "
                           "Add it in the card.")
        return prop

    _activity(f"Checking {p['label']}…", "route")
    got = _assess(provider, key, prop.get("base_url", ""), prop.get("hint_model") or None)
    if not got["ok"]:
        prop.update(stage="error", error=got["error"])
        _save_proposal(prop, secret, key_source)
        prop["message"] = (f"That's **{p['label']}**, but {got['error']}. "
                           "Fix it and paste it again, or pick a different service in the card.")
        return prop

    prop.update(stage="choose", models=got["models"], total_models=got["total"], error="")
    _save_proposal(prop, secret, key_source)
    picks = [m for m in got["models"] if m["selected"]]
    usable = [m for m in got["models"] if not m["existing"]]
    linked_existing = [m for m in got["models"] if m.get("linked") and m["existing"]]
    count = f"{got['total']} models" + (f", {got['free']} free" if 0 < got["free"] < got["total"] else "")
    if not usable:
        prop["message"] = (f"**{p['label']}** works, but every model it offers is already a planet. "
                           "Nothing new to install.")
    elif linked_existing and not picks:
        prop["message"] = (f"**{linked_existing[0]['name']}** is already one of my planets. {p['label']} "
                           f"has {count} — tick any others you want below.")
    elif picks:
        desc = "; ".join(f"**{m['name']}** for {' & '.join(m['jobs'])}" for m in picks)
        free_note = "" if all(m["cost"] in FREEISH for m in picks) else " Heads up: it's a paid model."
        prop["message"] = (f"That's **{p['label']}** and it works — {count}. "
                           f"I'd make {desc}.{free_note} Tick what you want below and hit Install.")
    elif got["free"]:
        prop["message"] = f"**{p['label']}** works — {count}. Tick the ones you want below."
    else:
        prop["message"] = (f"**{p['label']}** works — {got['total']} models, none of them free. "
                           "Tick the ones you're happy paying for, or skip it.")
    if prop.get("note"):
        prop["message"] += " " + prop["note"]
    return prop


def get_proposal(uid: str) -> dict | None:
    got = _load(uid)
    if not got:
        return None
    prop, _, _, _, status = got
    prop["status"] = status
    return prop


def identify(uid: str, provider: str | None = None, key: str | None = None,
             base_url: str | None = None) -> dict:
    """The card's follow-up answers: which service, the key, the base URL."""
    got = _load(uid)
    if not got:
        raise ValueError("that install card has expired — paste the key again")
    prop, secret, key_source, _, status = got
    if status in ("installed", "merged"):
        raise ValueError("already installed")
    if provider:
        if provider not in PROVIDERS:
            raise ValueError("unknown service")
        keep = {k: prop.get(k) for k in ("id", "source_url", "hint_model", "key_masked", "note")}
        prop = {**_blank(provider, prop.get("source_url", ""), prop.get("key_masked", "")), **keep}
        if provider != "custom":
            prop["base_url"] = PROVIDERS[provider].get("base", "")
    if key is not None and key.strip():
        found = find_keys(key.strip() + " key")
        secret = found[0][1] if found else key.strip()
        key_source = "chat"
        prop["key_masked"] = mask(secret)
        prop["key_from"] = ""
    if base_url:
        b = base_url.strip().rstrip("/")
        if not re.match(r"^https?://", b):
            raise ValueError("the base URL must start with http:// or https://")
        prop["base_url"] = b.removesuffix("/chat/completions")
    if not prop.get("provider"):
        raise ValueError("pick the service first")
    p = PROVIDERS[prop["provider"]]
    if p.get("needs_key") is False:
        # A local server takes no key — never forward one pasted for another service.
        secret, key_source = "", ""
        prop["key_masked"], prop["key_from"] = "", ""
    if not secret and not key_source and p.get("needs_key", True) and prop["provider"] != "custom":
        env_key, src = _env_key(prop["provider"])
        if env_key:
            key_source, prop["key_from"], prop["key_masked"] = src, src[4:], mask(env_key)
        else:
            prop.update(stage="need_key", error="")
            _save_proposal(prop, "", "")
            prop["message"] = f"Paste your {p['label']} API key and I'll check it."
            return prop
    return _finish(prop, secret, key_source)


def dismiss(uid: str) -> bool:
    conn = _conn()
    try:
        cur = conn.execute("UPDATE integrations SET status='dismissed', secret='' "
                           "WHERE uid=? AND status!='installed'", (uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── install ─────────────────────────────────────────────────────────────────
_PALETTE = ["#00E5C7", "#FF7AB6", "#9DFF6B", "#FFB454", "#7AB8FF", "#D17BFF",
            "#5CFFE1", "#FF9F7A", "#C6FF4D", "#8FA6FF", "#FFD86B", "#FF6B6B"]
_ROLE = {"Coding": "The Engineer", "Research": "The Thinker", "Chat": "The Talker",
         "Vision": "The Eye", "Background": "The Runner", "Search": "The Seeker"}
_NATURE = {"Coding": "Installed · Precise · Hands-on", "Research": "Installed · Deep · Patient",
           "Chat": "Installed · Warm · Quick", "Vision": "Installed · Observant · Literal",
           "Background": "Installed · Light · Instant", "Search": "Installed · Curious · Current"}


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def _live_test(style: str, url: str, key: str, wire: str) -> tuple[bool, str, int, str]:
    """One tiny real call. (ok, reason, latency ms, style to route it with).

    If the service rejects AURA's reasoning flags for this model (Groq's
    compound models do), it's retried as a plain request and the plain style
    is what gets stored — so routing never sends the flag it choked on.
    """
    timeout = 180 if _is_local(url) else 45     # a local model's first call loads it into memory
    body: dict = {"model": wire, "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                  "max_tokens": 300, "temperature": 0, "stream": False}
    if style == "openrouter":
        body["reasoning"] = {"exclude": True}
    elif style == "groq":
        body["reasoning_format"] = "hidden"
    t0 = time.time()
    try:
        r = requests.post(url, headers=_headers(style, key), json=body, timeout=timeout)
    except requests.Timeout:
        return False, f"didn't answer within {timeout}s", 0, style
    except requests.RequestException as e:
        return False, f"couldn't connect ({type(e).__name__})", 0, style
    ms = int((time.time() - t0) * 1000)
    if r.status_code == 400 and style == "groq" and "reasoning" in r.text.lower():
        return _live_test("compat", url, key, wire)
    if r.status_code == 429:
        # It exists and the key works — it's just busy. Worth keeping.
        return True, "rate-limited right now, but reachable", ms, style
    if r.status_code >= 400:
        return False, _explain_http(r, "the service"), ms, style
    try:
        j = r.json()
        if not j.get("choices"):
            return False, "answered without a reply", ms, style
    except Exception:  # noqa: BLE001
        return False, "answered with something that isn't JSON", ms, style
    return True, "", ms, style


def _unique_name(name: str, label: str) -> str:
    taken = set()
    try:
        from core import model_router
        taken |= set(model_router.MODELS)
    except Exception:  # noqa: BLE001
        pass
    taken |= {m["name"] for m in _models_cached()}
    if name not in taken:
        return name
    alt = f"{name} · {label.split(' ')[0]}"
    n = 2
    while alt in taken:
        alt = f"{name} · {label.split(' ')[0]} {n}"
        n += 1
    return alt


def _next_colors(n: int) -> list[str]:
    used = [m["color"] for m in _models_cached()]
    free = [c for c in _PALETTE if c not in used] or _PALETTE
    return [free[i % len(free)] for i in range(n)]


def confirm(uid: str, picks: list[dict], position: str = "backup",
            search_jobs: list[str] | None = None) -> dict:
    """Install the ticked models (after a live test each) or the search API."""
    got = _load(uid)
    if not got:
        raise ValueError("that install card has expired — paste the key again")
    prop, secret, key_source, row_id, status = got
    if status in ("installed", "merged"):
        raise ValueError("already installed")
    provider = prop.get("provider") or ""
    p = PROVIDERS.get(provider, PROVIDERS["custom"])
    key = secret or _resolve_key("", key_source, p)
    position = "first" if position == "first" else "backup"
    results: list[dict] = []

    if p["kind"] == "search":
        _activity(f"Test-searching with {p['label']}…", "route")
        try:
            hits = web_search("AURA assistant test", n=1, provider=provider, key=key)
            ok, why = True, f"{len(hits)} result(s)"
        except Exception as e:  # noqa: BLE001
            ok, why = False, str(e)[:160]
        results.append({"id": provider, "name": p["label"], "ok": ok, "why": why})
        if not ok:
            prop.update(stage="error", error=f"the test search failed: {why}", results=results)
            _save_proposal(prop, secret, key_source)
            return {"ok": False, "proposal": prop, "results": results,
                    "message": f"{p['label']} failed its test search ({why}). Nothing installed."}
        conn = _conn()
        try:
            conn.execute("UPDATE integrations SET status='installed', installed_at=? WHERE id=?",
                         (_now(), row_id))
            conn.execute("DELETE FROM integration_models WHERE integration_id=?", (row_id,))
            conn.commit()
        finally:
            conn.close()
        prop.update(stage="installed", status="installed", results=results,
                    search_jobs=search_jobs or ["Research", "Search"])
        _save_proposal(prop, secret, key_source)
        invalidate()
        _publish({"kind": "installed", "integration": uid})
        return {"ok": True, "proposal": prop, "results": results,
                "message": f"**{p['label']}** is installed — I can search the web now. Ask me to look something up."}

    wanted = {str(x.get("id")): [j for j in (x.get("jobs") or []) if j in JOBS] for x in picks if x.get("id")}
    offered = {m["id"]: m for m in prop.get("models") or []}
    chosen = [offered[mid] for mid in wanted if mid in offered and not offered[mid].get("existing")]
    if not chosen:
        raise ValueError("tick at least one model first")
    base = (prop.get("base_url") or p.get("base") or "").rstrip("/")
    url = base + "/chat/completions"
    _activity(f"Test-calling {len(chosen)} model{'s' if len(chosen) != 1 else ''}…", "route")

    with ThreadPoolExecutor(max_workers=4) as ex:
        tests = list(ex.map(lambda m: _live_test(p.get("style", "compat"), url, key, m["id"]), chosen))

    colors = _next_colors(len(chosen))
    batch: set[str] = set()
    conn = _conn()
    try:
        # Same service, same address, same key as something already installed?
        # Then these planets join that group instead of starting a second one.
        target_id = row_id
        for other_id, o_secret, o_source, o_base in conn.execute(
                "SELECT id, secret, key_source, base_url FROM integrations "
                "WHERE status='installed' AND provider=? AND id<>? ORDER BY id",
                (provider or "custom", row_id)).fetchall():
            if ((o_base or p.get("base", "")).rstrip("/") == base
                    and _resolve_key(o_secret, o_source, p) == key):
                target_id = other_id
                break
        for m, (ok, why, ms, style), color in zip(chosen, tests, colors):
            jobs = wanted.get(m["id"]) or m.get("best_for", ["Chat"])[:1]
            name = m["name"]
            if ok:
                name = _unique_name(name, p["label"])
                if name in batch:
                    name = f"{name} ({m['id'].split('/')[-1][:18]})"
                batch.add(name)
            results.append({"id": m["id"], "name": name, "ok": ok, "why": why, "jobs": jobs, "ms": ms})
            if not ok:
                continue
            primary = jobs[0] if jobs else "Chat"
            conn.execute(
                "INSERT INTO integration_models (integration_id, model_id, name, jobs, position, vision, cost, "
                "context, color, role, nature, best_for, status, error, latency_ms, style, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (target_id, m["id"], name, ",".join(jobs), position, 1 if m.get("vision") else 0,
                 m.get("cost", ""), m.get("context", ""), color, _ROLE.get(primary, "The Newcomer"),
                 _NATURE.get(primary, "Installed"), ",".join(m.get("best_for") or []),
                 "ok", why, ms, style if style != p.get("style") else "", _now()))
        passed = [r for r in results if r["ok"]]
        if passed and target_id == row_id:
            conn.execute("UPDATE integrations SET status='installed', installed_at=?, position=? WHERE id=?",
                         (_now(), position, row_id))
        elif passed:
            # folded into the existing group — this proposal row is spent
            conn.execute("UPDATE integrations SET status='merged', secret='' WHERE id=?", (row_id,))
        conn.commit()
    finally:
        conn.close()

    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    prop.update(results=results, position=position,
                stage="installed" if passed else "error",
                status="installed" if passed else "pending",
                error="" if passed else "every ticked model failed its test call")
    merged = bool(passed) and target_id != row_id
    # a merged row is spent: its key already lives on the group it joined
    _save_proposal(prop, "" if merged else secret, "" if merged else key_source)
    invalidate()
    if passed:
        _publish({"kind": "installed", "integration": uid})

    lines = []
    if passed:
        lines.append("New planet" + ("s" if len(passed) > 1 else "") + " in orbit: " + "; ".join(
            f"**{r['name']}** — {' & '.join(r['jobs'])}" for r in passed) + ".")
        lines.append("I'll use " + ("them" if len(passed) > 1 else "it") +
                     (" first for those jobs." if position == "first" else " as backup for those jobs."))
    if failed:
        lines.append("Skipped " + "; ".join(f"{r['name']} ({r['why']})" for r in failed) + ".")
    return {"ok": bool(passed), "proposal": prop, "results": results, "message": " ".join(lines)}


# ── managing what's installed ───────────────────────────────────────────────

def list_integrations() -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, uid, provider, label, kind, base_url, secret, key_source, status, position, "
            "created_at, installed_at, proposal FROM integrations "
            "WHERE status IN ('installed', 'pending') ORDER BY id DESC LIMIT 60").fetchall()
    finally:
        conn.close()
    models = _models_cached()
    out = []
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    for r in rows:
        if r[8] == "pending" and (r[10] or "") < cutoff:
            continue
        prov = PROVIDERS.get(r[2], PROVIDERS["custom"])
        key = _resolve_key(r[6], r[7], prov)
        try:
            prop = json.loads(r[12] or "{}")
        except Exception:  # noqa: BLE001
            prop = {}
        prop["id"] = r[1]
        prop["status"] = r[8]
        out.append({
            "id": r[0], "uid": r[1], "provider": r[2], "label": r[3], "kind": r[4],
            "base_url": r[5] if r[2] in ("custom", "ollama", "lmstudio") else "",
            "key_masked": mask(key) if key and key != "no-key" else "",
            "key_from": (r[7] or "")[4:] if (r[7] or "").startswith("env:") else "",
            "status": r[8], "position": r[9], "created_at": r[10], "installed_at": r[11],
            "about": prov.get("about", ""), "cost": prov.get("cost", ""),
            "models": [_public_model(m) for m in models if m["integration_id"] == r[0]],
            "search_jobs": prop.get("search_jobs", []) if r[4] == "search" else [],
            "proposal": prop if r[8] == "pending" else None,
        })
    return out


def _public_model(m: dict) -> dict:
    return {k: m[k] for k in ("row_id", "id", "planet_id", "wire", "name", "jobs", "position", "vision",
                              "cost", "context", "color", "role", "nature", "best_for", "status",
                              "error", "latency_ms", "created_at", "provider", "label")}


def planets() -> list[dict]:
    """Every installed model and search API, shaped like frontend ModelNodes."""
    out = []
    for m in _models_cached():
        primary = m["jobs"][0] if m["jobs"] else "Chat"
        out.append({
            "id": m["planet_id"], "name": m["name"], "short": m["name"].split(" ")[0][:10],
            "modelId": m["id"], "role": m["role"] or _ROLE.get(primary, "The Newcomer"),
            "nature": m["nature"], "status": "standby", "color": m["color"], "ring": m["vision"],
            "provider": m["label"], "speed": 70, "context": m["context"] or "—",
            "purpose": f"{' · '.join(m['jobs'])} — installed from {m['label']}",
            "cost": m["cost"] or "—", "priority": 50 + m["row_id"], "x": 0, "y": 0,
            "installed": True, "jobs": m["jobs"], "created_at": m["created_at"],
            "wire": m["wire"], "integration_id": m["integration_id"],
        })
    conn = _conn()
    try:
        rows = conn.execute("SELECT id, provider, label, installed_at FROM integrations "
                            "WHERE kind='search' AND status='installed'").fetchall()
    finally:
        conn.close()
    for i, r in enumerate(rows):
        out.append({
            "id": f"s{r[0]}", "name": r[2], "short": r[2].split(" ")[0][:10], "modelId": f"search:{r[0]}",
            "role": _ROLE["Search"], "nature": _NATURE["Search"], "status": "standby",
            "color": _PALETTE[(len(out) + i) % len(_PALETTE)], "ring": False, "provider": r[2],
            "speed": 80, "context": "—", "purpose": "Web search for Research & look-ups",
            "cost": PROVIDERS.get(r[1], {}).get("cost", ""), "priority": 90, "x": 0, "y": 0,
            "installed": True, "jobs": ["Search"], "created_at": r[3], "wire": "",
            "integration_id": r[0],
        })
    return out


def update_model(row_id: int, jobs: list[str] | None = None, position: str | None = None) -> bool:
    conn = _conn()
    try:
        if jobs is not None:
            clean = [j for j in jobs if j in JOBS]
            if not clean:
                raise ValueError("a planet needs at least one job")
            primary = clean[0]
            conn.execute("UPDATE integration_models SET jobs=?, role=?, nature=? WHERE id=?",
                         (",".join(clean), _ROLE.get(primary, "The Newcomer"), _NATURE.get(primary, ""), row_id))
        if position in ("first", "backup"):
            conn.execute("UPDATE integration_models SET position=? WHERE id=?", (position, row_id))
        conn.commit()
    finally:
        conn.close()
    invalidate()
    _publish({"kind": "updated"})
    return True


def remove_model(row_id: int) -> bool:
    conn = _conn()
    try:
        r = conn.execute("SELECT integration_id FROM integration_models WHERE id=?", (row_id,)).fetchone()
        if not r:
            return False
        conn.execute("DELETE FROM integration_models WHERE id=?", (row_id,))
        left = conn.execute("SELECT COUNT(*) FROM integration_models WHERE integration_id=?", (r[0],)).fetchone()[0]
        if not left:
            conn.execute("UPDATE integrations SET status='removed', secret='' WHERE id=? AND kind='llm'", (r[0],))
        conn.commit()
    finally:
        conn.close()
    invalidate()
    _publish({"kind": "removed"})
    return True


def uninstall(integration_id: int) -> bool:
    """Remove every planet from this integration and forget its key."""
    conn = _conn()
    try:
        conn.execute("DELETE FROM integration_models WHERE integration_id=?", (integration_id,))
        cur = conn.execute("UPDATE integrations SET status='removed', secret='' WHERE id=?", (integration_id,))
        conn.commit()
    finally:
        conn.close()
    invalidate()
    _publish({"kind": "removed"})
    return cur.rowcount > 0


def retest(integration_id: int) -> list[dict]:
    """Live-test every installed model of one integration again."""
    ms = [m for m in _models_cached() if m["integration_id"] == integration_id]
    out = []
    conn = _conn()
    try:
        for m in ms:
            prov_style = PROVIDERS.get(m["provider"], {}).get("style", "compat")
            ok, why, lat, style = _live_test(prov_style, m["base"] + "/chat/completions", m["key"], m["wire"])
            conn.execute("UPDATE integration_models SET status=?, error=?, latency_ms=?, style=? WHERE id=?",
                         ("ok" if ok else "failed", why, lat, style if style != prov_style else "",
                          m["row_id"]))
            out.append({"name": m["name"], "ok": ok, "why": why, "ms": lat})
        conn.commit()
    finally:
        conn.close()
    invalidate()
    _publish({"kind": "updated"})
    return out
