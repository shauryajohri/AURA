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
  | { type: "error"; payload: { message: string } }
  | { type: "pong" };

// Client -> Server
export type ClientMessage =
  | { type: "message"; payload: { text: string } }
  | { type: "ping" };

export type ConnStatus = "connecting" | "open" | "closed";

export interface ChatTurn {
  id: string;
  role: "user" | "aura";
  text: string;
  streaming?: boolean;
  source?: string; // for auto-chat pushes: proactive | curiosity | greeting
  ts?: string;     // wall-clock time when the turn was created
}

declare global {
  interface Window {
    aura?: {
      version: string;
      bridgeUrl: string;
      minimize?: () => void;
      close?: () => void;
    };
  }
}
