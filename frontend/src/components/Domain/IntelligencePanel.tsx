import { useEffect, useMemo, useState } from "react";
import { MODELS } from "../../data/models";
import { useActiveProject, useDomainStore } from "../../stores/domainStore";

// ============================================================================
// Right Intelligence Panel — AURA's visible thought process.
// Current model · active tasks · reasoning stream · suggestions · jobs.
// All mock-driven for now; the WebSocket brain replaces the intervals later.
// ============================================================================

const REASONING: Record<string, string[]> = {
  dashboard: [
    "Scanning project graph…",
    "AURA Core has 2 tasks in flight",
    "Suggesting next focus: portal polish",
    "All memory indices healthy",
  ],
  projects: [
    "Reading board state…",
    "In Progress column is balanced",
    "Review has 1 card aging — flag it?",
    "Estimating: shell lands today",
  ],
  code: [
    "Parsing open buffer…",
    "No syntax errors detected",
    "router.py: consider caching ranked list",
    "Style is consistent with core/",
  ],
  notes: [
    "Indexing document headings…",
    "Cross-linking to project board",
    "Tone: visionary. Keeping it.",
  ],
  default: [
    "Listening…",
    "Context window synced",
    "Background reasoning idle",
  ],
};

const SUGGESTIONS: Record<string, string[]> = {
  dashboard: ["Continue last session", "Plan today's build", "Review aging tasks"],
  projects: ["Break down 'WebSocket bridge'", "Assign an agent to Review", "Archive Done column"],
  code: ["Explain this file", "Generate unit tests", "Refactor for clarity"],
  notes: ["Summarize this doc", "Extract action items", "Polish the writing"],
  default: ["Ask AURA anything", "Generate an image", "Research a topic"],
};

interface Job {
  id: string;
  label: string;
  model: string;
  progress: number; // 0..1
}

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

export default function IntelligencePanel({ collapsed, onToggle }: Props) {
  const section = useDomainStore((s) => s.section);
  const modelId = useDomainStore((s) => s.modelId);
  const project = useActiveProject();

  const model = MODELS.find((m) => m.id === modelId) ?? MODELS[0];
  const lines = REASONING[section] ?? REASONING.default;
  const suggestions = SUGGESTIONS[section] ?? SUGGESTIONS.default;

  // reasoning stream: reveal lines one at a time, loop gently
  const [step, setStep] = useState(0);
  useEffect(() => {
    setStep(0);
    const t = setInterval(() => setStep((s) => (s + 1) % (lines.length + 2)), 2400);
    return () => clearInterval(t);
  }, [section, lines.length]);

  // background jobs: mock progress that creeps forward
  const [jobs, setJobs] = useState<Job[]>([
    { id: "j1", label: "Indexing project memory", model: "llama8b", progress: 0.35 },
    { id: "j2", label: "Watching repo for changes", model: "nemotron", progress: 0.72 },
  ]);
  useEffect(() => {
    const t = setInterval(
      () =>
        setJobs((js) =>
          js.map((j) => ({ ...j, progress: j.progress >= 1 ? 0.08 : j.progress + 0.013 }))
        ),
      900
    );
    return () => clearInterval(t);
  }, []);

  // active tasks = cards in the In Progress column
  const active = useMemo(
    () => project?.board.find((c) => c.id === "progress")?.cards ?? [],
    [project]
  );

  if (collapsed) {
    return (
      <button className="dintel-reveal" onClick={onToggle} title="Intelligence panel">
        ✦
      </button>
    );
  }

  return (
    <aside className="dintel">
      <div className="dintel__head">
        <span className="dintel__title">INTELLIGENCE</span>
        <button className="dintel__collapse" onClick={onToggle} title="Collapse">»</button>
      </div>

      {/* current model */}
      <div className="dintel__model">
        <span className="dintel__orb" style={{ background: model.color, boxShadow: `0 0 18px ${model.color}` }} />
        <div>
          <div className="dintel__modelname">{model.name}</div>
          <div className="dintel__modelrole">{model.role} · {model.nature}</div>
        </div>
      </div>

      {/* reasoning stream */}
      <div className="dintel__section">Reasoning</div>
      <div className="dintel__stream">
        {lines.map((l, i) => (
          <div
            key={section + i}
            className={"dintel__line" + (i <= step ? " dintel__line--on" : "")}
          >
            <span className="dintel__tick" />
            {l}
          </div>
        ))}
      </div>

      {/* active tasks */}
      <div className="dintel__section">Active tasks</div>
      <div className="dintel__tasks">
        {active.length === 0 && <div className="dintel__empty">Nothing in flight.</div>}
        {active.map((c) => {
          const agent = MODELS.find((m) => m.id === c.agent);
          return (
            <div key={c.id} className="dintel__task">
              <span
                className="dintel__taskdot"
                style={agent ? { background: agent.color, boxShadow: `0 0 6px ${agent.color}` } : undefined}
              />
              <span className="dintel__tasktitle">{c.title}</span>
              {agent && <span className="dintel__taskagent">{agent.name.split(" ")[0]}</span>}
            </div>
          );
        })}
      </div>

      {/* suggested actions */}
      <div className="dintel__section">Suggested</div>
      <div className="dintel__suggest">
        {suggestions.map((s) => (
          <button key={s} className="dintel__chip">{s}</button>
        ))}
      </div>

      {/* background jobs */}
      <div className="dintel__section">Background</div>
      <div className="dintel__jobs">
        {jobs.map((j) => {
          const m = MODELS.find((x) => x.id === j.model);
          return (
            <div key={j.id} className="dintel__job">
              <div className="dintel__jobrow">
                <span>{j.label}</span>
                <span className="dintel__jobmodel" style={{ color: m?.color }}>
                  {m?.name.split(" ")[0]}
                </span>
              </div>
              <div className="dintel__bar">
                <div
                  className="dintel__barfill"
                  style={{ width: `${Math.round(j.progress * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
