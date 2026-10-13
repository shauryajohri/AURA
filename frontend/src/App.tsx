import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { useAuraSocket } from "./hooks/useAuraSocket";
import { useBuddyRelay } from "./hooks/useBuddyRelay";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useSettingsStore } from "./stores/settingsStore";
import { useGuardStore } from "./stores/guardStore";
import { usePerfStore } from "./stores/perfStore";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Stage from "./components/Stage";
import ChatDock from "./components/ChatDock";
import HomeStatusCard from "./components/HomeStatusCard";
import WorldBackdrop from "./components/WorldBackdrop";
import ParticleField from "./components/ParticleField";
import CursorLens from "./components/CursorLens";
import PortalTransition from "./components/Domain/PortalTransition";
import { useSkinDocument } from "./skins/useSkin";
import AgentBar from "./components/AgentBar";

// Pages are code-split: Home boots instantly and the heavy panels (Domain's
// editor, the settings overlay, the memory/task views) only download when you
// actually open them. This is the single biggest startup win available.
const DomainScreen = lazy(() => import("./components/Domain/DomainScreen"));
const MemoryPage = lazy(() => import("./views/MemoryPage"));
const TasksPage = lazy(() => import("./views/TasksPage"));
const ModelsPage = lazy(() => import("./views/ModelsPage"));
const ThemesPage = lazy(() => import("./views/ThemesPage"));
const SettingsView = lazy(() => import("./views/SettingsView"));
const LabsPage = lazy(() => import("./views/LabsPage"));
const ChatsPage = lazy(() => import("./views/ChatsPage"));

/** A guest (Buddy Lock) gets AURA's conversation, not the owner's life. */
function GuestOnly({ owner, onGoHome }: { owner: string; onGoHome: () => void }) {
  return (
    <div className="guestonly">
      <span className="guestonly__icon">{"🔒"}</span>
      <h2>That's {owner || "my buddy"}'s</h2>
      <p>You're here as a guest — I can help you in the chat, but this page belongs to {owner || "them"}.</p>
      <button onClick={onGoHome}>Back to the chat</button>
    </div>
  );
}

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
const PAGES = ["home", "chats", "memory", "tasks", "models", "themes", "settings", "labs"];

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, v3Events, questEvent, roomEvent, activity, agent,
          send, loadTurns, clearTurns } = useAuraSocket();
  useBuddyRelay(status, auraState, presence, turns, send);
  const [collapsed, setCollapsed] = useLocalStorage<boolean>("aura.sidebarMin", false);
  const [rawView, setView] = useLocalStorage<string>("aura.view", "home");
  const view = PAGES.includes(rawView) ? rawView : LEGACY[rawView] ?? "home";
  const guest = useGuardStore((s) => s.status?.role === "guest");
  const ownerName = useGuardStore((s) => s.status?.owner_name ?? "");

  // Pull saved appearance/voice settings from the brain once at startup and
  // push them into the visual stores (core, planets, background).
  const perf = usePerfStore((s) => s.perf);
  const loadSettings = useSettingsStore((s) => s.load);
  useEffect(() => { loadSettings(); }, [loadSettings]);
  // In prod Electron spawns the brain alongside this window, so that first
  // load usually fails and leaves the store offline on defaults. Try again
  // when the socket opens. `loaded` is a dep so a load that fails after the
  // socket is already open still gets its retry; `offline` is read, not
  // watched, so a failed save doesn't trigger a reload over the user's edit.
  const settingsLoaded = useSettingsStore((s) => s.loaded);
  useEffect(() => {
    if (status === "open" && settingsLoaded && useSettingsStore.getState().offline) loadSettings();
  }, [status, settingsLoaded, loadSettings]);

  // The skin being worn: tints :root's colour variables, and picks the sky.
  const { skin, backdrop } = useSkinDocument();

  // ---- AURA Domain: the workspace beyond the portal -----------------------
  const [domainOpen, setDomainOpen] = useState(false);
  const [portal, setPortal] = useState<null | "in" | "out">(null);
  // Guests chat on Home; the Domain (the owner's code, terminal, projects)
  // stays shut — and an open one closes if the role drops to guest.
  const enterDomain = useCallback(() => { if (!guest) setPortal("in"); }, [guest]);
  useEffect(() => { if (guest && domainOpen) setDomainOpen(false); }, [guest, domainOpen]);
  const exitDomain = useCallback(() => setPortal("out"), []);
  const portalDone = useCallback(() => setPortal(null), []);

  const goHome = useCallback(() => setView("home"), [setView]);

  const renderPage = () => {
    if (guest) return <GuestOnly owner={ownerName} onGoHome={goHome} />;
    switch (view) {
      case "chats":
        // Same socket as the dock — one conversation, two places to see it.
        return <ChatsPage onSend={send} roomEvent={roomEvent} />;
      case "memory":
        return <MemoryPage />;
      case "tasks":
        return <TasksPage questEvent={questEvent} />;
      case "models":
        return <ModelsPage v3Events={v3Events} onGoHome={goHome} activeModelId={activeModelId} />;
      case "themes":
        return <ThemesPage />;
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
      {/* the living universe — always behind everything; which one is the
          skin's call (films fall back to a live sky if they can't play) */}
      <WorldBackdrop backdrop={backdrop} skin={skin} state={auraState} />
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
              <Stage
                state={auraState}
                activeModelId={activeModelId}
                activity={activity}
                listening={presence === "working"}
                // Home stays mounted under the Domain; without this the core
                // kept drawing behind it and the Domain ran at ~6 fps.
                paused={domainOpen}
              />
              <HomeStatusCard status={status} activeModelId={activeModelId} mode={mode} />
            </div>
            <ChatDock status={status} turns={turns} onSend={send} auraState={auraState}
                      onLoadTurns={loadTurns} onClearTurns={clearTurns} roomEvent={roomEvent} />
          </div>
        ) : (
          <div className="os-page page-fade" key={view}>
            <Suspense fallback={<PageLoading />}>{renderPage()}</Suspense>
          </div>
        )}
      </main>

      {/* ---- The Domain: a different workspace entirely ---- */}
      {domainOpen && (
        <div className="screen screen--domain">
          <Suspense fallback={<PageLoading />}>
            <DomainScreen onExit={exitDomain} />
          </Suspense>
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

      {/* AURA operating the screen (/do): what she's doing, Stop, Allow/Deny */}
      <AgentBar agent={agent} />

      {/* the pointer is a tiny black hole — lives above everything
          (skipped in performance mode; the OS cursor image stays) */}
      {!perf && <CursorLens />}
    </div>
  );
}
