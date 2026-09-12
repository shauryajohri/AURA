/* =====================================================================
   content.js — THE ONLY FILE YOU EDIT TO UPDATE THIS SITE.
   ---------------------------------------------------------------------
   Every word, every capability and every status mark on the page is read
   from this object. index.html is a shell; site.js renders this.

   To record an upgrade to AURA:
     • shipped something  → find it in `capabilities` and set status:'live'
     • started something  → set status:'forming'
     • built something new→ push one more object into `capabilities`
     • nothing else needs touching. The ledger, the counts, the progress
       bar and the "what's next" list all recalculate themselves.
   ===================================================================== */

window.AURA_CONTENT = {

  meta: {
    name: "AURA",
    tagline: "An AI that sits beside you",
    /* Shown in the status strip. Update when you cut a release. */
    stage: "Daily driver, still being built",
    updated: "September 2026",
    repo: "https://github.com/shauryajohri/AURA",
    description:
      "A self-hosted AI desktop companion and software development OS. " +
      "It watches, remembers, and stays quiet unless speaking up actually helps.",
  },

  /* The three states a capability can be in. Order matters: the ledger and
     the summary counts follow this order. */
  states: {
    live:    { label: "Running",     note: "used daily",        tone: "live" },
    forming: { label: "Being built", note: "partly wired up",   tone: "forming" },
    planned: { label: "Not yet",     note: "designed, not built", tone: "planned" },
  },

  hero: {
    kicker: "Self-hosted, and MIT licensed",
    headline: "She is already there.",
    lede:
      "Not a chatbot you summon. AURA runs on your own machine, watches what " +
      "you are working on, remembers it tomorrow, and decides most of the time " +
      "that the kindest thing it can do is say nothing.",
    actions: [
      { label: "Read the current stage", href: "#stage", kind: "go" },
      { label: "View the source",        href: "https://github.com/shauryajohri/AURA", kind: "ghost" },
    ],
  },

  /* The complaints section — kept from the original copy, it is good. */
  problems: {
    title: "What people actually say about AI assistants.",
    items: [
      {
        quote: "It is like supervising a junior developer with short-term memory loss.",
        answer: "She reads the project graph before she answers.",
        body:
          "Recent projects, percent done, last event, the current blocker, and the " +
          "decisions with their reasons. If nothing is stored she says it is fuzzy " +
          "rather than inventing a project name.",
        code: "core/work_recall.py",
      },
      {
        quote: "It keeps popping up to ask me something.",
        answer: "Silence is a valid output.",
        body:
          "An engagement gate decides whether anything she noticed is worth " +
          "interrupting you for. Most of the time it decides it is not, and you " +
          "never hear about it.",
        code: "core/engagement.py",
      },
      {
        quote: "Every query and document goes to a third party.",
        answer: "The server binds to 127.0.0.1.",
        body:
          "Your memory is a SQLite file sitting next to the code. Nothing public is " +
          "required, not even to sign in to GitHub, because the callback comes back " +
          "to your own machine.",
        code: "memory/store.py",
      },
    ],
  },

  /* Four steps of a single chat turn. */
  pipeline: {
    title: "Four steps, every single message.",
    lede: "Every turn is written back to SQLite, so the next one already knows.",
    steps: [
      {
        n: "01", title: "Classify", question: "What kind of message is this?",
        body:
          "Eight intents: casual, personal, coding, search, recall, save, command, " +
          "reminder. The classifier runs on a small model so it never eats the quota " +
          "the real reply needs.",
        code: "core/brain.py",
      },
      {
        n: "02", title: "Gather", question: "What does she need to know?",
        body:
          "Recent turns pulled from the store rather than from memory, durable facts, " +
          "the project block, and what is currently on your screen.",
        code: "core/work_recall.py",
      },
      {
        n: "03", title: "Route", question: "Which model answers?",
        body:
          "Five models across two providers, each lane on its own key, so one " +
          "exhausted free tier never takes the others down with it.",
        code: "core/ai_router.py",
      },
      {
        n: "04", title: "Guard", question: "Is this fit to show you?",
        body:
          "Reasoning models narrate their own thinking out loud. Two filter tiers and " +
          "a final gate stop that reaching you, and fenced code is lifted out first " +
          "and put back byte for byte.",
        code: "core/ai_router.py",
      },
    ],
    /* the closing thought for this section lives on figures.turn.caption */
  },

  /* The two halves. `key` is matched against capability.half below. */
  halves: [
    {
      key: "companion",
      name: "The companion",
      body:
        "Voice, screen awareness, durable memory, quests, and nudges she mostly " +
        "decides not to send. Ask what you were working on and she answers from the " +
        "graph instead of guessing.",
    },
    {
      key: "domain",
      name: "AURA Domain",
      body:
        "A development OS. Talk about your project and it becomes features, tasks and " +
        "decisions you can walk. Import a folder or clone a repo and she reads the " +
        "code and the git history. Commits close their own tasks.",
    },
  ],

  /* Three images, placed where they carry an idea rather than decorate one.
     Keyed by the section they belong to; drop a key to drop the image. */
  figures: {
    problem: {
      src: "assets/sanctuary.webp",
      alt: "A dark home office at night, empty chair, a laptop screen casting violet light across the desk.",
      caption: "The room she spends most of her time in, saying nothing.",
    },
    turn: {
      src: "assets/memory.webp",
      alt: "Stratified bands of violet and amber light in darkness, like a geological core sample.",
      caption:
        "A filter that flattens a C++ answer into one line is worse than the leak " +
        "it was written to prevent, so the code never goes through it.",
    },
    halves: {
      src: "assets/graph.webp",
      alt: "A constellation of luminous nodes joined by fine edges, flowing left to right in generations.",
      caption: "Idea, decision, feature, task, commit, file. The graph is the project.",
    },
  },

  /* ===================================================================
     THE LEDGER — the spine of this site.
     One row per capability. `status` must be a key of `states` above.
     This is the list to edit when AURA moves forward.
     =================================================================== */
  capabilities: [
    /* --- the companion half --------------------------------------- */
    { half: "companion", status: "live", name: "Model routing",
      blurb: "Five models across two providers, cost-aware, each lane on its own key.",
      code: "core/ai_router.py" },
    { half: "companion", status: "live", name: "Durable memory",
      blurb: "Facts, notes and session recaps in SQLite. She remembers rather than re-asks.",
      code: "memory/store.py" },
    { half: "companion", status: "live", name: "Project recall",
      blurb: "Every turn carries a compact block of what you are actually working on.",
      code: "core/work_recall.py" },
    { half: "companion", status: "live", name: "Voice",
      blurb: "Wake word, transcription, and a speaking voice that is not a robot.",
      code: "core/voice" },
    { half: "companion", status: "live", name: "Screen awareness",
      blurb: "Reads what is on screen when asked, including which language you are in.",
      code: "modules/screen_reader.py" },
    { half: "companion", status: "live", name: "Error intelligence",
      blurb: "A rule-based knowledge base that classifies errors before spending a model call.",
      code: "modules/error_intelligence.py" },
    { half: "companion", status: "live", name: "Quests",
      blurb: "Daily commitments, verified against a screenshot rather than taken on trust.",
      code: "core/quest_verify.py" },
    { half: "companion", status: "live", name: "The engagement gate",
      blurb: "Decides whether what she noticed is worth interrupting you for. Usually not.",
      code: "core/engagement.py" },
    { half: "companion", status: "live", name: "Reasoning-leak guard",
      blurb: "Two filter tiers and a final gate, so deliberation never reaches you as an answer.",
      code: "core/ai_router.py" },
    { half: "companion", status: "live", name: "Developer state",
      blurb: "Knows how long the session has run, what broke, and what you keep repeating.",
      code: "modules/developer_state.py" },

    /* --- the development OS --------------------------------------- */
    { half: "domain", status: "live", name: "The Project Brain",
      blurb: "A knowledge graph of typed nodes and edges, stored beside your code.",
      code: "core/domain/brain_store.py" },
    { half: "domain", status: "live", name: "Research capture",
      blurb: "Talk about the project; every sentence lands as a feature, decision, edit or note.",
      code: "core/domain/idea_capture.py" },
    { half: "domain", status: "live", name: "Knowledge graph",
      blurb: "Idea to decision to feature to task to commit to file, laid out as the lifecycle.",
      code: "core/domain/project_brain.py" },
    { half: "domain", status: "live", name: "Task board",
      blurb: "Generated from what you said, grouped by feature. Commits close their own tasks.",
      code: "core/domain/progress.py" },
    { half: "domain", status: "live", name: "Code review",
      blurb: "Her version against yours, a console, and a permission ladder that never self-escalates.",
      code: "domain_api.py" },
    { half: "domain", status: "live", name: "Filesystem and terminal",
      blurb: "A real editor and a real shell, both sandboxed to the project folder.",
      code: "core/domain_shell.py" },
    { half: "domain", status: "live", name: "Git import and rescan",
      blurb: "Reads local history with no auth, then folds new commits into the graph.",
      code: "core/domain/git_scan.py" },
    { half: "domain", status: "live", name: "GitHub import",
      blurb: "Clone a repo and build the whole graph from its code and history.",
      code: "core/domain/github_import.py" },

    /* --- honest about what is not here yet ------------------------- */
    { half: "domain", status: "forming", name: "Project-grounded chat rail",
      blurb: "Asking any single node works today. The right-hand rail is still generic.",
      code: "frontend/src/components/Domain" },
    { half: "domain", status: "planned", name: "Documentation generator",
      blurb: "Turn the graph into docs that stay true as the project moves." },
    { half: "domain", status: "planned", name: "Roadmap view",
      blurb: "The timeline forward, not just the history backward." },
    { half: "domain", status: "planned", name: "Release management",
      blurb: "Cut a version, collect what changed, and close the loop." },
  ],

  ladder: {
    title: "Nothing escalates itself.",
    body:
      "She reviews your file and proposes a revision. Everything above the rung you " +
      "picked is genuinely disabled, not merely discouraged. Applying her suggestion " +
      "is a click you make.",
    rungs: [
      { name: "Read only",    grants: "suggest only", note: "she starts here" },
      { name: "Sandbox",      grants: "run it" },
      { name: "Merge review", grants: "see the diff" },
      { name: "Write",        grants: "save to disk" },
      { name: "Push",         grants: "commit and push" },
    ],
  },

  install: {
    title: "Unzip it and double-click.",
    lede: "Three commands and one key. There is no config file to learn.",
    steps: [
      { name: "Install what it needs",
        code: "pip install -r requirements.txt\ncd frontend && npm install",
        note: "Or requirements-web.txt for the backend on its own." },
      { name: "Add one key",
        code: "# .env in the repo root\nGROQ_API_KEY=your key\nOPENROUTER_API_KEY=optional fallback",
        note: "A free Groq key is enough to start. Everything degrades on purpose: with no keys at all you still get the filesystem, git, the terminal and the offline planning paths." },
      { name: "Wake her up",
        code: "AURA.bat            # one click on Windows\n\npython server.py    # or by hand: 127.0.0.1:8760\ncd frontend && npm run dev",
        note: "On Windows the launcher builds the interface once, then Electron starts the Python side itself." },
    ],
    requires: "Python 3.10 or newer. Node 18 or newer. Windows, macOS and Linux.",
  },

  faq: {
    title: "The questions people ask first.",
    items: [
      { q: "Does my code leave my machine?",
        a: "The server, your memory, your project graph and your files stay on your computer. The one thing that goes out is the model call itself, to Groq or OpenRouter, on a key you provide and can swap. There is no AURA server in the middle and no account to make." },
      { q: "What can she actually touch?",
        a: "Whatever rung you set, and nothing above it. The filesystem is sandboxed to the project folder, the shell is scoped to it, and every commit and push needs a preview and a confirmation." },
      { q: "Is it finished?",
        a: "No, and the ledger above is the honest answer rather than a paragraph here. Most of it runs daily; a handful of things are designed and not yet built. That list is kept current because the site reads it from the same file the project does." },
      { q: "Is it free?",
        a: "MIT licensed, and the source is the download. You pay whoever provides your model key, which on the Groq free tier is nothing." },
    ],
  },

  close: {
    title: "Put her on your desktop.",
    body: "One clone. Three commands. She is running in about five minutes.",
    footnote: "Source, not an installer. MIT licensed. Windows, macOS and Linux.",
  },
};
