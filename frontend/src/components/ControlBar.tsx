import type { AuraState } from "../types";

interface Props {
  state: AuraState;
}

const LEFT = [
  { id: "see", label: "See", icon: "◉" },
  { id: "listen", label: "Listen", icon: "◟◞" },
];
const RIGHT = [
  { id: "think", label: "Think", icon: "❋" },
  { id: "act", label: "Act", icon: "✦" },
];

// The bottom faculty bar: See - Listen - [core] - Think - Act.
// The center core mirrors the black hole state; the four faculties are the
// hooks for screen-read / voice-in / reasoning / actions (wired later).
export default function ControlBar({ state }: Props) {
  return (
    <footer className="controlbar">
      {LEFT.map((f) => (
        <button key={f.id} className="faculty">
          <span className="faculty__icon">{f.icon}</span>
          <span className="faculty__label">{f.label}</span>
        </button>
      ))}

      <div className="controlbar__center">
        <button className="controlbar__nav">{"‹"}</button>
        <div className={"controlbar__core controlbar__core--" + state} />
        <button className="controlbar__nav">{"›"}</button>
      </div>

      {RIGHT.map((f) => (
        <button key={f.id} className="faculty">
          <span className="faculty__icon">{f.icon}</span>
          <span className="faculty__label">{f.label}</span>
        </button>
      ))}
    </footer>
  );
}
