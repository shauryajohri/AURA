import { useEffect, useState } from "react";
import { api, Settings } from "../api";
import SettingsOverlay, { SettingsCategory, CATEGORY_META } from "../components/Home/SettingsOverlay";
import { Layout, DEFAULT_LAYOUT } from "../components/Home/layoutTypes";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useSettingsStore } from "../stores/settingsStore";
import { setPref, usePrefs, type Pref } from "../stores/prefsStore";
import Icon from "../components/Icon";
import ResetPanel from "./ResetPanel";

const DEVICE: Array<{ key: Pref; name: string; desc: string }> = [
  { key: "intro", name: "Startup animation", desc: "The black hole forms each time AURA opens" },
  { key: "sfx", name: "Interface sounds", desc: "Soft tones when you type, send, click and get a reply" },
  { key: "cursor", name: "AURA cursor", desc: "The photon-and-ring pointer. Off uses your system cursor" },
];

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
  const [resetting, setResetting] = useState(false);
  const applySettings = useSettingsStore((s) => s.apply);
  // Sanctuary layout is edited here too — same store the sanctuary reads.
  const [layout, setLayout] = useLocalStorage<Layout>("aura.sanctuary", DEFAULT_LAYOUT);
  const prefs = usePrefs();

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => setOffline(true));
  }, []);

  return (
    <div className="setview">
      <header className="pagehead">
        <h2>Settings</h2>
      </header>

      <section className="setview__section">
        <h3 className="memtl__title">This device</h3>
        <div className="devprefs">
          {DEVICE.map((d) => (
            <button
              key={d.key}
              role="switch"
              aria-checked={prefs[d.key]}
              className={"devpref" + (prefs[d.key] ? " devpref--on" : "")}
              onClick={() => setPref(d.key, !prefs[d.key])}
            >
              <span className="devpref__text">
                <span className="devpref__name">{d.name}</span>
                <span className="devpref__desc">{d.desc}</span>
              </span>
              <span className="devpref__track"><span className="devpref__knob" /></span>
            </button>
          ))}
        </div>
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
                disabled={!settings && cat !== "layout" && cat !== "keys"}
              >
                <span className="san-setopt__icon">{CATEGORY_META[cat].icon}</span>
                <span className="san-setopt__meta">
                  <span className="san-setopt__name">{CATEGORY_META[cat].title}</span>
                  <span className="san-setopt__desc">{CATEGORY_META[cat].desc}</span>
                </span>
                <span className="san-setopt__go"><Icon name="right" size={16} /></span>
              </button>
            ))}
          </div>
        </section>
      ))}

      {/* Last, and on its own: everything above changes how AURA behaves,
          this one changes what AURA still has. */}
      <section className="setview__section">
        <h3 className="memtl__title">Start over</h3>
        <div className="setview__menu">
          <button className="san-setopt setview__opt setview__opt--danger"
                  onClick={() => setResetting(true)}>
            <span className="san-setopt__icon">↺</span>
            <span className="san-setopt__meta">
              <span className="san-setopt__name">Reset AURA</span>
              <span className="san-setopt__desc">
                Clear conversations, memory, saved info or settings — one at a time or all of it
              </span>
            </span>
            <span className="san-setopt__go"><Icon name="right" size={16} /></span>
          </button>
        </div>
      </section>

      {!settings && (
        <div className="setview__note">
          {offline
            ? "Brain offline — start server.py to load visual settings."
            : "Loading settings…"}
        </div>
      )}

      {resetting && (
        <div className="resetwrap" onClick={(e) => { if (e.target === e.currentTarget) setResetting(false); }}>
          <div className="resetwrap__card">
            <ResetPanel onClose={() => setResetting(false)} />
          </div>
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
