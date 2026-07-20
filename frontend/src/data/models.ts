// The AI model planet system orbiting the central black hole.
// Colors + archetypes follow the "AURA — Blackhole & Planets Design" sheet:
// each planet is a model with its own color, nature and orbit. The planet that
// last answered becomes ACTIVE (lights up + orbits faster).

export type ModelStatus = "active" | "standby";

export interface ModelNode {
  id: string;
  name: string;
  role: string;        // archetype, e.g. "The Researcher"
  nature: string;      // short personality line from the design sheet
  status: ModelStatus;
  color: string;
  ring?: boolean; // paid/premium LLMs wear Saturn rings
  // Legacy % offsets (old constellation layout) — kept for compatibility.
  x: number;
  y: number;
}

export const MODELS: ModelNode[] = [
  // ── The live AURA roster (core/model_router.MODELS) — names must match
  //    the model_lock keys so locking a planet really locks the model. ──
  { id: "laguna",   name: "Laguna M.1",       role: "The Coder",        nature: "Precise · Logical · Sharp",   status: "standby", color: "#6C6BFF", x: 12,  y: -36 },
  { id: "nemotron", name: "Nemotron 3 Super", role: "The Explorer",     nature: "Wide · Deep · Searching",     status: "standby", color: "#38E1FF", x: 40,  y: -8 },
  { id: "gemma",    name: "Gemma 4 31B",      role: "The Companion",    nature: "Friendly · Balanced · Clear", status: "standby", color: "#F472B6", x: 24,  y: 30 },
  { id: "llama",    name: "Llama 3.3 70B",    role: "The Guardian",     nature: "Protective · Active · Reliable", status: "standby", color: "#FF5A5A", x: -22, y: 30 },
  { id: "llama8b",  name: "Llama 3.1 8B",     role: "The Archivist",    nature: "Silent · Stable · Instant",   status: "standby", color: "#E6E6FF", x: -40, y: -20 },
  { id: "gpt4o",    name: "GPT-4o",           role: "The Communicator", nature: "Friendly · Balanced · Clear", status: "standby", color: "#35E08F", ring: true, x: -26, y: -30 },
  { id: "gemini",   name: "Gemini 1.5 Pro",   role: "The Researcher",   nature: "Curious · Smart · Fast",      status: "standby", color: "#4CC9FF", ring: true, x: -34, y: 2 },
  { id: "claude",   name: "Claude 3.5",       role: "The Thinker",      nature: "Deep · Analytical · Calm",    status: "standby", color: "#B18BFF", ring: true, x: 28,  y: -24 },
  { id: "grok",     name: "Grok 2 (xAI)",     role: "The Truth Seeker", nature: "Bold · Raw · Real-time",      status: "standby", color: "#FF8C42", ring: true, x: 32,  y: 8 },
];
