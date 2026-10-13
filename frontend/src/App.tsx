import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
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
import CursorLens from "./components/CursorLens";
import AgentBar from "./components/AgentBar";

// Pages are code-split: Home boots instantly and the heavy panels (the
// settings overlay, the memory/task views) only download when you actually
// open them. This is the single biggest startup win available.
const MemoryPage = lazy(() => import("./views/MemoryPage"));
const TasksPage = lazy(() => import("./views/TasksPage"));
const ModelsPage = lazy(() => import("./views/ModelsPage"));
const SettingsView = lazy(() => import("./views/SettingsView"));
const LabsPage = lazy(() => import("./views/LabsPage"));
const ChatsPage = lazy(() => import("./views/ChatsPage"));

/** Shown for the instant a lazy page is fetched — a calm pulse, never a jolt. */
function PageLoading() {
  return (
    <div className="pageloading">
      <span className="pageloading__orb" />
      <span className="pageloading__text">opening…</span>
    </div>
  );
}

/**
 * AURA OS — one fixed shell, no scroll journey.
 *
 * Home is the permanent landing page: the core at the center, the chat dock
 * at the bottom, one small status card. The glass sidebar opens every other
 * page with a crossfade. The old second "Village" screen is gone — what
 * lived there (tasks, links vault, memory, settings) lives in the pages now.
 */

// Old localStorage view ids → the page that now owns that feature.
const LEGACY: Record<string, string> = {
  quests: "tasks",
  skills: "models",
  analytics: "models",
};
const PAGES = ["home", "chats", "memory", "tasks", "models", "settings", "labs"];

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, v3Events, questEvent, activity, agent,
          send, loadTurns, clearTurns } = useAuraSocket();
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

  const goHome = useCallback(() => setView("home"), [setView]);

  const renderPage = () => {
    switch (view) {
      case "chats":
        // Same socket as the dock — one conversation, two places to see it.
        return <ChatsPage onSend={send} />;
      case "memory":
        return <MemoryPage />;
      case "tasks":
        return <TasksPage questEvent={questEvent} />;
      case "models":
        return <ModelsPage v3Events={v3Events} onGoHome={goHome} activeModelId={activeModelId} />;
      case "settings":
        return <SettingsView />;
      case "labs":
        return <LabsPage />;
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
        onToggle={() => setCollapsed(!collapsed)}
        listening={presence === "working" || auraState === "thinking"}
      />

      <main className="os-main">
        {view === "home" ? (
          <div className="os-home page-fade" key="home">
            <TopBar mode={mode} />
            <div className="os-stagewrap">
              <Stage
                state={auraState}
                activeModelId={activeModelId}
                activity={activity}
                listening={presence === "working"}
              />
              <HomeStatusCard status={status} activeModelId={activeModelId} mode={mode} />
            </div>
            <ChatDock status={status} turns={turns} onSend={send} auraState={auraState}
                      onLoadTurns={loadTurns} onClearTurns={clearTurns} />
          </div>
        ) : (
          <div className="os-page page-fade" key={view}>
            <Suspense fallback={<PageLoading />}>{renderPage()}</Suspense>
          </div>
        )}
      </main>

      {/* AURA operating the screen (/do): what she's doing, Stop, Allow/Deny */}
      <AgentBar agent={agent} />

      {/* the pointer is a tiny black hole — lives above everything */}
      <CursorLens />
    </div>
  );
}
