import { create } from "zustand";
import { persist } from "zustand/middleware";

// ============================================================================
// AURA Domain — project system store.
//
// Everything belonging to one project (board, tasks, notes, roadmap, repo,
// local folder) lives together. Deliberately separate from the rest of AURA:
// Domain tasks are NOT the sanctuary's tasks, and Domain notes are NOT
// research. The Python brain reads the real filesystem directly, so code files
// are no longer mirrored in here — only the folder each project points at.
// ============================================================================

export type DomainSection =
  | "dashboard" | "projects" | "tasks" | "code" | "research" | "documents"
  | "notes" | "agents" | "terminal" | "history" | "settings";

export type ProjectStatus = "idea" | "progress" | "paused" | "completed";

export interface BoardCard {
  id: string;
  title: string;
  tag?: string;    // e.g. "ai", "ui", "core"
  agent?: string;  // model id working on it
  taskId?: string; // promoted into a Domain task — the two stay in step
  file?: string;   // absolute path this card is about; opens in Code
}
export interface BoardColumn {
  id: string;
  title: string;
  cards: BoardCard[];
}

/** A Domain task — project-scoped engineering work, separate from AURA's
 *  personal/life tasks that live in the Python store. */
export interface DomainTask {
  id: string;
  title: string;
  done: boolean;
  priority: "low" | "medium" | "high";
  tag?: string;
  due?: string;        // yyyy-mm-dd
  createdAt: number;
  doneAt?: number;
  cardId?: string;     // the board card this came from
  file?: string;       // absolute path this task is about; opens in Code
}

// ---- activity log ----------------------------------------------------------
export type ActivityKind =
  | "project" | "task" | "card" | "code" | "doc" | "note"
  | "roadmap" | "source" | "office" | "terminal";

export interface Activity {
  id: string;
  ts: number;
  kind: ActivityKind;
  projectId: string | null;
  projectName: string;
  summary: string;      // "Saved router.py"
  detail?: string;      // path, old → new, etc.
}

export interface MdDoc {
  id: string;
  name: string;
  content: string;
  updatedAt: number;
}

/** Notes are quick, timestamped thoughts — not documents, not research. */
export interface Note {
  id: string;
  body: string;
  pinned: boolean;
  color?: string;
  createdAt: number;
  updatedAt: number;
}

export type RoadmapState = "planned" | "active" | "shipped";
export interface RoadmapItem {
  id: string;
  title: string;
  detail?: string;
  state: RoadmapState;
  target?: string;     // "Q3", "Aug", a date — free text on purpose
}

/** A file or folder you explicitly picked into the Code pane. Only these show
 *  in the rail — the Domain never dumps your whole drive on screen. Saved with
 *  the project, so reopening AURA restores exactly your working set. */
export interface CodeSource {
  path: string;
  name: string;
  dir: boolean;
  lang?: string | null;
  addedAt: number;
}

/** What the Code pane had open for this project, restored on the way back.
 *  Only paths are stored — contents are re-read from disk, which keeps the
 *  saved state tiny and means you never reopen a stale copy of a file. */
export interface CodeSession {
  tabs: string[];
  active: string | null;
  expanded: string[];   // folders left open in the explorer
}

/** A file pulled in from Figma / Word / Excel / PowerPoint via a connector. */
export interface LinkedDoc {
  id: string;
  name: string;
  kind: "word" | "excel" | "powerpoint" | "figma" | "repo";
  url: string;
  provider: string;
  addedAt: number;
}

export interface Project {
  id: string;
  name: string;
  blurb: string;
  accent: string;          // hex used for glows / identity
  status: ProjectStatus;
  createdAt: number;
  repoUrl?: string;        // github.com/owner/repo — drives live vitals
  folder?: string;         // absolute local path opened by the Code pane
  tags: string[];
  board: BoardColumn[];
  tasks: DomainTask[];
  docs: MdDoc[];
  notes: Note[];
  roadmap: RoadmapItem[];
  linked: LinkedDoc[];
  sources: CodeSource[];
  session: CodeSession;
}

export const emptySession = (): CodeSession => ({ tabs: [], active: null, expanded: [] });

