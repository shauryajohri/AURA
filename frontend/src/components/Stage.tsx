import type { AuraState } from "../types";
import BlackHole from "./BlackHole";
import EventsPanel from "./EventsPanel";

interface Props {
  state: AuraState;
  activeModelId?: string | null;
}

// ModelConstellation (planet orbs) removed — planets are being redesigned.
export default function Stage({ state }: Props) {
  return (
    <div className="stage">
      <BlackHole state={state} />

      <EventsPanel />
    </div>
  );
}
