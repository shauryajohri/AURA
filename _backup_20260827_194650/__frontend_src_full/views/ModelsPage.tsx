import PageShell from "./PageShell";
import ModelsView from "./ModelsView";
import ModelSpecs from "./ModelSpecs";
import SkillsView from "./SkillsView";
import IntelligenceView from "./IntelligenceView";
import { usePlanetStore } from "../stores/planetStore";
import { useCoreStore } from "../stores/coreStore";
import { MODELS } from "../data/models";
import type { V3Event } from "../types";

/**
 * Models — the planet system's control room. Roster + routing locks live in
 * ModelsView; the orbit editor is a launcher (orbits are edited live on the
 * Home canvas, where the planets actually are); Performance hosts the V3
 * intelligence stream; Skills rounds out what AURA can do.
 */

function OrbitEditorPane({ onGoHome }: { onGoHome: () => void }) {
  const startPlanets = usePlanetStore((s) => s.startEdit);
  const startCore = useCoreStore((s) => s.startEdit);

  return (
    <div className="orbitpane">
      <div className="orbitpane__roster">
        {MODELS.map((m) => (
          <div key={m.id} className="orbitpane__planet">
            <span className="orbitpane__dot" style={{ background: m.color }} />
            <span className="orbitpane__name">{m.name}</span>
            <span className="orbitpane__role">{m.role}</span>
            <span className="orbitpane__nature">{m.nature}</span>
            {m.ring && <span className="orbitpane__ring">◍ ringed</span>}
          </div>
        ))}
      </div>
      <p className="pane-note">
        Orbits are edited live around the core — drag any planet onto a new ring
        and the routing follows it. One planet per orbit; swaps are automatic.
      </p>
      <div className="orbitpane__actions">
        <button
          className="orbitpane__btn orbitpane__btn--primary"
          onClick={() => { startPlanets(); onGoHome(); }}
        >
          Edit orbits on Home →
        </button>
        <button
          className="orbitpane__btn"
          onClick={() => { startCore(); onGoHome(); }}
        >
          Adjust the AURA Core →
        </button>
      </div>
    </div>
  );
}

interface Props {
  v3Events: V3Event[];
  onGoHome: () => void;
  activeModelId?: string | null;
}

export default function ModelsPage({ v3Events, onGoHome, activeModelId = null }: Props) {
  return (
    <PageShell
      title="Models"
      tagline="Each model is a planet with its own nature — routing is gravity."
      storeKey="aura.page.models"
      tabs={[
        { id: "specs", label: "Specifications", body: <ModelSpecs activeModelId={activeModelId} /> },
        { id: "planets", label: "Planet Management", body: <ModelsView /> },
        { id: "orbits", label: "Orbit Editor", body: <OrbitEditorPane onGoHome={onGoHome} /> },
        { id: "performance", label: "Performance", body: <IntelligenceView events={v3Events} /> },
        { id: "skills", label: "Skills", body: <SkillsView /> },
      ]}
    />
  );
}
