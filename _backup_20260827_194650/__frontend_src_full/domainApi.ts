// REST client for the Domain's backend: real filesystem, real terminal,
// GitHub project vitals, and the OAuth connectors.
const BASE = "http://127.0.0.1:8760";

export interface FsEntry {
  name: string;
  path: string;
  dir: boolean;
  size: number;
  mtime: string | null;
  hidden: boolean;
  lang: string | null;
  children?: FsEntry[];
}

export interface FsRoot {
  label: string;
  path: string;
}

export interface FileContent {
  path: string;
  name: string;
  lang: string;
  content: string;
  size: number;
}

export interface ShellResult {
  id: string;
  output: string;
  code: number;
  cwd: string;
  ms?: number;
  truncated?: boolean;
  clear?: boolean;
  closed?: boolean;
}

export interface RepoStatus {
  ok: boolean;
  error?: string;
  full_name?: string;
  url?: string;
  description?: string | null;
  private?: boolean;
  stars?: number;
  forks?: number;
  open_issues?: number;
  language?: string | null;
  default_branch?: string;
  pushed_at?: string;
  archived?: boolean;
  last_commit?: { message: string; author?: string; date?: string; url?: string };
}

/** One thing AURA noticed while reading a file. `line` is 1-based when known. */
export interface ReviewFinding {
  line: number | null;
  severity: "bug" | "risk" | "style" | "idea" | string;
  note: string;
}

export interface ReviewResult {
  ok: boolean;
  error?: string;
  source?: "llm" | "unstructured";
  truncated?: boolean;
  suggestion?: string;
  findings?: ReviewFinding[];
}

/** git status, parsed — what a commit would actually include. */
export interface GitPreview {
  ok: boolean;
  error?: string;
  is_repo?: boolean;
  root?: string;
  branch?: string;
  protected?: boolean;
  files?: { path: string; state: string; staged: boolean }[];
  file_count?: number;
  clean?: boolean;
  has_upstream?: boolean;
  upstream?: string;
  ahead?: number;
  behind?: number;
  oversized?: boolean;
  remotes?: string[];
  can_push?: boolean;
}

export interface GitResult {
  ok: boolean;
  error?: string;
  output?: string;
  message?: string;
  sha?: string;
  files?: number;
  branch?: string;
  remote?: string;
  pushed?: number | null;
  preview?: GitPreview;
}

export interface GitHubRepo {
  name: string;
  full_name: string;
  private: boolean;
  description: string;
  language: string;
  default_branch: string;
  updated_at: string;
  clone_url: string;
  html_url: string;
}

export interface PullRequest {
  number: number;
  title: string;
  state: string;
  draft: boolean;
  author: string;
  head: string;
  base: string;
  url: string;
  updated_at: string;
  comments: number;
}

export interface GitCommit {
  sha: string;
  author: string;
  when: string;
  subject: string;
}

export interface GitBranches {
  ok: boolean;
  error?: string;
  branches: string[];
  current: string;
  protected?: string[];
}

export interface Connector {
  id: string;
  label: string;
  icon: string;
  color: string;
  blurb: string;
  docs: string;
  redirect_uri: string;
  configured: boolean;
  connected: boolean;
  expires_at?: number | null;
  expired?: boolean;
  account?: string | null;
}

export interface ConnectorDoc {
  id: string;
  name: string;
  kind: "word" | "excel" | "powerpoint" | "figma" | "repo";
  url: string;
  modified?: string;
  size?: number;
  thumbnail?: string;
  project?: string;
}

// ---- Office documents (opened from OneDrive, edited here, written back) ----
export interface WordParagraph { i: number; text: string; style: string; }
export interface ExcelSheet { name: string; rows: string[][]; truncated: boolean; }
export interface PptShape { i: number; name: string; text: string; placeholder: boolean; }
export interface PptSlide { i: number; title: string; shapes: PptShape[]; }

export interface OfficeDocument {
  id: string;
  name: string;
  kind: "word" | "excel" | "powerpoint";
  url: string;
  size?: number;
  modified?: string;
  modified_by?: string;
  content: {
    kind: string;
    paragraphs?: WordParagraph[];
    tables?: { i: number; rows: string[][] }[];
    sheets?: ExcelSheet[];
    slides?: PptSlide[];
  };
}

