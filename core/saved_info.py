"""
Saved Info — the links, PDFs and files you share with AURA.

Share a link in chat, or drop a PDF on the dock, and AURA:

1. saves it — one row per URL, so sharing the same link again refreshes it
   instead of piling up duplicates;
2. scans it — fetches the page (or GitHub README, or YouTube title), reads the
   PDF, pulls the text out;
3. files it — a title, a short summary, key points and tags, written by a
   small free model (a heuristic summary stands in when no model answers);
4. remembers it — later turns that mention "that pdf" or the item's title get
   its summary and a relevant excerpt as context, and the Saved Info page lists
   everything with Open / Ask AURA.

Scans run on worker threads and publish every state change through a sink
(the server broadcasts it as {"type": "saved"}), so the page fills in live.
Nothing here raises into the chat turn: a scan that fails leaves an item with
status "error" and a readable reason, and the link itself is still saved.
"""

from __future__ import annotations

import base64
import datetime
import io
import ipaddress
import json
import os
import re
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from memory import store

FILES_DIR = os.path.join(os.path.dirname(store.DB_PATH), "saved_files")

MAX_FETCH_BYTES = 15 * 1024 * 1024     # a page or remote PDF
MAX_UPLOAD_BYTES = 25 * 1024 * 1024    # a file dropped on the dock
MAX_CONTENT_CHARS = 60_000             # extracted text kept per item
SUMMARY_INPUT_CHARS = 8_000            # what the summariser reads (free-tier TPM)
FETCH_TIMEOUT = 12
MAX_LINKS_PER_MESSAGE = 3

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 AURA/3")

_DDL = """
    CREATE TABLE IF NOT EXISTS saved_info (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        kind        TEXT NOT NULL,
        title       TEXT NOT NULL DEFAULT '',
        url         TEXT DEFAULT '',
        file_name   TEXT DEFAULT '',
        file_path   TEXT DEFAULT '',
        mime        TEXT DEFAULT '',
        size        INTEGER DEFAULT 0,
        source      TEXT DEFAULT '',
        summary     TEXT DEFAULT '',
        key_points  TEXT DEFAULT '[]',
        tags        TEXT DEFAULT '',
        content     TEXT DEFAULT '',
        status      TEXT DEFAULT 'scanning',
        error       TEXT DEFAULT '',
        origin      TEXT DEFAULT 'chat',
        pinned      INTEGER DEFAULT 0,
        created_at  TEXT,
        updated_at  TEXT,
        opened_at   TEXT
    )
"""
_COLS = ("id, kind, title, url, file_name, file_path, mime, size, source, summary, "
         "key_points, tags, content, status, error, origin, pinned, created_at, "
         "updated_at, opened_at")

_ready = False
_sink: Optional[Callable[[dict], None]] = None


def set_sink(fn: Callable[[dict], None]) -> None:
    global _sink
    _sink = fn


def _publish(kind: str, item: dict | None = None, item_id: int | None = None) -> None:
    if _sink is None:
        return
    try:
        _sink({"kind": kind, "item": item, "id": item_id if item_id is not None else (item or {}).get("id")})
    except Exception:  # noqa: BLE001 — a dead socket must never break a scan
        pass


_quiet = threading.local()


def _activity(text: str) -> None:
    # Background scans (page / dock uploads) stay off the core's status line:
    # nothing ends a chat turn after them, so the line would never clear.
    if getattr(_quiet, "on", False):
        return
    try:
        from core import activity
        activity.emit(text, "memory")
    except Exception:  # noqa: BLE001
        pass


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _conn():
    global _ready
    conn = store._connect()
    if not _ready:
        conn.execute(_DDL)
        conn.commit()
        os.makedirs(FILES_DIR, exist_ok=True)
        _ready = True
    return conn


# ── rows ────────────────────────────────────────────────────────────────────

def _row(r, with_content: bool = False) -> dict:
    (iid, kind, title, url, file_name, file_path, mime, size, source, summary,
     key_points, tags, content, status, error, origin, pinned, created_at,
     updated_at, opened_at) = r
    try:
        points = json.loads(key_points or "[]")
        if not isinstance(points, list):
            points = []
    except Exception:  # noqa: BLE001
        points = []
    content = content or ""
    item = {
        "id": iid, "kind": kind, "title": title or (url or file_name or "Untitled"),
        "url": url or "", "file_name": file_name or "", "mime": mime or "",
        "size": size or 0, "source": source or "", "summary": summary or "",
        "key_points": [str(p) for p in points][:8],
        "tags": [t.strip() for t in (tags or "").split(",") if t.strip()],
        "status": status or "ready", "error": error or "", "origin": origin or "chat",
        "pinned": bool(pinned), "created_at": created_at, "updated_at": updated_at,
        "opened_at": opened_at, "has_file": bool(file_path),
        "content_chars": len(content),
        "excerpt": _excerpt(content, 360),
    }
    if with_content:
        item["content"] = content[:20_000]
    return item


