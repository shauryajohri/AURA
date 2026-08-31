import type { ActivityEvent, AuraState } from "../types";
import BlackHole from "./BlackHole";
import EventsPanel from "./EventsPanel";

interface Props {
  state: AuraState;
  activeModelId?: string | null;
  /** Live "what AURA is doing" line from the brain — wins over the state map. */
  activity?: ActivityEvent | null;
  /** Voice capture running (mic hot) — shows Listening… while idle. */
  listening?: boolean;
}

const STATE_TEXT: Record<string, string> = {
  idle: "Idle — ready",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

// Planets live inside the BlackHole canvas — models orbiting the core,
// the one that last answered lights up and orbits faster.
export default function Stage({ state, activeModelId = null, activity = null, listening = false }: Props) {
  const text =
    activity?.text ??
    (state === "idle" && listening ? "Listening…" : STATE_TEXT[state] ?? "");
  const live = state !== "idle" || !!activity || listening;

  return (
    <div className="stage">
      <BlackHole state={state} activeModelId={activeModelId} />

      <div className={"corestatus" + (live ? " corestatus--live" : "")}>
        <span className="corestatus__dot" />
        <span className="corestatus__text" key={text}>{text}</span>
      </div>

      <EventsPanel />
    </div>
  );
}
