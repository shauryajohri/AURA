"""
HTTP contract test for the Domain Brain endpoints the React UI actually calls.

The foundation test (tests/test_domain_foundation.py) proves the Python logic.
This one proves the *wire shapes*: every field brainApi.ts / brainStore.ts read
must exist in the JSON, with the type the UI assumes. A rename in core/domain
that silently breaks the workspace should fail here, not in the browser.

Runs offline (use_llm=False everywhere) on a THROWAWAY sqlite DB.

Run:  PYTHONPATH=. python tests/test_domain_api_contract.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB before anything binds to the real one
_TMP = tempfile.mkdtemp(prefix="aura_domain_api_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]

from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
brain_store.init_db()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from domain_api import router  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI()
app.include_router(router)
client = TestClient(app)

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


def has(d: dict, *keys: str) -> bool:
    """Every key present (value may be falsy — the UI guards for empties)."""
    missing = [k for k in keys if k not in d]
    if missing:
        print(f"      missing keys: {missing}")
    return not missing


# ── 1. project list + import (ProjectsView) ──────────────────────────────────
print("\n[1] GET /api/domain/projects  +  POST /projects/import")
r = client.get("/api/domain/projects").json()
check(r.get("ok") and isinstance(r.get("projects"), list), "projects list shape")

r = client.post("/api/domain/projects/import", json={"root": REPO, "name": "AURA"}).json()
check(r.get("ok"), "import_from_folder ok")
proj = r.get("project") or {}
check(has(proj, "id", "name", "root", "repo_url", "meta", "created_at", "updated_at"),
      "project row shape (brainApi.BrainProject)")
pid = proj.get("id")

an = (proj.get("meta") or {}).get("analysis") or {}
check(has(an, "primary_language", "frameworks", "file_count"),
      "meta.analysis fields the project card renders")
head = (proj.get("meta") or {}).get("head") or {}
check("branch" in head and "sha" in head, "meta.head.branch/sha for the card's commit line")


# ── 2. capture → feature + tasks (BrainstormView receipt) ────────────────────
print("\n[2] POST /project/{pid}/capture  (offline heuristics)")
r = client.post(f"/api/domain/project/{pid}/capture", json={
    "text": "Users should log in with GitHub OAuth because developers already have accounts",
    "use_llm": False,
}).json()
check(r.get("ok"), "capture ok")
check(r.get("kind") in {"feature", "decision", "edit", "note"}, f"kind is known ({r.get('kind')})")
if r.get("kind") == "feature":
    f = r.get("feature") or {}
    check(has(f, "id", "title", "priority", "category", "description"), "feature receipt shape")
    tasks = r.get("tasks") or []
    check(bool(tasks) and has(tasks[0], "id", "title"), "task receipt shape")
elif r.get("kind") == "decision":
    d = r.get("decision") or {}
    check(has(d, "topic", "choice", "reason"), "decision receipt shape")
    check("node_id" in r, "decision node_id present")

# guarantee a feature + tasks exist for the rest of the run
r = client.post(f"/api/domain/project/{pid}/plan", json={
    "text": "Add GitHub integration", "use_llm": False,
}).json()
check(r.get("ok"), "plan_and_record ok")


# ── 3. graph (GraphView) ─────────────────────────────────────────────────────
print("\n[3] GET /project/{pid}/graph")
g = client.get(f"/api/domain/project/{pid}/graph").json()
check(g.get("ok") and isinstance(g.get("nodes"), list) and isinstance(g.get("edges"), list),
      "graph returns nodes + edges")
node = g["nodes"][0]
check(has(node, "id", "project", "type", "title", "body", "status", "meta",
          "created_at", "updated_at"), "node shape (brainApi.BrainNode)")
edge = g["edges"][0] if g["edges"] else {}
check(has(edge, "id", "project", "src", "dst", "type", "meta", "created_at"),
      "edge shape (brainApi.BrainEdge)")

UI_NODE_TYPES = {"project", "idea", "discussion", "decision", "feature",
                 "task", "file", "commit", "test", "milestone"}
unknown = {n["type"] for n in g["nodes"]} - UI_NODE_TYPES
check(not unknown, f"every node type is one the UI can draw (extra: {unknown})")

UI_EDGE_TYPES = {"led_to", "belongs_to", "implements", "affects", "completes",
                 "depends_on", "rejected_alt", "relates_to", "authored"}
unknown_e = {e["type"] for e in g["edges"]} - UI_EDGE_TYPES
check(not unknown_e, f"every edge type has a label (extra: {unknown_e})")


# ── 4. task status + expand (BrainTasks, NodeDrawer) ────────────────────────
print("\n[4] POST /task/{tid}/status  +  /task/{tid}/expand")
tasks = [n for n in g["nodes"] if n["type"] == "task"]
check(bool(tasks), "tasks exist to drive the board")
tid = tasks[0]["id"]
r = client.post(f"/api/domain/task/{tid}/status",
                json={"pid": pid, "status": "in_progress"}).json()
check(r.get("ok") and (r.get("task") or {}).get("status") == "in_progress",
      "status change returns the updated task")
r = client.post(f"/api/domain/task/{tid}/status",
                json={"pid": pid, "status": "nonsense"}).json()
check(r.get("ok") is False and "error" in r, "bad status is rejected with an error string")


# ── 5. progress + dashboard (BrainDashboard) ─────────────────────────────────
print("\n[5] GET /project/{pid}/progress  +  /project/{pid}")
p = client.get(f"/api/domain/project/{pid}/progress").json()
check(has(p, "percent", "total", "completed", "in_progress", "blocked",
          "remaining", "rejected", "biggest_blocker", "by_feature", "summary"),
      "progress payload shape")
check(isinstance(p["by_feature"], list), "by_feature is a list")
if p["by_feature"]:
    check(has(p["by_feature"][0], "feature_id", "feature", "status", "total",
              "completed", "percent"), "by_feature row shape")

d = client.get(f"/api/domain/project/{pid}").json()
check(d.get("ok") and has(d, "project", "counts", "progress", "recent"),
      "dashboard payload shape")
check(isinstance(d["counts"], dict), "counts is a type->int map")


# ── 6. timeline (BrainTimeline) ──────────────────────────────────────────────
print("\n[6] GET /project/{pid}/timeline")
t = client.get(f"/api/domain/project/{pid}/timeline?limit=50").json()
check(t.get("ok") and isinstance(t.get("events"), list), "timeline returns events")
if t["events"]:
    check(has(t["events"][0], "id", "type", "title", "when", "status"),
          "timeline event shape")


# ── 7. why / related / ask (NodeDrawer) ─────────────────────────────────────
print("\n[7] GET /node/{nid}/why · /related  +  POST /node/{nid}/ask")
w = client.get(f"/api/domain/node/{tid}/why?pid={pid}").json()
check(w.get("ok") and has(w, "node", "chain", "narrative", "rejected_alternatives"),
      "why payload shape")
check(isinstance(w["chain"], list), "chain is a list of nodes")

rel = client.get(f"/api/domain/node/{tid}/related?pid={pid}").json()
check(rel.get("ok") and isinstance(rel.get("related"), dict),
      "related payload is grouped by edge type")

a = client.post(f"/api/domain/node/{tid}/ask",
                json={"pid": pid, "question": "why does this exist?", "use_llm": False}).json()
check(a.get("ok") and has(a, "answer", "grounded_in", "source"), "ask payload shape")
check(a["source"] in {"llm", "context-only"}, "ask source is a value the UI labels")


# ── 8. rescan + github status (Dashboard sync, ProjectsView) ────────────────
print("\n[8] POST /project/{pid}/rescan  +  GET /github/status")
r = client.post(f"/api/domain/project/{pid}/rescan").json()
check(r.get("ok") and isinstance(r.get("imported"), dict), "rescan reports what it imported")
check(has(r["imported"], "commits", "files", "tasks_completed"),
      "imported counters the UI summarises")

gh = client.get("/api/domain/github/status").json()
check(gh.get("ok") and "connected" in gh, "github status shape")


# ── 9. delete (ProjectsView 'Forget') ──────────────────────────────────────
print("\n[9] DELETE /project/{pid}")
r = client.delete(f"/api/domain/project/{pid}").json()
check(r.get("ok"), "project deleted")
left = client.get("/api/domain/projects").json().get("projects", [])
check(all(p["id"] != pid for p in left), "deleted project is gone from the list")


print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