def _excerpt(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _fetch_row(conn, item_id: int):
    return conn.execute(f"SELECT {_COLS} FROM saved_info WHERE id=?", (item_id,)).fetchone()


def get_item(item_id: int, with_content: bool = False) -> dict | None:
    conn = _conn()
    try:
        r = _fetch_row(conn, item_id)
        return _row(r, with_content) if r else None
    finally:
        conn.close()


def list_items(kind: str | None = None, limit: int = 300) -> list[dict]:
    conn = _conn()
    try:
        if kind:
            rows = conn.execute(
                f"SELECT {_COLS} FROM saved_info WHERE kind=? ORDER BY pinned DESC, id DESC LIMIT ?",
                (kind, limit)).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLS} FROM saved_info ORDER BY pinned DESC, id DESC LIMIT ?",
                (limit,)).fetchall()
        return [_row(r) for r in rows]
    finally:
        conn.close()


def _update(item_id: int, **fields) -> dict | None:
    if not fields:
        return get_item(item_id)
    fields["updated_at"] = _now()
    if "key_points" in fields and not isinstance(fields["key_points"], str):
        fields["key_points"] = json.dumps(list(fields["key_points"])[:8])
    if "tags" in fields and not isinstance(fields["tags"], str):
        fields["tags"] = ",".join(str(t).strip().lower() for t in fields["tags"] if str(t).strip())[:300]
    if "content" in fields:
        fields["content"] = (fields["content"] or "")[:MAX_CONTENT_CHARS]
    cols = ", ".join(f"{k}=?" for k in fields)
    conn = _conn()
    try:
        conn.execute(f"UPDATE saved_info SET {cols} WHERE id=?", (*fields.values(), item_id))
        conn.commit()
        r = _fetch_row(conn, item_id)
        return _row(r) if r else None
    finally:
        conn.close()


def update_item(item_id: int, title: str | None = None, pinned: bool | None = None,
                tags: list | None = None) -> dict | None:
    patch: dict = {}
    if title is not None and title.strip():
        patch["title"] = title.strip()[:200]
    if pinned is not None:
        patch["pinned"] = 1 if pinned else 0
    if tags is not None:
        patch["tags"] = tags
    item = _update(item_id, **patch)
    if item:
        _publish("update", item)
    return item


def mark_opened(item_id: int) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE saved_info SET opened_at=? WHERE id=?", (_now(), item_id))
        conn.commit()
    finally:
        conn.close()


