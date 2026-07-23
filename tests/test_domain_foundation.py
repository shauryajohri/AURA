"""
End-to-end smoke test for the AURA Domain V2 backend foundation.

Runs the whole chain offline against the AURA repo itself, on a THROWAWAY
sqlite DB so real memory is never touched:

    import_from_folder -> analyze + git import
    plan_and_record    -> feature + tasks   (heuristic path, use_llm=False)
    set_task_status    -> blocked / done
    progress.overall   -> smart progress + biggest blocker
    project_brain.why  -> causal chain traceback

Run:  python -m tests.test_domain_foundation
"""

import os
import sys
import tempfile

# point the shared store at a temp DB BEFORE importing the domain modules
_TMP = tempfile.mkdtemp(prefix="aura_domain_test_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]

# make brain_store bind to the patched path
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect  # ensure same DB

from core.domain import project_brain, planning, progress, analyzer, git_scan  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


print("\n[1] analyzer.analyze on the AURA repo")
an = analyzer.analyze(REPO)
check(an["ok"], "analysis ok")
check(an["file_count"] > 0, f"found files ({an['file_count']})")
check(bool(an["languages"]), f"languages: {list(an['languages'])[:4]}")
check(an["functions"] > 0, f"counted functions ({an['functions']})")
print(f"      frameworks={an['frameworks']}  arch='{an['architecture']}'")

print("\n[2] git_scan.scan (local git, no auth)")
gs = git_scan.scan(REPO)
check("is_repo" in gs, "scan returns a result")
if gs.get("is_repo"):
    check(len(gs["commits"]) > 0, f"read commits ({len(gs['commits'])})")
    print(f"      head={gs['head']}  branches={gs['branches'][:3]}")
else:
    print("      (repo has no git history — skipping commit checks)")

print("\n[3] import_from_folder -> project graph")
res = project_brain.import_from_folder("AURA-test", REPO)
pid = res["project"]["id"]
check(bool(pid), "project created")
counts = brain_store.counts(pid)
print(f"      node counts after import: {counts}")

print("\n[4] planning.plan_and_record (heuristic, offline)")
note = (
    "We should add GitHub integration.\n"
    "- OAuth\n- Repository Scanner\n- Commit Parser\n- Pull Request Viewer\n- Testing"
)
plan = planning.plan_and_record(pid, note, use_llm=False)
check(plan["ok"], "plan recorded")
check(len(plan["tasks"]) == 5, f"5 tasks created (got {len(plan['tasks'])})")
print(f"      feature='{plan['feature']['title']}' tasks={[t['title'] for t in plan['tasks']]}")

print("\n[5] task status transitions + smart progress")
t_ids = [t["id"] for t in plan["tasks"]]
project_brain.set_task_status(pid, t_ids[0], "done")
project_brain.set_task_status(pid, t_ids[1], "in_progress")
project_brain.set_task_status(pid, t_ids[2], "blocked", reason="waiting on OAuth app")
# make task[3] depend on the blocked task[2] so it's the biggest blocker
brain_store.add_edge(pid, t_ids[3], t_ids[2], "depends_on")
prog = progress.overall(pid)
check(prog["completed"] == 1, f"1 completed (got {prog['completed']})")
check(prog["blocked"] == 1, f"1 blocked (got {prog['blocked']})")
check(prog["biggest_blocker"] is not None, "biggest blocker identified")
if prog["biggest_blocker"]:
    check(prog["biggest_blocker"]["dependents"] == 1,
          f"blocker has 1 dependent (got {prog['biggest_blocker']['dependents']})")
print(f"      {prog['summary']}")

print("\n[6] project_brain.why — causal traceback")
# idea -> discussion(feature) -> feature -> task ; walk back from a task
why = project_brain.why(pid, t_ids[0])
check(why["ok"], "why() ok")
check(len(why["chain"]) >= 2, f"chain has >=2 hops (got {len(why['chain'])})")
print(f"      narrative: {why['narrative']}")

print("\n[7] git completion linking (Phase-6)")
# a task whose title matches a commit subject should auto-complete on rescan
demo = project_brain.add_task(pid, "zzz-unique-marker-task")
brain_store.add_node  # noqa - keep import used
# simulate a commit mentioning it, then re-import
fake_scan = {"commits": [{
    "sha": "deadbee", "full_sha": "deadbee", "subject": "done zzz-unique-marker-task",
    "author": "tester", "date": "2026-07-23T10:00:00", "files": ["x/y.py"],
}]}
imp = project_brain.import_git_scan(pid, fake_scan)
check(imp["tasks_completed"] >= 1, "commit auto-completed the matching task")
check(brain_store.get_node(demo["id"])["status"] == "done", "task marked done by commit")

print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES: {_fails}"))
sys.exit(1 if _fails else 0)
