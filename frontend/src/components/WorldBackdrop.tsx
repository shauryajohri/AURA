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

/** Re-checks per film, per run of the app, before it stays on its stand-in. */
const MAX_RETRIES = 2;

/**
 * Layer 1 — the living universe, always behind everything.
 *
 * Which universe is the skin's call: AURA's own filmed cosmos, a skin's
 * Higgsfield film, the constellation web, or one of the procedural skies.
 * A film that is missing or can't decode drops to its procedural stand-in.
 *
 * A transient decoder hiccup shouldn't cost the film until restart, so a
 * failed film is re-checked with backoff, but the re-check is a probe: an
 * off-screen <video> that hands the screen back to the film only once it
 * can actually play. The stand-in stays mounted the whole time, so a file
 * that simply isn't there never blanks the screen or reshuffles the sky.
 * Failures and retry counts are kept per film, so switching between skins
 * neither forgets that a film is missing nor restarts its retries.
 */
export default function WorldBackdrop({ backdrop, skin, state }: Props) {
  const sources = useMemo(
    () => (backdrop === "video" ? UNIVERSE_SOURCES : isFilm(backdrop) ? [FILMS[backdrop].src] : null),
    [backdrop],
  );
  const key = sources ? sources.join("|") : "";

  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set());
  const retries = useRef(new Map<string, number>());
  const handleFail = useCallback(
    () => setFailed((s) => (s.has(key) ? s : new Set(s).add(key))),
    [key],
  );
  const isFailed = !!sources && failed.has(key);

  useEffect(() => {
    if (!sources || !isFailed) return;
    let probe: HTMLVideoElement | null = null;
    let timer = 0;

    const release = () => {
      if (!probe) return;
      probe.removeAttribute("src");
      probe.load(); // frees the decoder
      probe = null;
    };
    const recovered = () =>
      setFailed((s) => {
        const next = new Set(s);
        next.delete(key);
        return next;
      });
    // A re-check counts once it has an answer, not when it starts: a probe
    // cut short by switching away mid-load (cleanup's release() swallows its
    // events) must not use up one of the film's retries.
    const counted = () => retries.current.set(key, (retries.current.get(key) ?? 0) + 1);
    const tryFrom = (i: number) => {
      if (i >= sources.length) { counted(); schedule(); return; } // nothing playable yet
      const v = document.createElement("video");
      v.muted = true;
      v.preload = "auto";
      v.addEventListener("canplay", () => { release(); counted(); recovered(); }, { once: true });
      v.addEventListener("error", () => { release(); tryFrom(i + 1); }, { once: true });
      probe = v;
      v.src = sources[i];
    };
    function schedule() {
      const n = retries.current.get(key) ?? 0;
      if (n >= MAX_RETRIES) return; // stay on the stand-in until restart
      timer = window.setTimeout(() => tryFrom(0), 15000 * (n + 1));
    }
    schedule();

    return () => {
      window.clearTimeout(timer);
      release();
    };
  }, [isFailed, key, sources]);

  if (sources && !isFailed) {
    return <UniverseBackground key={key} sources={sources} state={state} onFail={handleFail} />;
  }
  const still = stillFor(backdrop);
  if (still === "cosmos") return <CosmicBackground state={state} />;
  return <SkyBackground kind={still} sky={skin.sky} state={state} />;
}
