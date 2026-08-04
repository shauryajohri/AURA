// REST client for the AURA bridge (memory/store.py + model_lock).
const BASE = "http://127.0.0.1:8760";

export interface Task {
  id: number;
  title: string;
  priority: string;
  status: string;
  created_at: string | null;
  done_at: string | null;
  /** "now" = doing it today, "later" = the backlog. */
  bucket: "now" | "later";
  /** ISO date (YYYY-MM-DD) or null. */
  due?: string | null;
  /** Free-text project name this task belongs to. */
  project?: string | null;
  /** "user" = you typed it, "aura" = she suggested it. */
  origin?: "user" | "aura" | string;
}

/** One task AURA pulled out of a conversation — a suggestion, not a record. */
export interface SuggestedTask {
  title: string;
  group: string;
  complexity: "low" | "medium" | "high";
  hours: number;
  priority: "low" | "medium" | "high";
}

export interface ExtractResult {
  ok: boolean;
  source: "llm" | "heuristic" | "empty";
  tasks: SuggestedTask[];
  groups: { name: string; count: number }[];
  total_hours: number;
}

export interface ModelInfo {
  id: string;
  name: string;
  locked: boolean;
}

export interface Fact {
  id: number;
  fact: string;
  category: string;
  created_at: string | null;
}

export interface SavedLink {
  id: number;
  name: string;
  url: string;
  created_at: string | null;
}

/** A note AURA extracted from a conversation — written by the brain, not typed. */
export interface MemoryNote {
  id: number;
  title: string;
  summary: string;
  created_at: string | null;
}

/** A session snapshot: what you were doing in an app, summarised. */
export interface MemoryRecap {
  id: number;
  app: string;
  summary: string;
  created_at: string | null;
}

export interface DayStat {
  date: string;
  user_msgs: number;
  aura_msgs: number;
  facts_saved: number;
}

export interface UsageStats {
  days: DayStat[];
  totals: { user_messages: number; facts: number; knowledge: number; tasks: number };
}

export interface NatureInfo {
  id: string;
  label: string;
  icon: string;
}

export type Settings = Record<string, number | boolean | string>;

// ── Quests ─────────────────────────────────────────────────────────────────
export interface Quest {
  id: number;
  title: string;
  target_minutes: number;
  keywords: string;
  preset: string;
  color: string;
  sort_order: number;
  project_path: string;
  /** How it completes: time = tracked clock, proof = verified screenshot,
   *  manual = you tick it off. */
  kind: "time" | "proof" | "manual";
  /** For proof quests: how many of the thing ("leetcode 2 questions" → 2). */
  target_count: number;
  /** How many have been credited today — auto-detected or screenshot-verified. */
  done_count: number;
  count_percent: number;
  /** What AURA saw on the last verification attempt. */
  proof_note: string;
  seconds: number;
  target_seconds: number;
  /** No target set — monitored only, never completes. */
  untimed: boolean;
  percent: number;
  remaining_seconds: number;
  /** Time recorded beyond the target. Kept counting on purpose. */
  overtime_seconds: number;
  completed: boolean;
  completed_at: string | null;
}

export interface QuestPressure {
  status: "clear" | "ok" | "tight" | "rush" | "impossible" | "out_of_time" | "unknown";
  required_minutes: number;
  available_minutes: number;
  deficit_minutes: number;
}

export interface QuestBoard {
  day: string;
  quests: Quest[];
  unallocated_seconds: number;
  pressure: QuestPressure;
  active_quest_id: number | null;
}

export interface QuestPreset {
  id: string;
  label: string;
  icon: string;
  color: string;
  keyword_count: number;
}

export interface QuestHistoryRow {
  day: string;
  quest_id: number;
  seconds: number;
  completed: boolean;
}

// ── V3 intelligence ────────────────────────────────────────────────────────
export interface SessionSummary {
  state: string;
  state_emoji: string;
  confidence: number;
  session_minutes: number;
  flow_minutes: number;
  builds_total: number;
  builds_success: number;
  success_rate: number;
  errors_total: number;
  errors_now: number;
  lines_added: number;
  debug_minutes: number;
}

export interface MistakeRow {
  id: string;
  label: string;
  count: number;
}

