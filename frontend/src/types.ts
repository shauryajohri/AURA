// Shared message contract between the React face and the Python brain.
// Keep this in lockstep with server.py - one schema, both sides.

export type AuraState = "idle" | "thinking" | "speaking";
export type Presence = "working" | "idle" | "afk";

// One live event from the V3 intelligence layer (core/v3_bridge).
// `kind` says which engine spoke: an error classification, a build result,
// or an ambient developer-state announcement.
export interface V3Event {
  kind: "error" | "build" | "errors" | "activity" | "tick";
  ts: number;
  text: string;
  // developer-state announcements
  signal?: string;
  state?: string;
  confidence?: number;
  emoji?: string;
  // error classifications
  id?: string;
  label?: string;
  level?: "SILLY" | "MEDIUM" | "CONCEPTUAL" | "DANGEROUS" | "";
  category?: string;
  explanation?: string;
  repeat_count?: number;
  total_count?: number;
  serious?: boolean;
}

// A live event from the quest tracker (core/quests.py).
export interface QuestEvent {
  kind: "progress" | "complete" | "pressure";
  ts: number;
  quest_id?: number;
  title?: string;
  text?: string;
  seconds?: number;
  target_seconds?: number;
  percent?: number;
  day?: string;
  status?: string;
  required_minutes?: number;
  available_minutes?: number;
}

// A live "what AURA is doing right now" line (core/activity.py).
export interface ActivityEvent {
  text: string;
  kind: "info" | "route" | "memory" | "task" | "done" | string;
  ts: number;
}

// Server -> Client
export type ServerMessage =
  | { type: "state"; payload: { state: AuraState } }
  | { type: "chunk"; payload: { text: string } }
  | { type: "done"; payload: { text: string; model?: string } }
  | { type: "push"; payload: { text: string; source: string } }
  | { type: "presence"; payload: { state: Presence } }
  | { type: "mode"; payload: { mode: string } }
  | { type: "v3"; payload: V3Event }
  | { type: "quest"; payload: QuestEvent }
  | { type: "activity"; payload: ActivityEvent }
  // A pasted key / "install <link>" came back as an install card.
  | { type: "install"; payload: { text: string; proposal: InstallProposal | null; masked: string } }
  // Saved Info changed (a scan finished, an item was deleted).
  | { type: "saved"; payload: { kind: "update" | "delete"; item: SavedItem | null; id: number } }
  // A planet was installed, re-jobbed or removed.
  | { type: "planets"; payload: { kind: string } }
  /** A connected source finished syncing — the repo list or document set moved. */
  | { type: "sources"; payload: { sources: unknown[]; changed: unknown } }
  | { type: "error"; payload: { message: string } }
  | { type: "pong" };

// Client -> Server
export type ClientMessage =
  | { type: "message"; payload: { text: string; attachments?: number[]; intent?: "EXPLAIN" } }
  | { type: "ping" };

export type ConnStatus = "connecting" | "open" | "closed";

/** A file shared with a message — shown as a chip on the user's bubble. */
export interface TurnAttachment {
  id: number;
  name: string;
  kind: string;
}

export interface ChatTurn {
  id: string;
  role: "user" | "aura";
  text: string;
  streaming?: boolean;
  source?: string; // for auto-chat pushes: proactive | curiosity | greeting
  ts?: string;     // wall-clock time when the turn was created
  /** An install card rendered under AURA's line. */
  card?: InstallProposal;
  attachments?: TurnAttachment[];
}

// ── Saved Info (core/saved_info.py) ───────────────────────────────────────
export type SavedKind = "link" | "github" | "video" | "pdf" | "doc" | "image" | "file";

export interface SavedItem {
  id: number;
  kind: SavedKind;
  title: string;
  url: string;
  file_name: string;
  mime: string;
  size: number;
  /** Domain for links, "upload" for files. */
  source: string;
  summary: string;
  key_points: string[];
  tags: string[];
  status: "scanning" | "ready" | "error";
  error: string;
  origin: string;
  pinned: boolean;
  created_at: string | null;
  updated_at: string | null;
  opened_at: string | null;
  has_file: boolean;
  content_chars: number;
  excerpt: string;
  /** Only on the single-item endpoint. */
  content?: string;
}

// ── Planet installs (core/integrations.py) ────────────────────────────────
export type Job = "Coding" | "Research" | "Chat" | "Vision" | "Background";

export interface ProposalModel {
  id: string;
  name: string;
  cost: string;
  context: string;
  vision: boolean;
  /** What AURA thinks it's good at, strongest first. */
  best_for: Job[];
  /** The jobs pre-ticked for it. */
  jobs: Job[];
  selected: boolean;
  /** Already a planet — can't be installed twice. */
  existing: boolean;
  linked?: boolean;
  desc: string;
}

export interface InstallResult {
  id: string;
  name: string;
  ok: boolean;
  why: string;
  jobs?: Job[];
  ms?: number;
}

export interface InstallProposal {
  id: string;
  provider: string;
  label: string;
  kind: "llm" | "search";
  about: string;
  cost: string;
  base_url: string;
  key_masked: string;
  /** Name of the .env variable the key was reused from, if any. */
  key_from: string;
  stage: "choose" | "need_provider" | "need_key" | "need_base_url" | "error" | "installed" | "not_installable";
  error: string;
  note: string;
  models: ProposalModel[];
  total_models: number;
  position: "first" | "backup";
  search_jobs: string[];
  source_url: string;
  providers: { id: string; label: string; kind: string; cost: string }[];
  results: InstallResult[];
  status: string;
  hint_model: string;
}

declare global {
  interface Window {
    aura?: {
      version: string;
      bridgeUrl: string;
      minimize?: () => void;
      openExternal?: (url: string) => void;
      /** The floating orb (electron/orb.cjs) — desktop app only. */
      orbState?: (state: AuraState) => void;
      orbListening?: (on: boolean) => void;
      orbVisible?: (visible: boolean) => void;
      orbNotify?: (text: string) => void;
      close?: () => void;
    };
  }
}
