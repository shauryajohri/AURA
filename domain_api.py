"""
domain_api.py
-------------
Every REST route the AURA Domain needs, kept out of server.py so the bridge
file stays about the brain.

    /api/domain/fs/*        real filesystem for the Code pane
    /api/domain/shell/*     real command execution for the Terminal
    /api/domain/github      live repo vitals for dashboard project cards
    /api/connectors/*       Figma / Microsoft 365 / GitHub OAuth

Mounted by server.py via `app.include_router(domain_router)`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def _err(msg: str, code: int = 400) -> dict[str, Any]:
    return {"ok": False, "error": msg, "status": code}


# ============================================================================
# Filesystem
# ============================================================================
@router.get("/api/domain/fs/roots")
async def fs_roots() -> dict[str, Any]:
    from core import domain_fs
    return {"ok": True, "roots": domain_fs.roots()}


@router.get("/api/domain/fs/list")
async def fs_list(path: str, hidden: bool = False) -> dict[str, Any]:
    from core import domain_fs
    try:
        return {"ok": True, **domain_fs.list_dir(path, hidden)}
    except domain_fs.FsError as e:
        return _err(str(e))


@router.get("/api/domain/fs/tree")
async def fs_tree(path: str, depth: int = 2) -> dict[str, Any]:
    from core import domain_fs
    try:
        return {"ok": True, "tree": domain_fs.tree(path, min(depth, 5))}
    except domain_fs.FsError as e:
        return _err(str(e))


@router.get("/api/domain/fs/read")
async def fs_read(path: str) -> dict[str, Any]:
    from core import domain_fs
    try:
        return {"ok": True, **domain_fs.read_file(path)}
    except domain_fs.FsError as e:
        return _err(str(e))


@router.post("/api/domain/fs/write")
async def fs_write(req: Request) -> dict[str, Any]:
    from core import domain_fs
    body = await req.json()
    try:
        return domain_fs.write_file(body.get("path", ""), body.get("content", ""))
    except domain_fs.FsError as e:
        return _err(str(e))


@router.post("/api/domain/fs/create")
async def fs_create(req: Request) -> dict[str, Any]:
    from core import domain_fs
    body = await req.json()
    try:
        return domain_fs.create(body.get("path", ""), bool(body.get("dir")))
    except domain_fs.FsError as e:
        return _err(str(e))


@router.post("/api/domain/fs/rename")
async def fs_rename(req: Request) -> dict[str, Any]:
    from core import domain_fs
    body = await req.json()
    try:
        return domain_fs.rename(body.get("path", ""), body.get("name", ""))
    except domain_fs.FsError as e:
        return _err(str(e))


@router.post("/api/domain/fs/delete")
async def fs_delete(req: Request) -> dict[str, Any]:
    from core import domain_fs
    body = await req.json()
    try:
        return domain_fs.delete(body.get("path", ""))
    except domain_fs.FsError as e:
        return _err(str(e))


@router.get("/api/domain/fs/search")
async def fs_search(path: str, q: str) -> dict[str, Any]:
    from core import domain_fs
    try:
        return {"ok": True, "hits": domain_fs.search(path, q)}
    except domain_fs.FsError as e:
        return _err(str(e))


# ============================================================================
# Terminal
# ============================================================================
@router.post("/api/domain/shell/open")
async def shell_open(req: Request) -> dict[str, Any]:
    from core import domain_shell
    body = await req.json() if await req.body() else {}
    s = domain_shell.open_session(body.get("cwd"))
    return {"ok": True, "id": s.id, "cwd": s.cwd}


@router.post("/api/domain/shell/run")
async def shell_run(req: Request) -> dict[str, Any]:
    from core import domain_shell
    body = await req.json()
    s = domain_shell.get_session(body.get("id"), body.get("cwd"))
    result = s.run(body.get("command", ""), int(body.get("timeout") or 60))
    return {"ok": True, "id": s.id, **result}


@router.post("/api/domain/shell/close")
async def shell_close(req: Request) -> dict[str, Any]:
    from core import domain_shell
    body = await req.json()
    return {"ok": domain_shell.close_session(body.get("id", ""))}


@router.get("/api/domain/shell/sessions")
async def shell_sessions() -> dict[str, Any]:
    from core import domain_shell
    return {"ok": True, "sessions": domain_shell.list_sessions()}


# ============================================================================
# GitHub project status
# ============================================================================
@router.get("/api/domain/github")
async def github_status(url: str, force: bool = False) -> dict[str, Any]:
    from core.github_status import repo_status
    return repo_status(url, force)


# ============================================================================
# Connectors (OAuth)
# ============================================================================
@router.get("/api/connectors")
async def connectors_list() -> dict[str, Any]:
    from core import connectors
    return {
        "ok": True,
        "connectors": connectors.status_all(),
        "figma_teams": connectors.get_figma_teams(),
    }


@router.put("/api/connectors/{provider}/config")
async def connectors_config(provider: str, req: Request) -> dict[str, Any]:
    from core import connectors
    body = await req.json()
    try:
        connectors.set_credentials(
            provider, body.get("client_id", ""), body.get("client_secret", "")
        )
        if provider == "figma" and "team_ids" in body:
            connectors.set_figma_teams(body.get("team_ids", ""))
        return {"ok": True, "connector": connectors.status(provider)}
    except ValueError as e:
        return _err(str(e))


@router.get("/api/connectors/{provider}/auth")
async def connectors_auth(provider: str) -> dict[str, Any]:
    from core import connectors
    try:
        return {"ok": True, "url": connectors.auth_url(provider)}
    except ValueError as e:
        return _err(str(e))


@router.get("/api/connectors/callback/{provider}", response_class=HTMLResponse)
async def connectors_callback(provider: str, code: str = "", state: str = "",
                              error: str = "") -> HTMLResponse:
    """Where the provider sends the browser back. Renders a tiny done page."""
    from core import connectors

    if error:
        msg, ok = f"{provider} returned: {error}", False
    else:
        try:
            connectors.exchange_code(provider, code, state)
            try:
                connectors.me(provider)      # label the account, best effort
            except Exception:  # noqa: BLE001
                pass
            msg, ok = f"{provider.title()} connected. You can close this tab.", True
        except Exception as e:  # noqa: BLE001
            msg, ok = str(e), False

    accent = "#8b5cff" if ok else "#ff5a5a"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>AURA · {provider}</title></head>
<body style="margin:0;height:100vh;display:grid;place-items:center;
background:#05030f;color:#eceafe;font-family:system-ui,sans-serif">
  <div style="text-align:center;padding:36px 44px;border-radius:20px;
       border:1px solid {accent}44;background:#ffffff08;
       box-shadow:0 0 60px {accent}33">
    <div style="font-size:34px;color:{accent};margin-bottom:10px">{'✦' if ok else '✕'}</div>
    <div style="font-size:15px;line-height:1.6;max-width:380px">{msg}</div>
  </div>
  <script>{'setTimeout(function(){window.close()},1800)' if ok else ''}</script>
</body></html>""")


