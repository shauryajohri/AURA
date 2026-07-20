import { useState } from "react";
import { useDomainStore } from "../../../stores/domainStore";

// Landing view inside the Domain — projects + quick actions.
// "Where ideas evolve into real projects."

const QUICK: { icon: string; label: string; section?: string }[] = [
  { icon: "✚", label: "New Project" },
  { icon: "↻", label: "Continue Session", section: "projects" },
  { icon: "❖", label: "Generate Image", section: "images" },
  { icon: "◎", label: "Research Topic", section: "research" },
  { icon: "⌥", label: "Build Application", section: "code" },
  { icon: "≡", label: "Analyze PDF", section: "documents" },
  { icon: "⎇", label: "Open Repository", section: "code" },
];

export default function DomainDashboard() {
  const projects = useDomainStore((s) => s.projects);
  const activeId = useDomainStore((s) => s.activeId);
  const openProject = useDomainStore((s) => s.openProject);
  const createProject = useDomainStore((s) => s.createProject);
  const setSection = useDomainStore((s) => s.setSection);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createProject(name.trim());
    setName("");
    setCreating(false);
  };

  return (
    <div className="ddash">
      <div className="ddash__hero">
        <h2>Welcome to your Domain</h2>
        <p>Where ideas evolve into real projects.</p>
      </div>

      {/* quick actions */}
      <div className="ddash__quick">
        {QUICK.map((q) => (
          <button
            key={q.label}
            className="ddash__qbtn"
            onClick={() =>
              q.label === "New Project"
                ? setCreating(true)
                : q.section && setSection(q.section as any)
            }
          >
            <span className="ddash__qicon">{q.icon}</span>
            <span>{q.label}</span>
          </button>
        ))}
      </div>

      {creating && (
        <form className="ddash__create" onSubmit={submit}>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name the project…"
            onKeyDown={(e) => e.key === "Escape" && setCreating(false)}
          />
          <button type="submit">Create</button>
        </form>
      )}

      {/* projects */}
      <div className="ddash__section">Projects</div>
      <div className="ddash__grid">
        {projects.map((p) => {
          const total = p.board.reduce((n, c) => n + c.cards.length, 0);
          const done = p.board.find((c) => c.id === "done")?.cards.length ?? 0;
          const pct = total ? Math.round((done / total) * 100) : 0;
          return (
            <button
              key={p.id}
              className={"ddash__card" + (p.id === activeId ? " ddash__card--on" : "")}
              style={{ ["--accent" as string]: p.accent }}
              onClick={() => openProject(p.id)}
            >
              <div className="ddash__cardglow" />
              <div className="ddash__cardname">{p.name}</div>
              <div className="ddash__cardblurb">{p.blurb}</div>
              <div className="ddash__cardmeta">
                <span>{total} tasks</span>
                <span>{p.files.length} files</span>
                <span>{p.docs.length} docs</span>
              </div>
              <div className="ddash__cardbar">
                <div style={{ width: `${pct}%` }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
