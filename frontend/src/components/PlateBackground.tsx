import { useState } from "react";
import type { AuraState } from "../types";
import SkyBackground from "./SkyBackground";
import { PLATES, type PlateId, type Skin } from "../skins/skins";

interface Props {
  plate: PlateId;
  skin: Skin;
  state: AuraState;
}

/**
 * Layer 1 (still) — a rendered deep-space plate. It drifts very slowly so
 * the sky never looks frozen, brightens a little as AURA works, and pulses
 * while she speaks, like the filmed universe. A plate that is missing hands
 * the screen to its procedural stand-in. Keyed by plate in WorldBackdrop, so
 * a failure is forgotten when the plate changes.
 */
export default function PlateBackground({ plate, skin, state }: Props) {
  const [failed, setFailed] = useState(false);
  const { src, fallback } = PLATES[plate];
  if (failed) return <SkyBackground kind={fallback} sky={skin.sky} state={state} />;

  return (
    <div className={"plate-bg plate-bg--" + state} aria-hidden="true">
      <img src={src} alt="" decoding="async" onError={() => setFailed(true)} />
      {state === "speaking" && (
        <>
          <div className="universe-pulse" />
          <div className="universe-pulse universe-pulse--late" />
        </>
      )}
    </div>
  );
}