// ---- layout you can edit from Domain → Settings -----------------------------
export interface DomainLayout {
  navOrder: DomainSection[];
  hidden: DomainSection[];
  navWidth: number;        // px
  chatWidth: number;       // px
  density: "cosy" | "normal" | "compact";
  radius: number;          // px, panel corner rounding
  glass: number;           // 0..100 backdrop blur strength
  background: "video" | "gradient" | "flat";
  accent: string;
  showChat: boolean;
  showHeader: boolean;
}

export const ALL_SECTIONS: DomainSection[] = [
  "dashboard", "projects", "tasks", "code", "research",
  "documents", "notes", "agents", "terminal", "history", "settings",
];

export const SECTION_META: Record<DomainSection, { icon: string; label: string }> = {
  dashboard: { icon: "◈", label: "Dashboard" },
  projects: { icon: "▣", label: "Projects" },
  tasks: { icon: "☑", label: "Tasks" },
  code: { icon: "⌥", label: "Code" },
  research: { icon: "◎", label: "Research" },
  documents: { icon: "≡", label: "Documentation" },
  notes: { icon: "✎", label: "Notes" },
  agents: { icon: "✦", label: "AI Agents" },
  terminal: { icon: "❯", label: "Terminal" },
  history: { icon: "↺", label: "History" },
  settings: { icon: "⚙", label: "Settings" },
};

export const STATUS_META: Record<ProjectStatus, { label: string; color: string; icon: string }> = {
  idea: { label: "Idea", color: "#8b8fca", icon: "◌" },
  progress: { label: "In Progress", color: "#38e1ff", icon: "◐" },
  paused: { label: "Paused", color: "#ffb648", icon: "❙❙" },
  completed: { label: "Completed", color: "#35e08f", icon: "✓" },
};

export const DEFAULT_LAYOUT: DomainLayout = {
  navOrder: [...ALL_SECTIONS],
  hidden: [],
  navWidth: 216,
  chatWidth: 340,
  density: "normal",
  radius: 18,
  glass: 22,
  background: "video",
  accent: "#8b5cff",
  showChat: true,
  showHeader: true,
};

const uid = () => Math.random().toString(36).slice(2, 10);

/** How many activity entries History keeps before the oldest fall off. */
export const MAX_ACTIVITY = 500;

/**
 * Bring any stored project up to the current shape.
 *
 * This exists because a persisted blob can arrive from any past version of the
 * Domain — including ones written before `version` was even set, where zustand
 * hands `migrate` an undefined version and every `version < n` check quietly
 * evaluates false. Rather than trusting migrations to have run, every project
 * is normalized on the way in: a missing collection becomes an empty array,
 * never undefined. One missing field used to blank the whole workspace.
 */
function normalizeProject(p: any): Project {
  const legacyFiles: CodeSource[] = Array.isArray(p?.files)
    ? p.files
        .filter((f: any) => f?.name)
        .map((f: any) => ({
          path: f.path ?? f.name,
          name: f.name,
          dir: false,
          lang: f.lang ?? null,
          addedAt: Date.now(),
        }))
    : [];

  return {
    id: p?.id ?? uid(),
    name: p?.name ?? "Untitled project",
    blurb: p?.blurb ?? "",
    accent: p?.accent ?? ACCENTS[0],
    status: (["idea", "progress", "paused", "completed"] as const).includes(p?.status)
      ? p.status
      : "progress",
    createdAt: p?.createdAt ?? Date.now(),
    repoUrl: p?.repoUrl ?? "",
    folder: p?.folder ?? "",
    tags: Array.isArray(p?.tags) ? p.tags : [],
    board: Array.isArray(p?.board) && p.board.length
      ? p.board.map((c: any) => ({
          id: c?.id ?? uid(),
          title: c?.title ?? "Column",
          cards: Array.isArray(c?.cards) ? c.cards : [],
        }))
      : emptyBoard(),
    tasks: Array.isArray(p?.tasks) ? p.tasks : [],
    docs: Array.isArray(p?.docs)
      ? p.docs.map((d: any) => ({ ...d, updatedAt: d?.updatedAt ?? Date.now() }))
      : [],
    notes: Array.isArray(p?.notes) ? p.notes : [],
    roadmap: Array.isArray(p?.roadmap) ? p.roadmap : [],
    linked: Array.isArray(p?.linked) ? p.linked : [],
    session: {
      tabs: Array.isArray(p?.session?.tabs) ? p.session.tabs : [],
      active: typeof p?.session?.active === "string" ? p.session.active : null,
      expanded: Array.isArray(p?.session?.expanded) ? p.session.expanded : [],
    },
    sources: Array.isArray(p?.sources)
      ? p.sources
      : p?.folder
        ? [{
            path: p.folder,
            name: String(p.folder).split(/[\\/]/).filter(Boolean).pop() ?? p.folder,
            dir: true,
            addedAt: Date.now(),
          }, ...legacyFiles]
        : legacyFiles,
  };
}

