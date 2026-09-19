// The AI model planet system orbiting the central black hole.
// Colors + archetypes follow the "AURA — Blackhole & Planets Design" sheet:
// each planet is a model with its own color, nature and orbit. The planet that
// last answered becomes ACTIVE (lights up + orbits faster).
//
// Every planet is a real, FREE model AURA routes to — core/model_router.MODELS,
// on OpenRouter's ":free" endpoints or Groq's free tier. Rings used to mark
// paid LLMs; nothing here is paid, so a ring now marks a model that can see
// images.

export type ModelStatus = "active" | "standby";

export interface ModelNode {
  id: string;
  name: string;
  /** Short label for tight spots (agent strip, chips). */
  short: string;
  /** Backend model id — what the brain reports as the model that answered. */
  modelId: string;
  role: string;        // archetype, e.g. "The Researcher"
  nature: string;      // short personality line from the design sheet
  status: ModelStatus;
  color: string;
  ring?: boolean; // models that can see images wear Saturn rings
  // ---- spec sheet (Models page) ----
  provider: string;
  /** Rough throughput feel — used for the speed bar (0–100). */
  speed: number;
  /** Context window, human-readable. */
  context: string;
  /** What AURA routes to it for. */
  purpose: string;
  /** Cost band: "free" | "$" | "$$" | "$$$". */
  cost: string;
  /** Lower = earlier in the job chains (coding → research → chat → vision → safety net). */
  priority: number;
  // Legacy % offsets (old constellation layout) — kept for compatibility.
  x: number;
  y: number;
  // ---- planets installed from a pasted key or link (core/integrations) ----
  installed?: boolean;
  jobs?: string[];
  /** The provider's own model id (modelId is AURA's "ext:<n>" routing id). */
  wire?: string;
  integration_id?: number;
  created_at?: string | null;
}

export const MODELS: ModelNode[] = [
  // ── Names must match core/model_router.MODELS = the model_lock keys, so
  //    locking a planet really locks the model. ──
  // Coding: North Mini Code → Laguna XS 2.1 → Qwen3.8 27B
  { id: "north",     name: "North Mini Code",        short: "North",     modelId: "cohere/north-mini-code:free",
    role: "The Coder",        nature: "Precise · Logical · Sharp",      status: "standby", color: "#6C6BFF", x: 12,  y: -36,
    provider: "OpenRouter", speed: 82, context: "256K", purpose: "Code generation & refactors — first pick", cost: "free", priority: 1 },
  { id: "laguna",    name: "Laguna XS 2.1",          short: "Laguna",    modelId: "poolside/laguna-xs-2.1:free",
    role: "The Builder",      nature: "Steady · Methodical · Hands-on", status: "standby", color: "#B18BFF", x: 28,  y: -24,
    provider: "OpenRouter", speed: 55, context: "262K", purpose: "Coding backup", cost: "free", priority: 2 },
  { id: "qwen",      name: "Qwen3.8 27B",            short: "Qwen",      modelId: "qwen/qwen3.8-27b",
    role: "The Fixer",        nature: "Quick · Resourceful · Exact",    status: "standby", color: "#FFD166", x: -26, y: -30,
    provider: "Groq", speed: 97, context: "131K", purpose: "Third coder · backup for background jobs", cost: "free", priority: 3 },
  // Research, plans, explaining: Nemotron 3 Super → Dots 3 Note
  { id: "nemotron",  name: "Nemotron 3 Super",       short: "Nemotron",  modelId: "nvidia/nemotron-3-super-120b-a12b:free",
    role: "The Explorer",     nature: "Wide · Deep · Searching",        status: "standby", color: "#38E1FF", x: 40,  y: -8,
    provider: "OpenRouter", speed: 88, context: "262K", purpose: "Research, plans & long reasoning — first pick", cost: "free", priority: 4 },
  { id: "dots",      name: "Dots 3 Note",            short: "Dots",      modelId: "dots-studio/dots-3-note-preview:free",
    role: "The Scout",        nature: "Fast · Far-reaching · Focused",  status: "standby", color: "#4C8DFF", ring: true, x: 32, y: 8,
    provider: "OpenRouter", speed: 74, context: "512K", purpose: "Research backup (preview release)", cost: "free", priority: 5 },
  // Chat: Gemma 4 31B → Nex N2.5 Pro
  { id: "gemma",     name: "Gemma 4 31B",            short: "Gemma",     modelId: "google/gemma-4-31b-it:free",
    role: "The Companion",    nature: "Friendly · Balanced · Clear",    status: "standby", color: "#F472B6", ring: true, x: 24, y: 30,
    provider: "OpenRouter", speed: 80, context: "262K", purpose: "Conversation — first pick · image checks", cost: "free", priority: 6 },
  { id: "nex",       name: "Nex N2.5 Pro",           short: "Nex",       modelId: "nex-agi/nex-n2.5-pro:free",
    role: "The Communicator", nature: "Warm · Articulate · Grounded",   status: "standby", color: "#35E08F", ring: true, x: -34, y: 2,
    provider: "OpenRouter", speed: 58, context: "262K", purpose: "Conversation — third in line", cost: "free", priority: 7 },
  // Vision: Gemma 4 31B → Nemotron Nano Omni → Ling 3.0 Flash VL
  { id: "omni",      name: "Nemotron Nano Omni",     short: "Omni",      modelId: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    role: "The Observer",     nature: "Watchful · Literal · Quick",     status: "standby", color: "#FF8C42", ring: true, x: -12, y: 38,
    provider: "OpenRouter", speed: 80, context: "256K", purpose: "Image checks backup", cost: "free", priority: 8 },
  { id: "ling",      name: "Ling 3.0 Flash VL",      short: "Ling",      modelId: "inclusionai/ling-3.0-flash-vl:free",
    role: "The Lens",         nature: "Sharp-eyed · Brief · Calm",      status: "standby", color: "#A3E635", ring: true, x: 6, y: -44,
    provider: "OpenRouter", speed: 78, context: "262K", purpose: "Image checks — last resort", cost: "free", priority: 9 },
  // Groq safety net for every job, plus background work
  { id: "llama",     name: "GPT-OSS 120B",           short: "OSS-120B",  modelId: "openai/gpt-oss-120b",
    role: "The Guardian",     nature: "Protective · Active · Reliable", status: "standby", color: "#FF5A5A", x: -22, y: 30,
    provider: "Groq", speed: 92, context: "131K", purpose: "Safety net for every job — always on", cost: "free", priority: 10 },
  { id: "llama8b",   name: "GPT-OSS 20B",            short: "OSS-20B",   modelId: "openai/gpt-oss-20b",
    role: "The Archivist",    nature: "Silent · Stable · Instant",      status: "standby", color: "#E6E6FF", x: -40, y: -20,
    provider: "Groq", speed: 99, context: "131K", purpose: "Instant classification, memory & nudges", cost: "free", priority: 11 },
];
