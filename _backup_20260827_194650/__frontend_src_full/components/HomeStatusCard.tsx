import { useEffect, useState } from "react";
import type { ConnStatus } from "../types";
import { api } from "../api";
import { MODELS } from "../data/models";

/**
 * The one small widget Home keeps — a quiet system readout, not a dashboard.
 * Current model · connection · memory · the next task, if one exists.
 */

interface Props {
  status: ConnStatus;
  activeModelId?: string | null;
  mode?: string;
}

export default function HomeStatusCard({ status, activeModelId, mode = "CHAT" }: Props) {
  const [factCount, setFactCount] = useState<number | null>(null);
  const [nextTask, setNextTask] = useState<string | null>(null);

  // One gentle poll — refreshed when the connection (re)opens, never spammy.
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

  const model = MODELS.find((m) => m.id === activeModelId);

  return (
    <aside className="syscard">
      <div className="syscard__row">
        <span className={"syscard__dot syscard__dot--" + status} />
        <span className="syscard__key">Link</span>
        <span className="syscard__val">{status === "open" ? "connected" : status}</span>
      </div>
      <div className="syscard__row">
        <span className="syscard__orb" style={{ background: model?.color ?? "#7d3cff" }} />
        <span className="syscard__key">Model</span>
        <span className="syscard__val">{model ? model.name : "auto-routing"}</span>
      </div>
      <div className="syscard__row">
        <span className="syscard__spark">❋</span>
        <span className="syscard__key">Memory</span>
        <span className="syscard__val">
          {factCount === null ? "—" : factCount + " facts held"}
        </span>
      </div>
      {mode && mode !== "CHAT" && (
        <div className="syscard__row">
          <span className="syscard__spark">◎</span>
          <span className="syscard__key">Mode</span>
          <span className="syscard__val">{mode.toLowerCase()}</span>
        </div>
      )}
      {nextTask && (
        <div className="syscard__row syscard__row--task" title={nextTask}>
          <span className="syscard__spark">✓</span>
          <span className="syscard__key">Up next</span>
          <span className="syscard__val">{nextTask}</span>
        </div>
      )}
    </aside>
  );
}