/** Same idea for the top-level slice. */
function normalizeState(s: any): any {
  const projects = (Array.isArray(s?.projects) ? s.projects : []).map(normalizeProject);
  const known = new Set<DomainSection>(ALL_SECTIONS);
  return {
    ...s,
    projects: projects.length ? projects : [SEED],
    activeId:
      projects.find((p: Project) => p.id === s?.activeId)?.id ?? projects[0]?.id ?? SEED.id,
    section: known.has(s?.section) ? s.section : "dashboard",
    modelId: s?.modelId ?? "laguna",
    layout: { ...DEFAULT_LAYOUT, ...(s?.layout ?? {}) },
    activity: Array.isArray(s?.activity) ? s.activity : [],
    pendingFile: null,
  };
}

const emptyBoard = (): BoardColumn[] => [
  { id: "backlog", title: "Backlog", cards: [] },
  { id: "progress", title: "In Progress", cards: [] },
  { id: "review", title: "Review", cards: [] },
  { id: "done", title: "Done", cards: [] },
];

// ---- seed project so the Domain never opens empty --------------------------
const SEED: Project = {
  id: "aura-core",
  name: "AURA Core",
  blurb: "The companion itself — brain, face and voice.",
  accent: "#8b5cff",
  status: "progress",
  createdAt: Date.now(),
  repoUrl: "",
  folder: "",
  tags: ["ai", "desktop"],
  board: [
    {
      id: "backlog", title: "Backlog",
      cards: [
        { id: uid(), title: "Relationship surfacing in companion mode", tag: "ai" },
        { id: uid(), title: "Domain ↔ brain WebSocket bridge", tag: "core" },
      ],
    },
    {
      id: "progress", title: "In Progress",
      cards: [
        { id: uid(), title: "Domain workspace shell", tag: "ui", agent: "laguna" },
        { id: uid(), title: "Portal transition polish", tag: "ui", agent: "claude" },
      ],
    },
    {
      id: "review", title: "Review",
      cards: [{ id: uid(), title: "Error intelligence wiring", tag: "core", agent: "nemotron" }],
    },
    {
      id: "done", title: "Done",
      cards: [
        { id: uid(), title: "Scroll journey + sanctuary" },
        { id: uid(), title: "Universe video background" },
      ],
    },
  ],
  tasks: [
    { id: uid(), title: "Wire Code pane to the real filesystem", done: true, priority: "high", tag: "core", createdAt: Date.now(), doneAt: Date.now() },
    { id: uid(), title: "Terminal session persistence", done: false, priority: "medium", tag: "core", createdAt: Date.now() },
    { id: uid(), title: "Connector OAuth for Figma", done: false, priority: "low", tag: "integrations", createdAt: Date.now() },
  ],
  docs: [
    {
      id: uid(), name: "Domain vision", updatedAt: Date.now(), content:
`# AURA Domain

The primary productivity environment inside AURA.

Not a chatbot. Not a dashboard. An **AI-native operating environment** where:

- software engineering
- research
- creativity
- intelligent collaboration

merge into a single seamless workspace.

> "Now I'm inside AURA's brain."

## Principles

1. Everything belonging to one project stays together
2. The workspace adapts to what you are doing
3. AI collaboration is visible, never cluttered
`,
    },
  ],
  notes: [
    {
      id: uid(), pinned: true, createdAt: Date.now(), updatedAt: Date.now(),
      body: "Notes are for the half-formed thought you'd otherwise lose. Research is for sourced material — keep them apart.",
    },
  ],
  roadmap: [
    { id: uid(), title: "Domain shell + portal", state: "shipped", target: "Jul" },
    { id: uid(), title: "Real filesystem + terminal", state: "active", target: "Jul" },
    { id: uid(), title: "Connector-driven documentation", state: "active", target: "Aug" },
    { id: uid(), title: "Agent hand-off between panes", state: "planned", target: "Sep" },
  ],
  linked: [],
  sources: [],
  session: emptySession(),
};

