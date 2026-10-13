import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import GuardGate from "./components/Guard/GuardGate";
import AgentOverlay from "./AgentOverlay";
import "./styles.css";

// The same bundle also serves the desktop app's tiny always-on-top agent
// control bar (index.html#agent-overlay) — no universe, no chat, just the bar.
const overlay = window.location.hash === "#agent-overlay";
if (overlay) document.documentElement.classList.add("agent-overlay-root");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* Buddy Lock: AURA only opens up for her buddy (see core/guard). The
        agent bar is only Stop and Allow / Deny for a /do task started from
        the main window, which is behind the gate. */}
    {overlay ? (
      <AgentOverlay />
    ) : (
      <GuardGate>
        <App />
      </GuardGate>
    )}
  </React.StrictMode>
);
