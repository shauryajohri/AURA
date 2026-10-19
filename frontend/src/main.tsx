import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import GuardGate from "./components/Guard/GuardGate";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* Buddy Lock: AURA only opens up for her buddy (see core/guard). */}
    <GuardGate>
      <App />
    </GuardGate>
  </React.StrictMode>
);
