"""
core/patcher.py — how AURA changes code.

One engine serves both jobs: rewriting AURA's own source ("upgrade yourself so
you can X") and editing any project opened in the Domain. They are the same
act pointed at different trees, so they share the same rails.

Nothing is ever written without a human yes. A request produces a *proposal*:
the full new contents of every file it wants to touch, with a diff and a plain
sentence about why. The proposal sits there until it is approved. Approving
copies the current files into a backup first, so any applied change can be
rolled back whole — including an upgrade that breaks AURA itself.

The model is asked twice, on purpose:
  1. "Here is the file tree. Which files do you need to read?"  → a short list
  2. "Here are those files. Return the new contents."           → the rewrite
One-step patching against a whole repo either blows the context window or has
the model inventing files it never saw.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import time
import uuid
from typing import Any

# ── where proposals and their backups live ──────────────────────────────────
# Deliberately outside whatever tree is being edited: a proposal for a project
# must not show up as an untracked file in that project's own git status.
STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "memory", "patches")

AURA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── rails ───────────────────────────────────────────────────────────────────
MAX_FILES = 12               # per proposal
MAX_READ_BYTES = 180_000     # per file offered to the model
MAX_CONTEXT_BYTES = 420_000  # total source handed over in one call
MAX_TREE_ENTRIES = 1200

# The biggest file a model can be asked to hand back whole. Above this it runs
# out of output tokens part-way and returns a short file that looks like a
# valid rewrite and is actually the top of one — which, applied, deletes
# everything below the cut. The ceiling is well under the token budget on
# purpose: being told "that file is too big" is recoverable, silently losing
# 1600 lines is not.
MAX_REWRITE_BYTES = 28_000
# A rewrite that keeps less than this share of an existing file's lines is
# treated as truncation rather than an edit.
MIN_KEPT_RATIO = 0.35

# Directories never read, never written, never listed.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "dist", "build", ".next", ".cache", "site-packages", ".idea", ".vscode",
    "memory", "logs", "_backup", "_to_delete", ".codex_pycache",
}
# Files never handed to a model and never overwritten. Secrets, binaries and
# anything whose corruption cannot be undone by restoring text.
SKIP_NAMES = {".env", ".env.local", ".env.production", "aura_memory.db"}
SKIP_EXT = {
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin", ".pkl", ".db",
    ".sqlite", ".sqlite3", ".zip", ".gz", ".tar", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".mp4", ".webm",
    ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".otf", ".pdf",
    ".key", ".pem", ".crt", ".p12",
}
TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss",
    ".html", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".sh", ".bat", ".ps1", ".sql", ".go", ".rs", ".java", ".c", ".h", ".cpp",
    ".rb", ".php", ".swift", ".kt", ".vue", ".svelte", ".env.example",
}


# ── small helpers ───────────────────────────────────────────────────────────
def _store() -> str:
    os.makedirs(STORE, exist_ok=True)
    return STORE


def _index_path() -> str:
    return os.path.join(_store(), "index.json")


def _load_index() -> list[dict]:
    try:
        with open(_index_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_index(rows: list[dict]) -> None:
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    os.replace(tmp, _index_path())


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _skippable(name: str) -> bool:
    low = name.lower()
    if low in SKIP_NAMES:
        return True
    ext = os.path.splitext(low)[1]
    return ext in SKIP_EXT


def _is_text(path: str) -> bool:
    ext = os.path.splitext(path.lower())[1]
    return ext in TEXT_EXT


def safe_join(root: str, rel: str) -> str | None:
    """Absolute path for `rel` inside `root`, or None if it escapes the tree,
    lands on a skipped name, or walks through a skipped directory. Every write
    in this module goes through here."""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("../") or ".." in rel.split("/"):
        return None
    root_abs = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_abs, rel))
    if full != root_abs and not full.startswith(root_abs + os.sep):
        return None
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return None
    if _skippable(parts[-1]):
        return None
    return full


def file_tree(root: str, limit: int = MAX_TREE_ENTRIES) -> list[str]:
    """Every editable file under `root`, as paths relative to it."""
    out: list[str] = []
    root_abs = os.path.realpath(root)
    for base, dirs, files in os.walk(root_abs):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if _skippable(name) or not _is_text(name):
                continue
            rel = os.path.relpath(os.path.join(base, name), root_abs).replace("\\", "/")
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def read_file(root: str, rel: str) -> str | None:
    full = safe_join(root, rel)
    if not full or not os.path.isfile(full):
        return None
    try:
        if os.path.getsize(full) > MAX_READ_BYTES:
            return None
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


_OVERESCAPED = ("\\`", '\\"', "\\$", "\\'")


def _unescape(before: str, after: str) -> str:
    """Undo transport-escaping a model added that was never in the file.

    Models routinely emit \\` and \\" as if the reply were a JSON string, which
    would write literal backslashes into the source. The give-away is that the
    sequence appears in the rewrite and nowhere in the original — a file that
    genuinely contains \\" keeps it, because `before` has it too.
    """
    for seq in _OVERESCAPED:
        if seq in after and seq not in before and after.count(seq) >= 2:
            after = after.replace(seq, seq[1])
    return after


def _diff(rel: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + rel, tofile="b/" + rel, n=3,
    ))


def _counts(before: str, after: str) -> tuple[int, int]:
    added = removed = 0
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    return added, removed


# ── parsing what the model sends back ───────────────────────────────────────
def _json_block(text: str) -> Any:
    """The first JSON object or array in a reply, fences and chatter and all.
    Free models wrap JSON in prose more often than not."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except Exception:  # noqa: BLE001
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:  # noqa: BLE001
                continue
    try:
        return json.loads(text.strip())
    except Exception:  # noqa: BLE001
        return None


_FILE_RE = re.compile(
    # Leading spaces and stray ** are tolerated: models bold the delimiter or
    # indent it inside a list surprisingly often, and rejecting the whole
    # rewrite over a couple of asterisks helps nobody.
    r"^[ \t]*\**\s*===\s*FILE:\s*(?P<path>[^\n=]+?)\s*===\**[ \t]*\n(?P<body>.*?)"
    r"(?=^[ \t]*\**\s*===\s*FILE:|\Z)",
    re.S | re.M,
)


def _parse_files(text: str) -> dict[str, str]:
    """Whole-file rewrites out of a reply.

    The prompt asks for `=== FILE: path ===` blocks rather than JSON, because
    source code inside a JSON string means every quote, backslash and newline
    has to survive escaping — and small models get that wrong constantly.
    Plain delimiters can't be mangled.
    """
    out: dict[str, str] = {}
    for m in _FILE_RE.finditer(text):
        path = m.group("path").strip().strip("`\"'")
        body = m.group("body")
        # the model often fences the body anyway — unwrap one layer if so
        fence = re.match(r"\s*```[a-zA-Z0-9+#-]*\n(.*?)\n?```\s*\Z", body, re.S)
        if fence:
            body = fence.group(1)
        body = body.strip("\n")
        if path and body:
            out[path] = body + "\n"
    return out


