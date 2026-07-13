// The AI model "constellation" orbiting the central black hole.
// Positions are % offsets from the stage center (matching the mockup layout).
// status is static for now - a later milestone wires this to the real router
// so the model that actually answered lights up as ACTIVE.

export type ModelStatus = "active" | "standby";

export interface ModelNode {
  id: string;
  name: string;
  role: string;
  status: ModelStatus;
  color: string;
  // Position relative to stage center, in % of stage size. Negative = left/up.
  x: number;
  y: number;
}

export const MODELS: ModelNode[] = [
  { id: "gpt4o", name: "GPT-4o", role: "General Intelligence", status: "active", color: "#a855f7", x: -26, y: -30 },
  { id: "gemini", name: "Gemini 1.5 Pro", role: "Research & Analysis", status: "active", color: "#22d3ee", x: -34, y: 2 },
  { id: "llama", name: "Llama 3.3 70B", role: "Local Processing", status: "standby", color: "#f59e0b", x: -22, y: 30 },
  { id: "claude", name: "Claude 3.5", role: "Deep Reasoning", status: "standby", color: "#38bdf8", x: 28, y: -24 },
  { id: "grok", name: "Grok 2 (xAI)", role: "Real-time Intelligence", status: "standby", color: "#fb7185", x: 32, y: 8 },
];
