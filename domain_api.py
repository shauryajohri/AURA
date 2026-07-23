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


# ============================================================================
# Project Brain — AURA Domain V2 (AI Project Operating System)
#   /api/domain/projects            list / create
#   /api/domain/projects/import     create from a local folder (analyze + git)
#   /api/domain/project/{pid}       dashboard vitals
#   /api/domain/project/{pid}/...   graph, timeline, progress, plan, nodes...
# All routes delegate to core.domain.* — see that package for the real logic.
# ============================================================================
@router.get("/api/domain/projects")
async def brain_projects() -> dict[str, Any]:
    from core.domain import brain_store
    return {"ok": True, "projects": brain_store.list_projects()}


@router.post("/api/domain/projects")
async def brain_create_project(req: Request) -> dict[str, Any]:
    from core.domain import project_brain
    body = await req.json()
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name required")
    return {"ok": True, "project": project_brain.create_project(
        name, root=body.get("root", ""), repo_url=body.get("repo_url", ""))}


@router.post("/api/domain/projects/import")
async def brain_import_project(req: Request) -> dict[str, Any]:
    """Phase-1+2: create a project from a local folder — static analysis plus
    local-git history folded into the graph."""
    from core.domain import project_brain
    body = await req.json()
    root = (body.get("root") or "").strip()
    if not root:
        return _err("root (folder path) required")
    name = (body.get("name") or "").strip()
    if not name:
        import os as _os
        name = _os.path.basename(root.rstrip("/\\")) or "Project"
    try:
        return {"ok": True, **project_brain.import_from_folder(name, root)}
    except Exception as e:  # noqa: BLE001
        return _err(f"import failed: {e}")


@router.get("/api/domain/project/{pid}")
async def brain_dashboard(pid: str) -> dict[str, Any]:
    from core.domain import project_brain
    return project_brain.dashboard(pid)


@router.delete("/api/domain/project/{pid}")
async def brain_delete_project(pid: str) -> dict[str, Any]:
    from core.domain import brain_store
    brain_store.wipe_project(pid)
    return {"ok": True}


@router.get("/api/domain/project/{pid}/nodes")
async def brain_nodes(pid: str, type: str = "", status: str = "") -> dict[str, Any]:
    from core.domain import brain_store
    return {"ok": True, "nodes": brain_store.nodes(pid, type or None, status or None)}


@router.get("/api/domain/project/{pid}/graph")
async def brain_graph(pid: str) -> dict[str, Any]:
    """Whole graph — nodes + edges — for a knowledge-graph view."""
    from core.domain import brain_store
    return {"ok": True, "nodes": brain_store.nodes(pid),
            "edges": brain_store.edges(pid), "counts": brain_store.counts(pid)}


@router.get("/api/domain/project/{pid}/timeline")
async def brain_timeline(pid: str, limit: int = 100) -> dict[str, Any]:
    from core.domain import project_brain
    return {"ok": True, "events": project_brain.timeline(pid, limit)}


@router.get("/api/domain/project/{pid}/progress")
async def brain_progress(pid: str) -> dict[str, Any]:
    from core.domain import progress
    return {"ok": True, **progress.overall(pid)}


@router.get("/api/domain/node/{nid}/why")
async def brain_why(nid: str, pid: str = "") -> dict[str, Any]:
    from core.domain import project_brain
    return project_brain.why(pid, nid)


@router.get("/api/domain/node/{nid}/related")
async def brain_related(nid: str, pid: str = "") -> dict[str, Any]:
    from core.domain import project_brain
    return project_brain.related(pid, nid)


@router.post("/api/domain/project/{pid}/rescan")
async def brain_rescan(pid: str) -> dict[str, Any]:
    """Re-read local git and fold any new commits into the graph (Phase-6)."""
    from core.domain import brain_store, git_scan, project_brain
    p = brain_store.get_project(pid)
    if not p:
        return _err("project not found", 404)
    if not p.get("root"):
        return _err("project has no local root to scan")
    gs = git_scan.scan(p["root"])
    if not gs.get("is_repo"):
        return _err("root is not a git repo")
    return {"ok": True, "imported": project_brain.import_git_scan(pid, gs),
            "head": gs.get("head", {})}


