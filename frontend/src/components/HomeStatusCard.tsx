import { useEffect, useState } from "react";
import type { ConnStatus } from "../types";
import { api } from "../api";
import { useRoster } from "../stores/rosterStore";

/**
 * The quiet readout under the greeting: link, which model is answering,
 * how much AURA remembers, and the next task if there is one.
 */

interface Props {
  status: ConnStatus;
  activeModelId?: string | null;
}

const LINK: Record<string, string> = {
  open: "Connected",
  connecting: "Connecting",
  closed: "Brain offline",
  error: "Brain offline",
};

export default function HomeStatusCard({ status, activeModelId }: Props) {
  const [factCount, setFactCount] = useState<number | null>(null);
  const [nextTask, setNextTask] = useState<string | null>(null);

  // One gentle fetch — refreshed when the connection (re)opens.
  useEffect(() => {
    if (status !== "open") return;
    api.getFacts().then((f) => setFactCount(f.length)).catch(() => setFactCount(null));
    api.getTasks()
      .then((ts) => {
        const t = ts.find((x) => !x.done_at && x.bucket === "now") ?? ts.find((x) => !x.done_at);
        setNextTask(t ? t.title : null);
      })
      .catch(() => setNextTask(null));
  }, [status]);

  const roster = useRoster();
  const model = roster.find((m) => m.id === activeModelId);

  return (
    <p className="homeline" aria-live="polite">
      <span className={"homeline__item homeline__link homeline__link--" + status}>
        <i />{LINK[status] ?? status}
      </span>
      <span className="homeline__item">
        <i style={{ background: model?.color ?? "var(--horizon)" }} />
        {model ? `${model.name} answering` : "Picking the best model per message"}
      </span>
      {factCount !== null && (
        <span className="homeline__item">{factCount} things remembered</span>
      )}
      {nextTask && (
        <span className="homeline__item homeline__task" title={nextTask}>Next: {nextTask}</span>
      )}
    </p>
  );
}
