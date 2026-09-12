/* =====================================================================
   content.js, THE ONLY FILE YOU EDIT TO UPDATE THIS SITE.
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
      "Not a chatbot you summon. She runs on your own machine, remembers what " +
      "you were doing, and mostly decides not to interrupt you about it.",
    actions: [
      { label: "Try her", href: "#demo", kind: "go" },
      { label: "View the source",        href: "https://github.com/shauryajohri/AURA", kind: "ghost" },
    ],
  },


  /* ===================================================================
     THE DEMO, the top of the page.
     Every line here is scripted. The real AURA runs on your machine and
     answers with live models; this is a faithful reconstruction of what
     she does, not a model in a browser tab. Said plainly on the page.

     The natures and their overlay text are copied from core/nature.py.
     The models and intent lanes are from core/model_router.py.
     The sentence caps are from core/response_composer.py.
     If you change those files, change these.
     =================================================================== */
  demo: {
    kicker: "Try her",
    title: "Same question. Five different people.",
    lede:
      "Nature is a lock. Pick one and it is appended to every system prompt " +
      "until you change it, so she cannot drift back out halfway through an " +
      "evening. Pick a nature, then ask her something.",
    honesty:
      "Scripted, and worth saying so. The real AURA runs on your own machine " +
      "against live models; a browser tab has no screen, no files and no memory " +
      "of you. The words below are hers, the routing is real, the demo is a " +
      "reconstruction.",

    /* from core/nature.py: `overlay` is the actual prompt text appended */
    natures: [
      { key: "auto", label: "Auto", icon: "🟢",
        note: "No overlay. The intent lanes carry their own tone, so personal, casual and coding already sound different.",
        overlay: "(no overlay appended)" },
      { key: "chill", label: "Chill", icon: "😎",
        note: "Laid-back friend energy no matter the task.",
        overlay: "NATURE LOCK — CHILL: Laid-back friend energy no matter the task. Slow-night vibes, jokes welcome, zero productivity pushing. Even code questions get answered relaxed." },
      { key: "focus", label: "Focus", icon: "🎯",
        note: "All business. Minimal words, code and results first.",
        overlay: "NATURE LOCK — FOCUS: All business. Minimal words, direct answers, no teasing, no small talk, no questions unless essential to the task." },
      { key: "savage", label: "Savage", icon: "🔥",
        note: "Roast mode. Merciless, never cruel, and it still fixes the bug.",
        overlay: "NATURE LOCK — SAVAGE: Roast mode. Heavy banter, merciless (never cruel) teasing, dry burns. Still genuinely helpful — roast the code AND fix it." },
      { key: "professional", label: "Professional", icon: "👔",
        note: "For screen shares and demos. No slang, no sarcasm.",
        overlay: "NATURE LOCK — PROFESSIONAL: Polite, articulate, complete sentences. No slang, no teasing, no sarcasm." },
    ],

    /* Each question shows the real pipeline: intent → style → model.
       `cap` is the sentence cap that style enforces. */
    questions: [
      {
        id: "code",
        ask: "my retry loop keeps hammering the API",
        intent: "CODING", style: "coding", cap: "no cap",
        model: "Laguna M.1", gather: "screen context, recent turns",
        replies: {
          auto: "Your sleep is inside the `try`, so the moment the call raises you skip straight past the wait and fire again. Move it out, back off on `base * 2 ** attempt`, and add jitter so ten clients don't retry in lockstep.",
          chill: "Ah, that one. Your sleep is sitting inside the `try`, so when the call throws you never actually wait, you just go again. Pull it out of the block, add a bit of jitter, and it'll settle down on its own.",
          focus: "Sleep is inside the `try`. Move it out. Back off `base * 2 ** attempt`, add jitter, re-raise on the final attempt.",
          savage: "You wrote a retry loop that retries instantly. That is not a retry, that is a denial of service attack on someone who trusted you. The sleep is inside the `try`, so it never runs on failure. Move it out and add jitter before the API blocks your key.",
          professional: "The delay is currently inside the `try` block, so it is skipped whenever the request raises. Move it outside the block, apply exponential backoff of base × 2^attempt, and add jitter to avoid synchronised retries. Re-raise on the final attempt.",
        },
      },
      {
        id: "tired",
        ask: "I've been at this for six hours",
        intent: "PERSONAL", style: "casual", cap: "2 sentences",
        model: "Gemma 4 31B", gather: "work_recall, durable facts, session length",
        replies: {
          auto: "Six hours, and the last three commits are all called some version of fix. That is fatigue, not progress.",
          chill: "Six hours is plenty. Nothing here is on fire, go eat something.",
          focus: "Six hours. Returns are diminishing. Stop and resume tomorrow.",
          savage: "Six hours, and your last three commits are fix, fix2 and actually-fix. The code stopped being the problem around hour four.",
          professional: "You have been working for six hours, and your recent commits suggest fatigue rather than progress. I would suggest stopping here and returning tomorrow.",
        },
      },
      {
        id: "who",
        ask: "what are you?",
        intent: "CASUAL", style: "casual", cap: "2 sentences",
        model: "answered by AURA, not the model",
        gather: "identity block",
        identity: true,
        replies: {
          auto: "AURA. I live on your desktop, remember what you were doing, and mostly decide not to interrupt you about it.",
          chill: "I'm AURA. I hang around on your desktop, keep track of things, and stay out of the way.",
          focus: "AURA. Desktop companion. Memory, screen awareness, model routing, all local.",
          savage: "AURA. I am the thing that remembers what you swore you would fix last Tuesday.",
          professional: "I am AURA, a self-hosted desktop companion. I keep memory across sessions, read the screen when asked, and route each request to a suitable model.",
        },
      },
      {
        id: "search",
        ask: "mutex or semaphore?",
        intent: "SEARCH", style: "search", cap: "6 sentences",
        model: "Nemotron 3 Super", gather: "recent turns",
        replies: {
          auto: "A mutex if one thing may hold it at a time, a semaphore if you are counting permits. The mutex has an owner, so the thread that locked it is the thread that unlocks it. A semaphore has no owner, which is why it works for pools and producer-consumer queues.",
          chill: "Mutex when only one thing gets in, semaphore when you're handing out a few passes. The mutex remembers who took it, the semaphore just counts.",
          focus: "Mutex: one holder, ownership enforced, unlock by the locking thread. Semaphore: counted permits, no owner. Pools and queues want the semaphore.",
          savage: "If you have to ask, use the mutex. One holder, it remembers who took it, and it will scream when you unlock it from the wrong thread, which you were going to do. Semaphores are for counting permits, and they will let you leak every one.",
          professional: "Use a mutex when exactly one thread may hold the resource at a time. Ownership is enforced, so the locking thread must also unlock it. Use a semaphore when you are counting available permits, such as a connection pool. A semaphore has no owner and may be signalled by any thread.",
        },
      },
    ],

    /* the four steps, shown live beside the answer */
    steps: [
      { n: "1", name: "Classify", detail: "8 intents, on the small model" },
      { n: "2", name: "Gather",   detail: "memory, project block, screen" },
      { n: "3", name: "Route",    detail: "5 models, per-lane keys" },
      { n: "4", name: "Guard",    detail: "scrub, then the final gate" },
    ],

    /* shown under the guard step, real strings from response_composer.py */
    guard: {
      title: "What the guard removes",
      note: "Every model output passes the persona layer before you see it.",
      strips: [
        "As an AI language model...",
        "Certainly! I'd be happy to help.",
        "Great question!",
        "I don't have personal feelings.",
      ],
    },
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

  /* Images, placed where they carry an idea rather than decorate one.
     Keyed by the section they belong to; drop a key to drop the image. */
  figures: {
    halves: {
      src: "assets/graph.webp",
      alt: "A constellation of luminous nodes joined by fine edges, flowing left to right in generations.",
      caption: "Idea, decision, feature, task, commit, file. The graph is the project.",
    },
  },

  /* ===================================================================
     THE LEDGER, the spine of this site.
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