def delete_item(item_id: int) -> bool:
    conn = _conn()
    try:
        r = conn.execute("SELECT file_path FROM saved_info WHERE id=?", (item_id,)).fetchone()
        if not r:
            return False
        conn.execute("DELETE FROM saved_info WHERE id=?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    path = _abs_file(r[0] or "")
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    _publish("delete", item_id=item_id)
    return True


def file_for(item_id: int) -> tuple[str, str, str] | None:
    """(absolute path, download name, mime) of an item's stored file."""
    conn = _conn()
    try:
        r = conn.execute("SELECT file_path, file_name, mime FROM saved_info WHERE id=?",
                         (item_id,)).fetchone()
    finally:
        conn.close()
    if not r or not r[0]:
        return None
    path = _abs_file(r[0])
    if not path or not os.path.isfile(path):
        return None
    return path, r[1] or os.path.basename(path), r[2] or "application/octet-stream"


def _abs_file(rel: str) -> str:
    """Resolve a stored file name inside FILES_DIR — never outside it."""
    if not rel:
        return ""
    base = os.path.realpath(FILES_DIR)
    path = os.path.realpath(os.path.join(base, os.path.basename(rel)))
    return path if path.startswith(base + os.sep) else ""


def _write_file(item_id: int, name: str, data: bytes) -> str:
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", name or "file").strip(" .")[:120] or "file"
    rel = f"{item_id}-{safe}"
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(os.path.join(FILES_DIR, rel), "wb") as fh:
        fh.write(data)
    return rel


# ── finding links in a message ──────────────────────────────────────────────

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'`]+")
_TRAIL = ".,;:!?)]}>'\"*_"


def extract_urls(text: str) -> list[str]:
    """Web links in a message, normalised to https and de-duplicated. Local
    and private-network addresses are skipped: "save" must never turn into
    AURA poking at her own API or the router's admin page."""
    out: list[str] = []
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(_TRAIL)
        # a markdown link's closing paren belongs to the markdown, not the URL
        if url.count("(") < url.count(")"):
            url = url.rstrip(")")
        if url.lower().startswith("www."):
            url = "https://" + url
        if _is_public(url) and url not in out:
            out.append(url)
    return out


def _is_public(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host or "." not in host and host != "localhost":
        return False
    if host == "localhost" or host.endswith(".local") or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return True


_FILLER = set("""
save saved this that it its link links pls please plz aura hey hi hello yo ok okay
check out look at read here store keep bookmark for later me my the a an and to
into info page article pdf file doc document remember add these those one thanks
shared sharing sent attached attaching upload uploaded
thx in on is go through scan have can you u quick real just also btw see found
cool nice interesting worth
""".split())


def is_bare_share(text: str, urls: list[str] | None = None, names: list[str] | None = None) -> bool:
    """True when the message is only the shared thing (plus filler like "save
    this"), so the right reply is "saved — here's what it is" rather than a
    model turn trying to answer a question nobody asked. `names` are attached
    file names — "Shared paper.pdf" is the dock's own text for a bare upload."""
    rest = text or ""
    for u in urls if urls is not None else extract_urls(text):
        rest = rest.replace(u, " ")
    for n in names or []:
        if n:
            rest = rest.replace(n, " ")
    rest = _URL_RE.sub(" ", rest)
    words = [w for w in re.findall(r"[a-zA-Z']+", rest.lower()) if w not in _FILLER]
    return len(words) == 0 and "?" not in rest


# ── saving ──────────────────────────────────────────────────────────────────

def _find_by_url(url: str) -> int | None:
    conn = _conn()
    try:
        r = conn.execute("SELECT id FROM saved_info WHERE url=? ORDER BY id DESC LIMIT 1",
                         (url,)).fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def _guess_kind(url: str) -> str:
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.")
    if host == "github.com" and len([p for p in u.path.split("/") if p]) >= 2:
        return "github"
    if host in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
        return "video"
    if u.path.lower().endswith(".pdf"):
        return "pdf"
    return "link"


def _source(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def save_link(url: str, origin: str = "chat") -> dict:
    """Insert (or refresh) the row for a link. Returns the item, status
    'scanning' — call scan() to fill it in."""
    existing = _find_by_url(url)
    if existing:
        item = _update(existing, status="scanning", error="")
        _publish("update", item)
        return item or {}
    conn = _conn()
    try:
        now = _now()
        cur = conn.execute(
            "INSERT INTO saved_info (kind, title, url, source, status, origin, created_at, updated_at) "
            "VALUES (?,?,?,?, 'scanning', ?, ?, ?)",
            (_guess_kind(url), _source(url) or url, url, _source(url), origin, now, now))
        conn.commit()
        item = _row(_fetch_row(conn, cur.lastrowid))
    finally:
        conn.close()
    _publish("update", item)
    return item


_EXT_KIND = {
    ".pdf": "pdf", ".docx": "doc", ".txt": "doc", ".md": "doc", ".markdown": "doc",
    ".csv": "doc", ".json": "doc", ".log": "doc", ".html": "doc", ".htm": "doc",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
}
_TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".py", ".js", ".ts",
             ".tsx", ".jsx", ".css", ".yml", ".yaml", ".toml", ".ini", ".sql", ".sh"}


def save_upload(name: str, data: bytes, mime: str = "", origin: str = "upload") -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"that file is {len(data) // (1024 * 1024)} MB — the limit is "
                         f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    ext = os.path.splitext(name or "")[1].lower()
    kind = _EXT_KIND.get(ext) or ("doc" if ext in _TEXT_EXT else "file")
    if not ext and mime == "application/pdf":
        kind = "pdf"
    conn = _conn()
    try:
        now = _now()
        cur = conn.execute(
            "INSERT INTO saved_info (kind, title, file_name, mime, size, source, status, origin, "
            "created_at, updated_at) VALUES (?,?,?,?,?, 'upload', 'scanning', ?, ?, ?)",
            (kind, os.path.splitext(name)[0] or name, name, mime, len(data), origin, now, now))
        iid = cur.lastrowid
        rel = _write_file(iid, name, data)
        conn.execute("UPDATE saved_info SET file_path=? WHERE id=?", (rel, iid))
        conn.commit()
        item = _row(_fetch_row(conn, iid))
    finally:
        conn.close()
    _publish("update", item)
    return item


# ── scanning ────────────────────────────────────────────────────────────────

class _ScanError(Exception):
    pass


def _get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": _UA, "Accept-Language": "en;q=0.9"}
    headers.update(kw.pop("headers", {}))
    return requests.get(url, headers=headers, timeout=kw.pop("timeout", FETCH_TIMEOUT), **kw)


def _download(url: str) -> tuple[str, str, bytes]:
    """(final url, content type, body) — streamed with a hard size cap."""
    try:
        with _get(url, stream=True, allow_redirects=True) as r:
            if r.status_code >= 400:
                raise _ScanError(f"the site answered {r.status_code}")
            ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            buf = bytearray()
            for chunk in r.iter_content(65536):
                buf += chunk
                if len(buf) > MAX_FETCH_BYTES:
                    raise _ScanError("it's bigger than 15 MB")
            return r.url, ctype, bytes(buf)
    except requests.Timeout as e:
        raise _ScanError("the site took too long to answer") from e
    except requests.RequestException as e:
        raise _ScanError(f"couldn't reach it ({type(e).__name__})") from e


def _clean_text(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1 and out:
                out.append("")
            continue
        blank = 0
        out.append(re.sub(r"[ \t]+", " ", ln))
    return "\n".join(out).strip()[:MAX_CONTENT_CHARS]


def _html_extract(raw: bytes) -> tuple[str, str, str]:
    """(title, description, readable text) from an HTML page."""
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:  # noqa: BLE001 — lxml missing or choking: stdlib parser
        soup = BeautifulSoup(raw, "html.parser")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    title = meta("og:title", "twitter:title") or (soup.title.get_text(strip=True) if soup.title else "")
    desc = meta("og:description", "description", "twitter:description")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav",
                   "footer", "header", "aside", "button", "template"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    text = root.get_text("\n", strip=True)
    return title[:200], desc[:600], _clean_text(text)


def _pdf_extract(data: bytes) -> tuple[str, str, int]:
    """(title, text, pages) from PDF bytes."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise _ScanError("PDF reading needs pypdf — pip install pypdf") from e
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:  # noqa: BLE001
                raise _ScanError("the PDF is password-protected") from e
        title = ""
        try:
            title = str((reader.metadata or {}).get("/Title") or "").strip()
        except Exception:  # noqa: BLE001
            title = ""
        parts, total = [], 0
        for page in reader.pages[:300]:
            try:
                t = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — one bad page shouldn't lose the rest
                t = ""
            parts.append(t)
            total += len(t)
            if total > MAX_CONTENT_CHARS:
                break
        return title[:200], _clean_text("\n\n".join(parts)), len(reader.pages)
    except _ScanError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _ScanError(f"couldn't read the PDF ({type(e).__name__})") from e


def _docx_extract(data: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as e:
        raise _ScanError("Word files need python-docx") from e
    try:
        d = docx.Document(io.BytesIO(data))
        return _clean_text("\n".join(p.text for p in d.paragraphs))
    except Exception as e:  # noqa: BLE001
        raise _ScanError(f"couldn't read the Word file ({type(e).__name__})") from e


def _github(url: str) -> dict:
    """Repo metadata + README (or the raw file for a /blob/ link)."""
    u = urlparse(url)
    parts = [p for p in u.path.split("/") if p]
    owner, repo = parts[0], parts[1].removesuffix(".git")
    gh = {"Accept": "application/vnd.github+json", "User-Agent": "AURA"}
    if len(parts) > 4 and parts[2] == "blob":
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{parts[3]}/{'/'.join(parts[4:])}"
        r = _get(raw, headers={"User-Agent": "AURA"})
        if r.status_code >= 400:
            raise _ScanError(f"GitHub answered {r.status_code} for that file")
        return {"title": f"{owner}/{repo} — {parts[-1]}", "desc": "",
                "text": _clean_text(r.text), "tags": [parts[-1].rsplit(".", 1)[-1]]}
    meta = _get(f"https://api.github.com/repos/{owner}/{repo}", headers=gh)
    if meta.status_code == 404:
        raise _ScanError("GitHub says that repo doesn't exist (or it's private)")
    if meta.status_code >= 400:
        raise _ScanError(f"GitHub answered {meta.status_code}")
    m = meta.json()
    readme = ""
    rr = _get(f"https://api.github.com/repos/{owner}/{repo}/readme",
              headers={**gh, "Accept": "application/vnd.github.raw"})
    if rr.status_code < 400:
        readme = rr.text
    facts = []
    if m.get("language"):
        facts.append(m["language"])
    if m.get("stargazers_count") is not None:
        facts.append(f"★ {m['stargazers_count']:,}")
    if m.get("license") and m["license"].get("spdx_id"):
        facts.append(m["license"]["spdx_id"])
    head = f"{m.get('full_name') or owner + '/' + repo} — {m.get('description') or ''}\n{' · '.join(facts)}"
    return {"title": m.get("full_name") or f"{owner}/{repo}", "desc": m.get("description") or "",
            "text": _clean_text(head + "\n\n" + readme),
            "tags": [t for t in (m.get("topics") or [])][:5] + ([m["language"].lower()] if m.get("language") else [])}


def _youtube(url: str) -> dict:
    title, author = "", ""
    try:
        r = _get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
        if r.status_code < 400:
            j = r.json()
            title, author = j.get("title") or "", j.get("author_name") or ""
    except Exception:  # noqa: BLE001
        pass
    desc = ""
    try:
        _, _, raw = _download(url)
        _, desc, _ = _html_extract(raw)
    except _ScanError:
        pass
    text = f"{title}\nby {author}\n\n{desc}".strip()
    return {"title": title or "YouTube video", "desc": desc, "text": text,
            "tags": ["video"] + ([author.lower()] if author else [])}


def _scan_link(item: dict) -> dict:
    url = item["url"]
    kind = _guess_kind(url)
    if kind == "github":
        g = _github(url)
        return {"kind": "github", **g}
    if kind == "video":
        return {"kind": "video", **_youtube(url)}
    final, ctype, raw = _download(url)
    if ctype == "application/pdf" or raw[:5] == b"%PDF-":
        title, text, pages = _pdf_extract(raw)
        name = os.path.basename(urlparse(final).path) or "document.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        rel = _write_file(item["id"], name, raw)
        return {"kind": "pdf", "title": title or os.path.splitext(name)[0], "desc": "",
                "text": text, "file_path": rel, "file_name": name,
                "mime": "application/pdf", "size": len(raw), "pages": pages}
    if ctype.startswith("text/html") or ctype in ("application/xhtml+xml", "") or raw.lstrip()[:1] == b"<":
        title, desc, text = _html_extract(raw)
        return {"kind": "link", "title": title, "desc": desc, "text": text}
    if ctype.startswith("text/") or ctype in ("application/json", "application/xml"):
        return {"kind": "link", "title": "", "desc": "",
                "text": _clean_text(raw.decode("utf-8", errors="replace"))}
    raise _ScanError(f"it's a {ctype or 'binary'} file, not something I can read")


def _scan_upload(item: dict) -> dict:
    found = file_for(item["id"])
    if not found:
        raise _ScanError("the uploaded file went missing")
    path, name, mime = found
    with open(path, "rb") as fh:
        data = fh.read()
    ext = os.path.splitext(name)[1].lower()
    if item["kind"] == "pdf" or data[:5] == b"%PDF-":
        title, text, pages = _pdf_extract(data)
        return {"kind": "pdf", "title": title, "desc": "", "text": text, "pages": pages}
    if ext == ".docx":
        return {"kind": "doc", "title": "", "desc": "", "text": _docx_extract(data)}
    if item["kind"] == "image":
        return {"kind": "image", "title": "", "desc": _describe_image(data), "text": ""}
    if ext in _TEXT_EXT or ext in (".html", ".htm") or mime.startswith("text/"):
        body = data.decode("utf-8", errors="replace")
        if ext in (".html", ".htm"):
            title, desc, text = _html_extract(data)
            return {"kind": "doc", "title": title, "desc": desc, "text": text}
        return {"kind": "doc", "title": "", "desc": "", "text": _clean_text(body)}
    raise _ScanError("I can keep this file, but I can't read what's inside it")


def _describe_image(data: bytes) -> str:
    try:
        from core.ai_router import call_vision
        out = call_vision(
            "Describe this image for a personal knowledge vault in 2-3 plain sentences: "
            "what it shows and any text in it.",
            base64.b64encode(data).decode("ascii"), max_tokens=260, timeout=45)
        if out and out not in ("RATE_LIMIT", "CONNECTION_ERROR", "NO_VISION_KEY"):
            return out.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


_SUM_SYS = """You file things into a personal knowledge vault. Read the material and answer with ONE JSON object and nothing else:
{"title": "...", "summary": "...", "key_points": ["..."], "tags": ["..."]}
- title: the real name of the thing, max 80 characters. Keep the original title if it is already good.
- summary: 2-3 plain sentences — what it is and why someone would keep it. No hype. Never start with "This article" or "This document".
- key_points: 3-5 short facts worth remembering.
- tags: 3-6 lowercase topic words.
Use only facts that are in the material."""


def _summarise(title: str, desc: str, text: str, where: str) -> dict:
    """{title, summary, key_points, tags} from a free model, or a heuristic
    stand-in when every model is busy. Never raises."""
    material = "\n\n".join(p for p in (
        f"TITLE: {title}" if title else "", f"FROM: {where}" if where else "",
        f"DESCRIPTION: {desc}" if desc else "", text[:SUMMARY_INPUT_CHARS]) if p)
    if len(material.strip()) >= 40:
        try:
            from core.ai_router import GROQ_MODEL_LIGHT, call_groq_raw
            _activity("Summarising what I read…")
            reply = call_groq_raw(material, _SUM_SYS, max_tokens=700, temperature=0.2,
                                  model=GROQ_MODEL_LIGHT)
            parsed = _parse_json(reply)
            if parsed and str(parsed.get("summary") or "").strip():
                return {
                    "title": str(parsed.get("title") or title or "").strip()[:120],
                    "summary": str(parsed["summary"]).strip()[:900],
                    "key_points": [str(p).strip() for p in (parsed.get("key_points") or [])
                                   if str(p).strip()][:5],
                    "tags": [str(t).strip().lower() for t in (parsed.get("tags") or [])
                             if str(t).strip()][:6],
                }
        except Exception as e:  # noqa: BLE001
            print(f"[AURA saved] summary skipped: {e}")
    return {"title": title, "summary": _heuristic_summary(desc, text),
            "key_points": [], "tags": []}


def _parse_json(reply: str) -> dict | None:
    if not reply or reply in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return None
    s, e = reply.find("{"), reply.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        out = json.loads(reply[s:e + 1])
        return out if isinstance(out, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _heuristic_summary(desc: str, text: str) -> str:
    if desc and len(desc) > 30:
        return _excerpt(desc, 320)
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    picked = [s for s in sentences if 30 <= len(s) <= 400][:2]
    return _excerpt(" ".join(picked), 320) if picked else ""


_scan_locks: dict[int, threading.Lock] = {}


def scan(item_id: int) -> dict | None:
    """Read and summarise one item, in place. Safe to call from any thread;
    concurrent scans of the same item collapse into one."""
    lock = _scan_locks.setdefault(item_id, threading.Lock())
    if not lock.acquire(blocking=False):
        lock.acquire()          # someone else is scanning it — wait for their result
        lock.release()
        return get_item(item_id)
    try:
        item = get_item(item_id)
        if not item:
            return None
        where = item["url"] or item["file_name"]
        _activity(f"Reading {item['source'] if item['url'] else item['file_name']}…")
        try:
            got = _scan_link(item) if item["url"] else _scan_upload(item)
        except _ScanError as e:
            done = _update(item_id, status="error", error=str(e))
            _publish("update", done)
            return done
        except Exception as e:  # noqa: BLE001
            print(f"[AURA saved] scan crashed for #{item_id}: {e}")
            done = _update(item_id, status="error", error=f"scan failed ({type(e).__name__})")
            _publish("update", done)
            return done

        text = got.get("text") or ""
        desc = got.get("desc") or ""
        note = ""
        if got.get("kind") == "pdf" and len(text) < 40:
            note = "This PDF has no selectable text — it's probably a scan of paper pages."
        s = _summarise(got.get("title") or "", desc, text or desc, where)
        summary = s["summary"] or note or (
            "Saved. There wasn't much readable text to summarise." if not desc else _excerpt(desc, 300))
        fields = {
            "kind": got.get("kind") or item["kind"],
            "title": (s["title"] or got.get("title") or item["title"])[:200],
            "summary": summary,
            "key_points": s["key_points"],
            "tags": s["tags"] or got.get("tags") or [],
            "content": text or desc,
            "status": "ready", "error": "",
        }
        for k in ("file_path", "file_name", "mime", "size"):
            if got.get(k):
                fields[k] = got[k]
        done = _update(item_id, **fields)
        _publish("update", done)
        return done
    finally:
        lock.release()
        _scan_locks.pop(item_id, None)


def rescan(item_id: int) -> dict | None:
    """Mark an item as being read again and re-scan it in the background."""
    item = _update(item_id, status="scanning", error="")
    if item:
        _publish("update", item)
        scan_async(item_id)
    return item


def scan_async(item_id: int) -> None:
    def run() -> None:
        _quiet.on = True
        scan(item_id)
    threading.Thread(target=run, daemon=True, name=f"saved-scan-{item_id}").start()


def capture(urls: list[str], ids: list[int] | None = None, wait: float = 25.0,
            origin: str = "chat") -> list[dict]:
    """Save + scan the links in a message and pick up already-uploaded items,
    waiting up to `wait` seconds for scans so the reply can use them. Slow
    scans keep going in the background and update the page when they land."""
    items: list[dict] = []
    threads: list[threading.Thread] = []
    for url in urls[:MAX_LINKS_PER_MESSAGE]:
        it = save_link(url, origin=origin)
        if not it:
            continue
        items.append(it)
        t = threading.Thread(target=scan, args=(it["id"],), daemon=True)
        t.start()
        threads.append(t)
    for iid in ids or []:
        it = get_item(iid)
        if not it:
            continue
        items.append(it)
        if it["status"] == "scanning":
            t = threading.Thread(target=scan, args=(iid,), daemon=True)
            t.start()
            threads.append(t)
    deadline = time.time() + wait
    for t in threads:
        t.join(max(0.0, deadline - time.time()))
    fresh = [get_item(it["id"]) or it for it in items]
    if fresh:
        _note_recent([it["id"] for it in fresh])
    return fresh


def share_reply(items: list[dict]) -> str:
    """What AURA says when you share something without asking anything."""
    if not items:
        return "I couldn't find anything to save in that."

    def line(it: dict) -> str:
        name = it["title"] or it["url"] or it["file_name"]
        if it["status"] == "ready":
            return f"**{name}** — {it['summary'] or 'saved.'}"
        if it["status"] == "error":
            return f"**{name}** — saved, but I couldn't read it: {it['error']}."
        return f"**{name}** — saved; still reading it, it'll fill in on the Saved Info page."

    if len(items) == 1:
        it = items[0]
        if it["status"] == "ready":
            return f"Saved to Saved Info: {line(it)}"
        return f"Got it. {line(it)}"
    return "Saved to Saved Info:\n" + "\n".join(f"- {line(it)}" for it in items)


# ── context for the chat ────────────────────────────────────────────────────
# Two paths into a turn's prompt:
#   arm_turn()      — the message itself shared something (or "Ask AURA" on the
#                     page): its material is attached to THIS turn, once.
#   context_for()   — a later message refers back ("that pdf", "the repo I
#                     sent", or an item's own title): matching items come in.

_turn_lock = threading.Lock()
_turn: dict = {"ids": [], "at": 0.0}
_recent: dict = {"ids": [], "at": 0.0}
_TURN_TTL = 120.0
_RECENT_TTL = 15 * 60.0


def arm_turn(ids: list[int]) -> None:
    with _turn_lock:
        _turn["ids"] = [int(i) for i in ids][:5]
        _turn["at"] = time.time()


def _note_recent(ids: list[int]) -> None:
    with _turn_lock:
        _recent["ids"] = [int(i) for i in ids][:5]
        _recent["at"] = time.time()


def consume_turn_block() -> str:
    with _turn_lock:
        ids, at = list(_turn["ids"]), _turn["at"]
        _turn["ids"], _turn["at"] = [], 0.0
    if not ids or time.time() - at > _TURN_TTL:
        return ""
    items = [get_item(i, with_content=True) for i in ids]
    items = [it for it in items if it]
    if not items:
        return ""
    budget = max(1500, 7000 // len(items))
    blocks = [_material(it, budget) for it in items]
    return ("WHAT THEY SHARED (you saved it to their Saved Info and read it — "
            "answer from this material, don't guess. A room's teaching style is "
            "for the room's own subject; if this material is about something "
            "else, just answer about it plainly):\n" + "\n\n".join(blocks))


def _material(it: dict, budget: int, query: str = "") -> str:
    head = f'[Saved Info #{it["id"]} · {it["kind"]}] "{it["title"]}"'
    if it["url"]:
        head += f" — {it['url']}"
    elif it["file_name"]:
        head += f" — file {it['file_name']}"
    parts = [head]
    if it["status"] == "error":
        parts.append(f"(Couldn't read it: {it['error']})")
    if it["summary"]:
        parts.append("Summary: " + it["summary"])
    if it["key_points"]:
        parts.append("Key points: " + " | ".join(it["key_points"]))
    content = it.get("content") or ""
    if content:
        ex = _relevant_excerpt(content, query, budget) if query else content[:budget]
        parts.append("Text:\n" + ex)
    return "\n".join(parts)


_REF_RE = re.compile(
    r"(?i)\b(saved info|saved|bookmark|the (pdf|link|article|paper|doc|document|file|repo|"
    r"video|page|post|site|website|readme)|that (pdf|link|article|paper|doc|document|file|"
    r"repo|video|page|post|site)|(i|we) (shared|sent|saved|gave you|dropped)|key points|"
    r"takeaways|tl;?dr|summar(y|ise|ize)|what('?s| is| was) (it|this|that) about|"
    r"tell me more|more about (it|this|that)|in (it|there)|from (it|that))\b")

_STOP = set("""
the a an and or but is are was were be to of in on at for with from by this that it its
what whats how why who which about tell me my your you i we our they them do does did can
could would should please pls aura saved info link pdf file doc article page paper repo video
""".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]{2,}", (text or "").lower()) if w not in _STOP}


def search(query: str, limit: int = 5) -> list[dict]:
    """Items ranked by how well they match the query — title and tags weigh
    most, then summary, then body text."""
    q = _words(query)
    if not q:
        return []
    conn = _conn()
    try:
        rows = conn.execute(f"SELECT {_COLS} FROM saved_info ORDER BY id DESC LIMIT 400").fetchall()
    finally:
        conn.close()
    scored = []
    for r in rows:
        it = _row(r, with_content=True)
        title = _words(it["title"])
        tags = set(t.lower() for t in it["tags"])
        summ = _words(it["summary"] + " " + " ".join(it["key_points"]))
        body = (it.get("content") or "").lower()
        score = 0.0
        for w in q:
            if w in title:
                score += 3
            if w in tags:
                score += 2.5
            if w in summ:
                score += 1.5
            elif w in body:
                score += 0.6
        if it["source"] and it["source"].split(".")[0] in q:
            score += 2
        if score >= 2.5:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]]


def context_for(query: str) -> str:
    """Background block for a turn that refers back to saved things, or ""."""
    q = (query or "").strip()
    if len(q) < 4:
        return ""
    hits = search(q, limit=3)
    refers = bool(_REF_RE.search(q))
    if not hits and refers:
        with _turn_lock:
            ids, at = list(_recent["ids"]), _recent["at"]
        if ids and time.time() - at < _RECENT_TTL:
            hits = [it for it in (get_item(i, with_content=True) for i in ids) if it]
    if not hits:
        return ""
    # A title match alone is enough; a vague reference needs the recent share.
    blocks = [_material(it, 1800, query=q) for it in hits]
    return ("FROM THEIR SAVED INFO (things they shared with you earlier — use it if the "
            "message is about them; a room's teaching style is for the room's own "
            "subject, so answer about this material plainly):\n" + "\n\n".join(blocks))


def _relevant_excerpt(content: str, query: str, budget: int) -> str:
    """The parts of `content` around the query's words, up to `budget` chars."""
    words = [w for w in _words(query) if len(w) > 3]
    if not words or len(content) <= budget:
        return content[:budget]
    low = content.lower()
    spans: list[tuple[int, int]] = []
    for w in words:
        start = 0
        while len(spans) < 12:
            i = low.find(w, start)
            if i < 0:
                break
            spans.append((max(0, i - 300), min(len(content), i + 300)))
            start = i + len(w)
    if not spans:
        return content[:budget]
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, used = [], 0
    head = content[:400]
    out.append(head)
    used += len(head)
    for s, e in merged:
        if used >= budget:
            break
        piece = content[s:e]
        out.append("…" + piece[: budget - used])
        used += len(piece)
    return "\n".join(out)


def tool_lookup(query: str = "", **_) -> str:
    """For core/tools: what's in Saved Info that matches, with summaries."""
    q = (query or "").strip()
    items = search(q, limit=4) if q else list_items(limit=6)
    if not items:
        return "(nothing in Saved Info matches)"
    out = []
    for it in items:
        full = get_item(it["id"], with_content=True) or it
        out.append(_material(full, 500, query=q))
    return "\n\n".join(out)
