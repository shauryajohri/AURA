import { useState } from "react";
import { MODELS } from "../../data/models";
import { SECTION_META, useActiveProject, useDomainStore } from "../../stores/domainStore";

// Minimal top bar: project · breadcrumb · model selector · search · bells.

// Labels come from the store so nav, header and settings can never disagree.
const SECTION_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(SECTION_META).map(([k, v]) => [k, v.label])
);

export default function DomainHeader() {
  const project = useActiveProject();
  const section = useDomainStore((s) => s.section);
  const modelId = useDomainStore((s) => s.modelId);
  const setModel = useDomainStore((s) => s.setModel);
  const [modelOpen, setModelOpen] = useState(false);
  const [query, setQuery] = useState("");

  const model = MODELS.find((m) => m.id === modelId) ?? MODELS[0];

  return (
    <header className="dhead">
      <div className="dhead__crumb">
        <span className="dhead__brand">AURA DOMAIN</span>
        <span className="dhead__sep">/</span>
        <span className="dhead__project" style={{ color: project?.accent }}>
          {project?.name ?? "No project"}
        </span>
        <span className="dhead__sep">/</span>
        <span className="dhead__section">{SECTION_LABEL[section]}</span>
      </div>

      <div className="dhead__search">
        <span className="dhead__searchicon">◌</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search across everything…"
        />
      </div>

      <div className="dhead__right">
        <div className="dhead__model">
          <button className="dhead__modelbtn" onClick={() => setModelOpen((o) => !o)}>
            <span className="dhead__modeldot" style={{ background: model.color, boxShadow: `0 0 8px ${model.color}` }} />
            <span>{model.name}</span>
            <span className="dhead__chev">{modelOpen ? "▴" : "▾"}</span>
          </button>
          {modelOpen && (
            <div className="dhead__modelmenu">
              {MODELS.map((m) => (
                <button
                  key={m.id}
                  className={"dhead__modelrow" + (m.id === modelId ? " dhead__modelrow--on" : "")}
                  onClick={() => { setModel(m.id); setModelOpen(false); }}
                >
                  <span className="dhead__modeldot" style={{ background: m.color }} />
                  <span className="dhead__modelname">{m.name}</span>
                  <span className="dhead__modelrole">{m.role}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="dhead__iconbtn" title="Notifications">◔</button>
        <button className="dhead__avatar" title="Shaurya">S</button>
        <span className="winctl">
          <button className="winctl__btn" title="Minimize" onClick={() => window.aura?.minimize?.()}>—</button>
          <button className="winctl__btn winctl__btn--close" title="Close" onClick={() => window.aura?.close?.()}>✕</button>
        </span>
      </div>
    </header>
  );
}
