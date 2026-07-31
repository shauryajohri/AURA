"""
Tests for project-aware chat context (core/work_recall).

The bug, 2026-07-31: shaurya asked "find me some websites from where i can see
portfolio and design them" and AURA answered like a search engine — she never
noticed the portfolio project sitting in her own Domain brain. `context_block`
only ever offered the two most RECENTLY TOUCHED projects, so anything he named
but hadn't opened this week was invisible to the chat.

Now the message picks the project (`find_project`), and a matched project gets
its full detail (`focus_block`) instead of a one-line summary. The same block
feeds the sanctuary chat, the Domain chat and the recall path, which is what
"the three screens are interconnected" actually means in code.

Everything here stubs the store — no sqlite, no repo scan, no network.

Run:  PYTHONPATH=. python test_project_focus.py
"""

from core import work_recall as W

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


# ── a fake brain ────────────────────────────────────────────────────────────
PROJECTS = [
    {"id": "p1", "name": "AURA", "root": "C:/Users/shaur/Downloads/AURA",
     "updated_at": "2026-07-31 09:00:00"},
    {"id": "p2", "name": "Portfolio Site", "root": "C:/Users/shaur/dev/portfolio",
     "updated_at": "2026-06-02 11:00:00"},
    {"id": "p3", "name": "Kanji Trainer", "root": "C:/Users/shaur/dev/kanji",
     "updated_at": "2026-07-20 18:00:00"},
]

NODES = {
    ("p1", "feature"): [{"title": "voice pipeline", "status": "done"},
                        {"title": "quest verification", "status": "todo"}],
    ("p1", "task"): [{"title": "fix reasoning leak", "status": "in_progress"},
                     {"title": "ship markdown chat", "status": "todo"}],
    ("p1", "decision"): [{"title": "Groq over OpenAI", "meta": {"reason": "latency"}}],
    ("p2", "feature"): [{"title": "case study pages", "status": "todo"},
                        {"title": "dark theme", "status": "done"}],
    ("p2", "task"): [{"title": "pick a hosting provider", "status": "todo"}],
    ("p2", "decision"): [{"title": "Next.js on Vercel", "meta": {"reason": "free tier"}}],
    ("p3", "task"): [{"title": "SRS scheduling", "status": "todo"}],
}

W._list_projects = lambda: PROJECTS                                    # type: ignore[assignment]
W._nodes = lambda pid, kind: NODES.get((pid, kind), [])                # type: ignore[assignment]
W._progress = lambda pid: {"percent": 40, "completed": 2, "total": 5}  # type: ignore[assignment]
W._timeline = lambda pid, n: [{"title": "wrote the hero section",
                               "when": "2026-06-02 11:00:00"}]         # type: ignore[assignment]
W._stack = lambda root: {"ok": True, "languages": {"TypeScript": 20, "CSS": 4},
                         "frameworks": ["next", "tailwind"],
                         "architecture": "app-router site",
                         "file_count": 24}                             # type: ignore[assignment]
W._INDEX.clear()


print("\n[the message picks the project]")
p = W.find_project("find me some websites from where i can see portfolio and design them")
check("'portfolio' finds the Portfolio Site project", p is not None and p["id"] == "p2")
check("not the most recently touched one", p is not None and p["id"] != "p1")

check("a project named outright wins",
      (W.find_project("how's AURA going?") or {}).get("id") == "p1")
check("matched through a feature title, not just the name",
      (W.find_project("what about the case study pages?") or {}).get("id") == "p2")
check("matched through the folder name",
      (W.find_project("anything left in kanji?") or {}).get("id") == "p3")

print("\n[no match is a real answer]")
check("small talk matches nothing", W.find_project("morning mate, what's the plan?") is None)
check("an unrelated question matches nothing",
      W.find_project("explain how tcp handshakes work") is None)
check("empty query is safe", W.find_project("") is None)
check("stopwords alone don't match", W.find_project("can you give me some more of that") is None)

print("\n[improve intent]")
for q in ["how do i upgrade it", "give me better ideas", "what should i add next",
          "any ideas for the portfolio", "how can i make it better",
          "what's missing here", "next steps?"]:
    check(f"improve: {q!r}", W.improve_intent(q))
for q in ["what were we doing last time", "show me the open tasks",
          "what is next.js"]:
    check(f"not improve: {q!r}", not W.improve_intent(q))


print("\n[focus_block carries the specifics]")
proj = W.find_project("how do i upgrade my portfolio")
block = W.focus_block(proj, "how do i upgrade my portfolio")
check("names the project", "Portfolio Site" in block)
check("says what's already built", "dark theme" in block)
check("says what's planned", "case study pages" in block)
check("says what's open", "pick a hosting provider" in block)
check("carries decisions so she doesn't re-suggest them", "Next.js on Vercel" in block)
check("includes progress", "40%" in block)
# The stack only comes out for improve questions — analyze() walks the folder.
check("improve question pulls the stack", "tailwind" in block)
check("improve question gets the grounding instruction", "Generic advice" in block)

plain = W.focus_block(proj, "what's the status of the portfolio")
check("a plain question skips the expensive stack read", "tailwind" not in plain)
check("...but still gets the project detail", "case study pages" in plain)
check("...and is told to answer about this project", "THIS project" in plain)


print("\n[prompt_section picks the right tier]")
sec = W.prompt_section("how do i upgrade my portfolio")
check("focused project leads", sec.startswith("THE PROJECT THEY'RE ASKING ABOUT"))
check("other projects still mentioned underneath", "AURA" in sec)

sec2 = W.prompt_section("what were we doing last time?")
check("a general work question gets the expanded block", "PROJECTS (from your own" in sec2)

sec3 = W.prompt_section("morning, how are you?")
check("small talk gets only the compact block",
      "THE PROJECT THEY'RE ASKING ABOUT" not in sec3)


print("\n[never raises, never invents]")
W._list_projects = lambda: (_ for _ in ()).throw(RuntimeError("db gone"))  # type: ignore[assignment]
W._INDEX.clear()
check("a broken store degrades to no context, not an exception",
      W.find_project("portfolio") is None)
check("prompt_section survives it too", isinstance(W.prompt_section("portfolio"), str))

W._list_projects = lambda: []                                          # type: ignore[assignment]
check("an empty brain returns no placeholder", W.prompt_section("portfolio") == "")


print("\n" + "=" * 40)
print(f"{passed} passed, {failed} failed")
print("=" * 40)
