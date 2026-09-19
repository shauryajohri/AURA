import { useEffect, useRef } from "react";
import { useBootStore } from "../stores/bootStore";
import { coreGeom } from "../lib/coreBus";
import { sfx } from "../lib/sfx";
import { useClock } from "../hooks/useClock";

/**
 * The startup: the black hole forms from a single point of light (that part
 * is the film, drawn by the core), the wordmark settles in beneath it, then
 * space, the planets and the interface arrive. Any click or key skips ahead.
 */
export default function BootSequence() {
  const phase = useBootStore((s) => s.phase);
  const reveal = useBootStore((s) => s.reveal);
  const finish = useBootStore((s) => s.finish);
  const markRef = useRef<HTMLDivElement>(null);
  const { greeting } = useClock();

  useEffect(() => {
    if (phase !== "intro") return;
    sfx.boot();
    const skip = (e: Event) => {
      if (e instanceof KeyboardEvent && ["Shift", "Control", "Alt", "Meta"].includes(e.key)) return;
      reveal();
    };
    window.addEventListener("pointerdown", skip);
    window.addEventListener("keydown", skip);
    return () => {
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
    };
  }, [phase, reveal]);

  useEffect(() => {
    if (phase !== "reveal") return;
    const t = window.setTimeout(finish, 2400);
    return () => window.clearTimeout(t);
  }, [phase, finish]);

  // keep the wordmark tucked under the core wherever the layout put it
  useEffect(() => {
    if (phase === "done") return;
    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const el = markRef.current;
      if (el && coreGeom.r > 0) {
        el.style.left = `${coreGeom.x}px`;
        el.style.top = `${coreGeom.y + coreGeom.r * 1.6}px`;
      }
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [phase]);

  if (phase === "done") return null;
  return (
    <div className={"boot boot--" + phase} aria-live="polite">
      <div ref={markRef} className="boot__mark">
        <h1 className="boot__word">AURA</h1>
        <p className="boot__line">{greeting}, Shaurya</p>
      </div>
      {phase === "intro" && (
        <button className="boot__skip" onClick={reveal}>Skip intro</button>
      )}
    </div>
  );
}
