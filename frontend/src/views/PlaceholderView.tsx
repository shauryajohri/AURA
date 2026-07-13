interface Props {
  title: string;
}

// Honest placeholder for sidebar tabs that don't have a backend yet
// (Quests, Skills, Inventory, Workspace, Analytics, Settings).
export default function PlaceholderView({ title }: Props) {
  return (
    <div className="view view--placeholder">
      <h2>{title}</h2>
      <p className="view__empty">
        {title} isn't wired to the backend yet. Tell me what it should do and I'll build it.
      </p>
    </div>
  );
}
