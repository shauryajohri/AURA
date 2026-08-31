import { ReactNode, useState } from "react";
import { useLocalStorage } from "../hooks/useLocalStorage";

/**
 * PageShell — every sidebar destination opens as one of these: a breathable
 * glass page with a title, soft sub-tabs and a crossfading body. The tab bar
 * is the only chrome; content gets all the room.
 */

export interface PageTab {
  id: string;
  label: string;
  body: ReactNode;
}

interface Props {
  title: string;
  tagline?: string;
  tabs: PageTab[];
  /** localStorage key so each page remembers its last tab */
  storeKey: string;
}

export default function PageShell({ title, tagline, tabs, storeKey }: Props) {
  const [tab, setTab] = useLocalStorage<string>(storeKey, tabs[0]?.id ?? "");
  const activeId = tabs.some((t) => t.id === tab) ? tab : tabs[0]?.id;
  const active = tabs.find((t) => t.id === activeId);
  // key bump forces the crossfade animation on each switch
  const [, force] = useState(0);

  return (
    <div className="pageshell">
      <header className="pageshell__head">
        <h2>{title}</h2>
        {tagline && <p>{tagline}</p>}
      </header>

      {tabs.length > 1 && (
        <nav className="pageshell__tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={"pageshell__tab" + (t.id === activeId ? " pageshell__tab--on" : "")}
              onClick={() => { setTab(t.id); force((n) => n + 1); }}
            >
              {t.label}
            </button>
          ))}
        </nav>
      )}

      <div className="pageshell__body" key={activeId}>
        {active?.body}
      </div>
    </div>
  );
}
