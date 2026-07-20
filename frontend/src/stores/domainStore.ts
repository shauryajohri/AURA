import { create } from "zustand";
import { persist } from "zustand/middleware";

// ============================================================================
// AURA Domain — project system store.
// Everything belonging to one project (board, code, docs, notes) lives
// together. Persisted locally for now; the Python brain plugs in later.
// ============================================================================

export type DomainSection =
  | "dashboard" | "projects" | "code" | "research" | "documents"
  | "images" | "notes" | "agents" | "terminal" | "history";

export interface BoardCard {
  id: string;
  title: string;
  tag?: string;    // e.g. "ai", "ui", "core"
  agent?: string;  // model id working on it
}
export interface BoardColumn {
  id: string;
  title: string;
  cards: BoardCard[];
}
export interface CodeFile {
  id: string;
  name: string;
  lang: "ts" | "js" | "py" | "css" | "json" | "txt";
  content: string;
}
export interface MdDoc {
  id: string;
  name: string;
  content: string;
}
export interface Project {
  id: string;
  name: string;
  blurb: string;
  accent: string; // hex used for glows / identity
  createdAt: number;
  board: BoardColumn[];
  files: CodeFile[];
  docs: MdDoc[];
}

const uid = () => Math.random().toString(36).slice(2, 10);

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
  createdAt: Date.now(),
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
  files: [
    {
      id: uid(), name: "router.py", lang: "py",
      content:
`# AURA model router — picks the right mind for the moment.
from core.models import MODELS

def route(intent: str, locked: set[str]) -> str:
    """Choose a model id for this intent, honouring cosmos locks."""
    ranked = sorted(MODELS, key=lambda m: m.score(intent))
    for model in ranked:
        if model.id not in locked:
            return model.id
    return "llama8b"  # the archivist never sleeps
`,
    },
    {
      id: uid(), name: "domainStore.ts", lang: "ts",
      content:
`// Everything belonging to one project stays together.
export interface Project {
  id: string;
  name: string;
  board: BoardColumn[];
  files: CodeFile[];
  docs: MdDoc[];
}
`,
    },
  ],
  docs: [
    {
      id: uid(), name: "Domain vision", content:
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
};

interface DomainState {
  projects: Project[];
  activeId: string | null;
  section: DomainSection;
  modelId: string; // currently selected AI model

  setSection: (s: DomainSection) => void;
  setModel: (id: string) => void;
  openProject: (id: string) => void;
  createProject: (name: string, blurb?: string) => void;
  deleteProject: (id: string) => void;
  patchProject: (id: string, patch: Partial<Project>) => void;

  addCard: (colId: string, title: string) => void;
  moveCard: (cardId: string, toCol: string) => void;
  removeCard: (cardId: string) => void;

  addFile: (name: string) => void;
  updateFile: (fileId: string, content: string) => void;
  addDoc: (name: string) => void;
  updateDoc: (docId: string, content: string) => void;
}

const ACCENTS = ["#8b5cff", "#38e1ff", "#f472b6", "#35e08f", "#ff8c42", "#4cc9ff"];

const langOf = (name: string): CodeFile["lang"] => {
  const ext = name.split(".").pop() || "";
  if (ext === "ts" || ext === "tsx") return "ts";
  if (ext === "js" || ext === "jsx") return "js";
  if (ext === "py") return "py";
  if (ext === "css") return "css";
  if (ext === "json") return "json";
  return "txt";
};

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

      return {
        projects: [SEED],
        activeId: SEED.id,
        section: "dashboard",
        modelId: "laguna",

        setSection: (section) => set({ section }),
        setModel: (modelId) => set({ modelId }),
        openProject: (id) => set({ activeId: id, section: "projects" }),

        createProject: (name, blurb = "A new idea takes form.") => {
          const p: Project = {
            id: uid(),
            name,
            blurb,
            accent: ACCENTS[get().projects.length % ACCENTS.length],
            createdAt: Date.now(),
            board: emptyBoard(),
            files: [],
            docs: [],
          };
          set({ projects: [...get().projects, p], activeId: p.id, section: "projects" });
        },

        deleteProject: (id) => {
          const rest = get().projects.filter((p) => p.id !== id);
          set({
            projects: rest,
            activeId: get().activeId === id ? rest[0]?.id ?? null : get().activeId,
          });
        },

        patchProject: (id, patch) =>
          set({ projects: get().projects.map((p) => (p.id === id ? { ...p, ...patch } : p)) }),

        addCard: (colId, title) =>
          patchActive((p) => ({
            board: p.board.map((c) =>
              c.id === colId ? { ...c, cards: [...c.cards, { id: uid(), title }] } : c
            ),
          })),

        moveCard: (cardId, toCol) =>
          patchActive((p) => {
            let moved: BoardCard | undefined;
            const stripped = p.board.map((c) => {
              const hit = c.cards.find((k) => k.id === cardId);
              if (hit) moved = hit;
              return { ...c, cards: c.cards.filter((k) => k.id !== cardId) };
            });
            if (!moved) return {};
            return {
              board: stripped.map((c) =>
                c.id === toCol ? { ...c, cards: [...c.cards, moved!] } : c
              ),
            };
          }),

        removeCard: (cardId) =>
          patchActive((p) => ({
            board: p.board.map((c) => ({ ...c, cards: c.cards.filter((k) => k.id !== cardId) })),
          })),

        addFile: (name) =>
          patchActive((p) => ({
            files: [...p.files, { id: uid(), name, lang: langOf(name), content: "" }],
          })),

        updateFile: (fileId, content) =>
          patchActive((p) => ({
            files: p.files.map((f) => (f.id === fileId ? { ...f, content } : f)),
          })),

        addDoc: (name) =>
          patchActive((p) => ({
            docs: [...p.docs, { id: uid(), name, content: `# ${name}\n\n` }],
          })),

        updateDoc: (docId, content) =>
          patchActive((p) => ({
            docs: p.docs.map((d) => (d.id === docId ? { ...d, content } : d)),
          })),
      };
    },
    { name: "aura.domain" }
  )
);

export const useActiveProject = () =>
  useDomainStore((s) => s.projects.find((p) => p.id === s.activeId) ?? null);
