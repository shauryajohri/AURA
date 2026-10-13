import { useState } from "react";
import { api } from "../api";
import type { AgentEvent } from "../types";

/**
 * The control bar shown while AURA is operating the screen (/do).
 * Always says what she's doing, always has a Stop button, and when a step is
 * risky it becomes the Allow / Deny prompt. Used in the main window and in
 * the desktop app's always-on-top overlay.
 */
export const agentActive = (a: AgentEvent | null): boolean =>
  !!a && (a.state === "running" || a.state === "confirm");

export default function AgentBar({ agent, floating = false }: { agent: AgentEvent | null; floating?: boolean }) {
  const [busy, setBusy] = useState(false);
  if (!agent || !agentActive(agent)) return null;

  const answer = (allow: boolean) => {
    if (!agent.confirm_id) return;
    setBusy(true);
    api.agentConfirm(agent.confirm_id, allow).finally(() => setBusy(false));
  };
  const asking = agent.state === "confirm";

  return (
    <div className={"agentbar" + (floating ? " agentbar--floating" : "") + (asking ? " agentbar--ask" : "")}
         role={asking ? "alertdialog" : "status"} aria-live="polite">
      <div className="agentbar__row">
        <span className="agentbar__dot" />
        <span className="agentbar__text">
          <b>AURA is in control</b>
          <span className="agentbar__step">
            {asking ? agent.message : agent.action ? `step ${agent.step ?? 0}: ${agent.action}` : agent.goal}
          </span>
        </span>
        <button className="agentbar__stop" onClick={() => api.agentStop()} title="Stop (Esc)">
          Stop <kbd>Esc</kbd>
        </button>
      </div>
      {asking && (
        <div className="agentbar__row agentbar__row--ask">
          <button className="agentbar__allow" disabled={busy} onClick={() => answer(true)}>Allow</button>
          <button className="agentbar__deny" disabled={busy} onClick={() => answer(false)}>Deny</button>
        </div>
      )}
    </div>
  );
}
