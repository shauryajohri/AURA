import { useState } from "react";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import { useDomainStore } from "../../stores/domainStore";
import DomainNav from "./DomainNav";
import DomainHeader from "./DomainHeader";
import IntelligencePanel from "./IntelligencePanel";
import DomainDashboard from "./views/DomainDashboard";
import PlanningBoard from "./views/PlanningBoard";
import CodePane from "./views/CodePane";
import MarkdownPane from "./views/MarkdownPane";
import AgentsView from "./views/AgentsView";
import DomainPlaceholder from "./views/DomainPlaceholder";
import "./domain.css";

// ============================================================================
// AURA Domain — the workspace beyond the beam.
// Left nav · adaptive center · right intelligence panel, all glass floating
// over the (future) animated cosmic background.
// ============================================================================

interface Props {
  onExit: () => void;
}

export default function DomainScreen({ onExit }: Props) {
  const section = useDomainStore((s) => s.section);
  const [navMin, setNavMin] = useLocalStorage<boolean>("aura.domain.navMin", false);
  const [intelOpen, setIntelOpen] = useLocalStorage<boolean>("aura.domain.intel", true);
  const [videoOk, setVideoOk] = useState(true);

  const center = () => {
    switch (section) {
      case "dashboard": return <DomainDashboard />;
      case "projects": return <PlanningBoard />;
      case "code": return <CodePane />;
      case "notes":
      case "documents": return <MarkdownPane />;
      case "agents": return <AgentsView />;
      case "research":
        return <DomainPlaceholder icon="◎" title="Research Canvas" line="A thinking surface for sources, threads and discoveries — arriving soon." />;
      case "images":
        return <DomainPlaceholder icon="❖" title="Image Forge" line="Generation and galleries will materialize here." />;
      case "terminal":
        return <DomainPlaceholder icon="❯" title="Terminal" line="A direct line into the machine — being wired to the brain." />;
      case "history":
        return <DomainPlaceholder icon="↺" title="History" line="Every session, every decision, replayable. Soon." />;
      default: return <DomainDashboard />;
    }
  };

  return (
    <div className="domain">
      {/* background: drop /domain.mp4 into frontend/public and it plays here.
          Until then, the dark placeholder gradient stands in. */}
      {videoOk ? (
        <video
          className="domain__video"
          src="/domain.mp4"
          autoPlay muted loop playsInline preload="auto"
          onError={() => setVideoOk(false)}
        />
      ) : (
        <div className="domain__bgfallback" />
      )}
      <div className="domain__shade" />

      <div className={"domain__grid" + (navMin ? " domain__grid--navmin" : "") + (!intelOpen ? " domain__grid--nointel" : "")}>
        <DomainNav collapsed={navMin} onToggle={() => setNavMin((v) => !v)} onExit={onExit} />
        <section className="domain__center">
          <DomainHeader />
          <div className="domain__body" key={section}>
            {center()}
          </div>
        </section>
        <IntelligencePanel collapsed={!intelOpen} onToggle={() => setIntelOpen((v) => !v)} />
      </div>
    </div>
  );
}
