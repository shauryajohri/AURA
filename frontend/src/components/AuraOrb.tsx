/**
 * The AURA orb — the black hole held in a glass marble. The same film as the
 * core, cropped round; the glass (rim light, highlight) is CSS. Used as the
 * brand mark in the rail and as the loading mark; the floating desktop orb
 * (electron/orb.html) is the same design.
 */
export default function AuraOrb({ size = 32, live = false }: { size?: number; live?: boolean }) {
  return (
    <span className={"orb" + (live ? " orb--live" : "")} style={{ width: size, height: size }} aria-hidden="true">
      <video className="orb__film" src="./cosmos/orb.mp4" autoPlay muted loop playsInline />
      <span className="orb__glass" />
    </span>
  );
}
