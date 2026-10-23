import { useEffect, useState } from "react";
import { api, Settings } from "../api";
import SettingsOverlay, { SettingsCategory, CATEGORY_META } from "../components/Home/SettingsOverlay";
import { Layout, DEFAULT_LAYOUT } from "../components/Home/layoutTypes";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSettingsStore, withDefaults } from "../stores/settingsStore";
import BuddyLockPanel from "../components/Guard/BuddyLockPanel";
import { usePerfStore } from "../stores/perfStore";

// Settings — a menu → focused editor flow. Pick a category, edit it with a
// live preview, save, and you're back here. Grouped into sections so fourteen
// categories still feel calm rather than like a wall of buttons.

const SECTIONS: Array<{ title: string; cats: SettingsCategory[] }> = [
  { title: "System", cats: ["general", "keys", "privacy", "behavior"] },
  { title: "Appearance", cats: ["skins", "blackhole", "planets", "orbits", "animations", "wallpaper", "layout"] },
  { title: "Voice & Personality", cats: ["voice", "autochat", "phone"] },
  { title: "Advanced", cats: ["developer", "experimental"] },
];

export default function SettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [focus, setFocus] = useState<SettingsCategory | null>(null);
  const applySettings = useSettingsStore((s) => s.apply);
  const perf = usePerfStore((s) => s.perf);
  const setPerf = usePerfStore((s) => s.setPerf);
  // Sanctuary layout is edited here too — same store the sanctuary reads.
  const [layout, setLayout] = useLocalStorage<Layout>("aura.sanctuary", DEFAULT_LAYOUT);

  useEffect(() => {
    api.getSettings().then((s) => setSettings(withDefaults(s))).catch(() => setOffline(true));
  }, []);

  return (
    <div className="setview">
      <div className="setview__head">
        <h2>Settings</h2>
        <p>Tune AURA's world. Each area opens with a live preview.</p>
      </div>

      {/* Per-machine and instant — not part of a category draft, and works
          even while the brain is offline. */}
      <div className="setview__perf">
        <span className="san-setopt__icon">⚡</span>
        <span className="san-setopt__meta">
          <span className="san-setopt__name">Performance mode</span>
          <span className="san-setopt__desc">
            Smoother on laptops: 30 fps effects, fewer particles, no live glass blur.
            Saved on this computer only.
          </span>
        </span>
        <button
          className={"san-toggle" + (perf ? " san-toggle--on" : "")}
          onClick={() => setPerf(!perf)}
          role="switch"
          aria-checked={perf}
          aria-label="Performance mode"
        >
          <span className="san-toggle__knob" />
        </button>
      </div>
      {/* Buddy Lock lives inline rather than behind a category: it's a flow
          (camera, mic, PIN), not a set of sliders with a preview. */}
      <section className="setview__section">
        <h3 className="memtl__title">Security</h3>
        <BuddyLockPanel />
      </section>

      {SECTIONS.map((sec) => (
        <section key={sec.title} className="setview__section">
          <h3 className="memtl__title">{sec.title}</h3>
          <div className="setview__menu">
            {sec.cats.map((cat) => (
              <button
                key={cat}
                className="san-setopt setview__opt"
                onClick={() => setFocus(cat)}
                // layout, keys and skins work without the brain (skins are
                // cached locally); everything else needs its saved values
                disabled={!settings && cat !== "layout" && cat !== "keys" && cat !== "skins"}
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
