import { useCallback, useEffect, useRef, useState } from "react";
import { useAuraSocket } from "./hooks/useAuraSocket";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useSettingsStore } from "./stores/settingsStore";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Stage from "./components/Stage";
import ChatDock from "./components/ChatDock";
import HomeStatusCard from "./components/HomeStatusCard";
import CosmicBackground from "./components/CosmicBackground";
import UniverseBackground from "./components/UniverseBackground";
import ParticleField from "./components/ParticleField";
import DomainScreen from "./components/Domain/DomainScreen";
import PortalTransition from "./components/Domain/PortalTransition";
import MemoryPage from "./views/MemoryPage";
import TasksPage from "./views/TasksPage";
import ModelsPage from "./views/ModelsPage";
import SettingsView from "./views/SettingsView";

/**
 * AURA OS — one fixed shell, no scroll journey.
 *
 * Home is the permanent landing page: the core at the center, the chat dock
 * at the bottom, one small status card. The glass sidebar opens every other
 * page with a crossfade, and "Aura Domain" crosses the portal into the
 * dedicated coding workspace. The old second "Village" screen is gone — what
 * lived there (tasks, links vault, memory, settings) lives in the pages now.
 */

// Old localStorage view ids → the page that now owns that feature.
const LEGACY: Record<string, string> = {
  quests: "tasks",
  skills: "models",
  analytics: "models",
};
const PAGES = ["home", "memory", "tasks", "models", "settings"];

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, v3Events, questEvent, send } =
    useAuraSocket();
  const [collapsed, setCollapsed] = useLocalStorage<boolean>("aura.sidebarMin", false);
  const [rawView, setView] = useLocalStorage<string>("aura.view", "home");
  const view = PAGES.includes(rawView) ? rawView : LEGACY[rawView] ?? "home";

  // Background video health. A failure swaps in the CSS starfield, but a
  // transient decoder hiccup shouldn't cost the universe until restart —
  // retry with backoff before giving up.
  const [videoOk, setVideoOk] = useState(true);
  const videoRetriesRef = useRef(0);
  const handleVideoFail = useCallback(() => {
    setVideoOk(false);
    if (videoRetriesRef.current >= 2) return;
    const delay = 15000 * (videoRetriesRef.current + 1);
    videoRetriesRef.current += 1;
    setTimeout(() => setVideoOk(true), delay);
  }, []);

  // Pull saved appearance/voice settings from the brain once at startup and
  // push them into the visual stores (core, planets, background).
  const loadSettings = useSettingsStore((s) => s.load);
  useEffect(() => { loadSettings(); }, [loadSettings]);

  // ---- AURA Domain: the workspace beyond the portal -----------------------
  const [domainOpen, setDomainOpen] = useState(false);
  const [portal, setPortal] = useState<null | "in" | "out">(null);
  const enterDomain = useCallback(() => setPortal("in"), []);
  const exitDomain = useCallback(() => setPortal("out"), []);
  const portalDone = useCallback(() => setPortal(null), []);

  const goHome = useCallback(() => setView("home"), [setView]);

  const renderPage = () => {
    switch (view) {
      case "memory":
        return <MemoryPage />;
      case "tasks":
        return <TasksPage questEvent={questEvent} />;
      case "models":
        return <ModelsPage v3Events={v3Events} onGoHome={goHome} />;
      case "settings":
        return <SettingsView />;
      default:
        return null;
    }
  };

  return (
    <div className="os-root">
      {/* the living universe — always behind everything, never replaced */}
      {videoOk ? (
        <UniverseBackground state={auraState} onFail={handleVideoFail} />
      ) : (
        <CosmicBackground state={auraState} />
      )}
      <ParticleField state={auraState} />

      <Sidebar
        active={view}
        collapsed={collapsed}
        onNavigate={setView}
        onLaunchDomain={enterDomain}
        onToggle={() => setCollapsed(!collapsed)}
        listening={presence === "working" || auraState === "thinking"}
      />

      <main className="os-main">
        {view === "home" ? (
          <div className="os-home page-fade" key="home">
            <TopBar mode={mode} />
            <div className="os-stagewrap">
              <Stage state={auraState} activeModelId={activeModelId} />
              <HomeStatusCard status={status} activeModelId={activeModelId} mode={mode} />
            </div>
            <ChatDock status={status} turns={turns} onSend={send} auraState={auraState} />
          </div>
        ) : (
          <div className="os-page page-fade" key={view}>
            {renderPage()}
          </div>
        )}
      </main>

      {/* ---- The Domain: a different workspace entirely ---- */}
      {domainOpen && (
        <div className="screen screen--domain">
          <DomainScreen onExit={exitDomain} />
        </div>
      )}

      {/* ---- Portal overlay: crossing the threshold ---- */}
      {portal && (
        <PortalTransition
          direction={portal}
          onMid={() => setDomainOpen(portal === "in")}
          onDone={portalDone}
        />
      )}
    </div>
  );
}