@router.post("/api/domain/project/{pid}/plan")
async def brain_plan(pid: str, req: Request) -> dict[str, Any]:
    """Phase-3+4: turn a note into a feature + tasks, recorded into the graph.
    Pass {"preview": true} to plan without writing."""
    from core.domain import planning
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _err("text required")
    use_llm = bool(body.get("use_llm", True))
    if body.get("preview"):
        return {"ok": True, **planning.plan(text, use_llm=use_llm)}
    return planning.plan_and_record(pid, text, from_node=body.get("from_node"),
                                    use_llm=use_llm)


@router.post("/api/domain/task/{tid}/status")
async def brain_task_status(tid: str, req: Request) -> dict[str, Any]:
    from core.domain import project_brain, brain_store
    body = await req.json()
    status = (body.get("status") or "").strip()
    if status not in brain_store.TASK_STATES:
        return _err(f"status must be one of {sorted(brain_store.TASK_STATES)}")
    node = project_brain.set_task_status(
        body.get("pid", ""), tid, status, reason=body.get("reason", ""))
    return {"ok": bool(node), "task": node}


# ============================================================================
# Idea Capture — natural conversation -> structured project knowledge
#   /api/domain/project/{pid}/capture   classify + fold one utterance in
#   /api/domain/task/{tid}/expand       generate subtasks
#   /api/domain/node/{nid}/ask          ask anything about a feature/task
# ============================================================================
@router.post("/api/domain/project/{pid}/capture")
async def brain_capture(pid: str, req: Request) -> dict[str, Any]:
    """Talk naturally; AURA decides if it's a feature, decision, edit, or note
    and records it. Returns what was created (UI confirms 'Add these tasks?')."""
    from core.domain import idea_capture
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text:
        return _err("text required")
    return idea_capture.capture(
        pid, text, feature_id=body.get("feature_id"),
        use_llm=bool(body.get("use_llm", True)))


@router.post("/api/domain/task/{tid}/expand")
async def brain_expand_task(tid: str, req: Request) -> dict[str, Any]:
    from core.domain import idea_capture
    body = await req.json() if await req.body() else {}
    return idea_capture.expand_task(
        body.get("pid", ""), tid, use_llm=bool(body.get("use_llm", True)))


@router.post("/api/domain/node/{nid}/ask")
async def brain_ask(nid: str, req: Request) -> dict[str, Any]:
    from core.domain import idea_capture
    body = await req.json()
    question = (body.get("question") or "").strip()
    if not question:
        return _err("question required")
    return idea_capture.ask(body.get("pid", ""), nid, question,
                            use_llm=bool(body.get("use_llm", True)))


# ============================================================================
# GitHub projects — log in, list repos, import one into a project
#   /api/domain/github/status    is GitHub connected + which account
#   /api/domain/github/repos     the user's repos (needs login)
#   /api/domain/github/import    clone a repo locally + build its project graph
# The GitHub token is used ONLY here, for project repo access.
# ============================================================================
@router.get("/api/domain/github/status")
async def gh_status() -> dict[str, Any]:
    from core.domain import github_import
    return {"ok": True, "connected": github_import.is_connected(),
            "account": github_import.account()}


@router.get("/api/domain/github/repos")
async def gh_repos(limit: int = 100) -> dict[str, Any]:
    from core.domain import github_import
    return github_import.list_repos(limit)


@router.post("/api/domain/github/import")
async def gh_import(req: Request) -> dict[str, Any]:
    """Clone the chosen repo locally and build its project graph. Body:
    {full_name, clone_url?, name?, branch?, force?}."""
    from core.domain import github_import
    body = await req.json()
    full_name = (body.get("full_name") or "").strip()
    if not full_name:
        return _err("full_name required (e.g. 'octocat/Hello-World')")
    return github_import.import_repo(
        full_name, clone_url=body.get("clone_url", ""),
        name=body.get("name", ""), branch=body.get("branch", ""),
        force=bool(body.get("force")))
