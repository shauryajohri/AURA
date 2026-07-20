import { useCallback, useRef, useState } from "react";
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
import SanctuarySection from "./components/Home/SanctuarySection";
import TransitionParticles from "./components/Home/TransitionParticles";
import { useScrollJourney, seg } from "./components/Home/ScrollController";
import DomainScreen from "./components/Domain/DomainScreen";
import PortalTransition from "./components/Domain/PortalTransition";
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
  const [chatOpen, setChatOpen] = useLocalStorage<boolean>("aura.chatOpen", true);
  const [chatWidth, setChatWidth] = useLocalStorage<number>("aura.chatWidth", 460);
  const [view, setView] = useLocalStorage<string>("aura.view", "home");
  const [videoOk, setVideoOk] = useState(true);
  const handleVideoFail = useCallback(() => setVideoOk(false), []);
  const [ambientOk, setAmbientOk] = useState(true);
  const [transOk, setTransOk] = useState(true);

  // React state only flips at the very end of the journey (card reveal).
  const [entered, setEntered] = useState(false);
  const enteredRef = useRef(false);

  // ---- AURA Domain: the workspace beyond the beam -------------------------
  // portal: "in" = crossing into the Domain, "out" = returning to sanctuary.
  const [domainOpen, setDomainOpen] = useState(false);
  const [portal, setPortal] = useState<null | "in" | "out">(null);
  const enterDomain = useCallback(() => setPortal("in"), []);
  const exitDomain = useCallback(() => setPortal("out"), []);
  const portalDone = useCallback(() => setPortal(null), []);

  // Imperative layer refs — mutated per-frame, zero React re-renders.
  const screen1Ref = useRef<HTMLDivElement>(null);
  const transWrapRef = useRef<HTMLDivElement>(null);
  const transVideoRef = useRef<HTMLVideoElement>(null);
  const ambientWrapRef = useRef<HTMLDivElement>(null);
  const ambientVideoRef = useRef<HTMLVideoElement>(null);
  const sanRef = useRef<HTMLDivElement>(null);
  const transTextRef = useRef<HTMLDivElement>(null);
  const lastPRef = useRef(0);
  const dirRef = useRef<1 | -1>(1);

  useScrollJourney((p) => {
    const recede = seg(p, 0.25, 0.45);   // universe pulls back
    const uniFade = seg(p, 0.2, 0.5);    // and fades away
    const sanIn = seg(p, 0.88, 1);       // sanctuary emerges
    const vis = seg(p, 0.38, 0.48) * (1 - seg(p, 0.9, 0.99)); // bridge video

    const s1 = screen1Ref.current;
    if (s1) {
      s1.style.opacity = String(1 - uniFade);
      s1.style.transform = `scale(${1 - 0.1 * recede}) translateY(${-6 * recede}vh)`;
      s1.style.pointerEvents = p < 0.15 ? "auto" : "none";
      // fully faded → stop compositing the blurred panels entirely
      s1.style.visibility = uniFade >= 1 ? "hidden" : "visible";
    }

    const tw = transWrapRef.current;
    if (tw) {
      tw.style.opacity = String(vis);
      tw.style.visibility = vis <= 0 ? "hidden" : "visible";
    }
    const tv = transVideoRef.current;
    if (tv && tv.duration && vis > 0) {
      const t = tv.duration * seg(p, 0.45, 0.9);
      if (Math.abs(tv.currentTime - t) > 0.02) tv.currentTime = t;
    }

    // crossing-verses text: direction decides the message
    if (p !== lastPRef.current) dirRef.current = p > lastPRef.current ? 1 : -1;
    lastPRef.current = p;
    const tt = transTextRef.current;
    if (tt) {
      const msg = dirRef.current === 1 ? "ENTERING AURA CITY" : "ASCENDING TO THE COSMOS";
      if (tt.textContent !== msg) tt.textContent = msg;
      tt.style.opacity = String(vis);
    }

    const aw = ambientWrapRef.current;
    if (aw) {
      aw.style.opacity = String(sanIn);
      aw.style.visibility = sanIn <= 0 ? "hidden" : "visible";
    }
    const av = ambientVideoRef.current;
    if (av && sanIn > 0 && av.paused) av.play().catch(() => {});

    const sn = sanRef.current;
    if (sn) {
      sn.style.opacity = String(sanIn);
      sn.style.visibility = sanIn <= 0 ? "hidden" : "visible";
      sn.style.pointerEvents = p > 0.985 ? "auto" : "none";
    }

    const ent = p > 0.985;
    if (ent !== enteredRef.current) {
      enteredRef.current = ent;
      setEntered(ent);
    }
  });

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
      {/* ---- Section 1: the universe (scales back, then fades) ---- */}
      <div ref={screen1Ref} className="screen screen--one">
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

      {/* ---- Section 2: the bridge — video scrubbed by scroll ---- */}
      {transOk && (
        <div ref={transWrapRef} className="screen screen--transition" style={{ visibility: "hidden", opacity: 0 }}>
          <video
            ref={transVideoRef}
            src="/transition.mp4"
            muted
            playsInline
            preload="auto"
            onError={() => setTransOk(false)}
          />
          <TransitionParticles />
          <div ref={transTextRef} className="trans-text" style={{ opacity: 0 }}>
            ENTERING AURA CITY
          </div>
        </div>
      )}

      {/* ---- Section 3 background: looping ambient world ---- */}
      <div ref={ambientWrapRef} className="screen screen--ambient" style={{ visibility: "hidden", opacity: 0 }}>
        {ambientOk ? (
          <video
            ref={ambientVideoRef}
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

      {/* ---- Section 3 UI: the sanctuary ---- */}
      <div
        ref={sanRef}
        className={"screen screen--sanctuary" + (portal === "in" ? " screen--recede" : "")}
        style={{ visibility: "hidden", opacity: 0, pointerEvents: "none" }}
      >
        <SanctuarySection entered={entered} onEnterDomain={enterDomain} />
      </div>

      {/* ---- The Domain: workspace beyond the beam ---- */}
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
