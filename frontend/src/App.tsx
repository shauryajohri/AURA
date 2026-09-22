import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { useAuraSocket } from "./hooks/useAuraSocket";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useSettingsStore } from "./stores/settingsStore";
import { useSavedStore } from "./stores/savedStore";
import { useRosterStore } from "./stores/rosterStore";
import { useSkinStore } from "./stores/skinStore";
import { useBootStore } from "./stores/bootStore";
import { usePrefs } from "./stores/prefsStore";
import { emitCore } from "./lib/coreBus";
import { sources } from "./systemApi";
import { sfx } from "./lib/sfx";
import type { SavedItem } from "./types";
import Sidebar from "./components/Sidebar";
import Stage from "./components/Stage";
import ChatDock from "./components/ChatDock";
import HomeGreeting from "./components/HomeGreeting";
import { StageTools, WindowControls } from "./components/Chrome";
import SpaceBackground from "./components/SpaceBackground";
import AuraCursor from "./components/AuraCursor";
import AuraOrb from "./components/AuraOrb";
import BootSequence from "./components/BootSequence";
import PortalTransition from "./components/Domain/PortalTransition";

// Pages are code-split: Home boots instantly and the heavy panels (Domain's
// editor, the settings overlay, the memory/task views) only download when you
// actually open them. This is the single biggest startup win available.
const DomainScreen = lazy(() => import("./components/Domain/DomainScreen"));
const MemoryPage = lazy(() => import("./views/MemoryPage"));
const TasksPage = lazy(() => import("./views/TasksPage"));
const ModelsPage = lazy(() => import("./views/ModelsPage"));
const SettingsView = lazy(() => import("./views/SettingsView"));
const LabsPage = lazy(() => import("./views/LabsPage"));
const ChatsPage = lazy(() => import("./views/ChatsPage"));
const SavedInfoPage = lazy(() => import("./views/SavedInfoPage"));
const PlanetsPage = lazy(() => import("./views/PlanetsPage"));
const UpgradePage = lazy(() => import("./views/UpgradePage"));

/** Shown for the instant a lazy page is fetched — the orb, breathing. */
function PageLoading() {
  return (
    <div className="pageloading">
      <AuraOrb size={40} />
      <span className="pageloading__text">Opening</span>
    </div>
  );
}

/**
 * AURA — one fixed shell around a black hole.
 *
 * Home is the permanent landing page, split in two: the sky, where the core
 * and its planets live and never get pushed around, and the conversation pane
 * on the right. Every other page opens on a sheet laid over the sky, and
 * "Aura Domain" crosses the portal into the coding workspace.
 */

