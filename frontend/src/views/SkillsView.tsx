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
    routes: "Laguna M.1", live: true,
  },
  {
    icon: "◎", name: "Research anything",
    blurb: "Digs into a topic and reports back — direct answer first, detail second. Long-form mode for full write-ups.",
    routes: "Nemotron 3 Super", live: true,
  },
  {
    icon: "❋", name: "Remember you",
    blurb: "Durable facts about you, conversation history and session recaps. She actually recalls — nothing is faked.",
    routes: "Llama 3.1 8B", live: true,
  },
  {
    icon: "✓", name: "Manage tasks",
    blurb: "Add, complete, edit and clear tasks by voice or from any panel. Everything stays in one store.",
    routes: "local", live: true,
  },
  {
    icon: "◈", name: "Route between minds",
    blurb: "Classifies intent, picks the specialist model, falls back automatically when one is rate-limited, and honours your locks.",
    routes: "core router", live: true,
  },
  {
    icon: "♪", name: "Talk & listen",
    blurb: "Speaks replies aloud with a natural speech plan, listens for the wake word, and knows when to stay quiet.",
    routes: "local voice", live: true,
  },
  {
    icon: "◉", name: "Watch your screen",
    blurb: "Reads what's on screen when asked, notices patterns in what you're working on, and comments only when it helps.",
    routes: "local vision/OCR", live: true,
  },
  {
    icon: "✦", name: "Speak up on her own",
    blurb: "Proactive nudges, curiosity and attention — she starts conversations when something's worth saying.",
    routes: "Llama 3.3 70B", live: true,
  },
  {
    icon: "▣", name: "Plan & organise projects",
    blurb: "Breaks goals into plans, keeps projects, boards, notes and code together in the Domain workspace.",
    routes: "Nemotron 3 Super", live: true,
  },
  {
    icon: "❖", name: "Generate images",
    blurb: "Image creation from a prompt, kept alongside the project it belongs to.",
    routes: "planned", live: false,
  },
];

const MODEL_DETAIL: Record<string, { best: string; speed: string; provider: string }> = {
  laguna:   { best: "Writing and fixing code", speed: "Fast", provider: "OpenRouter" },
  nemotron: { best: "Research and long reasoning", speed: "Medium", provider: "OpenRouter" },
  gemma:    { best: "Everyday conversation", speed: "Fast", provider: "OpenRouter" },
  llama:    { best: "General fallback, proactive lines", speed: "Very fast", provider: "Groq" },
  llama8b:  { best: "Background jobs, classifying, memory", speed: "Instant", provider: "Groq" },
  gpt4o:    { best: "Balanced all-rounder", speed: "Fast", provider: "not routed yet" },
  gemini:   { best: "Research with wide context", speed: "Fast", provider: "not routed yet" },
  claude:   { best: "Deep analysis and writing", speed: "Medium", provider: "not routed yet" },
  grok:     { best: "Real-time, blunt takes", speed: "Fast", provider: "not routed yet" },
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
            const active = lastModel && (lastModel.includes(m.id) || m.name === lastModel);
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
