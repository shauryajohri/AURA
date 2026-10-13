import { useEffect, useState } from "react";
import AgentBar, { agentActive } from "./components/AgentBar";
import type { AgentEvent } from "./types";

/**
 * The desktop app's always-on-top control bar (loaded as index.html#agent-overlay
 * in its own small, non-focusable window). It listens to the brain directly —
 * only for "agent" events — and tells Electron when to show itself, so the bar
 * and the Allow / Deny buttons stay visible over whatever app AURA is using.
 */
const URL = window.aura?.bridgeUrl ?? "ws://127.0.0.1:8760/ws";

export default function AgentOverlay() {
  const [agent, setAgent] = useState<AgentEvent | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let alive = true;
    const connect = () => {
      ws = new WebSocket(URL);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "agent") setAgent(msg.payload);
        } catch { /* not ours */ }
      };
      ws.onclose = () => { if (alive) retry = setTimeout(connect, 2000); };
    };
    connect();
    return () => { alive = false; if (retry) clearTimeout(retry); ws?.close(); };
  }, []);

  const active = agentActive(agent);
  const height = agent?.state === "confirm" ? 118 : 64;
  useEffect(() => {
    window.aura?.agentOverlay?.({ active, height });
  }, [active, height]);

  return <AgentBar agent={agent} floating />;
}
