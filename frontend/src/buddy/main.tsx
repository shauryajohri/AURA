/// <reference types="vite/client" />
import React from "react";
import ReactDOM from "react-dom/client";
import Buddy from "./Buddy";
import type { BuddyBridge } from "../types";
import "./buddy.css";

function mount(bridge: BuddyBridge) {
  ReactDOM.createRoot(document.getElementById("buddy-root")!).render(
    <React.StrictMode>
      <Buddy bridge={bridge} />
    </React.StrictMode>
  );
}

// Inside Electron the preload provides the bridge. In a plain browser tab
// (dev only) a stand-in fakes the desktop so the buddy can be worked on there.
if (window.aura?.buddy) mount(window.aura.buddy);
else if (import.meta.env.DEV) import("./devBridge").then((m) => mount(m.createDevBridge()));
