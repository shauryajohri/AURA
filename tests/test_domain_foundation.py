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
    # every commit up to the limit, each with the paths it touched. A trailing
    # record separator once shifted each file list into the next record, so
    # only ~3 of 50 commits parsed and none of them had files.
    ok, total = git_scan._git(REPO, "rev-list", "--count", "HEAD")
    want = min(50, int(total.strip())) if ok else 0
    check(len(gs["commits"]) == want, f"read every commit up to the limit ({len(gs['commits'])}/{want})")
    wrong = []
    for c in gs["commits"]:
        _, parents = git_scan._git(REPO, "log", "-1", "--format=%P", c["full_sha"])
        if len(parents.split()) != 1:
            continue  # merges list no files; a shallow cut has no parent
        _, names = git_scan._git(REPO, "log", "-1", "--name-only", "--format=", c["full_sha"])
        if c["files"] != [f.strip() for f in names.splitlines() if f.strip()]:
            wrong.append(c["sha"])
    check(not wrong, f"each commit carries its own changed files (wrong: {wrong[:5]})")
    check(any(c["files"] for c in gs["commits"]), "commits that changed files have them")
    print(f"      head={gs['head']}  branches={gs['branches'][:3]}")
else:
    print("      (repo has no git history — skipping commit checks)")

print("\n[2b] git_scan.commits — empty, merge and shallow-cut commits")
_G = os.path.join(_TMP, "gitrepo")
os.makedirs(_G)


def _g(*args, cwd=_G):
    ok, out = git_scan._git(cwd, "-c", "user.name=t", "-c", "user.email=t@t",
                            "-c", "commit.gpgsign=false", *args)
    assert ok, out
    return out


def _write(name, text):
    with open(os.path.join(_G, name), "w", encoding="utf-8") as fh:
        fh.write(text)


_g("init", "-q", "-b", "main")
_write("a.py", "a = 1\n")
_write("b c.md", "spaces\n")
_g("add", "-A"); _g("commit", "-q", "-m", "first")
_g("commit", "-q", "--allow-empty", "-m", "nothing changed")
_g("checkout", "-q", "-b", "side")
_write("side.py", "s = 1\n")
_g("add", "-A"); _g("commit", "-q", "-m", "side work")
_g("checkout", "-q", "main")
_write("a.py", "a = 2\n")
_g("add", "-A"); _g("commit", "-q", "-m", "main work")
_g("merge", "-q", "--no-ff", "side", "-m", "merge side")
_write("last.py", "z = 1\n")
_g("add", "-A"); _g("commit", "-q", "-m", "last")
cs = {c["subject"]: c["files"] for c in git_scan.commits(_G, 50)}
check(len(cs) == 6, f"all 6 commits parsed (got {len(cs)}: {list(cs)})")
check(cs.get("last") == ["last.py"], f"newest commit has its file ({cs.get('last')})")
check(cs.get("merge side") == [], "merge commit parsed, no files")
check(cs.get("main work") == ["a.py"], f"commit after a merge keeps its own file ({cs.get('main work')})")
check(cs.get("side work") == ["side.py"], f"branch commit has its file ({cs.get('side work')})")
check(cs.get("nothing changed") == [], "empty commit parsed, no files")
check(sorted(cs.get("first") or []) == ["a.py", "b c.md"], f"root commit lists what it added ({cs.get('first')})")
check(len(git_scan.commits(_G, 2)) == 2, "limit respected")

# GitHub import clones --depth 50: the cut-off commit has no parent on disk
# and git would list its whole tree, which isn't what that commit changed.
_S = os.path.join(_TMP, "shallow")
_g("clone", "-q", "--depth", "3", "file:///" + _G.replace(os.sep, "/").lstrip("/"), _S, cwd=_TMP)
sh = {c["subject"]: c["files"] for c in git_scan.commits(_S, 50)}
check(sorted(sh) == ["last", "main work", "merge side", "side work"], f"shallow clone parsed ({sorted(sh)})")
check(sh.get("last") == ["last.py"], "shallow: newest commit keeps its file")
check(sh.get("main work") == [] and sh.get("side work") == [],
      f"shallow: cut-off commits don't claim their whole tree ({sh.get('main work')}, {sh.get('side work')})")

print("\n[3] import_from_folder -> project graph")
res = project_brain.import_from_folder("AURA-test", REPO)
pid = res["project"]["id"]
check(bool(pid), "project created")
counts = brain_store.counts(pid)
print(f"      node counts after import: {counts}")
if gs.get("is_repo"):
    check(counts.get("commit", 0) == len(gs["commits"]), "a commit node per commit read")
    check(counts.get("file", 0) > 0, "file nodes built from what the commits touched")

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