// Old localStorage view ids → the page that now owns that feature.
const LEGACY: Record<string, string> = {
  quests: "tasks",
  skills: "models",
  analytics: "models",
};
const PAGES = ["home", "chats", "saved", "memory", "tasks", "models", "planets", "settings", "labs", "upgrade"];

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, v3Events, questEvent, activity, send,
          loadTurns, clearTurns } = useAuraSocket();
  const [collapsed, setCollapsed] = useLocalStorage<boolean>("aura.sidebarMin", true);
  const [rawView, setView] = useLocalStorage<string>("aura.view", "home");
  const view = PAGES.includes(rawView) ? rawView : LEGACY[rawView] ?? "home";
  const bootPhase = useBootStore((s) => s.phase);
  const customCursor = usePrefs((s) => s.cursor);
  // The system cursor is hidden only while AURA's own cursor is drawn.
  useEffect(() => {
    document.documentElement.classList.toggle("aura-cursor", customCursor);
  }, [customCursor]);

  // The startup plays on Home — that's where the black hole lives.
  useEffect(() => {
    if (bootPhase === "intro" && view !== "home") setView("home");
  }, [bootPhase]); // eslint-disable-line react-hooks/exhaustive-deps

  // The floating orb (desktop app) glows with whatever AURA is doing.
  useEffect(() => { window.aura?.orbState?.(auraState); }, [auraState]);
  // …and appears whenever this page can't be seen. Chromium reports real
  // occlusion on Windows, so "another window is on top of AURA" lands here
  // even when the OS focus events don't say so.
  useEffect(() => {
    const report = () => window.aura?.orbVisible?.(document.visibilityState === "visible");
    report();
    document.addEventListener("visibilitychange", report);
    return () => document.removeEventListener("visibilitychange", report);
  }, []);

  // Pull saved appearance/voice settings from the brain once at startup.
  const loadSettings = useSettingsStore((s) => s.load);
  useEffect(() => { loadSettings(); }, [loadSettings]);

  // Saved Info and installed planets: loaded once here, then kept live by the
  // socket's "saved" / "planets" frames.
  const loadSaved = useSavedStore((s) => s.load);
  const loadRoster = useRosterStore((s) => s.load);
  useEffect(() => { void loadSaved(); void loadRoster(); }, [loadSaved, loadRoster]);
  // The brain may boot after the window — retry the roster when it connects.
  useEffect(() => { if (status === "open") void loadRoster(); }, [status, loadRoster]);

  // Everything you've connected — your GitHub, your document folders — is
  // pulled fresh the moment AURA can reach the brain. The brain also syncs on
  // its own startup; this covers the other order, where the window was already
  // open and the brain came up second.
  const syncedRef = useRef(false);
  useEffect(() => {
    if (status !== "open" || syncedRef.current) return;
    syncedRef.current = true;
    void sources.syncAll().catch(() => { syncedRef.current = false; });
  }, [status]);

  // A reply arriving sends a ring of light out of the core.
  const lastAuraRef = useRef<{ id: string | null; n: number }>({ id: null, n: 0 });
  useEffect(() => {
    const last = turns[turns.length - 1];
    const prev = lastAuraRef.current;
    if (last && last.role === "aura" && last.id !== prev.id && turns.length - prev.n <= 1) {
      emitCore({ kind: "pulse" });
      sfx.chime();
    }
    lastAuraRef.current = { id: last?.role === "aura" ? last.id : prev.id, n: turns.length };
  }, [turns]);

  // Clicking a planet in orbit opens it on the Planets page.
  const setFocus = useSkinStore((s) => s.setFocus);
  useEffect(() => {
    const open = (e: Event) => {
      setFocus((e as CustomEvent<string>).detail);
      setView("planets");
    };
    window.addEventListener("aura:open-planet", open);
    return () => window.removeEventListener("aura:open-planet", open);
  }, [setFocus, setView]);

  // ---- AURA Domain: the workspace beyond the portal -----------------------
  const [domainOpen, setDomainOpen] = useState(false);
  const [portal, setPortal] = useState<null | "in" | "out">(null);
  const enterDomain = useCallback(() => setPortal("in"), []);
  const exitDomain = useCallback(() => setPortal("out"), []);
  const portalDone = useCallback(() => setPortal(null), []);

  const goHome = useCallback(() => setView("home"), [setView]);

  // Saved Info → "Ask AURA about it": back to Home, where the answer streams
  // into the dock (and is spoken, if voice is on).
  const askAbout = useCallback((item: SavedItem) => {
    setView("home");
    send(`Tell me about “${item.title}” from my Saved Info.`, {
      attachments: [{ id: item.id, name: item.title, kind: item.kind }],
      intent: "EXPLAIN",
    });
  }, [setView, send]);

  const renderPage = () => {
    switch (view) {
      case "chats":
        // Same socket as the dock — one conversation, two places to see it.
        return <ChatsPage onSend={send} />;
      case "saved":
        return <SavedInfoPage onAsk={askAbout} />;
      case "memory":
        return <MemoryPage />;
      case "tasks":
        return <TasksPage questEvent={questEvent} />;
      case "models":
        return <ModelsPage v3Events={v3Events} onGoHome={goHome} activeModelId={activeModelId} />;
      case "planets":
        return <PlanetsPage />;
      case "settings":
        return <SettingsView />;
      case "labs":
        return <LabsPage />;
      case "upgrade":
        return <UpgradePage />;
      default:
        return null;
    }
  };

  return (
    <div className="os-root" data-boot={bootPhase}>
      {/* deep space — always behind everything */}
      <SpaceBackground state={auraState} />

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
            <div className="sky">
              <Stage
                state={auraState}
                activeModelId={activeModelId}
                activity={activity}
                listening={presence === "working"}
              />
              <StageTools />
            </div>
            <ChatDock status={status} turns={turns} onSend={send} auraState={auraState}
                      onLoadTurns={loadTurns} onClearTurns={clearTurns}
                      head={<HomeGreeting status={status} mode={mode} />} />
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

      {!domainOpen && <WindowControls />}
      <BootSequence />
      {customCursor && <AuraCursor />}
    </div>
  );
}