interface DomainState {
  projects: Project[];
  activeId: string | null;
  section: DomainSection;
  modelId: string;
  layout: DomainLayout;
  activity: Activity[];
  /** Set by "open in Code" links; CodePane consumes it and clears it. */
  pendingFile: string | null;

  log: (kind: ActivityKind, summary: string, detail?: string) => void;
  clearActivity: () => void;
  openInCode: (path: string) => void;
  consumePendingFile: () => void;

  setSection: (s: DomainSection) => void;
  setModel: (id: string) => void;
  openProject: (id: string) => void;
  /** Open a project straight into a given section (dashboard → code/tasks). */
  openProjectAt: (id: string, section: DomainSection) => void;
  createProject: (name: string, blurb?: string) => void;
  deleteProject: (id: string) => void;
  patchProject: (id: string, patch: Partial<Project>) => void;
  setStatus: (id: string, status: ProjectStatus) => void;

  // layout
  setLayout: (patch: Partial<DomainLayout>) => void;
  toggleSection: (s: DomainSection) => void;
  moveSection: (s: DomainSection, dir: -1 | 1) => void;
  resetLayout: () => void;

  // board
  addCard: (colId: string, title: string) => void;
  moveCard: (cardId: string, toCol: string) => void;
  removeCard: (cardId: string) => void;

  // domain tasks
  addTask: (title: string, priority?: DomainTask["priority"], tag?: string, extra?: Partial<DomainTask>) => void;
  /** Board card → Domain task, linked both ways. */
  promoteCard: (cardId: string) => void;
  /** Domain task → board card in Backlog, linked both ways. */
  taskToCard: (taskId: string) => void;
  attachFileToCard: (cardId: string, path: string | undefined) => void;
  toggleTask: (taskId: string) => void;
  patchTask: (taskId: string, patch: Partial<DomainTask>) => void;
  removeTask: (taskId: string) => void;

  // docs / notes / roadmap / linked files
  addDoc: (name: string) => void;
  updateDoc: (docId: string, content: string) => void;
  renameDoc: (docId: string, name: string) => void;
  removeDoc: (docId: string) => void;

  addNote: (body?: string) => void;
  updateNote: (noteId: string, body: string) => void;
  pinNote: (noteId: string) => void;
  setNoteColor: (noteId: string, color: string) => void;
  removeNote: (noteId: string) => void;

  addRoadmap: (title: string, target?: string) => void;
  patchRoadmap: (itemId: string, patch: Partial<RoadmapItem>) => void;
  removeRoadmap: (itemId: string) => void;

  linkDoc: (doc: Omit<LinkedDoc, "addedAt">) => void;
  unlinkDoc: (docId: string) => void;

  addSource: (src: Omit<CodeSource, "addedAt">) => void;
  removeSource: (path: string) => void;
  /** Remember which files the Code pane had open for a project. */
  saveSession: (projectId: string, session: CodeSession) => void;
}

const ACCENTS = ["#8b5cff", "#38e1ff", "#f472b6", "#35e08f", "#ff8c42", "#4cc9ff"];

