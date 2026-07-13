import { useState } from "react";
import { useClock } from "../hooks/useClock";

const USER = "Shaurya";

interface Props {
  mode?: string;
}

export default function TopBar({ mode = "CHAT" }: Props) {
  const { time, date, greeting } = useClock();
  const [focus, setFocus] = useState(true);

  return (
    <header className="topbar">
      <div className="topbar__greet">
        <h2>
          {greeting}, {USER} <span className="topbar__spark">{"✦"}</span>
          {mode && mode !== "CHAT" && <span className="modechip">{mode} mode</span>}
        </h2>
        <p>I'm here, ready to help you achieve more today.</p>
      </div>

      <div className="clock">
        <div className="clock__time">
          <span className="clock__moon">{"☾"}</span> {time}
        </div>
        <div className="clock__date">{date}</div>
      </div>

      <button
        className={"focus " + (focus ? "focus--on" : "")}
        onClick={() => setFocus((f) => !f)}
      >
        <span className="focus__icon">{"✧"}</span>
        <div className="focus__text">
          <span className="focus__label">Focus Mode</span>
          <span className="focus__state">{focus ? "● ON" : "● OFF"}</span>
        </div>
      </button>
    </header>
  );
}
