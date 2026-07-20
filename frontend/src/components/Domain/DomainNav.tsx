import { DomainSection, useDomainStore } from "../../stores/domainStore";

// Left navigation — collapsible, minimal glyphs, elegant spacing.

const ITEMS: { id: DomainSection; icon: string; label: string }[] = [
  { id: "dashboard", icon: "◈", label: "Dashboard" },
  { id: "projects", icon: "▣", label: "Projects" },
  { id: "tasks", icon: "☑", label: "Tasks" },
  { id: "code", icon: "⌥", label: "Code" },
  { id: "research", icon: "◎", label: "Research" },
  { id: "documents", icon: "≡", label: "Documents" },
  { id: "images", icon: "❖", label: "Images" },
  { id: "notes", icon: "✎", label: "Notes" },
  { id: "agents", icon: "✦", label: "AI Agents" },
  { id: "terminal", icon: "❯", label: "Terminal" },
  { id: "history", icon: "↺", label: "History" },
];

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  onExit: () => void;
}

export default function DomainNav({ collapsed, onToggle, onExit }: Props) {
  const section = useDomainStore((s) => s.section);
  const setSection = useDomainStore((s) => s.setSection);

  return (
    <nav className={"dnav" + (collapsed ? " dnav--min" : "")}>
      <button className="dnav__collapse" onClick={onToggle} title={collapsed ? "Expand" : "Collapse"}>
        {collapsed ? "»" : "«"}
      </button>

      <div className="dnav__items">
        {ITEMS.map((it) => (
          <button
            key={it.id}
            className={"dnav__item" + (section === it.id ? " dnav__item--on" : "")}
            onClick={() => setSection(it.id)}
            title={collapsed ? it.label : undefined}
          >
            <span className="dnav__icon">{it.icon}</span>
            {!collapsed && <span className="dnav__label">{it.label}</span>}
            {section === it.id && <span className="dnav__glow" />}
          </button>
        ))}
      </div>

      <button className="dnav__exit" onClick={onExit} title="Return to Sanctuary">
        <span className="dnav__icon">⌂</span>
        {!collapsed && <span className="dnav__label">Sanctuary</span>}
      </button>
    </nav>
  );
}
