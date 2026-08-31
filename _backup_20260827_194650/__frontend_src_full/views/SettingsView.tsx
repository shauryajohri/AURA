import { useEffect, useState } from "react";
import { api, Settings } from "../api";
import SettingsOverlay, { SettingsCategory, CATEGORY_META } from "../components/Home/SettingsOverlay";
import { Layout, DEFAULT_LAYOUT } from "../components/Home/layoutTypes";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSettingsStore } from "../stores/settingsStore";

// Settings — a menu → focused editor flow. Pick a category, edit it with a
// live preview, save, and you're back here. Grouped into sections so fourteen
// categories still feel calm rather than like a wall of buttons.

const SECTIONS: Array<{ title: string; cats: SettingsCategory[] }> = [
  { title: "System", cats: ["general", "keys", "privacy", "behavior"] },
  { title: "Appearance", cats: ["blackhole", "planets", "orbits", "animations", "wallpaper", "layout"] },
  { title: "Voice & Personality", cats: ["voice", "autochat"] },
  { title: "Advanced", cats: ["developer", "experimental"] },
];

export default function SettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [focus, setFocus] = useState<SettingsCategory | null>(null);
  const applySettings = useSettingsStore((s) => s.apply);
  // Sanctuary layout is edited here too — same store the sanctuary reads.
  const [layout, setLayout] = useLocalStorage<Layout>("aura.sanctuary", DEFAULT_LAYOUT);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => setOffline(true));
  }, []);

  return (
    <div className="setview">
      <div className="setview__head">
        <h2>Settings</h2>
        <p>Tune AURA's world. Each area opens with a live preview.</p>
      </div>

      {SECTIONS.map((sec) => (
        <section key={sec.title} className="setview__section">
          <h3 className="memtl__title">{sec.title}</h3>
          <div className="setview__menu">
            {sec.cats.map((cat) => (
              <button
                key={cat}
                className="san-setopt setview__opt"
                onClick={() => setFocus(cat)}
                disabled={!settings && cat !== "layout" && cat !== "keys"}
              >
                <span className="san-setopt__icon">{CATEGORY_META[cat].icon}</span>
                <span className="san-setopt__meta">
                  <span className="san-setopt__name">{CATEGORY_META[cat].title}</span>
                  <span className="san-setopt__desc">{CATEGORY_META[cat].desc}</span>
                </span>
                <span className="san-setopt__go">→</span>
              </button>
            ))}
          </div>
        </section>
      ))}

      {!settings && (
        <div className="setview__note">
          {offline
            ? "Brain offline — start server.py to load visual settings."
            : "Loading settings…"}
        </div>
      )}

      {focus && (
        <SettingsOverlay
          category={focus}
          settings={settings ?? {}}
          layout={layout}
          onSaveSettings={(patch) => {
            setSettings((s) => (s ? { ...s, ...patch } : s));
            // Route through the store, not straight to the API — it persists
            // AND pushes the new values into the black hole / planet visuals,
            // which is what makes these sliders actually do something.
            applySettings(patch).catch(() => setOffline(true));
          }}
          onSaveLayout={(l) => setLayout(l)}
          onClose={() => setFocus(null)}
        />
      )}
    </div>
  );
}
