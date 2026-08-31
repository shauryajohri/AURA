import {
  ALL_SECTIONS,
  SECTION_META,
  useDomainStore,
  type DomainSection,
} from "../../stores/domainStore";

// Left navigation — collapsible, minimal glyphs.
// Order and visibility come from Domain → Settings → Layout.

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  onExit: () => void;
}

export default function DomainNav({ collapsed, onToggle, onExit }: Props) {
  const section = useDomainStore((s) => s.section);
  const setSection = useDomainStore((s) => s.setSection);
  const layout = useDomainStore((s) => s.layout);

  // any section added after the user saved a layout still shows up, at the end
  const ordered: DomainSection[] = [
    ...layout.navOrder.filter((s) => ALL_SECTIONS.includes(s)),
    ...ALL_SECTIONS.filter((s) => !layout.navOrder.includes(s)),
  ];
  const items = ordered.filter((s) => !layout.hidden.includes(s));

  return (
    <nav className={"dnav" + (collapsed ? " dnav--min" : "")}>
      <button className="dnav__collapse" onClick={onToggle} title={collapsed ? "Expand" : "Collapse"}>
        {collapsed ? "»" : "«"}
      </button>

      <div className="dnav__items">
        {items.map((id) => (
          <button
            key={id}
            className={"dnav__item" + (section === id ? " dnav__item--on" : "")}
            onClick={() => setSection(id)}
            title={collapsed ? SECTION_META[id].label : undefined}
          >
            <span className="dnav__icon">{SECTION_META[id].icon}</span>
            {!collapsed && <span className="dnav__label">{SECTION_META[id].label}</span>}
            {section === id && <span className="dnav__glow" />}
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
