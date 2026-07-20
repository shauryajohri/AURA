import type { AuraState } from "../types";
import BlackHole from "./BlackHole";
import EventsPanel from "./EventsPanel";

interface Props {
  state: AuraState;
  activeModelId?: string | null;
}

// Planets live inside the BlackHole canvas now — models orbiting the core,
// the one that last answered lights up and orbits faster.
export default function Stage({ state, activeModelId = null }: Props) {
  return (
    <div className="stage">
      <BlackHole state={state} activeModelId={activeModelId} />

      <EventsPanel />
    </div>
  );
}
