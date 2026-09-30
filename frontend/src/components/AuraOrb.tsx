/**
 * The AURA orb — a pocket black hole: the core's film cut out of its
 * background (orb.webm carries alpha) over a true-black event horizon, so the
 * photon ring and the disk band float with nothing behind them. Used as the
 * brand mark in the rail and as the loading mark; the floating desktop orb
 * (electron/orb.js) is the same design.
 */
export default function AuraOrb({ size = 32, live = false }: { size?: number; live?: boolean }) {
  return (
    <span className={"orb" + (live ? " orb--live" : "")} style={{ width: size, height: size }} aria-hidden="true">
      <span className="orb__hole" />
      <video className="orb__film" src="./cosmos/orb.webm" autoPlay muted loop playsInline />
    </span>
  );
}
