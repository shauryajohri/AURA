import PageShell from "./PageShell";

/**
 * Labs — what's coming. Honest placeholders, not fake UI: each card says what
 * the feature will do and where it stands, so the roadmap is visible inside
 * the product instead of living in a document.
 */

interface Coming {
  icon: string;
  title: string;
  blurb: string;
  status: "designing" | "planned" | "exploring";
  points: string[];
}

const ITEMS: Coming[] = [
  {
    icon: "⧉", title: "Plugin System", status: "designing",
    blurb: "Drop a folder into AURA and she gains a new skill — tools, panels and slash-commands, sandboxed.",
    points: ["Manifest + permission prompt", "Tool calls from chat", "Own panel in the sidebar"],
  },
  {
    icon: "◈", title: "Marketplace", status: "planned",
    blurb: "Browse and install plugins, personalities and planet packs made by other people.",
    points: ["Signed packages", "One-click install", "Ratings & updates"],
  },
  {
    icon: "☁", title: "Cloud Sync", status: "exploring",
    blurb: "Your memory, tasks and settings following you between machines — encrypted, opt-in, yours.",
    points: ["End-to-end encryption", "Conflict-free merge", "Selective sync"],
  },
  {
    icon: "⚯", title: "Team Collaboration", status: "exploring",
    blurb: "Share a project brain with teammates so AURA knows what everyone is building.",
    points: ["Shared project graph", "Per-person memory scopes", "Activity feed"],
  },
  {
    icon: "⌘", title: "Extension SDK", status: "planned",
    blurb: "A typed API for building against AURA — the same surface her own panels use.",
    points: ["TypeScript client", "Event subscriptions", "Custom renderers"],
  },
];

function ComingPane() {
  return (
    <div className="labs">
      {ITEMS.map((it) => (
        <article key={it.title} className="labcard">
          <header>
            <span className="labcard__icon">{it.icon}</span>
            <h4>{it.title}</h4>
            <span className={"labcard__status labcard__status--" + it.status}>{it.status}</span>
          </header>
          <p>{it.blurb}</p>
          <ul>
            {it.points.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </article>
      ))}
    </div>
  );
}

export default function LabsPage() {
  return (
    <PageShell
      title="Labs"
      tagline="Where AURA is going next. Nothing here is finished — that's the point."
      storeKey="aura.page.labs"
      tabs={[{ id: "coming", label: "Coming Soon", body: <ComingPane /> }]}
    />
  );
}
