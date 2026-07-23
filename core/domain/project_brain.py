"""
core.domain.project_brain
-------------------------
The high-level "Project Brain" — the killer feature of AURA Domain V2. A thin,
intention-revealing API over brain_store that records the project's living
knowledge graph and lets you query it in human terms.

The chain the spec describes:

    idea -> discussion -> decision -> feature -> task -> file -> commit -> test

This module gives you verbs to build that chain (record_idea, record_decision,
add_feature, add_task, link, ...) and readers to walk it back
(why, timeline, related, ask_context). git_scan output is folded straight in by
import_git_scan so commits become first-class graph citizens that "complete"
tasks and "affect" files.

No LLM here — this is deterministic graph plumbing. planning.py is where the
model turns conversation into these structures.
"""

from __future__ import annotations

import os
from typing import Any

from core.domain import brain_store as store
from core.domain import git_scan, analyzer


# ── project lifecycle ────────────────────────────────────────────────────────
def create_project(name: str, root: str = "", repo_url: str = "") -> dict[str, Any]:
    """New project + a root `project` node so everything has something to hang
    off. Returns the project dict with `.root_node` added."""
    p = store.create_project(name, root=root, repo_url=repo_url)
    root_node = store.add_node(p["id"], "project", name,
                               body=f"Root of {name}", meta={"root": root})
    store.update_project(p["id"], meta={"root_node": root_node["id"]})
    return {**store.get_project(p["id"]), "root_node": root_node["id"]}


def import_from_folder(name: str, root: str) -> dict[str, Any]:
    """Phase-1+2 in one call: create the project, run static analysis, fold in
    the local-git history. Returns {project, analysis, git}."""
    root = os.path.abspath(os.path.expanduser(root))
    proj = create_project(name, root=root)
    pid = proj["id"]

    an = analyzer.analyze(root)
    store.update_project(pid, meta={"analysis": an})

    gs = git_scan.scan(root)
    if gs.get("is_repo"):
        store.update_project(pid, repo_url=gs.get("remote_url", ""),
                             meta={"head": gs.get("head", {})})
        import_git_scan(pid, gs)

    return {"project": store.get_project(pid), "analysis": an, "git": gs}


# ── recording the causal chain ───────────────────────────────────────────────
def record_idea(pid: str, title: str, body: str = "") -> dict[str, Any]:
    return store.add_node(pid, "idea", title, body=body)


def record_discussion(pid: str, title: str, body: str = "",
                      from_idea: str | None = None) -> dict[str, Any]:
    n = store.add_node(pid, "discussion", title, body=body)
    if from_idea:
        store.add_edge(pid, from_idea, n["id"], "led_to")
    return n


def record_decision(pid: str, title: str, reason: str = "",
                    alternatives: list[str] | None = None,
                    from_node: str | None = None) -> dict[str, Any]:
    """A decision, with its reason and the alternatives that were rejected.
    Each rejected alternative becomes its own decision node linked by
    rejected_alt, so "why not X?" is answerable too."""
    dec = store.add_node(pid, "decision", title, body=reason,
                         meta={"reason": reason})
    if from_node:
        store.add_edge(pid, from_node, dec["id"], "led_to")
    for alt in alternatives or []:
        alt_node = store.add_node(pid, "decision", alt, status="rejected",
                                  meta={"rejected": True})
        store.add_edge(pid, dec["id"], alt_node["id"], "rejected_alt")
    return dec


def add_feature(pid: str, title: str, description: str = "",
               status: str = "planning", from_node: str | None = None) -> dict[str, Any]:
    f = store.add_node(pid, "feature", title, body=description, status=status)
    if from_node:
        store.add_edge(pid, from_node, f["id"], "led_to")
    return f


def add_task(pid: str, title: str, feature_id: str | None = None,
             description: str = "", status: str = "todo",
             files: list[str] | None = None, effort: str = "",
             depends_on: list[str] | None = None) -> dict[str, Any]:
    t = store.add_node(pid, "task", title, body=description, status=status,
                       meta={"files": files or [], "effort": effort})
    if feature_id:
        store.add_edge(pid, t["id"], feature_id, "belongs_to")
    for dep in depends_on or []:
        store.add_edge(pid, t["id"], dep, "depends_on")
    return t


def set_task_status(pid: str, task_id: str, status: str,
                    reason: str = "") -> dict[str, Any] | None:
    meta = {"blocked_reason": reason} if status == "blocked" and reason else {}
    return store.update_node(task_id, status=status, meta=meta)


def add_milestone(pid: str, title: str, status: str = "planning") -> dict[str, Any]:
    return store.add_node(pid, "milestone", title, status=status)


def link(pid: str, src: str, dst: str, type: str,
         meta: dict | None = None) -> dict[str, Any]:
    return store.add_edge(pid, src, dst, type, meta)


