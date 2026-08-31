// ============================================================================
// brainApi — the REST client for AURA Domain's Project Brain (core/domain/*).
//
// This is the *knowledge* half of the Domain backend: projects, the node/edge
// graph, idea capture, planning, progress and the ask-anything endpoint.
// (domainApi.ts remains the *machine* half: filesystem, shell, office, git.)
//
// Every shape here mirrors what core/domain returns verbatim — nodes carry a
// free-form `meta`, so views read meta fields defensively rather than assuming.
// ============================================================================
const BASE = "http://127.0.0.1:8760";

export type NodeType =
  | "project" | "idea" | "discussion" | "decision" | "feature"
  | "task" | "file" | "commit" | "test" | "milestone";

export type TaskState =
  | "planning" | "todo" | "in_progress" | "blocked" | "done" | "rejected";

export const TASK_STATES: TaskState[] = [
  "todo", "in_progress", "blocked", "done", "rejected",
];

export type EdgeType =
  | "led_to" | "belongs_to" | "implements" | "affects" | "completes"
  | "depends_on" | "rejected_alt" | "relates_to" | "authored";

export interface BrainNode {
  id: string;
  project: string;
  type: NodeType;
  title: string;
  body: string;
  status: string;
  meta: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface BrainEdge {
  id: string;
  project: string;
  src: string;
  dst: string;
  type: EdgeType;
  meta: Record<string, any>;
  created_at: string;
}

export interface BrainProject {
  id: string;
  name: string;
  root: string;
  repo_url: string;
  meta: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface FeatureProgress {
  feature_id: string;
  feature: string;
  status: string;
  total: number;
  completed: number;
  percent: number;
}

export interface Blocker {
  id: string;
  title: string;
  dependents: number;
  reason: string;
}

export interface Progress {
  project: string;
  percent: number;
  total: number;
  completed: number;
  in_progress: number;
  blocked: number;
  remaining: number;
  rejected: number;
  biggest_blocker: Blocker | null;
  by_feature: FeatureProgress[];
  summary: string;
}

export interface TimelineEvent {
  id: string;
  type: NodeType;
  title: string;
  when: string | null;
  status: string;
}

export interface Dashboard {
  ok: boolean;
  error?: string;
  project?: BrainProject;
  counts?: Record<string, number>;
  progress?: Progress;
  recent?: TimelineEvent[];
}

/** What /capture reports back — the UI shows it as "here's what I understood". */
export interface CaptureResult {
  ok: boolean;
  error?: string;
  kind?: "feature" | "decision" | "edit" | "note";
  source?: string;
  node_id?: string;
  feature?: {
    id: string;
    title: string;
    priority: string;
    category: string;
    description: string;
  };
  tasks?: { id: string; title: string }[];
  decision?: { topic: string; choice: string; reason: string; source?: string };
  // apply_edit spreads its own keys through
  task_id?: string;
  old?: string;
  new?: string;
}

export interface WhyResult {
  ok: boolean;
  error?: string;
  node?: BrainNode;
  chain?: BrainNode[];
  narrative?: string;
  rejected_alternatives?: string[];
}

export interface RelatedResult {
  ok: boolean;
  node_id?: string;
  related?: Record<string, { id: string; type: NodeType; title: string }[]>;
}

export interface AskResult {
  ok: boolean;
  error?: string;
  answer?: string;
  grounded_in?: string;
  source?: "llm" | "context-only";
}

export interface PlanResult {
  ok: boolean;
  error?: string;
  feature?: string | { id: string; title: string };
  title?: string;
  description?: string;
  priority?: string;
  category?: string;
  tasks?: any[];
  source?: string;
}

export interface GhRepo {
  full_name: string;
  name: string;
  clone_url?: string;
  description?: string | null;
  private?: boolean;
  language?: string | null;
  default_branch?: string;
  updated_at?: string;
  html_url?: string;
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return (await res.json()) as T;
}

const post = <T,>(path: string, body?: unknown) =>
  j<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

const q = (o: Record<string, string | number | boolean | undefined>) => {
  const parts = Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? "?" + parts.join("&") : "";
};

export const brainApi = {
  // ---- projects (Module 1) ------------------------------------------------
  projects: () => j<{ ok: boolean; projects: BrainProject[] }>("/api/domain/projects"),
  createProject: (name: string, root = "", repo_url = "") =>
    post<{ ok: boolean; error?: string; project?: BrainProject }>(
      "/api/domain/projects", { name, root, repo_url }
    ),
  importFolder: (root: string, name = "") =>
    post<{ ok: boolean; error?: string; project?: BrainProject; analysis?: any; git?: any }>(
      "/api/domain/projects/import", { root, name }
    ),
  deleteProject: (pid: string) =>
    j<{ ok: boolean }>(`/api/domain/project/${pid}`, { method: "DELETE" }),

  // ---- vitals (Modules 8 + 14) -------------------------------------------
  dashboard: (pid: string) => j<Dashboard>(`/api/domain/project/${pid}`),
  progress: (pid: string) =>
    j<{ ok: boolean } & Progress>(`/api/domain/project/${pid}/progress`),
  timeline: (pid: string, limit = 100) =>
    j<{ ok: boolean; events: TimelineEvent[] }>(
      `/api/domain/project/${pid}/timeline` + q({ limit })
    ),

  // ---- the graph (Module 12) ---------------------------------------------
  nodes: (pid: string, type?: NodeType | "", status?: string) =>
    j<{ ok: boolean; nodes: BrainNode[] }>(
      `/api/domain/project/${pid}/nodes` + q({ type, status })
    ),
  graph: (pid: string) =>
    j<{ ok: boolean; nodes: BrainNode[]; edges: BrainEdge[]; counts: Record<string, number> }>(
      `/api/domain/project/${pid}/graph`
    ),

  // ---- conversation → knowledge (Modules 2, 3, 4) ------------------------
  capture: (pid: string, text: string, opts?: { feature_id?: string; use_llm?: boolean }) =>
    post<CaptureResult>(`/api/domain/project/${pid}/capture`, {
      text, feature_id: opts?.feature_id, use_llm: opts?.use_llm ?? true,
    }),
  plan: (pid: string, text: string, opts?: { preview?: boolean; from_node?: string; use_llm?: boolean }) =>
    post<PlanResult>(`/api/domain/project/${pid}/plan`, {
      text, preview: opts?.preview ?? false, from_node: opts?.from_node,
      use_llm: opts?.use_llm ?? true,
    }),
  expandTask: (pid: string, tid: string, use_llm = true) =>
    post<{ ok: boolean; error?: string; parent?: string; subtasks?: { id: string; title: string }[] }>(
      `/api/domain/task/${tid}/expand`, { pid, use_llm }
    ),
  setTaskStatus: (pid: string, tid: string, status: TaskState, reason = "") =>
    post<{ ok: boolean; error?: string; task?: BrainNode }>(
      `/api/domain/task/${tid}/status`, { pid, status, reason }
    ),

  // ---- memory & reasoning (Modules 5, 9) ---------------------------------
  why: (pid: string, nid: string) =>
    j<WhyResult>(`/api/domain/node/${nid}/why` + q({ pid })),
  related: (pid: string, nid: string) =>
    j<RelatedResult>(`/api/domain/node/${nid}/related` + q({ pid })),
  ask: (pid: string, nid: string, question: string, use_llm = true) =>
    post<AskResult>(`/api/domain/node/${nid}/ask`, { pid, question, use_llm }),

  // ---- git + GitHub (Modules 6, 7) ---------------------------------------
  rescan: (pid: string) =>
    post<{ ok: boolean; error?: string; imported?: Record<string, number>; head?: any }>(
      `/api/domain/project/${pid}/rescan`
    ),
  ghStatus: () =>
    j<{ ok: boolean; connected: boolean; account?: string | null }>("/api/domain/github/status"),
  ghRepos: (limit = 100) =>
    j<{ ok: boolean; error?: string; connected?: boolean; account?: string | null; repos?: GhRepo[] }>(
      "/api/domain/github/repos" + q({ limit })
    ),
  ghImport: (full_name: string, opts?: { clone_url?: string; name?: string; branch?: string; force?: boolean }) =>
    post<{ ok: boolean; error?: string; project?: BrainProject; analysis?: any; git?: any; path?: string }>(
      "/api/domain/github/import", { full_name, ...opts }
    ),
};

// ---- small shared helpers the brain views all want --------------------------

export const NODE_META: Record<NodeType, { icon: string; label: string; color: string }> = {
  project:    { icon: "◈", label: "Project",    color: "#8b5cff" },
  idea:       { icon: "✧", label: "Idea",       color: "#c9a6ff" },
  discussion: { icon: "❝", label: "Discussion", color: "#8b8fca" },
  decision:   { icon: "⚖", label: "Decision",   color: "#ffb648" },
  feature:    { icon: "◆", label: "Feature",    color: "#38e1ff" },
  task:       { icon: "☑", label: "Task",       color: "#35e08f" },
  file:       { icon: "▤", label: "File",       color: "#7f8aa3" },
  commit:     { icon: "⎇", label: "Commit",     color: "#ff8fb1" },
  test:       { icon: "⚗", label: "Test",       color: "#9be15d" },
  milestone:  { icon: "⚑", label: "Milestone",  color: "#ffd166" },
};

export const TASK_META: Record<TaskState, { label: string; color: string }> = {
  planning:    { label: "Planning",    color: "#8b8fca" },
  todo:        { label: "To do",       color: "#7f8aa3" },
  in_progress: { label: "In progress", color: "#38e1ff" },
  blocked:     { label: "Blocked",     color: "#ff6b6b" },
  done:        { label: "Done",        color: "#35e08f" },
  rejected:    { label: "Dropped",     color: "#555b6e" },
};

/** Backend timestamps are local "YYYY-MM-DDTHH:MM:SS" or git ISO strings. */
export function whenLabel(s: string | null | undefined): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const diff = Date.now() - d.getTime();
  const day = 86400000;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return Math.floor(diff / 60000) + "m ago";
  if (diff < day) return Math.floor(diff / 3600000) + "h ago";
  if (diff < 7 * day) return Math.floor(diff / day) + "d ago";
  return d.toLocaleDateString();
}
