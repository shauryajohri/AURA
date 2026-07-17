import { useCallback, useEffect, useRef, useState } from "react";
import { useAuraSocket } from "./hooks/useAuraSocket";
import { useLocalStorage } from "./hooks/useLocalStorage";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Stage from "./components/Stage";
import ChatPanel from "./components/ChatPanel";
import Resizer from "./components/Resizer";
import CosmicBackground from "./components/CosmicBackground";
import UniverseBackground from "./components/UniverseBackground";
import ParticleField from "./components/ParticleField";
import Sanctuary from "./components/Sanctuary";
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

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export default function App() {
  const { status, auraState, presence, mode, activeModelId, turns, send } = useAuraSocket();
  const [sidebarOpen, setSidebarOpen] = useLocalStorage<boolean>("aura.sidebarOpen", true);
  const [chatOpen, setChatOpen] = useLocalStorage<boolean>("aura.chatOpen", true);
  const [chatWidth, setChatWidth] = useLocalStorage<number>("aura.chatWidth", 460);
  const [view, setView] = useLocalStorage<string>("aura.view", "home");
  // Animated universe video (Layer 1). If the file is missing/unplayable we
  // fall back to the procedural cosmic canvas so the app never goes flat black.
  const [videoOk, setVideoOk] = useState(true);
  const handleVideoFail = useCallback(() => setVideoOk(false), []);

  // ---- Screen 1 ⇄ Screen 2 cinematic transition ---------------------------
  // Wheel-driven: scrolling down glides into the sanctuary, scrolling up
  // returns. Progress p ∈ [0,1] is eased every frame — no cuts, no routes.
  const [target, setTarget] = useState(0);
  const [p, setP] = useState(0);
  const pRef = useRef(0);
  const [ambientOk, setAmbientOk] = useState(true);
  const ambientRef = useRef<HTMLVideoElement>(null);

  // Some Chromium builds refuse autoplay for videos that mount at opacity 0.
  // Kick playback explicitly whenever the sanctuary comes into view (and the
  // wheel gesture itself counts as user activation, so play() always succeeds).
  useEffect(() => {
    const v = ambientRef.current;
    if (target === 1 && v && v.paused) {
      v.play().catch(() => { /* retried on next transition */ });
    }
  }, [target]);

  useEffect(() => {
    let raf = 0;
    const step = () => {
      const cur = pRef.current;
      const next = cur + (target - cur) * 0.085;
      if (Math.abs(next - target) < 0.001) {
        pRef.current = target;
        setP(target);
        return; // settled
      }
      pRef.current = next;
      setP(next);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  useEffect(() => {
    const onWheel = (e: WheelEvent) => {
      const el = e.target as HTMLElement | null;
      // don't hijack scrolling inside scrollable UI (chat log, views, nav)
      if (el?.closest(".chat__log, .view, .nav, .coremenu, .sanctuary__grid")) return;
      if (e.deltaY > 25) setTarget(1);
      else if (e.deltaY < -25) setTarget(0);
    };
    window.addEventListener("wheel", onWheel, { passive: true });
    return () => window.removeEventListener("wheel", onWheel);
  }, []);

  const entered = p > 0.85;

  // Only emit tracks for panels that are actually rendered —
  // otherwise the center section lands in a 0px track and the layout implodes.
  const cols =
    (sidebarOpen ? SIDEBAR_W + "px " : "") +
    "1fr" +
    (chatOpen ? " 6px " + chatWidth + "px" : "");

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
    <div className="scroll-root">
      {/* ---- Screen 1: the cosmos dashboard (fades upward on scroll) ---- */}
      <div
        className="screen screen--one"
        style={{
          opacity: 1 - p,
          transform: `translateY(${-38 * p}vh)`,
          pointerEvents: p < 0.4 ? "auto" : "none",
        }}
      >
        <div className="app" style={{ gridTemplateColumns: cols }}>
          {videoOk ? (
            <UniverseBackground state={auraState} onFail={handleVideoFail} />
          ) : (
            <CosmicBackground state={auraState} />
          )}
          <ParticleField state={auraState} />

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
          </section>

          {chatOpen ? (
            <>
              <Resizer onResize={setChatWidth} />
              <ChatPanel status={status} turns={turns} onSend={send} onCollapse={() => setChatOpen(false)} />
            </>
          ) : (
            <button className="chat-reveal" onClick={() => setChatOpen(true)} title="Show chat">
              {"💬"}
            </button>
          )}
        </div>
      </div>

      {/* ---- Screen 2 background: looping ambient video ---- */}
      <div className="screen screen--ambient" style={{ opacity: p }} aria-hidden={p === 0}>
        {ambientOk ? (
          <video
            ref={ambientRef}
            src="/ambient.mp4"
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
            onError={() => setAmbientOk(false)}
          />
        ) : (
          <div className="ambient-fallback" />
        )}
        <div className="ambient-shade" />
      </div>

      {/* ---- Screen 2 UI: the sanctuary ---- */}
      <div
        className="screen screen--sanctuary"
        style={{
          opacity: clamp01((p - 0.35) / 0.65),
          pointerEvents: p > 0.75 ? "auto" : "none",
        }}
      >
        <Sanctuary entered={entered} onHome={() => setTarget(0)} />
      </div>
    </div>
  );
}
