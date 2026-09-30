import Icon, { type IconName } from "./Icon";
import AuraOrb from "./AuraOrb";
import { NotifyBell } from "./Chrome";

/**
 * The rail — AURA's navigation, drawn straight onto space (no panel). Slim by
 * default (icons, names on hover); the orb at the top widens it to show names.
 * Pages are grouped by what they hold: your things, AURA's models, and the
 * portal to the Domain, which doesn't swap the page but crosses into the
 * coding workspace.
 */

interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  domain?: boolean;
}

const GROUPS: NavItem[][] = [
  [
    { id: "home", label: "Home", icon: "home" },
    { id: "chats", label: "Chats", icon: "chats" },
    { id: "saved", label: "Saved info", icon: "saved" },
    { id: "memory", label: "Memory", icon: "memory" },
    { id: "tasks", label: "Tasks", icon: "tasks" },
  ],
  [
    { id: "models", label: "Models", icon: "models" },
    { id: "planets", label: "Planets", icon: "planets" },
    { id: "labs", label: "Labs", icon: "labs" },
    { id: "upgrade", label: "Upgrade", icon: "upgrade" },
  ],
  [{ id: "domain", label: "Aura Domain", icon: "domain", domain: true }],
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
      <span className="rail__iconwrap"><Icon name={it.icon} size={19} /></span>
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
        <AuraOrb size={28} live={listening} />
        <span className="rail__word">AURA</span>
      </button>

      <nav className="rail__nav">
        {GROUPS.map((g, i) => (
          <div key={i} className="rail__group">{g.map(item)}</div>
        ))}
      </nav>

      <div className="rail__foot">
        <NotifyBell slim={collapsed} />
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
