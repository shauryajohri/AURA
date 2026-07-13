const NAV = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "quests", label: "Quests", icon: "❖" },
  { id: "tasks", label: "Tasks", icon: "✓" },
  { id: "skills", label: "Skills", icon: "⚚" },
  { id: "inventory", label: "Inventory", icon: "❐" },
  { id: "models", label: "Models", icon: "◈" },
  { id: "memory", label: "Memory", icon: "❋" },
  { id: "workspace", label: "Workspace", icon: "⎔" },
  { id: "analytics", label: "Analytics", icon: "♪" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

interface Props {
  active: string;
  onNavigate: (id: string) => void;
  listening?: boolean;
  onCollapse?: () => void;
}

export default function Sidebar({ active, onNavigate, listening = false, onCollapse }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand__mark" />
        <div className="brand__text">
          <h1>A U R A</h1>
          <span className="brand__sub">Prime Core Online</span>
          <span className="brand__tag">Your AI Companion</span>
        </div>
        <button className="brand__collapse" onClick={onCollapse} title="Hide sidebar">
          {"«"}
        </button>
      </div>

      <nav className="nav">
        {NAV.map((item) => (
          <button
            key={item.id}
            className={"nav__item " + (active === item.id ? "nav__item--active" : "")}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav__icon">{item.icon}</span>
            <span className="nav__label">{item.label}</span>
            {active === item.id && <span className="nav__chevron">{"›"}</span>}
          </button>
        ))}
      </nav>

      <div className={"voice-card " + (listening ? "voice-card--on" : "")}>
        <span className="voice-card__title">VOICE MODE</span>
        <div className="voice-card__mic">{"🎙"}</div>
        <div className="voice-card__wave">
          {Array.from({ length: 20 }).map((_, i) => (
            <span key={i} style={{ animationDelay: i * 0.06 + "s" }} />
          ))}
        </div>
        <span className="voice-card__status">{listening ? "Listening..." : "Tap to speak"}</span>
      </div>
    </aside>
  );
}