# ── step 1: which files? ────────────────────────────────────────────────────
_PLAN_SYSTEM = """You are a senior engineer picking which files to open.

You will be given a request and a list of every file in a codebase.
Reply with ONLY a JSON array of file paths — the files you must read and
probably edit to fulfil the request. Copy paths EXACTLY as listed.

Rules:
- At most 8 paths. Fewer is better.
- Order them most-important first.
- Include a file you intend to CREATE only if it does not exist yet.
- No prose, no markdown, no explanation. Just the JSON array.

Example reply:
["frontend/src/components/Sidebar.tsx", "frontend/src/styles.css"]"""


def plan_files(root: str, request: str, hint: list[str] | None = None) -> list[str]:
    """The files a change will need. `hint` (paths the caller already knows)
    always survives, so an edit aimed at an open file starts from that file."""
    from core import ai_router

    tree = file_tree(root)
    picked: list[str] = []
    for h in (hint or []):
        rel = (h or "").replace("\\", "/").lstrip("/")
        if rel and rel not in picked:
            picked.append(rel)

    if len(picked) < MAX_FILES and tree:
        listing = "\n".join(tree)
        if len(listing) > 60_000:
            listing = listing[:60_000] + "\n… (truncated)"
        reply = ai_router.call_raw(
            f"REQUEST:\n{request}\n\nFILES:\n{listing}",
            _PLAN_SYSTEM, intent="CODING", max_tokens=700, temperature=0.1, timeout=60,
        )
        data = _json_block(reply)
        if isinstance(data, dict):
            data = data.get("files") or data.get("paths") or []
        if isinstance(data, list):
            known = set(tree)
            for item in data:
                rel = str(item).strip().strip("`\"'").replace("\\", "/").lstrip("/")
                if not rel or rel in picked:
                    continue
                # a path the model invented is only allowed if it is a new file
                # in a directory that exists — otherwise it is a hallucination
                if rel not in known and not os.path.isdir(
                        os.path.join(root, os.path.dirname(rel) or ".")):
                    continue
                picked.append(rel)
                if len(picked) >= MAX_FILES:
                    break

    # Nothing chosen and nothing hinted: fall back to whatever the request
    # names literally, so a specific ask still gets somewhere.
    if not picked:
        for rel in tree:
            if os.path.basename(rel).lower() in request.lower():
                picked.append(rel)
                if len(picked) >= 4:
                    break
    return picked[:MAX_FILES]