export interface TrendRow {
  id: string;
  label: string;
  recent: number;
  previous: number;
  delta_pct: number | null;
  direction: "up" | "down" | "flat" | "new";
}

export interface V3Snapshot {
  session: SessionSummary;
  mistakes: MistakeRow[];
  trends: TrendRow[];
  events: import("./types").V3Event[];
  personality: string;
}

export interface ErrorClassification {
  matched: boolean;
  needs_llm: boolean;
  text: string;
  id: string;
  label: string;
  level: string;
  category: string;
  emoji: string;
  language: string;
  explanation: string;
  confidence: number;
  repeat_count: number;
  total_count: number;
  serious: boolean;
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return res.json() as Promise<T>;
}

export const api = {
  // Tasks
  getTasks: () => j<{ tasks: Task[] }>("/api/tasks").then((r) => r.tasks),
  addTask: (
    title: string,
    priority = "medium",
    bucket: "now" | "later" = "now",
    extra: { due?: string | null; project?: string | null; origin?: string } = {},
  ) =>
    j("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ title, priority, bucket, ...extra }),
    }),
  /** AI Task Assistant — suggestions only, nothing is stored until accepted. */
  extractTasks: (text?: string, limit = 40) =>
    j<ExtractResult>("/api/tasks/extract", {
      method: "POST",
      body: JSON.stringify({ text: text ?? "", limit }),
    }),
  rewriteTask: (title: string) =>
    j<{ ok: boolean; title: string; complexity: string; hours: number; original: string; source: string }>(
      "/api/tasks/rewrite",
      { method: "POST", body: JSON.stringify({ title }) },
    ),
  setTaskBucket: (id: number, bucket: "now" | "later") =>
    j(`/api/tasks/${id}/bucket`, { method: "POST", body: JSON.stringify({ bucket }) }),
  promoteTask: (id: number, target_minutes = 0) =>
    j<{ ok: boolean; quest_id: number; title: string; target_minutes: number }>(
      `/api/tasks/${id}/promote`,
      { method: "POST", body: JSON.stringify({ target_minutes }) },
    ),
  completeTask: (id: number) => j(`/api/tasks/${id}/complete`, { method: "POST" }),
  uncompleteTask: (id: number) => j(`/api/tasks/${id}/uncomplete`, { method: "POST" }),
  deleteTask: (id: number) => j(`/api/tasks/${id}`, { method: "DELETE" }),

  // Models
  getModels: () => j<{ models: ModelInfo[]; last_model: string }>("/api/models"),
  toggleLock: (name: string) =>
    j<{ locked: boolean }>(`/api/models/${encodeURIComponent(name)}/toggle`, { method: "POST" }),

  // Facts
  getFacts: () => j<{ facts: Fact[] }>("/api/facts").then((r) => r.facts),
  addFact: (fact: string, category = "general") =>
    j("/api/facts", { method: "POST", body: JSON.stringify({ fact, category }) }),
  updateFact: (id: number, fact: string) =>
    j(`/api/facts/${id}`, { method: "PUT", body: JSON.stringify({ fact }) }),
  deleteFact: (id: number) => j(`/api/facts/${id}`, { method: "DELETE" }),

  // Saved notes + session recaps (read/delete — the brain writes them)
  getNotes: (limit = 300) =>
    j<{ notes: MemoryNote[] }>(`/api/notes?limit=${limit}`).then((r) => r.notes),
  deleteNote: (id: number) => j(`/api/notes/${id}`, { method: "DELETE" }),
  getRecaps: (limit = 60) =>
    j<{ recaps: MemoryRecap[] }>(`/api/recaps?limit=${limit}`).then((r) => r.recaps),
  deleteRecap: (id: number) => j(`/api/recaps/${id}`, { method: "DELETE" }),

  // Task edit
  updateTask: (
    id: number,
    patch: { title?: string; priority?: string; due?: string | null; project?: string | null },
  ) =>
    j(`/api/tasks/${id}`, { method: "PUT", body: JSON.stringify(patch) }),

  // Saved links
  getLinks: () => j<{ links: SavedLink[] }>("/api/links").then((r) => r.links),
  addLink: (url: string, name?: string) =>
    j<{ ok: boolean; id: number; name: string; url: string }>("/api/links", {
      method: "POST",
      body: JSON.stringify({ url, name }),
    }),
  updateLink: (id: number, patch: { name?: string; url?: string }) =>
    j(`/api/links/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteLink: (id: number) => j(`/api/links/${id}`, { method: "DELETE" }),

  // Usage stats (memory graph)
  getStats: () => j<UsageStats>("/api/stats"),

  // Nature (personality lock)
  getNature: () => j<{ current: string; natures: NatureInfo[] }>("/api/nature"),
  setNature: (nature: string) =>
    j<{ ok: boolean; current: string }>("/api/nature", {
      method: "PUT",
      body: JSON.stringify({ nature }),
    }),

  // Quests — the daily board AURA verifies from the screen
  getQuests: () => j<QuestBoard>("/api/quests"),
  addQuest: (body: { text?: string; title?: string; target_minutes?: number; preset?: string; keywords?: string; project_path?: string }) =>
    j<{ ok: boolean; id?: number }>("/api/quests", { method: "POST", body: JSON.stringify(body) }),
  updateQuest: (id: number, patch: Partial<Pick<Quest, "title" | "target_minutes" | "keywords" | "preset" | "color" | "sort_order" | "project_path" | "kind" | "target_count">> & { active?: number }) =>
    j(`/api/quests/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  /** Omit `image` and AURA captures the screen herself; pass base64 (no
   *  data: prefix) to verify a file you picked instead. */
  verifyQuest: (id: number, image?: string) =>
    j<{
      ok: boolean;
      title: string;
      verdict: "pass" | "fail" | "";
      evidence: string;
      completed: boolean;
      error: string;
    }>(`/api/quests/${id}/verify`, {
      method: "POST",
      body: JSON.stringify(image ? { image } : {}),
    }),
  getQuestTerms: (id: number) =>
    j<{ ok: boolean; anchors: string[]; supporting: string[]; project_path: string; harvested: string[] }>(
      `/api/quests/${id}/terms`,
    ),
  deleteQuest: (id: number) => j(`/api/quests/${id}`, { method: "DELETE" }),
  completeQuest: (id: number, undo = false) =>
    j(`/api/quests/${id}/complete`, { method: "POST", body: JSON.stringify({ undo }) }),
  adjustQuest: (id: number, minutes: number) =>
    j<{ ok: boolean; seconds: number }>(`/api/quests/${id}/adjust`, {
      method: "POST",
      body: JSON.stringify({ minutes }),
    }),
  getQuestPresets: () => j<{ presets: QuestPreset[] }>("/api/quests/presets").then((r) => r.presets),
  getQuestHistory: (days = 30) =>
    j<{ history: QuestHistoryRow[]; streaks: Record<string, number> }>(`/api/quests/history?days=${days}`),

  // V3 intelligence (error knowledge base + developer session state)
  getV3Snapshot: () => j<V3Snapshot>("/api/v3/snapshot"),
  getV3Session: () => j<{ session: SessionSummary }>("/api/v3/session").then((r) => r.session),
  getV3Mistakes: () => j<{ mistakes: MistakeRow[]; trends: TrendRow[] }>("/api/v3/mistakes"),
  explainError: (text: string, record = false) =>
    j<ErrorClassification>("/api/v3/explain", {
      method: "POST",
      body: JSON.stringify({ text, record }),
    }),
  reportBuild: (success: boolean) =>
    j<{ ok: boolean; spoken: string | null; session: SessionSummary }>("/api/v3/build", {
      method: "POST",
      body: JSON.stringify({ success }),
    }),

  // Voice — fallback speech-to-text when the browser's Web Speech API can't
  // do the job. `wavBase64` is a bare base64 16 kHz mono WAV (no data: prefix).
  transcribe: (wavBase64: string) =>
    j<{ ok: boolean; text: string; error: string }>("/api/voice/transcribe", {
      method: "POST",
      body: JSON.stringify({ audio: wavBase64 }),
    }),

  // App settings
  getSettings: () => j<{ settings: Settings }>("/api/settings").then((r) => r.settings),
  saveSettings: (patch: Settings) =>
    j<{ ok: boolean; settings: Settings }>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ settings: patch }),
    }),
};
