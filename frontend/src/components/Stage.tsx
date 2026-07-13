import type { AuraState } from "../types";
import BlackHole from "./BlackHole";
import ModelConstellation from "./ModelConstellation";
import EventsPanel from "./EventsPanel";

interface Props {
  state: AuraState;
  activeModelId?: string | null;
}

export default function Stage({ state, activeModelId = null }: Props) {
  return (
    <div className="stage">
      <ModelConstellation activeId={activeModelId} />
      <BlackHole state={state} />

      <EventsPanel />
    </div>
  );
}
