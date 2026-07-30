import { useState } from "react";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import { useDomainStore } from "../../stores/domainStore";
import DomainNav from "./DomainNav";
import DomainHeader from "./DomainHeader";
import DomainChat from "./DomainChat";
import DomainBoundary from "./DomainBoundary";
import BrainDashboard from "./brain/BrainDashboard";
import ProjectsView from "./brain/ProjectsView";
import ResearchView from "./brain/ResearchView";
import BrainTasks from "./brain/BrainTasks";
import GraphView from "./brain/GraphView";
import BrainTimeline from "./brain/BrainTimeline";
import NodeDrawer from "./brain/NodeDrawer";
import CodePane from "./views/CodePane";
import CodeReviewView from "./views/CodeReviewView";
import DocumentationView from "./views/DocumentationView";
import NotesView from "./views/NotesView";
import TerminalView from "./views/TerminalView";
import DomainSettings from "./views/DomainSettings";
import AgentsView from "./views/AgentsView";
import "./domain.css";
import "./brain/brain.css";

// ============================================================================
// AURA Domain — the workspace beyond the beam.
// Left nav · adaptive center · right AURA chat. Widths, density, rounding,
// glass and background all come from the user's layout settings.
// ============================================================================

interface Props {
  onExit: () => void;
}

export default function DomainScreen({ onExit }: Props) {
  const section = useDomainStore((s) => s.section);
  const layout = useDomainStore((s) => s.layout);
  const [navMin, setNavMin] = useLocalStorage<boolean>("aura.domain.navMin", false);
  const [chatOpen, setChatOpen] = useLocalStorage<boolean>("aura.domain.intel", true);
  const [videoOk, setVideoOk] = useState(true);

  const showChat = layout.showChat && chatOpen;

  const center = () => {
    switch (section) {
      // the Project Brain owns these — real graph, not local mock state
      case "dashboard": return <BrainDashboard />;
      case "projects": return <ProjectsView />;
      case "research": return <ResearchView />;
      case "tasks": return <BrainTasks />;
      case "graph": return <GraphView />;
      case "history": return <BrainTimeline />;
      case "code": return <CodePane />;
      case "review": return <CodeReviewView />;
      case "documents": return <DocumentationView />;
      case "notes": return <NotesView />;
      case "terminal": return <TerminalView />;
      case "settings": return <DomainSettings />;
      case "agents": return <AgentsView />;
      default: return <BrainDashboard />;
    }
  };

  // layout knobs drive CSS custom properties on the root
  const vars = {
    ["--dnav-w" as string]: (navMin ? 64 : layout.navWidth) + "px",
    ["--dchat-w" as string]: layout.chatWidth + "px",
    ["--dradius" as string]: layout.radius + "px",
    ["--dglass" as string]: `blur(${layout.glass}px)`,
    ["--daccent" as string]: layout.accent,
  };

  return (
    <div
      className={"domain domain--" + layout.density + " domain--bg-" + layout.background}
      style={vars}
    >
      {layout.background === "video" && videoOk ? (
        <video
          className="domain__video"
          src="./domain.mp4"
          autoPlay muted loop playsInline preload="auto"
          onError={() => setVideoOk(false)}
        />
      ) : (
        <div className="domain__bgfallback" />
      )}
      <div className="domain__shade" />

      <div className={"domain__grid" + (!showChat ? " domain__grid--nochat" : "")}>
        <DomainNav collapsed={navMin} onToggle={() => setNavMin((v) => !v)} onExit={onExit} />

        <section className="domain__center">
          {layout.showHeader && <DomainHeader />}
          <div className="domain__body" key={section}>
            <DomainBoundary resetKey={section}>{center()}</DomainBoundary>
          </div>
        </section>

        {layout.showChat && (
          <DomainChat collapsed={!chatOpen} onToggle={() => setChatOpen((v) => !v)} />
        )}
      </div>

      {/* one drawer for the whole workspace: any view can open any node */}
      <NodeDrawer />
    </div>
  );
}
