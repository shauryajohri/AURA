"""
core.domain.progress
--------------------
Phase-7 "Smart Progress" for AURA Domain V2. Instead of a bare "70%", this
computes an explained progress picture from the task nodes in the graph:
completed / in-progress / blocked / remaining, per-feature rollups, and the
single biggest blocker (the blocked task that the most other work waits on).

Reads only through brain_store, so it always reflects the live graph.
"""

from __future__ import annotations

from typing import Any

from core.domain import brain_store as store

# task.status -> bucket
_DONE = {"done"}
_ACTIVE = {"in_progress"}
_BLOCKED = {"blocked"}
_REMAINING = {"planning", "todo", ""}


def _bucket(status: str) -> str:
    if status in _DONE:
        return "completed"
    if status in _ACTIVE:
        return "in_progress"
    if status in _BLOCKED:
        return "blocked"
    if status == "rejected":
        return "rejected"
    return "remaining"


def _pct(done: int, total: int) -> int:
    return round(100 * done / total) if total else 0


def feature_progress(project: str) -> list[dict[str, Any]]:
    """Per-feature rollup: tasks belonging to each feature, grouped by bucket."""
    features = store.nodes(project, "feature")
    tasks = store.nodes(project, "task")
    # map task -> feature via belongs_to edges
    belongs: dict[str, str] = {}
    for e in store.edges(project, "belongs_to"):
        # task --belongs_to--> feature
        belongs[e["src"]] = e["dst"]

    by_feature: dict[str, list[dict]] = {f["id"]: [] for f in features}
    for t in tasks:
        fid = belongs.get(t["id"])
        if fid in by_feature:
            by_feature[fid].append(t)

    out = []
    for f in features:
        ts = by_feature.get(f["id"], [])
        counted = [t for t in ts if _bucket(t["status"]) != "rejected"]
        done = sum(1 for t in counted if _bucket(t["status"]) == "completed")
        out.append({
            "feature_id": f["id"],
            "feature": f["title"],
            "status": f["status"],
            "total": len(counted),
            "completed": done,
            "percent": _pct(done, len(counted)),
        })
    return out


def biggest_blocker(project: str) -> dict[str, Any] | None:
    """The blocked task that the most other tasks depend on (transitively 1 hop).
    Falls back to the earliest-created blocked task if none have dependents."""
    tasks = store.nodes(project, "task")
    blocked = [t for t in tasks if _bucket(t["status"]) == "blocked"]
    if not blocked:
        return None
    # count dependents: task --depends_on--> blocked  (incoming depends_on)
    best = None
    best_dependents = -1
    for b in blocked:
        deps = [e for e in store.edges_of(b["id"], "in") if e["type"] == "depends_on"]
        if len(deps) > best_dependents:
            best_dependents = len(deps)
            best = b
    if best is None:
        best = blocked[0]
        best_dependents = 0
    return {
        "id": best["id"],
        "title": best["title"],
        "dependents": max(best_dependents, 0),
        "reason": best["meta"].get("blocked_reason", ""),
    }


def overall(project: str) -> dict[str, Any]:
    """The Phase-7 payload: totals, buckets, percent, biggest blocker, and a
    one-line human summary."""
    tasks = store.nodes(project, "task")
    buckets = {"completed": 0, "in_progress": 0, "blocked": 0,
               "remaining": 0, "rejected": 0}
    for t in tasks:
        buckets[_bucket(t["status"])] += 1

    counted = len(tasks) - buckets["rejected"]
    percent = _pct(buckets["completed"], counted)
    blocker = biggest_blocker(project)

    summary = (
        f"{percent}% done — {buckets['completed']} of {counted} tasks complete, "
        f"{buckets['in_progress']} in progress, {buckets['blocked']} blocked."
    )
    if blocker:
        summary += f" Biggest blocker: {blocker['title']}."

    return {
        "project": project,
        "percent": percent,
        "total": counted,
        "completed": buckets["completed"],
        "in_progress": buckets["in_progress"],
        "blocked": buckets["blocked"],
        "remaining": buckets["remaining"],
        "rejected": buckets["rejected"],
        "biggest_blocker": blocker,
        "by_feature": feature_progress(project),
        "summary": summary,
    }
