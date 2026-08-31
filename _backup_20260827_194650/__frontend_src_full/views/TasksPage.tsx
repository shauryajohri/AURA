import { useEffect, useState } from "react";
import { api, UsageStats } from "../api";
import PageShell from "./PageShell";
import TaskBoard from "./TaskBoard";
import MilestonesPane from "./MilestonesPane";
import TaskAssistant from "./TaskAssistant";
import QuestsView from "./QuestsView";
import type { QuestEvent } from "../types";

/**
 * Tasks — the doing page. Project backlog, today's quests (time AURA
 * verifies from the screen), and a quiet progress readout. Quests moved in
 * here from their old sidebar slot; nothing was lost, just gathered.
 */

function ProgressPane() {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    api.getStats().then(setStats).catch(() => setOffline(true));
  }, []);

  if (offline) return <p className="pane-note">Brain offline — progress needs server.py.</p>;
  if (!stats) return <p className="pane-note">Reading the story so far…</p>;

  const days = stats.days.slice(-14);
  const max = Math.max(1, ...days.map((d) => d.user_msgs + d.aura_msgs));

  return (
    <div className="progress">
      <div className="progress__totals">
        <div className="progress__stat">
          <strong>{stats.totals.user_messages}</strong><span>messages with AURA</span>
        </div>
        <div className="progress__stat">
          <strong>{stats.totals.facts}</strong><span>facts remembered</span>
        </div>
        <div className="progress__stat">
          <strong>{stats.totals.knowledge}</strong><span>knowledge entries</span>
        </div>
        <div className="progress__stat">
          <strong>{stats.totals.tasks}</strong><span>tasks tracked</span>
        </div>
      </div>
      <div className="progress__chart">
        {days.map((d) => (
          <div key={d.date} className="progress__col" title={`${d.date} — ${d.user_msgs + d.aura_msgs} messages`}>
            <span style={{ height: `${Math.max(4, ((d.user_msgs + d.aura_msgs) / max) * 100)}%` }} />
            <em>{d.date.slice(5)}</em>
          </div>
        ))}
      </div>
      <p className="pane-note">Milestones grow from here — promote a task to a quest and AURA holds you to it.</p>
    </div>
  );
}

interface Props {
  questEvent: QuestEvent | null;
}

export default function TasksPage({ questEvent }: Props) {
  return (
    <PageShell
      title="Tasks"
      tagline="The backlog you think in, the quests you commit to, the progress you keep."
      storeKey="aura.page.tasks"
      tabs={[
        { id: "board", label: "Task Board", body: <TaskBoard /> },
        { id: "assistant", label: "✦ AI Assistant", body: <TaskAssistant /> },
        { id: "milestones", label: "Milestones", body: <MilestonesPane /> },
        { id: "today", label: "Today's Quests", body: <QuestsView event={questEvent} /> },
        { id: "progress", label: "Progress", body: <ProgressPane /> },
      ]}
    />
  );
}
