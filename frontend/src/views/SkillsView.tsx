import { useEffect, useState } from "react";
import { MODELS } from "../data/models";
import { api, ModelInfo } from "../api";

// ============================================================================
// Skills — what AURA can do, and which mind she uses to do it.
// Two halves: her capabilities, and the live LLM roster (who's specialised in
// what, who's locked, who answered last).
// ============================================================================

interface Skill {
  icon: string;
  name: string;
  blurb: string;
  routes: string;   // which model usually handles it
  live: boolean;    // wired up vs planned
}

const SKILLS: Skill[] = [
  {
    icon: "⌨", name: "Write & debug code",
    blurb: "Writes, explains, refactors and debugs across Python, JS/TS, C++ and more. Reads your project files for context and classifies errors by severity.",
    routes: "North Mini Code → Laguna XS 2.1 → Qwen3.8 27B", live: true,
  },
  {
    icon: "◎", name: "Research anything",
    blurb: "Digs into a topic and reports back — direct answer first, detail second. Long-form mode for full write-ups.",
    routes: "Nemotron 3 Super → Dots 3 Note", live: true,
  },
  {
    icon: "◌", name: "Chat with you",
    blurb: "Everyday conversation, opinions and brainstorming — in the nature you picked, with your shared history in mind.",
    routes: "Gemma 4 31B → Nex N2.5 Pro", live: true,
  },
  {
    icon: "❋", name: "Remember you",
    blurb: "Durable facts about you, conversation history and session recaps. She actually recalls — nothing is faked.",
    routes: "GPT-OSS 20B → Qwen3.8 27B", live: true,
  },
  {
    icon: "✓", name: "Manage tasks",
    blurb: "Add, complete, edit and clear tasks by voice or from any panel. Everything stays in one store.",
    routes: "local", live: true,
  },
  {
    icon: "◈", name: "Route between minds",
    blurb: "Classifies intent, picks the specialist model, falls back automatically when one is rate-limited, and honours your locks. Every job has at least two free models.",
    routes: "core router", live: true,
  },
  {
    icon: "♪", name: "Talk & listen",
    blurb: "Speaks replies aloud with a natural speech plan, listens for the wake word, and knows when to stay quiet.",
    routes: "hears: Whisper v3 Turbo → Whisper v3 → Google · speaks: edge-tts → Windows voice", live: true,
  },
  {
    icon: "◉", name: "Watch your screen",
    blurb: "Reads what's on screen when asked, notices patterns in what you're working on, and comments only when it helps.",
    routes: "local OCR · image checks: Gemma 4 31B → Nemotron Nano Omni → Ling 3.0 Flash VL", live: true,
  },
  {
    icon: "✦", name: "Speak up on her own",
    blurb: "Proactive nudges, curiosity and attention — she starts conversations when something's worth saying.",
    routes: "GPT-OSS 120B / 20B → Qwen3.8 27B", live: true,
  },
  {
    icon: "▣", name: "Plan & organise projects",
    blurb: "Breaks goals into plans, keeps projects, boards, notes and code together in the Domain workspace.",
    routes: "Nemotron 3 Super → Dots 3 Note", live: true,
  },
  {
    icon: "❖", name: "Generate images",
    blurb: "Image creation from a prompt, kept alongside the project it belongs to.",
    routes: "planned", live: false,
  },
];

const MODEL_DETAIL: Record<string, { best: string; speed: string; provider: string }> = {
  north:    { best: "Writing and fixing code", speed: "Fast", provider: "OpenRouter" },
  laguna:   { best: "Coding when North is busy", speed: "Medium", provider: "OpenRouter" },
  qwen:     { best: "Third coder, backup for background jobs", speed: "Very fast", provider: "Groq" },
  nemotron: { best: "Research and long reasoning", speed: "Fast", provider: "OpenRouter" },
  dots:     { best: "Research when Nemotron is busy", speed: "Fast", provider: "OpenRouter" },
  gemma:    { best: "Everyday conversation and image checks", speed: "Fast", provider: "OpenRouter" },
  nex:      { best: "Conversation when Gemma is busy", speed: "Slow", provider: "OpenRouter" },
  omni:     { best: "Image checks backup", speed: "Fast", provider: "OpenRouter" },
  ling:     { best: "Image checks, last resort", speed: "Fast", provider: "OpenRouter" },
  llama:    { best: "Safety net for every job, proactive lines", speed: "Very fast", provider: "Groq" },
  llama8b:  { best: "Background jobs, classifying, memory", speed: "Instant", provider: "Groq" },
};

export default function SkillsView() {
  const [locks, setLocks] = useState<ModelInfo[]>([]);
  const [lastModel, setLastModel] = useState("");
  const [tab, setTab] = useState<"skills" | "models">("skills");

  const refresh = () =>
    api.getModels()
      .then((r) => { setLocks(r.models); setLastModel(r.last_model); })
      .catch(() => {});

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);

  const isLocked = (name: string) => locks.find((l) => l.name === name)?.locked ?? false;

  return (
    <div className="skills">
      <div className="skills__head">
        <div>
          <h2>Skills</h2>
          <p>What AURA can do — and which mind she uses for it.</p>
        </div>
        <div className="skills__tabs">
          <button className={"skills__tab" + (tab === "skills" ? " skills__tab--on" : "")} onClick={() => setTab("skills")}>
            Abilities
          </button>
          <button className={"skills__tab" + (tab === "models" ? " skills__tab--on" : "")} onClick={() => setTab("models")}>
            Models
          </button>
        </div>
      </div>

      {tab === "skills" ? (
        <div className="skills__grid">
          {SKILLS.map((s) => (
            <div key={s.name} className={"skillcard" + (s.live ? "" : " skillcard--soon")}>
              <div className="skillcard__top">
                <span className="skillcard__icon">{s.icon}</span>
                <span className="skillcard__name">{s.name}</span>
                {!s.live && <span className="skillcard__soon">soon</span>}
              </div>
              <p className="skillcard__blurb">{s.blurb}</p>
              <div className="skillcard__routes">
                <span className="skillcard__routelabel">handled by</span>
                <span className="skillcard__route">{s.routes}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="skills__models">
          {MODELS.map((m) => {
            const d = MODEL_DETAIL[m.id];
            const locked = isLocked(m.name);
            const active = lastModel === m.modelId;
            return (
              <div key={m.id} className={"mrow" + (locked ? " mrow--locked" : "")}>
                <span className="mrow__orb" style={{ background: m.color, boxShadow: `0 0 12px ${m.color}` }} />
                <div className="mrow__meta">
                  <div className="mrow__namerow">
                    <span className="mrow__name">{m.name}</span>
                    <span className="mrow__role">{m.role}</span>
                    {active && <span className="mrow__badge mrow__badge--live">answered last</span>}
                    {locked && <span className="mrow__badge mrow__badge--locked">locked</span>}
                  </div>
                  <div className="mrow__nature">{m.nature}</div>
                  {d && <div className="mrow__best"><b>Best at:</b> {d.best}</div>}
                </div>
                {d && (
                  <div className="mrow__stats">
                    <span>{d.speed}</span>
                    <span className="mrow__provider">{d.provider}</span>
                  </div>
                )}
              </div>
            );
          })}
          <p className="skills__note">
            AURA picks the right model automatically for each request. Lock one from the
            Models panel and she'll never route to it.
          </p>
        </div>
      )}
    </div>
  );
}
