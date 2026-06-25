# modules/project_context.py
"""
Lets AURA answer questions about its OWN codebase with real, grounded
content instead of guessing.

The problem this fixes: when you ask something like "which API can I
use for this project", the CODING intent used to route straight to a
generic LLM call with zero knowledge of your actual files — so it would
hallucinate a plausible-sounding but completely made-up answer (e.g. an
OpenWeatherMap tutorial that has nothing to do with AURA).

This module:
  1. Walks the project directory and chunks every .py file
  2. Embeds each chunk locally with sentence-transformers (no API key,
     no per-call cost, no network dependency)
  3. Caches the index to disk, only re-embedding files that changed
     (checked via mtime) so restarts are fast
  4. On a query, embeds it and returns the top matching chunks as
     labeled, truncated excerpts — or "" if nothing is relevant enough,
     so irrelevant noise never gets forced into unrelated questions

Usage from brain.py:
    from modules.project_context import get_relevant_context
    context_block = get_relevant_context(query)
    # context_block is "" if nothing relevant was found — safe to
    # always concatenate onto the prompt.
"""

import os
import re
import time
import pickle

PROJECT_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH     = os.path.join(PROJECT_ROOT, ".aura_index.pkl")
MODEL_NAME     = "all-MiniLM-L6-v2"   # small, fast, good enough for code+docs
RELEVANCE_MIN  = 0.35                  # cosine similarity floor — below this, don't inject anything
TOP_K          = 3                     # max chunks to inject per query
MAX_CHUNK_CHARS = 3000                 # cap per-chunk size before embedding/injecting
SKIP_DIRS      = {".git", "__pycache__", "venv", ".venv", "node_modules", ".idea", ".vscode"}

_model       = None
_model_error = ""
_index       = None   # list of {"file": str, "start_line": int, "text": str, "mtime": float, "vector": np.ndarray}


def _get_model():
    global _model, _model_error
    if _model is None and not _model_error:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            _model_error = str(e)
            print(f"[AURA ProjectContext] Embedding model unavailable: {e}")
    return _model


def _iter_py_files():
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                yield os.path.join(dirpath, fname)


def _chunk_file(path: str) -> list[dict]:
    """Split a file into chunks at function/class boundaries where
    possible, falling back to fixed-size blocks for everything else."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[AURA ProjectContext] Could not read {path}: {e}")
        return []

    chunks = []
    current = []
    start_line = 1

    def flush(end_line):
        if current:
            text = "".join(current).strip()
            if text:
                chunks.append({"start_line": start_line, "text": text[:MAX_CHUNK_CHARS]})

    for i, line in enumerate(lines, start=1):
        if re.match(r"^(def |class |async def )", line) and current:
            flush(i - 1)
            current = [line]
            start_line = i
        else:
            current.append(line)
        # hard cap so one giant function doesn't become one giant chunk
        if len("".join(current)) > MAX_CHUNK_CHARS:
            flush(i)
            current = []
            start_line = i + 1

    flush(len(lines))
    return chunks


def _build_or_update_index():
    """Rebuild the index, re-embedding only files whose mtime changed
    since the last run. Persists to disk afterward."""
    global _index
    model = _get_model()
    if model is None:
        return

    cached_by_file = {}
    if _index is None:
        _index = _load_cached_index()
    for entry in _index:
        cached_by_file.setdefault(entry["file"], []).append(entry)

    new_index = []
    for path in _iter_py_files():
        rel_path = os.path.relpath(path, PROJECT_ROOT)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue

        existing = cached_by_file.get(rel_path)
        if existing and existing[0]["mtime"] == mtime:
            new_index.extend(existing)
            continue

        chunks = _chunk_file(path)
        if not chunks:
            continue

        texts = [c["text"] for c in chunks]
        try:
            vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        except Exception as e:
            print(f"[AURA ProjectContext] Embedding failed for {rel_path}: {e}")
            continue

        for chunk, vector in zip(chunks, vectors):
            new_index.append({
                "file": rel_path,
                "start_line": chunk["start_line"],
                "text": chunk["text"],
                "mtime": mtime,
                "vector": vector,
            })

    _index = new_index
    _save_cached_index()
    print(f"[AURA ProjectContext] Index ready: {len(_index)} chunks across project")


def _load_cached_index() -> list:
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"[AURA ProjectContext] Could not load cached index: {e}")
    return []


def _save_cached_index():
    try:
        with open(INDEX_PATH, "wb") as f:
            pickle.dump(_index, f)
    except Exception as e:
        print(f"[AURA ProjectContext] Could not save index cache: {e}")


def _ensure_index():
    if _index is None:
        _build_or_update_index()


def get_relevant_context(query: str, top_k: int = TOP_K) -> str:
    """
    Returns a formatted block of the most relevant code excerpts for
    `query`, labeled by filename and line number. Returns "" if nothing
    clears the relevance threshold — safe to always call and concatenate.
    """
    model = _get_model()
    if model is None:
        return ""

    _ensure_index()
    if not _index:
        return ""

    try:
        import numpy as np
        query_vec = model.encode([query], convert_to_numpy=True, show_progress_bar=False)[0]

        scored = []
        for entry in _index:
            v = entry["vector"]
            denom = (np.linalg.norm(query_vec) * np.linalg.norm(v))
            sim = float(np.dot(query_vec, v) / denom) if denom else 0.0
            scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [(sim, e) for sim, e in scored[:top_k] if sim >= RELEVANCE_MIN]

        if not top:
            return ""

        blocks = []
        for sim, entry in top:
            blocks.append(
                f"--- {entry['file']} (line {entry['start_line']}, relevance {sim:.2f}) ---\n"
                f"{entry['text']}"
            )
        return "\n\n".join(blocks)

    except Exception as e:
        print(f"[AURA ProjectContext] Retrieval error: {e}")
        return ""


def rebuild_index():
    """Force a full index rebuild. Call this manually after large edits
    if you don't want to wait for the next query to pick up changes."""
    global _index
    _index = []
    _build_or_update_index()