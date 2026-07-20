import { useEffect, useState } from "react";
import { api, Settings } from "../api";
import SettingsOverlay, { SettingsCategory, CATEGORY_META } from "../components/Home/SettingsOverlay";
import { Layout, DEFAULT_LAYOUT } from "../components/Home/layoutTypes";
import { useLocalStorage } from "../hooks/useLocalStorage";

// Screen-1 settings — the same menu → focused editor flow as the Sanctuary.
// Pick a category, edit it with a live preview, save, and you're back here.

export default function SettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [focus, setFocus] = useState<SettingsCategory | null>(null);
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

      <div className="setview__menu">
        {(Object.keys(CATEGORY_META) as SettingsCategory[]).map((cat) => (
          <button
            key={cat}
            className="san-setopt setview__opt"
            onClick={() => setFocus(cat)}
            disabled={!settings && cat !== "layout"}
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
            api.saveSettings(patch).catch(() => setOffline(true));
          }}
          onSaveLayout={(l) => setLayout(l)}
          onClose={() => setFocus(null)}
        />
      )}
    </div>
  );
}
