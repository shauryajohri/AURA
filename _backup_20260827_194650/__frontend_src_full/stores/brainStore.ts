import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  brainApi,
  type BrainEdge,
  type BrainNode,
  type BrainProject,
  type Dashboard,
  type Progress,
  type TaskState,
  type TimelineEvent,
} from "../brainApi";

// ============================================================================
// brainStore — the live mirror of the Project Brain.
//
// Only the *selection* is persisted (which project you were in, which node the
// drawer had open). Everything else is server truth, re-fetched on entry, so
// the UI can never show a graph that disagrees with SQLite.
//
// One rule throughout: any mutation that changes the graph calls refresh() for
// the affected slices rather than patching local copies. The brain derives
// progress and edges server-side; guessing them here would drift.
// ============================================================================

interface BrainState {
  // ---- selection (persisted) ----
  activeId: string | null;
  openNodeId: string | null;
  useLlm: boolean;

  // ---- server truth ----
  projects: BrainProject[];
  dashboard: Dashboard | null;
  progress: Progress | null;
  nodes: BrainNode[];
  edges: BrainEdge[];
  timeline: TimelineEvent[];

  // ---- transient ----
  loading: boolean;
  busy: string | null;      // label of whatever long call is in flight
  error: string | null;
  reachable: boolean;       // false once a fetch fails — views show "brain offline"

  // ---- actions ----
  select: (pid: string | null) => Promise<void>;
  openNode: (nid: string | null) => void;
  setUseLlm: (v: boolean) => void;

  loadProjects: () => Promise<void>;
  refresh: () => Promise<void>;
  refreshGraph: () => Promise<void>;

  createProject: (name: string) => Promise<string | null>;
  importFolder: (root: string, name?: string) => Promise<string | null>;
  importRepo: (fullName: string, cloneUrl?: string) => Promise<string | null>;
  deleteProject: (pid: string) => Promise<void>;
  rescan: () => Promise<string>;

  capture: (text: string, featureId?: string) => Promise<any>;
  expandTask: (tid: string) => Promise<any>;
  setTaskStatus: (tid: string, status: TaskState, reason?: string) => Promise<void>;

  clearError: () => void;
}

const fail = (set: any, e: unknown, label: string) => {
  const msg = e instanceof Error ? e.message : String(e);
  const offline = /fetch|network|load failed/i.test(msg);
  set({
    error: offline ? "Project Brain unreachable — is AURA's server running?" : `${label}: ${msg}`,
    reachable: !offline,
    loading: false,
    busy: null,
  });
};

