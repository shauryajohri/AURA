// ============================================================================
// systemApi — the client for AURA changing itself and staying in step.
//
// Three groups, matching system_api.py: upgrades (AURA writing code, its own
// included), reset, and connected sources. Kept out of api.ts because none of
// it is about a conversation — it is about the machine underneath one.
// ============================================================================
import { BASE } from "./api";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return res.json() as Promise<T>;
}

const post = (body?: unknown): RequestInit =>
  ({ method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

// ---- upgrades --------------------------------------------------------------

/** One file a proposal would rewrite. `before`/`after` are whole files. */
export interface FileChange {
  path: string;
  new: boolean;
  before: string;
  after: string;
  diff: string;
  added: number;
  removed: number;
}

export type ProposalStatus = "pending" | "applied" | "rejected" | "rolled_back";

/** The summary form, as the list endpoint returns it. */
export interface ProposalRow {
  id: string;
  /** "self" = AURA's own source. Anything else is a project in the Domain. */
  scope: string;
  root: string;
  label: string;
  request: string;
  why: string;
  status: ProposalStatus;
  created_at: string;
  applied_at: string;
  files: string[];
  added: number;
  removed: number;
}

/** The full form, with every file's before/after. */
export interface Proposal extends Omit<ProposalRow, "files"> {
  changes: FileChange[];
}

export interface ProposeResult extends Partial<Proposal> {
  ok: boolean;
  error?: string;
}

export const upgrades = {
  list: (scope = "", root = "") =>
    j<{ ok: boolean; proposals: ProposalRow[] }>(
      `/api/upgrade/proposals?scope=${encodeURIComponent(scope)}&root=${encodeURIComponent(root)}`,
    ).then((r) => r.proposals ?? []),

  get: (id: string) =>
    j<{ ok: boolean; proposal: Proposal | null }>(`/api/upgrade/proposals/${id}`)
      .then((r) => r.proposal),

  /** Ask for a change. Nothing is written — this returns a proposal to review. */
  propose: (body: { request: string; scope?: "self" | "project"; root?: string; files?: string[]; label?: string }) =>
    j<ProposeResult>("/api/upgrade/propose", post(body)),

  /** `restart` comes back true when AURA rewrote its own source. */
  approve: (id: string) =>
    j<{ ok: boolean; error?: string; applied?: string[]; restart?: boolean }>(
      `/api/upgrade/proposals/${id}/approve`, post()),

  reject: (id: string) =>
    j<{ ok: boolean; error?: string }>(`/api/upgrade/proposals/${id}/reject`, post()),

  rollback: (id: string) =>
    j<{ ok: boolean; error?: string; restored?: string[]; failed?: string[]; restart?: boolean }>(
      `/api/upgrade/proposals/${id}/rollback`, post()),

  remove: (id: string) =>
    j<{ ok: boolean; error?: string }>(`/api/upgrade/proposals/${id}`, { method: "DELETE" }),

  files: (root = "") =>
    j<{ ok: boolean; root: string; files: string[] }>(
      `/api/upgrade/files?root=${encodeURIComponent(root)}`),

  file: (path: string, root = "") =>
    j<{ ok: boolean; content?: string; error?: string }>(
      `/api/upgrade/file?path=${encodeURIComponent(path)}&root=${encodeURIComponent(root)}`),
};

// ---- reset -----------------------------------------------------------------

export interface ResetScope {
  id: string;
  label: string;
  desc: string;
}

export const system = {
  resetScopes: () =>
    j<{ ok: boolean; scopes: ResetScope[] }>("/api/system/reset").then((r) => r.scopes ?? []),

  /** `confirm` must be the literal word RESET. */
  reset: (scopes: string[], confirm: string) =>
    j<{ ok: boolean; error?: string; cleared?: string[]; labels?: string[]; backup?: string }>(
      "/api/system/reset", { method: "POST", body: JSON.stringify({ scopes, confirm }) }),
};

// ---- sources ---------------------------------------------------------------

export type SourceKind = "github" | "docs" | "link";
export type SourceStatus = "idle" | "syncing" | "ok" | "error";

export interface RepoRef {
  full_name: string;
  name: string;
  description: string;
  language: string;
  default_branch: string;
  updated_at: string;
  pushed_at: string;
  html_url: string;
  private: boolean;
  stars: number;
  /** Set once the repo has been cloned — the folder it lives in. */
  local?: string;
  pulled?: string;
  source_id?: number;
}

export interface Source {
  id: number;
  kind: SourceKind;
  url: string;
  label: string;
  room_id: number | null;
  auto_sync: boolean;
  status: SourceStatus;
  /** Human sentence about the last sync — "8 repos, 2 cloned locally". */
  detail: string;
  meta: {
    owner?: string;
    repo?: string;
    repos?: RepoRef[];
    files?: Record<string, { name: string; item: number; stamp: string }>;
    item?: number;
  };
  last_sync: string;
  created_at: string;
}

export const sources = {
  list: (roomId?: number | null) =>
    j<{ ok: boolean; sources: Source[] }>(
      "/api/sources" + (roomId != null ? `?room_id=${roomId}` : ""),
    ).then((r) => r.sources ?? []),

  add: (url: string, opts: { label?: string; room_id?: number | null } = {}) =>
    j<{ ok: boolean; error?: string; source?: Source }>("/api/sources", post({ url, ...opts })),

  update: (id: number, patch: { label?: string; room_id?: number | null; auto_sync?: boolean }) =>
    j<{ ok: boolean; source?: Source }>(`/api/sources/${id}`, {
      method: "PATCH", body: JSON.stringify(patch),
    }),

  remove: (id: number) => j<{ ok: boolean }>(`/api/sources/${id}`, { method: "DELETE" }),

  sync: (id: number) => j<{ ok: boolean; source?: Source }>(`/api/sources/${id}/sync`, post()),

  /** Fire-and-forget: what the app calls on open. */
  syncAll: () => j<{ ok: boolean }>("/api/sources/sync", post()),

  repos: () => j<{ ok: boolean; repos: RepoRef[] }>("/api/sources/repos").then((r) => r.repos ?? []),

  /** Bring a repo to disk so it can be opened, prompted and edited. */
  clone: (id: number, fullName: string) =>
    j<{ ok: boolean; error?: string; path?: string; already?: boolean }>(
      `/api/sources/${id}/clone`, post({ full_name: fullName })),
};
