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
};