export interface FigmaFrame { id: string; name: string; type: string; }
export interface FigmaPage { id: string; name: string; frames: FigmaFrame[]; }
export interface FigmaFile {
  kind: "figma";
  name: string;
  modified?: string;
  version?: string;
  url: string;
  pages: FigmaPage[];
  thumbnails: Record<string, string>;
  readonly: boolean;
}

/** Edits are keyed by the same indices the reader handed out. */
export type OfficeEdits =
  | { paragraphs: Record<string, string> }
  | { cells: Record<string, Record<string, string>> }
  | { slides: Record<string, Record<string, string>> };

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return res.json() as Promise<T>;
}

const q = (o: Record<string, string | number | boolean | undefined>) =>
  "?" +
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");

export const domainApi = {
  // ---- filesystem ---------------------------------------------------------
  roots: () => j<{ ok: boolean; roots: FsRoot[] }>("/api/domain/fs/roots"),
  list: (path: string, hidden = false) =>
    j<{ ok: boolean; error?: string; path: string; parent: string | null; entries: FsEntry[] }>(
      "/api/domain/fs/list" + q({ path, hidden })
    ),
  tree: (path: string, depth = 2) =>
    j<{ ok: boolean; error?: string; tree: FsEntry }>("/api/domain/fs/tree" + q({ path, depth })),
  read: (path: string) =>
    j<{ ok: boolean; error?: string } & Partial<FileContent>>("/api/domain/fs/read" + q({ path })),
  write: (path: string, content: string) =>
    j<{ ok: boolean; error?: string; size?: number }>("/api/domain/fs/write", {
      method: "POST",
      body: JSON.stringify({ path, content }),
    }),
  create: (path: string, dir = false) =>
    j<{ ok: boolean; error?: string }>("/api/domain/fs/create", {
      method: "POST",
      body: JSON.stringify({ path, dir }),
    }),
  rename: (path: string, name: string) =>
    j<{ ok: boolean; error?: string; path?: string }>("/api/domain/fs/rename", {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),
  remove: (path: string) =>
    j<{ ok: boolean; error?: string }>("/api/domain/fs/delete", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  searchFiles: (path: string, query: string) =>
    j<{ ok: boolean; hits: FsEntry[] }>("/api/domain/fs/search" + q({ path, q: query })),

  // ---- terminal -----------------------------------------------------------
  shellOpen: (cwd?: string) =>
    j<{ ok: boolean; id: string; cwd: string }>("/api/domain/shell/open", {
      method: "POST",
      body: JSON.stringify({ cwd }),
    }),
  shellRun: (id: string | null, command: string, cwd?: string, timeout = 60) =>
    j<ShellResult>("/api/domain/shell/run", {
      method: "POST",
      body: JSON.stringify({ id, command, cwd, timeout }),
    }),
  shellClose: (id: string) =>
    j<{ ok: boolean }>("/api/domain/shell/close", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),

  // ---- github -------------------------------------------------------------
  repo: (url: string, force = false) =>
    j<RepoStatus>("/api/domain/github" + q({ url, force })),

  // ---- code review --------------------------------------------------------
  /** AURA reads a file and proposes a revised version. Never writes. */
  review: (body: { path?: string; content?: string; lang?: string; instruction?: string }) =>
    j<ReviewResult>("/api/domain/review", { method: "POST", body: JSON.stringify(body) }),

  // ---- local git write path (preview → commit → push) ---------------------
  gitPreview: (root: string) =>
    j<GitPreview>("/api/domain/git/preview" + q({ root })),
  gitCommit: (root: string, message: string, opts?: { paths?: string[]; allow_oversized?: boolean }) =>
    j<GitResult>("/api/domain/git/commit", {
      method: "POST",
      body: JSON.stringify({ root, message, confirm: true, ...opts }),
    }),
  gitPush: (root: string, opts?: { allow_protected?: boolean; remote?: string }) =>
    j<GitResult>("/api/domain/git/push", {
      method: "POST",
      body: JSON.stringify({ root, confirm: true, ...opts }),
    }),
  gitPublish: (root: string, message: string, opts?: { allow_protected?: boolean; allow_oversized?: boolean }) =>
    j<GitResult>("/api/domain/git/publish", {
      method: "POST",
      body: JSON.stringify({ root, message, confirm: true, ...opts }),
    }),

  // ---- GitHub: account, repos, pull requests, import ----------------------
  ghStatus: () =>
    j<{ ok: boolean; connected: boolean; account: string }>("/api/domain/github/status"),
  ghRepos: (limit = 100) =>
    j<{ ok: boolean; connected?: boolean; error?: string; account?: string; repos?: GitHubRepo[] }>(
      "/api/domain/github/repos" + q({ limit }),
    ),
  ghPulls: (full_name: string, state = "open", limit = 30) =>
    j<{ ok: boolean; connected?: boolean; error?: string; pulls: PullRequest[] }>(
      "/api/domain/github/pulls" + q({ full_name, state, limit }),
    ),
  ghImport: (full_name: string, clone_url?: string, branch?: string) =>
    j<{ ok: boolean; error?: string; cloned_to?: string; updated?: boolean }>(
      "/api/domain/github/import",
      { method: "POST", body: JSON.stringify({ full_name, clone_url, branch }) },
    ),

  // ---- git panel: history, branches, staging, diffs, pull -----------------
  gitLog: (root: string, limit = 40) =>
    j<{ ok: boolean; commits: GitCommit[]; note?: string }>("/api/domain/git/log" + q({ root, limit })),
  gitBranches: (root: string) =>
    j<GitBranches>("/api/domain/git/branches" + q({ root })),
  gitDiff: (root: string, path = "", staged = false) =>
    j<{ ok: boolean; diff: string; error?: string }>("/api/domain/git/diff" + q({ root, path, staged })),
  gitCheckout: (root: string, branch: string, create = false) =>
    j<{ ok: boolean; error?: string; branch?: string }>("/api/domain/git/checkout", {
      method: "POST",
      body: JSON.stringify({ root, branch, create }),
    }),
  gitPull: (root: string, remote = "origin") =>
    j<{ ok: boolean; error?: string; output?: string; hint?: string }>("/api/domain/git/pull", {
      method: "POST",
      body: JSON.stringify({ root, remote }),
    }),
  gitStage: (root: string, paths?: string[], unstage = false) =>
    j<{ ok: boolean; error?: string; preview?: GitPreview }>("/api/domain/git/stage", {
      method: "POST",
      body: JSON.stringify({ root, paths, unstage }),
    }),

  // ---- connectors ---------------------------------------------------------
  connectors: () =>
    j<{ ok: boolean; connectors: Connector[]; figma_teams: string }>("/api/connectors"),
  configureConnector: (
    provider: string,
    client_id: string,
    client_secret: string,
    team_ids?: string
  ) =>
    j<{ ok: boolean; error?: string; connector?: Connector }>(
      `/api/connectors/${provider}/config`,
      { method: "PUT", body: JSON.stringify({ client_id, client_secret, team_ids }) }
    ),
  connectorAuthUrl: (provider: string) =>
    j<{ ok: boolean; error?: string; url?: string }>(`/api/connectors/${provider}/auth`),
  disconnectConnector: (provider: string) =>
    j<{ ok: boolean; connector?: Connector }>(`/api/connectors/${provider}/disconnect`, {
      method: "POST",
    }),
  connectorDocs: (provider: string, query = "", kind?: string) =>
    j<{ ok: boolean; error?: string; documents?: ConnectorDoc[] }>(
      `/api/connectors/${provider}/documents` + q({ q: query, kind })
    ),

  // ---- office round-trip --------------------------------------------------
  officeOpen: (id: string) =>
    j<{ ok: boolean; error?: string; document?: OfficeDocument }>(
      "/api/domain/office/open" + q({ id })
    ),
  officeSave: (id: string, edits: OfficeEdits) =>
    j<{ ok: boolean; error?: string; modified?: string; size?: number }>(
      "/api/domain/office/save",
      { method: "POST", body: JSON.stringify({ id, edits }) }
    ),
  officeMeta: (id: string) =>
    j<{ ok: boolean; error?: string; modified?: string; modified_by?: string }>(
      "/api/domain/office/meta" + q({ id })
    ),
  figmaFile: (key: string) =>
    j<{ ok: boolean; error?: string; file?: FigmaFile }>("/api/domain/figma/file" + q({ key })),
};
