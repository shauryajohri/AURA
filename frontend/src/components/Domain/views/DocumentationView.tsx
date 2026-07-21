import { useMemo, useState } from "react";
import { renderMd } from "../markdown";
import AppsTab from "./AppsTab";
import {
  useActiveProject,
  useDomainStore,
  type RoadmapState,
} from "../../../stores/domainStore";

// ============================================================================
// Documentation — project docs, roadmaps, and the connected apps.
//
// Three surfaces:
//   Docs     markdown editor + live preview (project documentation)
//   Roadmap  planned / in-flight / shipped lanes with targets
//   Apps     Figma, Word, PowerPoint, Excel — live files, edited in place
// ============================================================================

type Tab = "docs" | "roadmap" | "apps";

const LANES: { id: RoadmapState; label: string; color: string }[] = [
  { id: "planned", label: "Planned", color: "#8b8fca" },
  { id: "active", label: "In Flight", color: "#38e1ff" },
  { id: "shipped", label: "Shipped", color: "#35e08f" },
];

// ---------------------------------------------------------------- docs tab
function DocsTab() {
  const project = useActiveProject()!;
  const addDoc = useDomainStore((s) => s.addDoc);
  const updateDoc = useDomainStore((s) => s.updateDoc);
  const renameDoc = useDomainStore((s) => s.renameDoc);
  const removeDoc = useDomainStore((s) => s.removeDoc);

  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  const doc = project.docs.find((d) => d.id === openId) ?? project.docs[0] ?? null;
  const html = useMemo(() => (doc ? renderMd(doc.content) : ""), [doc?.content]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) addDoc(name.trim());
    setName("");
    setAdding(false);
  };

  return (
    <div className="dmd">
      <div className="dcode__rail">
        <div className="dcode__railhead">
          <span>DOCS</span>
          <button onClick={() => setAdding(true)} title="New doc">✚</button>
        </div>
        {adding && (
          <form onSubmit={submit} className="dcode__newfile">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Doc name"
              onBlur={() => setAdding(false)}
              onKeyDown={(e) => e.key === "Escape" && setAdding(false)}
            />
          </form>
        )}
        {project.docs.map((d) => (
          <div key={d.id} className="dcode__row">
            <button
              className={"dcode__file" + (doc?.id === d.id ? " dcode__file--on" : "")}
              onClick={() => setOpenId(d.id)}
              onDoubleClick={() => {
                const n = prompt("Rename doc", d.name);
                if (n?.trim()) renameDoc(d.id, n.trim());
              }}
            >
              <span className="dcode__lang dcode__lang--md">md</span>
              <span className="dcode__fname">{d.name}</span>
            </button>
            <button className="dcode__del" onClick={() => removeDoc(d.id)} title="Delete">✕</button>
          </div>
        ))}
        {project.docs.length === 0 && <div className="dcode__empty">No docs yet.</div>}
      </div>

      {doc ? (
        <div className="dmd__split">
          <textarea
            className="dmd__editor"
            value={doc.content}
            spellCheck={false}
            onChange={(e) => updateDoc(doc.id, e.target.value)}
          />
          <div className="dmd__preview" dangerouslySetInnerHTML={{ __html: html }} />
        </div>
      ) : (
        <div className="dph"><h3>No doc open</h3><p>Create one in the rail.</p></div>
      )}
    </div>
  );
}

// ------------------------------------------------------------- roadmap tab
function RoadmapTab() {
  const project = useActiveProject()!;
  const addRoadmap = useDomainStore((s) => s.addRoadmap);
  const patchRoadmap = useDomainStore((s) => s.patchRoadmap);
  const removeRoadmap = useDomainStore((s) => s.removeRoadmap);

  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    addRoadmap(title.trim(), target.trim() || undefined);
    setTitle("");
    setTarget("");
  };

  const advance = (id: string, state: RoadmapState) => {
    const next: RoadmapState =
      state === "planned" ? "active" : state === "active" ? "shipped" : "planned";
    patchRoadmap(id, { state: next });
  };

  return (
    <div className="droad">
      <form className="droad__new" onSubmit={submit}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Milestone…" />
        <input
          className="droad__target"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="target (Q3, Aug…)"
        />
        <button type="submit" disabled={!title.trim()}>Add</button>
      </form>

      <div className="droad__lanes">
        {LANES.map((lane) => {
          const items = project.roadmap.filter((r) => r.state === lane.id);
          return (
            <div key={lane.id} className="droad__lane" style={{ ["--lane" as string]: lane.color }}>
              <div className="droad__lanehead">
                {lane.label}
                <span>{items.length}</span>
              </div>
              {items.map((r) => (
                <div key={r.id} className="droad__item">
                  <button
                    className="droad__advance"
                    onClick={() => advance(r.id, r.state)}
                    title="Move to next stage"
                  >
                    →
                  </button>
                  <div className="droad__body">
                    <div className="droad__title">{r.title}</div>
                    {r.target && <div className="droad__when">{r.target}</div>}
                  </div>
                  <button className="droad__del" onClick={() => removeRoadmap(r.id)} title="Remove">✕</button>
                </div>
              ))}
              {items.length === 0 && <div className="droad__empty">—</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- shell
export default function DocumentationView() {
  const project = useActiveProject();
  const [tab, setTab] = useState<Tab>("docs");

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  return (
    <div className="ddocs">
      <div className="ddocs__tabs">
        {([["docs", "Docs"], ["roadmap", "Roadmap"], ["apps", "Apps"]] as [Tab, string][])
          .map(([id, label]) => (
            <button
              key={id}
              className={"ddocs__tab" + (tab === id ? " ddocs__tab--on" : "")}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
      </div>
      <div className="ddocs__body">
        {tab === "docs" && <DocsTab />}
        {tab === "roadmap" && <RoadmapTab />}
        {tab === "apps" && <AppsTab />}
      </div>
    </div>
  );
}
