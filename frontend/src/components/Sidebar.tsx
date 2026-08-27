/**
 * The fixed glass sidebar — AURA OS navigation.
 *
 * Six destinations. "Aura Domain" is special: it doesn't swap the page, it
 * crosses the portal into the dedicated coding workspace. Collapsed mode is
 * icons-only; the width animates (CSS) and labels fade out, nothing snaps.
 * The bottom is reserved for identity: profile, version, plan.
 */

interface NavItem {
  id: string;
  label: string;
  icon: string;
  hint: string;
  domain?: boolean;
}

const NAV: NavItem[] = [
  { id: "home", label: "Home", icon: "⌂", hint: "The AURA core" },
  { id: "chats", label: "Chats", icon: "◈", hint: "Rooms · chats · history" },
  { id: "domain", label: "Aura Domain", icon: "❖", hint: "Coding workspace", domain: true },
  { id: "memory", label: "Memory", icon: "❋", hint: "Timeline · search · bookmarks" },
  { id: "tasks", label: "Tasks", icon: "✓", hint: "Today · projects · quests" },
  { id: "models", label: "Models", icon: "◈", hint: "Planets · routing · orbits" },
  { id: "settings", label: "Settings", icon: "⚙", hint: "Appearance · voice · keys" },
  { id: "labs", label: "Labs", icon: "⚗", hint: "What's coming next" },
];

interface Props {
  active: string;
  collapsed: boolean;
  onNavigate: (id: string) => void;
  onLaunchDomain: () => void;
  onToggle: () => void;
  listening?: boolean;
}

export default function Sidebar({
  active,
  collapsed,
  onNavigate,
  onLaunchDomain,
  onToggle,
  listening = false,
}: Props) {
  return (
    <aside className={"osbar" + (collapsed ? " osbar--min" : "")}>
      <div className="osbar__brand" onClick={onToggle} title={collapsed ? "Expand" : "Collapse"}>
        <div className={"osbar__mark" + (listening ? " osbar__mark--live" : "")} />
        <div className="osbar__brandtext">
          <h1>A U R A</h1>
          <span>Prime Core Online</span>
        </div>
        <span className="osbar__fold">{collapsed ? "»" : "«"}</span>
      </div>

      <nav className="osbar__nav">
        {NAV.map((item) => (
          <button
            key={item.id}
            className={
              "osbar__item" +
              (active === item.id && !item.domain ? " osbar__item--active" : "") +
              (item.domain ? " osbar__item--domain" : "")
            }
            onClick={() => (item.domain ? onLaunchDomain() : onNavigate(item.id))}
            title={collapsed ? item.label : undefined}
          >
            <span className="osbar__icon">{item.icon}</span>
            <span className="osbar__meta">
              <span className="osbar__label">{item.label}</span>
              <span className="osbar__hint">{item.hint}</span>
            </span>
            {active === item.id && !item.domain && <span className="osbar__glowline" />}
          </button>
        ))}
      </nav>

      <div className="osbar__foot">
        <div className="osbar__profile" title="Shaurya">
          <span className="osbar__avatar">S</span>
          <span className="osbar__meta">
            <span className="osbar__label">Shaurya</span>
            <span className="osbar__hint">Companion linked</span>
          </span>
        </div>
        <div className="osbar__plan">
          <span className="osbar__planbadge">SUPERNOVA</span>
          <span className="osbar__version">v3.0</span>
        </div>
      </div>
    </aside>
  );
}