@router.post("/api/connectors/{provider}/disconnect")
async def connectors_disconnect(provider: str) -> dict[str, Any]:
    from core import connectors
    try:
        connectors.disconnect(provider)
        return {"ok": True, "connector": connectors.status(provider)}
    except ValueError as e:
        return _err(str(e))


@router.get("/api/connectors/{provider}/documents")
async def connectors_documents(provider: str, q: str = "", kind: str = "") -> dict[str, Any]:
    """Files from a connected app. `kind` filters to word/excel/powerpoint."""
    from core import connectors
    try:
        docs = connectors.list_documents(provider, q)
        if kind:
            wanted = {k.strip() for k in kind.split(",") if k.strip()}
            docs = [d for d in docs if d.get("kind") in wanted]
        return {"ok": True, "documents": docs}
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


# ============================================================================
# Office documents — open the real file, edit it, write it back
# ============================================================================
@router.get("/api/domain/office/open")
async def office_open(id: str) -> dict[str, Any]:
    from core import office_sync
    try:
        return {"ok": True, "document": office_sync.open_document(id)}
    except office_sync.OfficeError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"could not open: {e}")


@router.post("/api/domain/office/save")
async def office_save(req: Request) -> dict[str, Any]:
    from core import office_sync
    body = await req.json()
    try:
        return office_sync.save_document(body.get("id", ""), body.get("edits") or {})
    except office_sync.OfficeError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"could not save: {e}")


@router.get("/api/domain/office/meta")
async def office_meta(id: str) -> dict[str, Any]:
    """Cheap poll: has this file changed in Word/Excel/PowerPoint since we looked?"""
    from core import office_sync
    try:
        return {"ok": True, **office_sync.meta(id)}
    except office_sync.OfficeError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(str(e))


@router.get("/api/domain/figma/file")
async def figma_file(key: str) -> dict[str, Any]:
    from core import office_sync
    try:
        return {"ok": True, "file": office_sync.figma_file(key)}
    except office_sync.OfficeError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
