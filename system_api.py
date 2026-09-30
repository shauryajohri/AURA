"""
system_api.py — the routes for AURA changing itself and staying in step.

Three groups, mounted as one router so a failure here can't take the brain
down with it:

    /api/upgrade/*   AURA proposing changes to its own source, and to any
                     project open in the Domain. Nothing is written until a
                     proposal is approved, and anything applied can be rolled
                     back.
    /api/system/*    resetting AURA, scope by scope.
    /api/sources/*   the GitHub link, document folders and pages AURA keeps
                     synced, and the repos it can pull down to work on.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

AURA_ROOT = os.path.dirname(os.path.abspath(__file__))


def _err(msg: str) -> dict[str, Any]:
    return {"ok": False, "error": msg}


# ════════════════════════════════════════════════════════════════════════════
# Upgrades — AURA writing code, its own included
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/upgrade/proposals")
async def upgrade_list(scope: str = "", root: str = "", limit: int = 50) -> dict[str, Any]:
    from core import patcher
    return {"ok": True, "proposals": patcher.list_proposals(scope, root, limit)}


@router.get("/api/upgrade/proposals/{pid}")
async def upgrade_get(pid: str) -> dict[str, Any]:
    from core import patcher
    p = patcher.get(pid)
    return {"ok": bool(p), "proposal": p}


@router.post("/api/upgrade/propose")
async def upgrade_propose(req: Request) -> dict[str, Any]:
    """Ask for a change. `scope: "self"` points at AURA's own source; anything
    else needs a `root`. Returns the proposal — it is NOT applied."""
    from core import patcher
    body = await req.json()
    request_text = str(body.get("request") or "").strip()
    if not request_text:
        return _err("tell me what to change")

    scope = str(body.get("scope") or "project")
    if scope == "self":
        root = AURA_ROOT
    else:
        root = str(body.get("root") or "").strip()
        if not root:
            return _err("which project?")
        if not os.path.isdir(root):
            return _err("that folder isn't there")

    hint = body.get("files") or body.get("hint") or []
    if isinstance(hint, str):
        hint = [hint]
    return patcher.propose(root, request_text, scope=scope,
                           hint=[str(h) for h in hint][:6],
                           label=str(body.get("label") or ""))


@router.post("/api/upgrade/proposals/{pid}/approve")
async def upgrade_approve(pid: str) -> dict[str, Any]:
    from core import patcher
    return patcher.approve(pid)


@router.post("/api/upgrade/proposals/{pid}/reject")
async def upgrade_reject(pid: str) -> dict[str, Any]:
    from core import patcher
    return patcher.reject(pid)


@router.post("/api/upgrade/proposals/{pid}/rollback")
async def upgrade_rollback(pid: str) -> dict[str, Any]:
    from core import patcher
    return patcher.rollback(pid)


@router.delete("/api/upgrade/proposals/{pid}")
async def upgrade_delete(pid: str) -> dict[str, Any]:
    from core import patcher
    return patcher.delete(pid)


@router.get("/api/upgrade/files")
async def upgrade_files(root: str = "", limit: int = 1200) -> dict[str, Any]:
    """The editable files under a tree — what the file picker lists."""
    from core import patcher
    target = root or AURA_ROOT
    if not os.path.isdir(target):
        return _err("that folder isn't there")
    return {"ok": True, "root": os.path.realpath(target),
            "files": patcher.file_tree(target, limit)}


@router.get("/api/upgrade/file")
async def upgrade_file(path: str, root: str = "") -> dict[str, Any]:
    from core import patcher
    target = root or AURA_ROOT
    body = patcher.read_file(target, path)
    if body is None:
        return _err("can't read that file")
    return {"ok": True, "path": path, "content": body}


# ════════════════════════════════════════════════════════════════════════════
# Reset
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/system/reset")
async def reset_scopes() -> dict[str, Any]:
    from core import system_reset
    return {"ok": True, "scopes": system_reset.scopes()}


@router.post("/api/system/reset")
async def reset_run(req: Request) -> dict[str, Any]:
    """Clear the named scopes. `confirm` must be the word RESET — a stray
    POST must not be able to wipe someone's memory."""
    from core import system_reset
    body = await req.json()
    if str(body.get("confirm") or "").strip().upper() != "RESET":
        return _err("type RESET to confirm")
    scopes = body.get("scopes") or []
    if not isinstance(scopes, list):
        return _err("nothing was selected")
    return system_reset.reset([str(s) for s in scopes])


# ════════════════════════════════════════════════════════════════════════════
# Sources
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/sources")
async def sources_list(room_id: int | None = None) -> dict[str, Any]:
    from core import sources
    return {"ok": True, "sources": sources.list_sources(room_id)}


@router.post("/api/sources")
async def sources_add(req: Request) -> dict[str, Any]:
    """Connect a GitHub link, a folder of documents, or a page. The first sync
    starts immediately, in the background."""
    from core import sources
    body = await req.json()
    raw = str(body.get("url") or body.get("path") or "").strip()
    if not raw:
        return _err("paste a link or a folder path")
    room = body.get("room_id")
    return sources.add(raw, label=str(body.get("label") or ""),
                       room_id=int(room) if room is not None else None,
                       auto_sync=bool(body.get("auto_sync", True)))


@router.patch("/api/sources/{source_id}")
async def sources_update(source_id: int, req: Request) -> dict[str, Any]:
    from core import sources
    body = await req.json()
    return sources.update(
        source_id,
        label=body.get("label"),
        room_id=body["room_id"] if "room_id" in body else "keep",
        auto_sync=body.get("auto_sync"),
    )


@router.delete("/api/sources/{source_id}")
async def sources_remove(source_id: int) -> dict[str, Any]:
    from core import sources
    return sources.remove(source_id)


@router.post("/api/sources/{source_id}/sync")
async def sources_sync(source_id: int) -> dict[str, Any]:
    from core import sources
    return sources.sync(source_id)


@router.post("/api/sources/sync")
async def sources_sync_all() -> dict[str, Any]:
    """What the app calls on open."""
    from core import sources
    sources.sync_all()
    return {"ok": True, "started": True}


@router.get("/api/sources/repos")
async def sources_repos() -> dict[str, Any]:
    from core import sources
    return {"ok": True, "repos": sources.repos()}


@router.post("/api/sources/{source_id}/clone")
async def sources_clone(source_id: int, req: Request) -> dict[str, Any]:
    """Bring a repo to disk so it can be opened, prompted and edited."""
    from core import sources
    body = await req.json()
    full_name = str(body.get("full_name") or "").strip()
    if not full_name or "/" not in full_name:
        return _err("which repo?")
    return sources.clone(source_id, full_name)
