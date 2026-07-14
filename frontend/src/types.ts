// Shared message contract between the React face and the Python brain.
// Keep this in lockstep with server.py - one schema, both sides.

export type AuraState = "idle" | "thinking" | "speaking";
export type Presence = "working" | "idle" | "afk";

// Server -> Client
export type ServerMessage =
  | { type: "state"; payload: { state: AuraState } }
  | { type: "chunk"; payload: { text: string } }
  | { type: "done"; payload: { text: string; model?: string } }
  | { type: "push"; payload: { text: string; source: string } }
  | { type: "presence"; payload: { state: Presence } }
  | { type: "mode"; payload: { mode: string } }
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
    aura?: { version: string; bridgeUrl: string };
  }
}
