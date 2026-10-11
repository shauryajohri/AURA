import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AuraState } from "../types";
import UniverseBackground, { UNIVERSE_SOURCES } from "./UniverseBackground";
import CosmicBackground from "./CosmicBackground";
import SkyBackground from "./SkyBackground";
import { FILMS, isFilm, type BackdropId, type Skin } from "../skins/skins";
import type { SkyKind } from "../skins/backdrops";

interface Props {
  backdrop: BackdropId;
  skin: Skin;
  state: AuraState;
}

/** What to paint when there is no film to play (or it failed). */
function stillFor(backdrop: BackdropId): "cosmos" | SkyKind {
  if (backdrop === "video") return "cosmos";
  if (isFilm(backdrop)) return FILMS[backdrop].fallback;
  return backdrop;
}

/**
 * Layer 1 — the living universe, always behind everything.
 *
 * Which universe is the skin's call: AURA's own filmed cosmos, a skin's
 * Higgsfield film, the constellation web, or one of the procedural skies.
 * A film that is missing or can't decode drops to its procedural stand-in,
 * and a transient decoder hiccup shouldn't cost the film until restart, so
 * it's retried with backoff (twice) before staying on the stand-in.
 */
export default function WorldBackdrop({ backdrop, skin, state }: Props) {
  const sources = useMemo(
    () => (backdrop === "video" ? UNIVERSE_SOURCES : isFilm(backdrop) ? [FILMS[backdrop].src] : null),
    [backdrop],
  );
  const key = sources ? sources.join("|") : "";

  const [failedKey, setFailedKey] = useState<string | null>(null);
  const retries = useRef({ key: "", n: 0 });
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const handleFail = useCallback(() => {
    setFailedKey(key);
    const r = retries.current;
    if (r.key !== key) { r.key = key; r.n = 0; }
    if (r.n >= 2) return;
    const delay = 15000 * (r.n + 1);
    r.n += 1;
    window.clearTimeout(timer.current);
    // only clear the failure if the same film is still the one wanted
    timer.current = window.setTimeout(() => setFailedKey((k) => (k === key ? null : k)), delay);
  }, [key]);

  if (sources && failedKey !== key) {
    return <UniverseBackground key={key} sources={sources} state={state} onFail={handleFail} />;
  }
  const still = stillFor(backdrop);
  if (still === "cosmos") return <CosmicBackground state={state} />;
  return <SkyBackground kind={still} sky={skin.sky} state={state} />;
}
