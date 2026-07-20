import { useEffect, useMemo } from "react";

// ============================================================================
// The portal — pressing "Enter Workspace" doesn't switch screens, it crosses
// a threshold. The sanctuary's beam intensifies, particles rise into it, the
// view is pulled forward into light, and the Domain condenses out of the glow.
//
// Timeline (entering, ~2.2s):
//   0.00s  beam widens + brightens, sanctuary recedes underneath
//   0.55s  particles stream upward along the beam
//   1.15s  bloom peak — screen is pure violet-white light  → onMid() fires
//          (App swaps sanctuary → domain beneath the light)
//   2.20s  bloom recedes, Domain revealed                  → onDone()
//
// Exiting plays a shorter reverse (~1.4s).
// ============================================================================

interface Props {
  direction: "in" | "out";
  onMid: () => void;
  onDone: () => void;
}

const RISE_COUNT = 46;

export default function PortalTransition({ direction, onMid, onDone }: Props) {
  const entering = direction === "in";

  // random particle field, stable for the life of the overlay
  const particles = useMemo(
    () =>
      Array.from({ length: RISE_COUNT }, (_, i) => ({
        left: 50 + (Math.random() - 0.5) * (Math.random() < 0.6 ? 22 : 70), // most hug the beam
        size: 1.5 + Math.random() * 3,
        delay: Math.random() * 700,
        dur: 900 + Math.random() * 900,
        drift: (Math.random() - 0.5) * 60,
        cyan: i % 5 === 0,
      })),
    []
  );

  useEffect(() => {
    const mid = setTimeout(onMid, entering ? 1150 : 650);
    const done = setTimeout(onDone, entering ? 2250 : 1400);
    return () => {
      clearTimeout(mid);
      clearTimeout(done);
    };
  }, [entering, onMid, onDone]);

  return (
    <div className={"portal portal--" + direction} aria-hidden="true">
      {/* the beam column, widening into an event horizon */}
      <div className="portal__beam" />
      {/* rising particles */}
      <div className="portal__particles">
        {particles.map((p, i) => (
          <span
            key={i}
            style={{
              left: `${p.left}%`,
              width: p.size,
              height: p.size,
              background: p.cyan ? "var(--cyan)" : "var(--violet-bright)",
              animationDelay: `${p.delay}ms`,
              animationDuration: `${p.dur}ms`,
              // custom drift per particle
              ["--drift" as string]: `${p.drift}px`,
            }}
          />
        ))}
      </div>
      {/* full-screen bloom that swallows the frame at the midpoint */}
      <div className="portal__bloom" />
      {/* faint chromatic ring expanding outward */}
      <div className="portal__ring" />
    </div>
  );
}