# ── git -> graph ─────────────────────────────────────────────────────────────
def import_git_scan(pid: str, scan: dict[str, Any]) -> dict[str, int]:
    """Fold a git_scan.scan() result into the graph. Commits become `commit`
    nodes, touched paths become (deduped) `file` nodes, and an `affects` edge
    links them. If a commit subject mentions a task title, we mark that task
    complete and add a `completes` edge (Phase-6 auto-progress). Idempotent on
    sha."""
    added_commits = added_files = linked_tasks = 0
    file_index: dict[str, str] = {
        n["meta"].get("path"): n["id"]
        for n in store.nodes(pid, "file") if n["meta"].get("path")
    }
    tasks = store.nodes(pid, "task")

    for c in scan.get("commits", []):
        if store.find_node(pid, "commit", sha=c["sha"]):
            continue  # already imported
        cnode = store.add_node(
            pid, "commit", c["subject"] or c["sha"],
            body=c["subject"],
            meta={"sha": c["sha"], "full_sha": c.get("full_sha", ""),
                  "author": c.get("author", ""), "date": c.get("date", "")},
        )
        added_commits += 1

        for path in c.get("files", []):
            fid = file_index.get(path)
            if not fid:
                fnode = store.add_node(pid, "file", os.path.basename(path),
                                       meta={"path": path})
                fid = fnode["id"]
                file_index[path] = fid
                added_files += 1
            store.add_edge(pid, cnode["id"], fid, "affects")

        # crude Phase-6 completion: commit subject references a task title
        subj = (c.get("subject") or "").lower()
        for t in tasks:
            title = t["title"].lower().strip()
            if title and len(title) > 4 and title in subj:
                store.add_edge(pid, cnode["id"], t["id"], "completes")
                if t["status"] != "done":
                    store.update_node(t["id"], status="done")
                linked_tasks += 1

    return {"commits": added_commits, "files": added_files,
            "tasks_completed": linked_tasks}


# ── reading the graph ────────────────────────────────────────────────────────
def why(pid: str, node_id: str) -> dict[str, Any]:
    """"Why does this exist?" — walk the causal chain back to the originating
    idea/discussion/decision and return it as a readable narrative + the raw
    chain for a UI to render as a path."""
    chain = store.trace_back(node_id)
    target = store.get_node(node_id)
    if not target:
        return {"ok": False, "error": "node not found"}

    # attach any decision reasons and rejected alternatives found on the way
    story: list[str] = []
    for n in chain:
        label = n["type"].capitalize()
        line = f"{label}: {n['title']}"
        reason = n["meta"].get("reason")
        if reason:
            line += f" — {reason}"
        story.append(line)

    rejected = []
    for n in chain:
        if n["type"] == "decision":
            for alt in store.neighbors(n["id"], "rejected_alt", "out"):
                rejected.append(alt["title"])

    return {
        "ok": True,
        "node": target,
        "chain": chain,
        "narrative": " → ".join(story) if story else f"{target['type']}: {target['title']}",
        "rejected_alternatives": rejected,
    }


def related(pid: str, node_id: str) -> dict[str, Any]:
    """Everything one hop from a node, grouped by edge type — powers the
    Phase-9 'Ask about anything' panel (related files, commits, tasks...)."""
    grouped: dict[str, list[dict]] = {}
    for e in store.edges_of(node_id, "both"):
        other_id = e["dst"] if e["src"] == node_id else e["src"]
        other = store.get_node(other_id)
        if other:
            grouped.setdefault(e["type"], []).append(
                {"id": other["id"], "type": other["type"], "title": other["title"]}
            )
    return {"ok": True, "node_id": node_id, "related": grouped}


def timeline(pid: str, limit: int = 100) -> list[dict[str, Any]]:
    """Flat, newest-first event stream across the whole graph — Phase-11.
    Commits, decisions, completed tasks, milestones."""
    events: list[dict[str, Any]] = []
    for t in ("commit", "decision", "milestone", "task"):
        for n in store.nodes(pid, t):
            if t == "task" and n["status"] != "done":
                continue
            events.append({
                "id": n["id"], "type": n["type"], "title": n["title"],
                "when": n["meta"].get("date") or n["updated_at"] or n["created_at"],
                "status": n["status"],
            })
    events.sort(key=lambda e: e["when"] or "", reverse=True)
    return events[:limit]


def dashboard(pid: str) -> dict[str, Any]:
    """Phase-12 vitals in one call."""
    from core.domain import progress
    p = store.get_project(pid)
    if not p:
        return {"ok": False, "error": "project not found"}
    return {
        "ok": True,
        "project": p,
        "counts": store.counts(pid),
        "progress": progress.overall(pid),
        "recent": timeline(pid, limit=8),
    }