export const useBrainStore = create<BrainState>()(
  persist(
    (set, get) => ({
      activeId: null,
      openNodeId: null,
      useLlm: true,

      projects: [],
      dashboard: null,
      progress: null,
      nodes: [],
      edges: [],
      timeline: [],

      loading: false,
      busy: null,
      error: null,
      reachable: true,

      setUseLlm: (v) => set({ useLlm: v }),
      openNode: (nid) => set({ openNodeId: nid }),
      clearError: () => set({ error: null }),

      async loadProjects() {
        try {
          const r = await brainApi.projects();
          const projects = r.projects ?? [];
          set({ projects, reachable: true, error: null });
          // keep the persisted selection only if it still exists server-side
          const { activeId } = get();
          if (activeId && !projects.some((p) => p.id === activeId)) {
            set({ activeId: null, dashboard: null, progress: null, nodes: [], edges: [], timeline: [] });
          } else if (activeId) {
            await get().refresh();
          }
        } catch (e) {
          fail(set, e, "load projects");
        }
      },

      async select(pid) {
        set({ activeId: pid, openNodeId: null });
        if (!pid) {
          set({ dashboard: null, progress: null, nodes: [], edges: [], timeline: [] });
          return;
        }
        await get().refresh();
      },

      /** Everything for the active project, in one round of parallel calls. */
      async refresh() {
        const pid = get().activeId;
        if (!pid) return;
        set({ loading: true });
        try {
          const [dash, graph, tl] = await Promise.all([
            brainApi.dashboard(pid),
            brainApi.graph(pid),
            brainApi.timeline(pid, 200),
          ]);
          set({
            dashboard: dash.ok ? dash : null,
            progress: dash.ok ? dash.progress ?? null : null,
            nodes: graph.nodes ?? [],
            edges: graph.edges ?? [],
            timeline: tl.events ?? [],
            loading: false,
            reachable: true,
            error: dash.ok ? null : dash.error ?? null,
          });
        } catch (e) {
          fail(set, e, "refresh");
        }
      },

      /** Graph + progress only — cheaper than refresh() after a task edit. */
      async refreshGraph() {
        const pid = get().activeId;
        if (!pid) return;
        try {
          const [graph, prog] = await Promise.all([
            brainApi.graph(pid),
            brainApi.progress(pid),
          ]);
          set({
            nodes: graph.nodes ?? [],
            edges: graph.edges ?? [],
            progress: prog.ok ? (prog as Progress) : get().progress,
            reachable: true,
          });
        } catch (e) {
          fail(set, e, "refresh graph");
        }
      },

      async createProject(name) {
        set({ busy: "Creating project…" });
        try {
          const r = await brainApi.createProject(name);
          set({ busy: null });
          if (!r.ok || !r.project) {
            set({ error: r.error ?? "could not create project" });
            return null;
          }
          await get().loadProjects();
          await get().select(r.project.id);
          return r.project.id;
        } catch (e) {
          fail(set, e, "create project");
          return null;
        }
      },

      async importFolder(root, name) {
        set({ busy: "Reading the folder — analysing code and git history…" });
        try {
          const r = await brainApi.importFolder(root, name ?? "");
          set({ busy: null });
          if (!r.ok || !r.project) {
            set({ error: r.error ?? "import failed" });
            return null;
          }
          await get().loadProjects();
          await get().select(r.project.id);
          return r.project.id;
        } catch (e) {
          fail(set, e, "import folder");
          return null;
        }
      },

      async importRepo(fullName, cloneUrl) {
        set({ busy: `Cloning ${fullName}…` });
        try {
          const r = await brainApi.ghImport(fullName, { clone_url: cloneUrl });
          set({ busy: null });
          if (!r.ok || !r.project) {
            set({ error: r.error ?? "GitHub import failed" });
            return null;
          }
          await get().loadProjects();
          await get().select(r.project.id);
          return r.project.id;
        } catch (e) {
          fail(set, e, "github import");
          return null;
        }
      },

      async deleteProject(pid) {
        try {
          await brainApi.deleteProject(pid);
          if (get().activeId === pid) {
            set({ activeId: null, dashboard: null, progress: null, nodes: [], edges: [], timeline: [] });
          }
          await get().loadProjects();
        } catch (e) {
          fail(set, e, "delete project");
        }
      },

      /** Module 7: re-read local git, fold new commits in, auto-close tasks. */
      async rescan() {
        const pid = get().activeId;
        if (!pid) return "No project selected.";
        set({ busy: "Reading git history…" });
        try {
          const r = await brainApi.rescan(pid);
          set({ busy: null });
          if (!r.ok) {
            set({ error: r.error ?? "rescan failed" });
            return r.error ?? "rescan failed";
          }
          await get().refresh();
          const i = r.imported ?? {};
          const bits = Object.entries(i)
            .filter(([, n]) => Number(n) > 0)
            .map(([k, n]) => `${n} ${k}`);
          return bits.length ? "Folded in " + bits.join(", ") + "." : "Already up to date.";
        } catch (e) {
          fail(set, e, "rescan");
          return "Rescan failed.";
        }
      },

      /** Modules 2–4: one utterance in, structured knowledge out. */
      async capture(text, featureId) {
        const pid = get().activeId;
        if (!pid) return { ok: false, error: "no project selected" };
        set({ busy: "Thinking…" });
        try {
          const r = await brainApi.capture(pid, text, {
            feature_id: featureId,
            use_llm: get().useLlm,
          });
          set({ busy: null });
          if (r.ok) await get().refresh();
          else set({ error: r.error ?? null });
          return r;
        } catch (e) {
          fail(set, e, "capture");
          return { ok: false, error: "capture failed" };
        }
      },

      async expandTask(tid) {
        const pid = get().activeId;
        if (!pid) return { ok: false };
        set({ busy: "Breaking that down…" });
        try {
          const r = await brainApi.expandTask(pid, tid, get().useLlm);
          set({ busy: null });
          if (r.ok) await get().refreshGraph();
          else set({ error: r.error ?? null });
          return r;
        } catch (e) {
          fail(set, e, "expand task");
          return { ok: false };
        }
      },

      async setTaskStatus(tid, status, reason) {
        const pid = get().activeId;
        if (!pid) return;
        // optimistic: the board should not lag a click
        set({
          nodes: get().nodes.map((n) => (n.id === tid ? { ...n, status } : n)),
        });
        try {
          const r = await brainApi.setTaskStatus(pid, tid, status, reason ?? "");
          if (!r.ok) set({ error: r.error ?? "could not update task" });
          await get().refreshGraph();
        } catch (e) {
          fail(set, e, "task status");
          await get().refreshGraph();
        }
      },
    }),
    {
      name: "aura.brain",
      version: 1,
      partialize: (s) => ({
        activeId: s.activeId,
        openNodeId: s.openNodeId,
        useLlm: s.useLlm,
      }),
    }
  )
);

// ---- selectors views share --------------------------------------------------

/** Nodes of one type, in graph order. */
export const nodesOfType = (nodes: BrainNode[], type: string) =>
  nodes.filter((n) => n.type === type);

/** task id -> feature id, from belongs_to edges (tasks point at their feature). */
export function taskFeatureMap(edges: BrainEdge[]): Record<string, string> {
  const m: Record<string, string> = {};
  for (const e of edges) if (e.type === "belongs_to") m[e.src] = e.dst;
  return m;
}

export const nodeById = (nodes: BrainNode[], id: string | null) =>
  (id ? nodes.find((n) => n.id === id) ?? null : null);
