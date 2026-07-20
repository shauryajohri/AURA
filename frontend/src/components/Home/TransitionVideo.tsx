import { useEffect, useRef, useState } from "react";
import { seg } from "./ScrollController";

// ============================================================================
// The bridge — /transition.mp4 scrubbed by scroll position.
// currentTime = duration × progress, so the animation IS the scroll.
// Fades in as the universe recedes, hands off to the sanctuary at the end.
// ============================================================================

interface Props {
  p: number; // journey progress 0..1
}

export default function TransitionVideo({ p }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ok, setOk] = useState(true);
  const durRef = useRef(0);

  // scrub: map journey window 0.45–0.90 onto the video timeline
  const scrub = seg(p, 0.45, 0.9);
  const visible = seg(p, 0.38, 0.48) * (1 - seg(p, 0.9, 0.99));

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !durRef.current || visible <= 0) return;
    const t = durRef.current * scrub;
    // only seek when meaningfully different — avoids decoder thrash
    if (Math.abs(v.currentTime - t) > 0.033) {
      v.currentTime = t;
    }
  }, [scrub, visible]);

  if (!ok) return null; // no file yet → journey still works, video phase skipped

  return (
    <div
      className="screen screen--transition"
      style={{ opacity: visible, pointerEvents: "none" }}
      aria-hidden={visible === 0}
    >
      <video
        ref={videoRef}
        src="./transition.mp4"
        muted
        playsInline
        preload="auto"
        onLoadedMetadata={(e) => { durRef.current = e.currentTarget.duration || 0; }}
        onError={() => setOk(false)}
      />
    </div>
  );
}