_IMPORT_RE = re.compile(
    r"""(?:from|import)\s+['"](?P<rel>\.[^'"]+)['"]|"""      # JS/TS: from "./x"
    r"""require\(\s*['"](?P<req>\.[^'"]+)['"]\s*\)|"""
    # Python: `from core.x import y`. Indented too — this codebase imports
    # inside functions on purpose, so module-level only would miss most of it.
    # The names matter as much as the package: `from core import saved_info`
    # points at core/saved_info.py, which the package alone never would.
    r"""^[ \t]*from\s+(?P<py>[.\w]+)\s+import\s+(?P<names>[^\n#(]+)""",
    re.M,
)
_JS_EXT = [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", ".css"]


def expand_with_imports(root: str, paths: list[str], budget: int) -> list[str]:
    """The picked files plus what they import, one hop out.

    Without this a model asked to change a component that renders another one
    can't see the thing it has to change, and the good ones say so while the
    small ones invent it. One hop is the sweet spot: enough to make the change
    correct, not so much that the whole app arrives in the prompt.
    """
    out = list(paths)
    known = set(file_tree(root))
    for rel in paths:
        body = read_file(root, rel)
        if not body:
            continue
        base = os.path.dirname(rel)
        for m in _IMPORT_RE.finditer(body):
            target = m.group("rel") or m.group("req") or ""
            if target:
                joined = os.path.normpath(os.path.join(base, target)).replace("\\", "/")
                cands = [joined] if os.path.splitext(joined)[1] else [joined + e for e in _JS_EXT]
            elif m.group("py"):
                mod = m.group("py").lstrip(".")
                if not mod or mod.split(".")[0] not in {"core", "memory", "modules", "tools"}:
                    continue
                pkg = mod.replace(".", "/")
                cands = [pkg + ".py"]
                # `from core import saved_info, brain` — each name may itself
                # be a module in that package.
                for name in (m.group("names") or "").split(","):
                    name = name.strip().split(" as ")[0].strip()
                    if name.isidentifier():
                        cands.append(f"{pkg}/{name}.py")
            else:
                continue
            for c in cands:
                if c in known and c not in out:
                    out.append(c)
                    if len(out) >= budget:
                        return out[:budget]
                    break
    return out[:budget]


# ── step 2: the rewrite ─────────────────────────────────────────────────────
_WRITE_SYSTEM = """You are a senior engineer making a surgical change to a real codebase.

You will be given a request and the CURRENT contents of the relevant files.
Return the COMPLETE new contents of every file you change.

OUTPUT FORMAT — follow exactly:

WHY: one sentence saying what you changed and why.

=== FILE: path/to/file.ext ===
<the complete new contents of that file>
=== FILE: another/file.ext ===
<the complete new contents of that file>

Rules:
- Use the EXACT path given to you. To create a new file, use its new path.
- Output the WHOLE file, from its first line to its last. Never write
  "... rest unchanged ...", never elide, never send a diff or a fragment.
- Only include files you actually changed. Leave untouched files out.
- Match the existing style: same indentation, same naming, same comment voice.
- Do not add dependencies that are not already used in the project.
- No markdown fences around the file bodies. No commentary between blocks.
- Write the file exactly as it must appear on disk. Do NOT escape anything for
  transport: a backtick is ` and a quote is " — never \\` or \\"."""


def propose(root: str, request: str, scope: str = "project",
            hint: list[str] | None = None, label: str = "") -> dict:
    """Ask for a change and store the result as a pending proposal.

    Returns the proposal dict. `ok` is False when nothing usable came back —
    the reason is in `error`, and no proposal is stored.
    """
    from core import ai_router

    root = os.path.realpath(root)
    if not os.path.isdir(root):
        return {"ok": False, "error": "that folder doesn't exist"}

    chosen = plan_files(root, request, hint)
    if not chosen:
        return {"ok": False, "error": "I couldn't work out which files that touches."}

    # Files too big to be handed back whole are dropped before the model ever
    # sees them as editable, rather than after it has quietly truncated one.
    too_big = [r for r in chosen
               if (b := read_file(root, r)) is not None and len(b) > MAX_REWRITE_BYTES]
    chosen = [r for r in chosen if r not in too_big]
    if not chosen:
        names = ", ".join(too_big)
        return {"ok": False,
                "error": f"{names} is too big for me to rewrite in one go — "
                         f"ask for a change to a smaller file, or split it first."}
    # …plus whatever they import, so the model isn't asked to change code that
    # calls something it was never shown.
    paths = expand_with_imports(root, chosen, MAX_FILES)

    blocks, used, offered = [], 0, []
    for rel in paths:
        body = read_file(root, rel)
        if body is None:
            # a file the model wants to create — tell it so explicitly
            if safe_join(root, rel):
                blocks.append(f"=== FILE: {rel} ===\n(this file does not exist yet)")
                offered.append(rel)
            continue
        if used + len(body) > MAX_CONTEXT_BYTES:
            break
        used += len(body)
        blocks.append(f"=== FILE: {rel} ===\n{body}")
        offered.append(rel)

    if not offered:
        return {"ok": False, "error": "none of those files could be read"}

    # Files pulled in only for context are named, so the model knows it may
    # read them but shouldn't be rewriting them wholesale.
    editable = ", ".join(chosen)
    reply = ai_router.call_raw(
        f"REQUEST:\n{request}\n\nCHANGE THESE FILES: {editable}\n"
        f"The other files are shown so you can see what they do. Everything you "
        f"need is below — do not ask for more files.\n\nCURRENT FILES:\n\n"
        + "\n\n".join(blocks),
        _WRITE_SYSTEM, intent="CODING", max_tokens=12000, temperature=0.15, timeout=180,
        validate=lambda r: bool(_parse_files(r)),
    )
    if not reply.strip():
        return {"ok": False, "error": "no model answered — check the roster in Models"}

    rewrites = _parse_files(reply)
    if not rewrites:
        return {"ok": False,
                "error": "the model replied but not with file contents — try rephrasing"}

    why = ""
    m = re.search(r"^\s*WHY:\s*(.+)$", reply, re.M)
    if m:
        why = m.group(1).strip()

    changes, truncated = [], []
    for rel, after in rewrites.items():
        full = safe_join(root, rel)
        if not full:
            continue                       # outside the tree, or a protected name
        before = read_file(root, rel) or ""
        after = _unescape(before, after)
        if before == after:
            continue                       # nothing actually changed
        # A "rewrite" that threw most of the file away is a reply that ran out
        # of room, not an edit. Applying it would delete working code, so the
        # file is dropped and the user is told which one it was.
        n_before = before.count("\n")
        if n_before >= 40 and after.count("\n") < n_before * MIN_KEPT_RATIO:
            truncated.append(rel)
            continue
        added, removed = _counts(before, after)
        changes.append({
            "path": rel,
            "new": bool(before == "" and not os.path.exists(full)),
            "before": before,
            "after": after,
            "diff": _diff(rel, before, after),
            "added": added,
            "removed": removed,
        })

    if not changes:
        if truncated:
            return {"ok": False,
                    "error": f"the reply for {', '.join(truncated)} was cut off part-way — "
                             f"ask for something smaller"}
        return {"ok": False, "error": "that change is already in the code — nothing to do"}

    pid = uuid.uuid4().hex[:12]
    proposal = {
        "id": pid,
        "scope": scope,                    # "self" = AURA's own source
        "root": root,
        "label": label or (os.path.basename(root) or root),
        "request": request,
        "why": why,
        "status": "pending",
        "created_at": _now(),
        "applied_at": "",
        "changes": changes,
    }
    _write(proposal)
    rows = _load_index()
    rows.insert(0, _summary(proposal))
    _save_index(rows[:200])
    return {"ok": True, **proposal}


# ── storage ─────────────────────────────────────────────────────────────────
def _proposal_path(pid: str) -> str:
    return os.path.join(_store(), f"{pid}.json")


def _write(proposal: dict) -> None:
    with open(_proposal_path(proposal["id"]), "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2)


def _summary(p: dict) -> dict:
    return {
        "id": p["id"], "scope": p["scope"], "root": p["root"], "label": p["label"],
        "request": p["request"], "why": p["why"], "status": p["status"],
        "created_at": p["created_at"], "applied_at": p.get("applied_at", ""),
        "files": [c["path"] for c in p["changes"]],
        "added": sum(c["added"] for c in p["changes"]),
        "removed": sum(c["removed"] for c in p["changes"]),
    }


def get(pid: str) -> dict | None:
    try:
        with open(_proposal_path(pid), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def list_proposals(scope: str = "", root: str = "", limit: int = 50) -> list[dict]:
    rows = _load_index()
    if scope:
        rows = [r for r in rows if r.get("scope") == scope]
    if root:
        target = os.path.realpath(root)
        rows = [r for r in rows if os.path.realpath(r.get("root", "")) == target]
    return rows[:limit]


def _touch_index(pid: str, **fields) -> None:
    rows = _load_index()
    for r in rows:
        if r.get("id") == pid:
            r.update(fields)
            break
    _save_index(rows)


# ── approve / reject / rollback ─────────────────────────────────────────────
def _backup_dir(pid: str) -> str:
    return os.path.join(_store(), pid, "backup")


def _verify(changes: list[dict]) -> str:
    """The last gate before anything is written. AURA rewriting its own source
    can otherwise leave a brain that won't import — and the UI needed to roll
    it back lives behind that brain.

    The truncation check is repeated here even though propose() already made
    it: propose decides what to offer, approve decides what reaches the disk,
    and a proposal written before this check existed must still be stopped.
    """
    for c in changes:
        rel, after, before = c["path"], c["after"], c.get("before", "")
        n_before = before.count("\n")
        if n_before >= 40 and after.count("\n") < n_before * MIN_KEPT_RATIO:
            return (f"{rel} would lose most of its content "
                    f"({n_before} lines down to {after.count(chr(10))}) — that reply was cut off")
        ext = os.path.splitext(rel.lower())[1]
        if ext == ".py":
            try:
                compile(after, rel, "exec")
            except SyntaxError as e:
                return f"{rel} line {e.lineno}: {e.msg}"
        elif ext == ".json":
            try:
                json.loads(after)
            except Exception as e:  # noqa: BLE001
                return f"{rel}: invalid JSON ({e})"
        elif ext in (".ts", ".tsx", ".js", ".jsx", ".css"):
            # No parser here, but unbalanced braces catch the common failure:
            # a truncated reply that stops mid-file.
            for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
                if after.count(open_c) != after.count(close_c):
                    return f"{rel}: unbalanced {open_c}{close_c} — the reply looks truncated"
    return ""


def approve(pid: str) -> dict:
    """Write the proposal to disk, after copying every file it touches into a
    backup. Either all of it lands or none of it does: a failure part-way
    restores what was already written."""
    p = get(pid)
    if not p:
        return {"ok": False, "error": "no such proposal"}
    if p["status"] == "applied":
        return {"ok": False, "error": "that one is already applied"}

    broken = _verify(p["changes"])
    if broken:
        return {"ok": False, "error": f"refusing to apply — {broken}"}

    root, backup = p["root"], _backup_dir(pid)
    os.makedirs(backup, exist_ok=True)
    written: list[tuple[str, str, bool]] = []   # (full, rel, was_new)

    try:
        for c in p["changes"]:
            full = safe_join(root, c["path"])
            if not full:
                raise ValueError(f"{c['path']} is outside the project")
            existed = os.path.isfile(full)
            if existed:
                dest = os.path.join(backup, c["path"].replace("/", "__"))
                shutil.copy2(full, dest)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(c["after"])
            written.append((full, c["path"], not existed))
    except Exception as e:  # noqa: BLE001
        for full, rel, was_new in reversed(written):
            try:
                if was_new:
                    os.remove(full)
                else:
                    shutil.copy2(os.path.join(backup, rel.replace("/", "__")), full)
            except Exception:  # noqa: BLE001
                pass
        return {"ok": False, "error": f"couldn't apply it: {e}"}

    p["status"] = "applied"
    p["applied_at"] = _now()
    _write(p)
    _touch_index(pid, status="applied", applied_at=p["applied_at"])
    return {"ok": True, "applied": [c["path"] for c in p["changes"]],
            "restart": p["scope"] == "self"}


def reject(pid: str) -> dict:
    p = get(pid)
    if not p:
        return {"ok": False, "error": "no such proposal"}
    if p["status"] == "applied":
        return {"ok": False, "error": "that one is applied — roll it back instead"}
    p["status"] = "rejected"
    _write(p)
    _touch_index(pid, status="rejected")
    return {"ok": True}


def rollback(pid: str) -> dict:
    """Put every file back the way it was before this proposal was applied."""
    p = get(pid)
    if not p:
        return {"ok": False, "error": "no such proposal"}
    if p["status"] != "applied":
        return {"ok": False, "error": "that one was never applied"}

    root, backup = p["root"], _backup_dir(pid)
    restored, failed = [], []
    for c in p["changes"]:
        full = safe_join(root, c["path"])
        if not full:
            failed.append(c["path"])
            continue
        try:
            if c.get("new"):
                if os.path.isfile(full):
                    os.remove(full)
            else:
                src = os.path.join(backup, c["path"].replace("/", "__"))
                if os.path.isfile(src):
                    shutil.copy2(src, full)
                else:                       # backup lost — the stored text still has it
                    with open(full, "w", encoding="utf-8", newline="") as f:
                        f.write(c["before"])
            restored.append(c["path"])
        except Exception:  # noqa: BLE001
            failed.append(c["path"])

    p["status"] = "rolled_back"
    _write(p)
    _touch_index(pid, status="rolled_back")
    return {"ok": not failed, "restored": restored, "failed": failed,
            "restart": p["scope"] == "self"}


def delete(pid: str) -> dict:
    """Forget a proposal entirely. An applied one keeps its backup — dropping
    that would make the change permanent by accident."""
    p = get(pid)
    if p and p["status"] == "applied":
        return {"ok": False, "error": "roll it back before deleting it"}
    try:
        os.remove(_proposal_path(pid))
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(os.path.join(_store(), pid), ignore_errors=True)
    _save_index([r for r in _load_index() if r.get("id") != pid])
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
# Saying it out loud
#
# "Upgrade yourself so you can X" should work in the chat, not only on the
# Upgrade page. The reply is deliberately short and ends by pointing at the
# diff: AURA writing its own code is exactly the moment to make you look at
# what it wrote rather than take its word for it.
# ════════════════════════════════════════════════════════════════════════════

_ASK_RE = re.compile(
    r"\b(?:upgrade|update|improve|change|modify|edit|rewrite|fix)\s+"
    r"(?:your\s*self|yourself|your\s+(?:own\s+)?(?:code|codebase|source|ui|interface))\b",
    re.I,
)
_APPROVE_RE = re.compile(
    r"\b(?:approve|apply|accept|do)\s+(?:it|that|the\s+(?:upgrade|change|update))\b|"
    r"\b(?:go\s+ahead|ship\s+it)\s+with\s+(?:it|that|the\s+upgrade)\b",
    re.I,
)
_ROLLBACK_RE = re.compile(
    # "roll it back" puts the object in the middle, which is how people
    # actually say it — more often than "roll back that change".
    r"\broll\s+(?:it|that|them)\s+back\b|"
    r"\b(?:roll\s*back|undo|revert)\s+(?:it|that|the\s+(?:last\s+)?(?:upgrade|change|update))\b",
    re.I,
)
_LIST_RE = re.compile(
    r"\b(?:what|which|any)\b.{0,24}\b(?:upgrades?|pending\s+changes?)\b|"
    r"\bpending\s+upgrades?\b",
    re.I,
)


def _strip_ask(text: str) -> str:
    """What the user actually wants changed, with the "upgrade yourself to"
    framing removed — the model gets the request, not the preamble."""
    out = _ASK_RE.sub("", text, count=1).strip()
    out = re.sub(r"^(?:so\s+(?:that\s+)?|to\s+|and\s+|:|,)\s*", "", out, flags=re.I).strip()
    return out or text.strip()


def _newest_self(status: str) -> dict | None:
    for row in list_proposals("self"):
        if row["status"] == status:
            return row
    return None


def chat_command(query: str) -> str | None:
    """Handle an upgrade said in conversation. None means "not about upgrades",
    and the normal reply path takes over."""
    text = (query or "").strip()
    if not text:
        return None

    if _LIST_RE.search(text):
        rows = list_proposals("self")
        pending = [r for r in rows if r["status"] == "pending"]
        if not rows:
            return "Nothing yet. Tell me what to change about myself and I'll write it."
        if not pending:
            last = rows[0]
            return (f"Nothing waiting. The last one was “{last['request'][:80]}” "
                    f"({last['status'].replace('_', ' ')}).")
        bits = [f"• {p['request'][:90]} — {len(p['files'])} file(s)" for p in pending[:4]]
        return ("Waiting on you:\n" + "\n".join(bits)
                + "\n\nOpen Upgrade to read the diff, or say “apply it”.")

    if _APPROVE_RE.search(text):
        row = _newest_self("pending")
        if not row:
            return "There's nothing waiting to be applied."
        res = approve(row["id"])
        if not res.get("ok"):
            return f"I couldn't apply it: {res.get('error', 'something went wrong')}"
        files = ", ".join(res.get("applied", []))
        return (f"Applied — {files}. Restart me and it's live. "
                f"Say “roll it back” if it isn't right.")

    if _ROLLBACK_RE.search(text):
        row = _newest_self("applied")
        if not row:
            return "Nothing of mine is applied right now, so there's nothing to undo."
        res = rollback(row["id"])
        if not res.get("ok"):
            return f"Rollback didn't fully work: {res.get('failed')}"
        return "Rolled back. Restart me to load the old code."

    if not _ASK_RE.search(text):
        return None

    request = _strip_ask(text)
    if len(request) < 8:
        return "Tell me what to change — “upgrade yourself so the sidebar remembers my last page”."

    result = propose(AURA_ROOT, request, scope="self")
    if not result.get("ok"):
        return f"I couldn't write that one: {result.get('error', 'no idea why')}"
    files = ", ".join(c["path"] for c in result["changes"])
    return (f"Written. {result.get('why') or 'Here it is.'} — {files}. "
            f"Read the diff in Upgrade, then say “apply it”.")
