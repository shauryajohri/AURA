import { useEffect, useState } from "react";
import { MODELS } from "../../../data/models";
import { useDomainStore } from "../../../stores/domainStore";

// AI Agents — the collaboration view. Who is thinking, who is queued,
// what has been delegated. Calm, not cluttered.

interface Delegation {
  agent: string;
  job: string;
  state: "reasoning" | "queued" | "done";
}

const DELEGATIONS: Delegation[] = [
  { agent: "laguna", job: "Implement Domain workspace shell", state: "reasoning" },
  { agent: "claude", job: "Review portal transition timing", state: "reasoning" },
  { agent: "nemotron", job: "Research: local vector memory options", state: "queued" },
  { agent: "gemma", job: "Draft companion-mode copy", state: "queued" },
  { agent: "llama8b", job: "Index yesterday's session", state: "done" },
  { agent: "gpt4o", job: "Summarize repo changes", state: "done" },
];

export default function AgentsView() {
  const modelId = useDomainStore((s) => s.modelId);
  const [pulse, setPulse] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setPulse((p) => p + 1), 2000);
    return () => clearInterval(t);
  }, []);

  const groups: { title: string; state: Delegation["state"]; hint: string }[] = [
    { title: "Reasoning now", state: "reasoning", hint: "active thought" },
    { title: "Queued", state: "queued", hint: "waiting for a mind" },
    { title: "Completed", state: "done", hint: "delivered" },
  ];

  return (
    <div className="dagents">
      {/* the constellation strip — every mind, the selected one burning brighter */}
      <div className="dagents__ring">
        {MODELS.map((m, i) => {
          const active = m.id === modelId || DELEGATIONS.some((d) => d.agent === m.id && d.state === "reasoning");
          return (
            <div key={m.id} className={"dagents__node" + (active ? " dagents__node--on" : "")}>
              <span
                className="dagents__orb"
                style={{
                  background: m.color,
                  boxShadow: active ? `0 0 ${14 + ((pulse + i) % 2) * 6}px ${m.color}` : "none",
                }}
              />
              <span className="dagents__name">{m.name.split(" ")[0]}</span>
              <span className="dagents__role">{m.role}</span>
            </div>
          );
        })}
      </div>

      <div className="dagents__cols">
        {groups.map((g) => (
          <div key={g.state} className="dagents__col">
            <div className="dagents__colhead">
              <span>{g.title}</span>
              <span className="dagents__hint">{g.hint}</span>
            </div>
            {DELEGATIONS.filter((d) => d.state === g.state).map((d) => {
              const m = MODELS.find((x) => x.id === d.agent)!;
              return (
                <div key={d.job} className={"dagents__job dagents__job--" + d.state}>
                  <span className="dagents__jobdot" style={{ background: m.color, boxShadow: `0 0 8px ${m.color}` }} />
                  <div>
                    <div className="dagents__jobtitle">{d.job}</div>
                    <div className="dagents__jobagent">{m.name}</div>
                  </div>
                  {d.state === "reasoning" && <span className="dagents__think"><i /><i /><i /></span>}
                  {d.state === "done" && <span className="dagents__check">✓</span>}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
