"""
core.domain.analyzer
--------------------
Phase-2 "Project Analysis" for AURA Domain V2. Walks a folder on disk and
builds the understanding the spec asks for:

    Project summary  — languages, frameworks, files/classes/functions
    Module overview  — top-level packages and what's in them
    Architecture hint — a coarse layer guess (frontend / backend / core ...)

Pure static analysis, no execution. Python class/function counts are exact
(AST); other languages use cheap regex heuristics. Framework detection reads
manifest files (package.json, requirements.txt, pyproject, etc).
"""

from __future__ import annotations

import ast
import os
import re
from collections import Counter
from typing import Any

# directories we never descend into
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".cache", ".mypy_cache", ".pytest_cache",
    "coverage", ".idea", ".vscode", "site-packages", ".turbo",
}

_LANG = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".json": "JSON", ".md": "Markdown", ".html": "HTML", ".css": "CSS",
    ".scss": "CSS", ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby",
    ".sh": "Shell", ".yml": "YAML", ".yaml": "YAML", ".vue": "Vue",
    ".svelte": "Svelte",
}

# framework -> (manifest filename, substring to look for in it). A manifest
# hit is strong evidence; substring "" means "presence of the file is enough".
_FRAMEWORK_SIGNS = [
    ("FastAPI", "requirements.txt", "fastapi"),
    ("FastAPI", "pyproject.toml", "fastapi"),
    ("Flask", "requirements.txt", "flask"),
    ("Django", "requirements.txt", "django"),
    ("PySide6", "requirements.txt", "pyside6"),
    ("PyQt", "requirements.txt", "pyqt"),
    ("React", "package.json", "\"react\""),
    ("Next.js", "package.json", "\"next\""),
    ("Vue", "package.json", "\"vue\""),
    ("Svelte", "package.json", "\"svelte\""),
    ("Electron", "package.json", "\"electron\""),
    ("Vite", "package.json", "\"vite\""),
    ("Express", "package.json", "\"express\""),
    ("Tailwind", "package.json", "tailwindcss"),
]

# cheap per-language counters for non-Python files
_TS_CLASS = re.compile(r"\bclass\s+[A-Za-z_$]")
_TS_FUNC = re.compile(
    r"\bfunction\s+[A-Za-z_$]"          # function foo()
    r"|\b(?:const|let)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?\("  # const foo = (
    r"|\b(?:const|let)\s+[A-Za-z_$][\w$]*\s*:\s*[A-Za-z<>\[\], ]+=\s*(?:async\s*)?\("
)


def _iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def _count_python(path: str) -> tuple[int, int]:
    """(classes, functions) via AST; falls back to 0 on syntax errors."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            tree = ast.parse(fh.read())
    except Exception:
        return 0, 0
    classes = funcs = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs += 1
    return classes, funcs


def _count_regex(path: str) -> tuple[int, int]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except Exception:
        return 0, 0
    return len(_TS_CLASS.findall(src)), len(_TS_FUNC.findall(src))


def _detect_frameworks(root: str) -> list[str]:
    found: list[str] = []
    cache: dict[str, str] = {}
    for name, manifest, needle in _FRAMEWORK_SIGNS:
        if name in found:
            continue
        # manifests can live at root OR one level down (e.g. frontend/package.json)
        candidates = [os.path.join(root, manifest)]
        for sub in os.listdir(root) if os.path.isdir(root) else []:
            p = os.path.join(root, sub, manifest)
            if os.path.isfile(p):
                candidates.append(p)
        for path in candidates:
            if not os.path.isfile(path):
                continue
            if path not in cache:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        cache[path] = fh.read().lower()
                except Exception:
                    cache[path] = ""
            if not needle or needle.lower() in cache[path]:
                found.append(name)
                break
    return found


def _module_overview(root: str) -> list[dict[str, Any]]:
    """Top-level packages/dirs and how many code files each holds."""
    overview: list[dict[str, Any]] = []
    if not os.path.isdir(root):
        return overview
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if not os.path.isdir(full) or entry in _SKIP_DIRS or entry.startswith("."):
            continue
        n = sum(1 for f in _iter_files(full)
                if os.path.splitext(f)[1].lower() in _LANG)
        if n:
            overview.append({"module": entry, "files": n})
    overview.sort(key=lambda m: m["files"], reverse=True)
    return overview


def _architecture_hint(modules: list[dict[str, Any]], frameworks: list[str]) -> str:
    names = {m["module"].lower() for m in modules}
    layers = []
    if names & {"frontend", "ui", "web", "client", "src"}:
        layers.append("frontend")
    if names & {"backend", "server", "api", "core", "app"}:
        layers.append("backend/core")
    if names & {"memory", "db", "data", "store"}:
        layers.append("persistence")
    if names & {"tests", "test"}:
        layers.append("tests")
    fw = ", ".join(frameworks[:4])
    if layers:
        return f"{' + '.join(layers)} split" + (f" ({fw})" if fw else "")
    return fw or "flat / single-module"


def analyze(root: str) -> dict[str, Any]:
    """Full Phase-2 analysis of a folder. Never raises."""
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        return {"ok": False, "error": "path not found", "root": root}

    lang_counter: Counter[str] = Counter()
    file_count = classes = functions = 0
    for path in _iter_files(root):
        ext = os.path.splitext(path)[1].lower()
        lang = _LANG.get(ext)
        if not lang:
            continue
        file_count += 1
        lang_counter[lang] += 1
        if ext == ".py":
            c, f = _count_python(path)
        elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs"}:
            c, f = _count_regex(path)
        else:
            c, f = 0, 0
        classes += c
        functions += f

    frameworks = _detect_frameworks(root)
    modules = _module_overview(root)
    languages = dict(lang_counter.most_common())
    return {
        "ok": True,
        "root": root,
        "name": os.path.basename(root.rstrip(os.sep)) or root,
        "languages": languages,
        "primary_language": next(iter(languages), ""),
        "frameworks": frameworks,
        "file_count": file_count,
        "classes": classes,
        "functions": functions,
        "modules": modules,
        "architecture": _architecture_hint(modules, frameworks),
    }
