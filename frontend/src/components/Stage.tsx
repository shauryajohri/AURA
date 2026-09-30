import type { ActivityEvent, AuraState } from "../types";
import BlackHole from "./BlackHole";

interface Props {
  state: AuraState;
  activeModelId?: string | null;
  /** Live "what AURA is doing" line from the brain — wins over the state map. */
  activity?: ActivityEvent | null;
  /** AURA is busy on something in the background. */
  listening?: boolean;
}

const STATE_TEXT: Record<string, string> = {
  idle: "Ready",
  thinking: "Thinking",
  speaking: "Speaking",
};

// Planets live inside the BlackHole canvas — models orbiting the core; the
// one that last answered lights up and orbits faster.
export default function Stage({ state, activeModelId = null, activity = null, listening = false }: Props) {
  const text =
    activity?.text ??
    (state === "idle" && listening ? "Working" : STATE_TEXT[state] ?? "");
  const live = state !== "idle" || !!activity || listening;

  return (
    <div className="stage">
      <BlackHole state={state} activeModelId={activeModelId} />
      <div className={"corestatus" + (live ? " corestatus--live" : "")} aria-live="polite">
        <span className="corestatus__dot" />
        <span className="corestatus__text" key={text}>{text}</span>
      </div>
    </div>
  );
}
