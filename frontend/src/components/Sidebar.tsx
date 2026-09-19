import Icon, { type IconName } from "./Icon";
import AuraOrb from "./AuraOrb";

/**
 * The rail — AURA's navigation. Slim by default (icons, names on hover);
 * the orb at the top widens it to show names. "Aura Domain" doesn't swap the
 * page, it crosses the portal into the coding workspace.
 */

interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  domain?: boolean;
}

const NAV: NavItem[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "chats", label: "Chats", icon: "chats" },
  { id: "domain", label: "Aura Domain", icon: "domain", domain: true },
  { id: "saved", label: "Saved info", icon: "saved" },
  { id: "memory", label: "Memory", icon: "memory" },
  { id: "tasks", label: "Tasks", icon: "tasks" },
  { id: "models", label: "Models", icon: "models" },
  { id: "planets", label: "Planets", icon: "planets" },
  { id: "labs", label: "Labs", icon: "labs" },
];

interface Props {
  active: string;
  collapsed: boolean;
  onNavigate: (id: string) => void;
  onLaunchDomain: () => void;
  onToggle: () => void;
  listening?: boolean;
}

export default function Sidebar({ active, collapsed, onNavigate, onLaunchDomain, onToggle, listening = false }: Props) {
  const item = (it: NavItem) => (
    <button
      key={it.id}
      className={
        "rail__item" +
        (active === it.id && !it.domain ? " rail__item--on" : "") +
        (it.domain ? " rail__item--portal" : "")
      }
      onClick={() => (it.domain ? onLaunchDomain() : onNavigate(it.id))}
      aria-current={active === it.id && !it.domain ? "page" : undefined}
      aria-label={it.label}
      data-tip={collapsed ? it.label : undefined}
    >
      <Icon name={it.icon} size={19} />
      <span className="rail__label">{it.label}</span>
    </button>
  );

  return (
    <aside className={"rail" + (collapsed ? " rail--slim" : "")}>
      <button
        className="rail__brand"
        onClick={onToggle}
        aria-label={collapsed ? "Show page names" : "Hide page names"}
        data-tip={collapsed ? "Show names" : undefined}
      >
        <AuraOrb size={34} live={listening} />
        <span className="rail__word">AURA</span>
        <Icon name={collapsed ? "right" : "left"} size={14} className="rail__fold" />
      </button>

      <nav className="rail__nav">{NAV.map(item)}</nav>

      <div className="rail__foot">
        {item({ id: "settings", label: "Settings", icon: "settings" })}
        <div className="rail__me" data-tip={collapsed ? "Shaurya" : undefined}>
          <span className="rail__avatar">S</span>
          <span className="rail__who">
            <span>Shaurya</span>
            <small>Supernova</small>
          </span>
        </div>
      </div>
    </aside>
  );
}
