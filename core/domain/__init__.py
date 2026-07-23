"""
core.domain
-----------
Backend foundation for AURA Domain V2 — the "AI Project Operating System".

Everything here is the persistence + intelligence layer that all 12 phases of
the Domain spec sit on top of. No UI. The pieces:

    brain_store    low-level SQLite graph (projects / nodes / edges)
    project_brain  high-level knowledge-graph API (record + link + query)
    git_scan       local git reader (no auth) — commits, files, branches
    analyzer       project analysis — structure, languages, counts, modules
    progress       smart progress + biggest blocker from task nodes
    planning       conversation -> feature + structured tasks

The whole thing is a *living knowledge graph of the project*:

    idea -> discussion -> decision -> feature -> task -> file -> commit -> test

so months later you can ask "why does this module exist?" and get the chain
back. REST routes live in domain_api.py.
"""
