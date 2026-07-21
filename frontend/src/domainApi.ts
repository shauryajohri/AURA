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
