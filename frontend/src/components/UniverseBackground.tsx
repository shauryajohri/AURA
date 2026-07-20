import { useEffect, useRef } from "react";
import type { AuraState } from "../types";

interface Props {
  state: AuraState;
  /** Called if the video file is missing/unplayable so App can fall back. */
  onFail?: () => void;
}

// Relative path — works from Vite's dev server AND Electron's file:// origin
// (an absolute "/universe.mp4" resolves to the DISK root under file://).
const SRC = "./universe.mp4";
/** Seconds of crossfade around the loop point so the restart is invisible. */
const FADE_S = 0.9;

/**
 * Layer 1 — the permanent living universe.
 *
 * Two stacked <video> elements play the same file; shortly before the active
 * one ends, the other starts from 0 and crossfades in, so the loop never
 * shows a cut or jump. Autoplay, muted, inline, GPU-composited
 * (object-fit: cover + opacity transitions only), never visibly restarts.
 *
 * State language:
 *   idle      → slow drift (playbackRate 0.85)
 *   listening → slight brightening
 *   thinking  → energetic (rate 1.4, brighter/saturated)
 *   speaking  → light pulses spread across the universe (overlay)
 *
 * Pauses completely while the window is hidden/minimized.
 */
const RATE: Record<string, number> = {
  idle: 0.85,
  listening: 1.0,
  thinking: 1.4,
  speaking: 1.1,
};
const FILTER: Record<string, string> = {
  idle: "brightness(1) saturate(1)",
  listening: "brightness(1.12) saturate(1.05)",
  thinking: "brightness(1.18) saturate(1.2)",
  speaking: "brightness(1.1) saturate(1.1)",
};

export default function UniverseBackground({ state, onFail }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const vaRef = useRef<HTMLVideoElement>(null);
  const vbRef = useRef<HTMLVideoElement>(null);
  const stateRef = useRef<AuraState>(state);
  stateRef.current = state;

  /* state → tempo + tone (no re-render churn; direct style writes) */
  useEffect(() => {
    const rate = RATE[state] ?? 1;
    for (const v of [vaRef.current, vbRef.current]) {
      if (v) v.playbackRate = rate;
    }
    if (wrapRef.current) {
      wrapRef.current.style.filter = FILTER[state] ?? FILTER.idle;
    }
  }, [state]);

  useEffect(() => {
    const va = vaRef.current!;
    const vb = vbRef.current!;
    let active = va;
    let standby = vb;
    let fading = false;
    let failed = false;
    let fadeTimer = 0;

    va.style.opacity = "1";
    vb.style.opacity = "0";

    const play = (v: HTMLVideoElement) =>
      v.play().catch(() => {
        /* autoplay is muted+inline, retry on first user gesture just in case */
        const kick = () => { v.play().catch(() => {}); window.removeEventListener("pointerdown", kick); };
        window.addEventListener("pointerdown", kick);
      });

    /* seamless loop: crossfade to the standby copy near the end */
    const onTime = () => {
      if (fading || failed || !active.duration) return;
      const remain = active.duration - active.currentTime;
      if (remain <= FADE_S) {
        fading = true;
        standby.currentTime = 0;
        standby.playbackRate = RATE[stateRef.current] ?? 1;
        play(standby);
        standby.style.opacity = "1";
        active.style.opacity = "0";
        fadeTimer = window.setTimeout(() => {
          active.pause();
          const t = active; active = standby; standby = t;
          fading = false;
        }, FADE_S * 1000);
      }
    };

    const onError = () => {
      if (failed) return;
      failed = true;
      onFail?.();
    };

    /* pause rendering while minimized/hidden; resume seamlessly */
    const onVis = () => {
      if (document.hidden) {
        va.pause(); vb.pause();
      } else if (!failed) {
        play(active);
        if (fading) play(standby);
      }
    };

    va.addEventListener("timeupdate", onTime);
    vb.addEventListener("timeupdate", onTime);
    va.addEventListener("error", onError);
    document.addEventListener("visibilitychange", onVis);
    play(va);

    return () => {
      window.clearTimeout(fadeTimer);
      va.removeEventListener("timeupdate", onTime);
      vb.removeEventListener("timeupdate", onTime);
      va.removeEventListener("error", onError);
      document.removeEventListener("visibilitychange", onVis);
      va.pause(); vb.pause();
    };
  }, [onFail]);

  return (
    <div ref={wrapRef} className="universe-bg" aria-hidden="true">
      <video ref={vaRef} src={SRC} muted playsInline autoPlay preload="auto" />
      <video ref={vbRef} src={SRC} muted playsInline preload="auto" />
      {/* speaking: light pulses spreading across the universe */}
      {state === "speaking" && (
        <>
          <div className="universe-pulse" />
          <div className="universe-pulse universe-pulse--late" />
        </>
      )}
    </div>
  );
}
