// REST client for the AURA bridge (memory/store.py + model_lock).
const BASE = "http://127.0.0.1:8760";

export interface Task {
  id: number;
  title: string;
  priority: string;
  status: string;
  created_at: string | null;
  done_at: string | null;
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

export type Settings = Record<string, number | boolean | string>;

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
  addTask: (title: string, priority = "medium") =>
    j("/api/tasks", { method: "POST", body: JSON.stringify({ title, priority }) }),
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

  // Task edit
  updateTask: (id: number, patch: { title?: string; priority?: string }) =>
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

  // App settings
  getSettings: () => j<{ settings: Settings }>("/api/settings").then((r) => r.settings),
  saveSettings: (patch: Settings) =>
    j<{ ok: boolean; settings: Settings }>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ settings: patch }),
    }),
};
