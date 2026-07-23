"""
Offline smoke test for the AURA Domain V2 upgrades:
Idea Capture (feature / decision / edit / note), subtask expansion, and
ask-anything. Everything runs with use_llm=False so it's deterministic and
needs no network. Throwaway DB.

Run:  python -m tests.test_idea_capture
"""

import os
import sys
import tempfile

os.environ["AURA_TEST_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="aura_capture_test_"), "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect

from core.domain import project_brain, idea_capture, github_import  # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


proj = project_brain.create_project("Smart City Digital Twin")
pid = proj["id"]

print("\n[1] classify")
check(idea_capture.classify("We should have a real-time dashboard") == "feature", "feature detected")
check(idea_capture.classify("maybe use PostgreSQL because it scales") == "decision", "decision detected")
check(idea_capture.classify("Actually make the map 3D") == "edit", "edit detected")
check(idea_capture.classify("use Kafka instead of RabbitMQ") == "decision", "tech-swap = decision")

print("\n[2] capture a feature (offline heuristic)")
res = idea_capture.capture(
    pid,
    "We should have a dashboard where city admins monitor everything in real "
    "time, maybe with maps and alerts.",
    use_llm=False)
check(res["kind"] == "feature", "routed to feature")
check(bool(res["feature"]["title"]), f"feature title: {res['feature']['title']}")
check(res["feature"]["category"] in {"Frontend", "Data", "Backend", "Infra", "Auth", "Other"},
      f"category assigned: {res['feature']['category']}")
check(len(res["tasks"]) >= 1, f"tasks generated ({len(res['tasks'])})")
feature_id = res["feature"]["id"]
print(f"      priority={res['feature']['priority']} tasks={[t['title'] for t in res['tasks']][:4]}...")

print("\n[3] capture a decision from a ramble")
res = idea_capture.capture(
    pid,
    "I think maybe we should use PostgreSQL because later we're going to store "
    "analytics and I don't think SQLite will scale",
    feature_id=feature_id, use_llm=False)
check(res["kind"] == "decision", "routed to decision")
check("postgres" in res["decision"]["choice"].lower(), f"choice={res['decision']['choice']}")
check(bool(res["decision"]["reason"]), f"reason extracted: {res['decision']['reason']}")

print("\n[4] natural-language edit")
# add a known task then edit it
t = project_brain.add_task(pid, "Map Integration", feature_id=feature_id)
res = idea_capture.capture(pid, "Actually make the map 3D", use_llm=False)
check(res["kind"] == "edit", "routed to edit")
check(res.get("ok"), f"edit applied: {res.get('old')} -> {res.get('new')}")

print("\n[5] subtask expansion (canned, offline)")
auth = project_brain.add_task(pid, "Authentication", feature_id=feature_id)
res = idea_capture.expand_task(pid, auth["id"], use_llm=False)
check(res["ok"], "expanded")
check(len(res["subtasks"]) == 5, f"5 subtasks (got {len(res.get('subtasks', []))})")
print(f"      {[s['title'] for s in res['subtasks']]}")

print("\n[6] ask anything (context-only, offline)")
ans = idea_capture.ask(pid, feature_id, "Why did we choose PostgreSQL?", use_llm=False)
check(ans["ok"], "ask ok")
check("postgres" in ans["answer"].lower(), "answer surfaces the PostgreSQL decision from context")

print("\n[7] github_import guards without login")
r = github_import.list_repos()
check(r["ok"] is False and r["connected"] is False, "list_repos blocked when not connected")
r2 = github_import.import_repo("octocat/Hello-World")
check(r2["ok"] is False, "import blocked when not connected")
check(callable(github_import.projects_dir), "projects_dir available")

print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES: {_fails}"))
sys.exit(1 if _fails else 0)
