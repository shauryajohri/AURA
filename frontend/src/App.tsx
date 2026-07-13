import { useAuraSocket } from "./hooks/useAuraSocket";
import { useLocalStorage } from "./hooks/useLocalStorage";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Stage from "./components/Stage";
import ChatPanel from "./components/ChatPanel";
import ControlBar from "./components/ControlBar";
import Resizer from "./components/Resizer";
import CosmicBackground from "./components/CosmicBackground";
import TasksView from "./views/TasksView";
import ModelsView from "./views/ModelsView";
import MemoryView from "./views/MemoryView";
import PlaceholderView from "./views/PlaceholderView";

const SIDEBAR_W = 244;

const TITLES: Record<string, string> = {
  quests: "Quests",
  skills: "Skills",
  inventory: "Inventory",
  workspace: "Workspace",
  analytics: "Analytics",
  settings: "Settings",
};

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, send } = useAuraSocket();
  const [sidebarOpen, setSidebarOpen] = useLocalStorage<boolean>("aura.sidebarOpen", true);
  const [chatWidth, setChatWidth] = useLocalStorage<number>("aura.chatWidth", 460);
  const [view, setView] = useLocalStorage<string>("aura.view", "home");

  const cols = (sidebarOpen ? SIDEBAR_W : 0) + "px 1fr 6px " + chatWidth + "px";

  const renderCenterBody = () => {
    switch (view) {
      case "home":
        return <Stage state={auraState} activeModelId={activeModelId} />;
      case "tasks":
        return <TasksView />;
      case "models":
        return <ModelsView />;
      case "memory":
      case "settings":
        return view === "memory" ? <MemoryView /> : <PlaceholderView title="Settings" />;
      default:
        return <PlaceholderView title={TITLES[view] || view} />;
    }
  };

  return (
    <div className="app" style={{ gridTemplateColumns: cols }}>
      <CosmicBackground state={auraState} />

      {sidebarOpen ? (
        <Sidebar
          active={view}
          onNavigate={setView}
          listening={presence === "working" || auraState === "thinking"}
          onCollapse={() => setSidebarOpen(false)}
        />
      ) : (
        <button className="sidebar-reveal" onClick={() => setSidebarOpen(true)} title="Show sidebar">
          {"☰"}
        </button>
      )}

      <section className="center">
        <TopBar mode={mode} />
        {renderCenterBody()}
        <ControlBar state={auraState} />
      </section>

      <Resizer onResize={setChatWidth} />

      <ChatPanel status={status} turns={turns} onSend={send} />
    </div>
  );
}