export const useDomainStore = create<DomainState>()(
  persist(
    (set, get) => {
      // helper: immutably patch the active project
      const patchActive = (fn: (p: Project) => Partial<Project>) => {
        const { activeId, projects } = get();
        if (!activeId) return;
        set({
          projects: projects.map((p) => (p.id === activeId ? { ...p, ...fn(p) } : p)),
        });
      };

      // helper: append to the activity log (newest first, capped)
      const log = (kind: ActivityKind, summary: string, detail?: string) => {
        const { activeId, projects, activity } = get();
        const project = projects.find((p) => p.id === activeId);
        const entry: Activity = {
          id: uid(),
          ts: Date.now(),
          kind,
          projectId: activeId,
          projectName: project?.name ?? "—",
          summary,
          detail,
        };
        set({ activity: [entry, ...activity].slice(0, MAX_ACTIVITY) });
      };

      return {
        projects: [SEED],
        activeId: SEED.id,
        section: "dashboard",
        modelId: "laguna",
        layout: { ...DEFAULT_LAYOUT },
        activity: [],
        pendingFile: null,

        log,
        clearActivity: () => set({ activity: [] }),

        // Jump to the Code pane with a specific file queued up. Used by the
        // dashboard, the board and tasks — anything that references a path.
        openInCode: (path) => set({ pendingFile: path, section: "code" }),
        consumePendingFile: () => set({ pendingFile: null }),

        setSection: (section) => set({ section }),
        setModel: (modelId) => set({ modelId }),
        openProject: (id) => set({ activeId: id, section: "projects" }),
        openProjectAt: (id, section) => set({ activeId: id, section }),

        createProject: (name, blurb = "A new idea takes form.") => {
          const p: Project = {
            id: uid(),
            name,
            blurb,
            accent: ACCENTS[get().projects.length % ACCENTS.length],
            status: "idea",
            createdAt: Date.now(),
            tags: [],
            board: emptyBoard(),
            tasks: [],
            docs: [],
            notes: [],
            roadmap: [],
            linked: [],
            sources: [],
            session: emptySession(),
          };
          set({ projects: [...get().projects, p], activeId: p.id, section: "projects" });
          log("project", `Created project "${name}"`);
        },

        deleteProject: (id) => {
          const gone = get().projects.find((p) => p.id === id);
          const rest = get().projects.filter((p) => p.id !== id);
          set({
            projects: rest,
            activeId: get().activeId === id ? rest[0]?.id ?? null : get().activeId,
          });
          if (gone) log("project", `Deleted project "${gone.name}"`);
        },

        patchProject: (id, patch) => {
          const before = get().projects.find((p) => p.id === id);
          set({ projects: get().projects.map((p) => (p.id === id ? { ...p, ...patch } : p)) });
          if (before && patch.repoUrl !== undefined && patch.repoUrl !== before.repoUrl)
            log("project", `Linked repo for "${before.name}"`, patch.repoUrl || "(cleared)");
        },

        setStatus: (id, status) => {
          const before = get().projects.find((p) => p.id === id);
          set({ projects: get().projects.map((p) => (p.id === id ? { ...p, status } : p)) });
          if (before && before.status !== status)
            log(
              "project",
              `"${before.name}" → ${STATUS_META[status].label}`,
              `was ${STATUS_META[before.status].label}`
            );
        },

        // ---- layout ---------------------------------------------------------
        setLayout: (patch) => set({ layout: { ...get().layout, ...patch } }),

        toggleSection: (s) => {
          if (s === "dashboard" || s === "settings") return; // always reachable
          const hidden = get().layout.hidden;
          set({
            layout: {
              ...get().layout,
              hidden: hidden.includes(s) ? hidden.filter((x) => x !== s) : [...hidden, s],
            },
          });
        },

        moveSection: (s, dir) => {
          const order = [...get().layout.navOrder];
          const i = order.indexOf(s);
          const jdx = i + dir;
          if (i < 0 || jdx < 0 || jdx >= order.length) return;
          [order[i], order[jdx]] = [order[jdx], order[i]];
          set({ layout: { ...get().layout, navOrder: order } });
        },

        resetLayout: () => set({ layout: { ...DEFAULT_LAYOUT } }),

        // ---- board ----------------------------------------------------------
        addCard: (colId, title) => {
          patchActive((p) => ({
            board: p.board.map((c) =>
              c.id === colId ? { ...c, cards: [...c.cards, { id: uid(), title }] } : c
            ),
          }));
          log("card", `Added card "${title}"`);
        },

        moveCard: (cardId, toCol) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const card = proj?.board.flatMap((c) => c.cards).find((k) => k.id === cardId);
          const target = proj?.board.find((c) => c.id === toCol);

          patchActive((p) => {
            let moved: BoardCard | undefined;
            const stripped = p.board.map((c) => {
              const hit = c.cards.find((k) => k.id === cardId);
              if (hit) moved = hit;
              return { ...c, cards: c.cards.filter((k) => k.id !== cardId) };
            });
            if (!moved) return {};

            // A card that owns a task keeps it in step: landing in Done ticks
            // the task off, leaving Done reopens it.
            const tasks = moved.taskId
              ? p.tasks.map((t) =>
                  t.id === moved!.taskId
                    ? {
                        ...t,
                        done: toCol === "done",
                        doneAt: toCol === "done" ? Date.now() : undefined,
                      }
                    : t
                )
              : p.tasks;

            return {
              tasks,
              board: stripped.map((c) =>
                c.id === toCol ? { ...c, cards: [...c.cards, moved!] } : c
              ),
            };
          });

          if (card && target) log("card", `"${card.title}" → ${target.title}`);
        },

        removeCard: (cardId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const card = proj?.board.flatMap((c) => c.cards).find((k) => k.id === cardId);
          patchActive((p) => ({
            board: p.board.map((c) => ({ ...c, cards: c.cards.filter((k) => k.id !== cardId) })),
            // the linked task survives, it just loses its card
            tasks: p.tasks.map((t) => (t.cardId === cardId ? { ...t, cardId: undefined } : t)),
          }));
          if (card) log("card", `Removed card "${card.title}"`);
        },

        // ---- card ↔ task ↔ file links ---------------------------------------
        promoteCard: (cardId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const card = proj?.board.flatMap((c) => c.cards).find((k) => k.id === cardId);
          if (!card || card.taskId) return;
          const taskId = uid();
          patchActive((p) => ({
            tasks: [
              {
                id: taskId, title: card.title, done: false, priority: "medium",
                tag: card.tag, createdAt: Date.now(), cardId, file: card.file,
              },
              ...p.tasks,
            ],
            board: p.board.map((c) => ({
              ...c,
              cards: c.cards.map((k) => (k.id === cardId ? { ...k, taskId } : k)),
            })),
          }));
          log("task", `Card "${card.title}" became a task`);
        },

        taskToCard: (taskId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const task = proj?.tasks.find((t) => t.id === taskId);
          if (!task || task.cardId) return;
          const cardId = uid();
          patchActive((p) => ({
            board: p.board.map((c) =>
              c.id === "backlog"
                ? {
                    ...c,
                    cards: [
                      ...c.cards,
                      { id: cardId, title: task.title, tag: task.tag, taskId, file: task.file },
                    ],
                  }
                : c
            ),
            tasks: p.tasks.map((t) => (t.id === taskId ? { ...t, cardId } : t)),
          }));
          log("card", `Task "${task.title}" added to the board`);
        },

        attachFileToCard: (cardId, path) => {
          patchActive((p) => ({
            board: p.board.map((c) => ({
              ...c,
              cards: c.cards.map((k) => (k.id === cardId ? { ...k, file: path } : k)),
            })),
            tasks: p.tasks.map((t) => (t.cardId === cardId ? { ...t, file: path } : t)),
          }));
          if (path) log("code", "Linked a file to a card", path);
        },

        // ---- domain tasks ---------------------------------------------------
        addTask: (title, priority = "medium", tag, extra) => {
          patchActive((p) => ({
            tasks: [
              { id: uid(), title, done: false, priority, tag, createdAt: Date.now(), ...extra },
              ...p.tasks,
            ],
          }));
          log("task", `Added task "${title}"`);
        },

        toggleTask: (taskId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const task = proj?.tasks.find((t) => t.id === taskId);

          patchActive((p) => {
            const hit = p.tasks.find((t) => t.id === taskId);
            const nowDone = hit ? !hit.done : false;
            return {
              tasks: p.tasks.map((t) =>
                t.id === taskId
                  ? { ...t, done: nowDone, doneAt: nowDone ? Date.now() : undefined }
                  : t
              ),
              // ticking a task moves its card to Done (and back to Progress)
              board: hit?.cardId
                ? (() => {
                    let moved: BoardCard | undefined;
                    const stripped = p.board.map((c) => {
                      const found = c.cards.find((k) => k.id === hit.cardId);
                      if (found) moved = found;
                      return { ...c, cards: c.cards.filter((k) => k.id !== hit.cardId) };
                    });
                    if (!moved) return p.board;
                    const target = nowDone ? "done" : "progress";
                    return stripped.map((c) =>
                      c.id === target ? { ...c, cards: [...c.cards, moved!] } : c
                    );
                  })()
                : p.board,
            };
          });

          if (task) log("task", `${task.done ? "Reopened" : "Completed"} "${task.title}"`);
        },

        patchTask: (taskId, patch) => {
          patchActive((p) => ({
            tasks: p.tasks.map((t) => (t.id === taskId ? { ...t, ...patch } : t)),
            // keep a linked card's title in step with its task
            board: patch.title
              ? p.board.map((c) => ({
                  ...c,
                  cards: c.cards.map((k) =>
                    k.taskId === taskId ? { ...k, title: patch.title! } : k
                  ),
                }))
              : p.board,
          }));
          if (patch.title) log("task", `Renamed a task`, patch.title);
        },

        removeTask: (taskId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const task = proj?.tasks.find((t) => t.id === taskId);
          patchActive((p) => ({
            tasks: p.tasks.filter((t) => t.id !== taskId),
            board: p.board.map((c) => ({
              ...c,
              cards: c.cards.map((k) => (k.taskId === taskId ? { ...k, taskId: undefined } : k)),
            })),
          }));
          if (task) log("task", `Deleted task "${task.title}"`);
        },

        // ---- docs -----------------------------------------------------------
        addDoc: (name) => {
          patchActive((p) => ({
            docs: [
              ...p.docs,
              { id: uid(), name, content: `# ${name}\n\n`, updatedAt: Date.now() },
            ],
          }));
          log("doc", `Created doc "${name}"`);
        },

        updateDoc: (docId, content) =>
          patchActive((p) => ({
            docs: p.docs.map((d) =>
              d.id === docId ? { ...d, content, updatedAt: Date.now() } : d
            ),
          })),

        renameDoc: (docId, name) =>
          patchActive((p) => ({
            docs: p.docs.map((d) => (d.id === docId ? { ...d, name } : d)),
          })),

        removeDoc: (docId) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const doc = proj?.docs.find((d) => d.id === docId);
          patchActive((p) => ({ docs: p.docs.filter((d) => d.id !== docId) }));
          if (doc) log("doc", `Deleted doc "${doc.name}"`);
        },

        // ---- notes ----------------------------------------------------------
        addNote: (body = "") =>
          patchActive((p) => ({
            notes: [
              { id: uid(), body, pinned: false, createdAt: Date.now(), updatedAt: Date.now() },
              ...p.notes,
            ],
          })),

        updateNote: (noteId, body) =>
          patchActive((p) => ({
            notes: p.notes.map((n) =>
              n.id === noteId ? { ...n, body, updatedAt: Date.now() } : n
            ),
          })),

        pinNote: (noteId) =>
          patchActive((p) => ({
            notes: p.notes.map((n) => (n.id === noteId ? { ...n, pinned: !n.pinned } : n)),
          })),

        setNoteColor: (noteId, color) =>
          patchActive((p) => ({
            notes: p.notes.map((n) => (n.id === noteId ? { ...n, color } : n)),
          })),

        removeNote: (noteId) =>
          patchActive((p) => ({ notes: p.notes.filter((n) => n.id !== noteId) })),

        // ---- roadmap --------------------------------------------------------
        addRoadmap: (title, target) => {
          patchActive((p) => ({
            roadmap: [...p.roadmap, { id: uid(), title, state: "planned", target }],
          }));
          log("roadmap", `Planned "${title}"`, target);
        },

        patchRoadmap: (itemId, patch) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const item = proj?.roadmap.find((r) => r.id === itemId);
          patchActive((p) => ({
            roadmap: p.roadmap.map((r) => (r.id === itemId ? { ...r, ...patch } : r)),
          }));
          if (item && patch.state && patch.state !== item.state)
            log("roadmap", `"${item.title}" → ${patch.state}`);
        },

        removeRoadmap: (itemId) =>
          patchActive((p) => ({ roadmap: p.roadmap.filter((r) => r.id !== itemId) })),

        // ---- linked connector docs ------------------------------------------
        linkDoc: (doc) =>
          patchActive((p) =>
            p.linked.some((l) => l.id === doc.id)
              ? {}
              : { linked: [...p.linked, { ...doc, addedAt: Date.now() }] }
          ),

        unlinkDoc: (docId) =>
          patchActive((p) => ({ linked: p.linked.filter((l) => l.id !== docId) })),

        // ---- code sources (the picked working set) ---------------------------
        addSource: (src) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          if (proj?.sources.some((s) => s.path === src.path)) return;
          patchActive((p) => ({ sources: [...p.sources, { ...src, addedAt: Date.now() }] }));
          log("source", `Added ${src.dir ? "folder" : "file"} "${src.name}"`, src.path);
        },

        removeSource: (path) => {
          const proj = get().projects.find((p) => p.id === get().activeId);
          const src = proj?.sources.find((s) => s.path === path);
          patchActive((p) => ({
            sources: p.sources.filter((s) => s.path !== path),
            // drop anything under it from the remembered session too
            session: {
              tabs: p.session.tabs.filter((t) => !t.startsWith(path)),
              active: p.session.active?.startsWith(path) ? null : p.session.active,
              expanded: p.session.expanded.filter((e) => !e.startsWith(path)),
            },
          }));
          if (src) log("source", `Removed "${src.name}" from the working set`, path);
        },

        // No logging here: this fires as you click around the editor, and the
        // History log is for changes you made, not windows you opened.
        saveSession: (projectId, session) =>
          set({
            projects: get().projects.map((p) =>
              p.id === projectId ? { ...p, session } : p
            ),
          }),
      };
    },
    {
      name: "aura.domain",
      version: 5,

      // Belt and braces: whatever migrate did or didn't do, the state that
      // reaches the app is always complete. A blob written before `version`
      // existed skips every migration, which is exactly how the Domain ended
      // up rendering a blank screen.
      merge: (persisted, current) => ({ ...current, ...normalizeState(persisted) }),
      // Backfill for older blobs. `merge` above already guarantees a valid
      // shape, so this only needs to handle genuine semantic changes.
      // Note the ?? 0: a pre-versioning blob arrives as undefined, and every
      // `undefined < n` comparison is false — that's the bug that blanked the
      // Domain, so the version is coerced before anything is compared.
      migrate: (state: any, version: number) => {
        if (!state) return state;
        version = version ?? 0;
        if (version < 2) {
          state.layout = { ...DEFAULT_LAYOUT };
          state.projects = (state.projects ?? []).map((p: any) => ({
            ...p,
            status: p.status ?? "progress",
            tags: p.tags ?? [],
            tasks: p.tasks ?? [],
            notes: p.notes ?? [],
            roadmap: p.roadmap ?? [],
            linked: p.linked ?? [],
            docs: (p.docs ?? []).map((d: any) => ({ ...d, updatedAt: d.updatedAt ?? Date.now() })),
          }));
          if (state.section === "images") state.section = "dashboard";
        }
        if (version < 3) {
          // Code went from "browse the whole drive" to "only what you picked".
          // Seed each project's working set with the folder it already had.
          state.projects = (state.projects ?? []).map((p: any) => ({
            ...p,
            sources:
              p.sources ??
              (p.folder
                ? [{
                    path: p.folder,
                    name: String(p.folder).split(/[\\/]/).filter(Boolean).pop() ?? p.folder,
                    dir: true,
                    addedAt: Date.now(),
                  }]
                : []),
          }));
        }
        if (version < 4) {
          state.activity = state.activity ?? [];
          state.pendingFile = null;
        }
        return state;
      },
    }
  )
);

export const useActiveProject = () =>
  useDomainStore((s) => s.projects.find((p) => p.id === s.activeId) ?? null);
