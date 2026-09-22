import { useEffect, useState } from "react";
import type { ConnStatus } from "../types";
import { api } from "../api";
import { useClock } from "../hooks/useClock";

/**
 * The head of the conversation pane: who AURA is talking to, the time, whether
 * the brain is reachable, and the next task if there is one. Nothing else —
 * the model that's answering already lights up in the sky.
 */

interface Props {
  status: ConnStatus;
  mode?: string;
}

const USER = "Shaurya";

const LINK: Record<string, string> = {
  open: "Connected",
  connecting: "Connecting",
  closed: "Brain offline",
  error: "Brain offline",
};

export default function HomeGreeting({ status, mode = "CHAT" }: Props) {
  const { time, greeting } = useClock();
  const [nextTask, setNextTask] = useState<string | null>(null);

  // One gentle fetch — refreshed when the connection (re)opens.
  useEffect(() => {
    if (status !== "open") return;
    api.getTasks()
      .then((ts) => {
        const t = ts.find((x) => !x.done_at && x.bucket === "now") ?? ts.find((x) => !x.done_at);
        setNextTask(t ? t.title : null);
      })
      .catch(() => setNextTask(null));
  }, [status]);

  const special = mode && !["CHAT", "NORMAL"].includes(mode.toUpperCase());

  return (
    <header className="greet">
      <h2 className="greet__hi">{greeting}, {USER}</h2>
      <p className="greet__line" aria-live="polite">
        <span className={"greet__link greet__link--" + status}><i />{LINK[status] ?? status}</span>
        <span className="greet__time">{time}</span>
        {special && <span className="greet__mode">{mode.toLowerCase()} mode</span>}
      </p>
      {nextTask && <p className="greet__task" title={nextTask}>Next up: {nextTask}</p>}
    </header>
  );
}
