import { useClock } from "../hooks/useClock";

// ============================================================================
// Screen 2 — AURA's Sanctuary.
// Deliberately empty: the looping ambient video IS the experience.
// Just the greeting floating above the living world. No cards, no controls.
// ============================================================================

const USER = "Shaurya";

interface Props {
  entered: boolean;    // scroll transition finished
  onHome?: () => void; // glide back to Screen 1
}

export default function Sanctuary({ entered, onHome }: Props) {
  const { greeting } = useClock();

  return (
    <div className="sanctuary">
      <header className="sanctuary__top">
        <div className="sanctuary__brand">
          <span className="brand__mark" />
          <span className="sanctuary__logo">AURA</span>
        </div>
        <div className="sanctuary__greet">
          <h1>{greeting}, {USER}</h1>
          <p>Welcome back to your sanctuary</p>
        </div>
        <div className="sanctuary__actions">
          <button className="sanctuary__profile" title="Profile">S</button>
        </div>
      </header>

      <div className="sanctuary__void" />

      {entered && (
        <button className="sanctuary__return" onClick={onHome} title="Back to cosmos">
          {"↑"} <span>scroll up to return</span>
        </button>
      )}
    </div>
  );
}
