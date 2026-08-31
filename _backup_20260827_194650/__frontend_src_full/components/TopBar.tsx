import { useState } from "react";
import { useClock } from "../hooks/useClock";
import { useCoreStore } from "../stores/coreStore";
import { usePlanetStore } from "../stores/planetStore";
import { useNotifyStore } from "../stores/notifyStore";
import { MODELS } from "../data/models";

const KIND_ICON: Record<string, string> = {
  route: "◈", memory: "❋", task: "✓", quest: "❖", build: "⚙", done: "●", info: "◎",
};

function timeAgo(ts: number): string {
  const s = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return s + "s ago";
  const m = Math.round(s / 60);
  if (m < 60) return m + "m ago";
  const h = Math.round(m / 60);
  if (h < 24) return h + "h ago";
  return Math.round(h / 24) + "d ago";
}

const USER = "Shaurya";

interface Props {
  mode?: string;
}

export default function TopBar({ mode = "CHAT" }: Props) {
  const { time, date, greeting } = useClock();
  const [focus, setFocus] = useState(true);

  const menuOpen = useCoreStore((s) => s.menuOpen);
  const setMenuOpen = useCoreStore((s) => s.setMenuOpen);
  const editing = useCoreStore((s) => s.editing);
  const scale = useCoreStore((s) => s.scale);
  const glow = useCoreStore((s) => s.glow);
  const setCfg = useCoreStore((s) => s.set);
  const startEdit = useCoreStore((s) => s.startEdit);
  const save = useCoreStore((s) => s.save);
  const cancel = useCoreStore((s) => s.cancel);
  const resetSpec = useCoreStore((s) => s.resetSpec);

  const pMenuOpen = usePlanetStore((s) => s.menuOpen);
  const pSetMenuOpen = usePlanetStore((s) => s.setMenuOpen);
  const pEditing = usePlanetStore((s) => s.editing);
  const pOrbit = usePlanetStore((s) => s.orbit);
  const pSize = usePlanetStore((s) => s.size);
  const pSpeed = usePlanetStore((s) => s.speed);
  const pRingsV = usePlanetStore((s) => s.rings);
  const pSetCfg = usePlanetStore((s) => s.set);
  const pStartEdit = usePlanetStore((s) => s.startEdit);
  const pSave = usePlanetStore((s) => s.save);
  const pCancel = usePlanetStore((s) => s.cancel);
  const pResetSpec = usePlanetStore((s) => s.resetSpec);
  const pMeta = usePlanetStore((s) => s.meta);
  const pSetMeta = usePlanetStore((s) => s.setMeta);

  const notices = useNotifyStore((s) => s.notices);
  const bellOpen = useNotifyStore((s) => s.open);
  const setBellOpen = useNotifyStore((s) => s.setOpen);
  const clearNotices = useNotifyStore((s) => s.clear);
  const unread = notices.filter((n) => !n.read).length;

  return (
    <header className="topbar">
      <div className="topbar__greet">
        <h2>
          {greeting}, {USER} <span className="topbar__spark">{"✦"}</span>
          {mode && mode !== "CHAT" && <span className="modechip">{mode} mode</span>}
        </h2>
        <p>I'm here, ready to help you achieve more today.</p>
      </div>

      <div className="clock">
        <div className="clock__time">
          <span className="clock__moon">{"☾"}</span> {time}
        </div>
        <div className="clock__date">{date}</div>
      </div>

      <div className="topbar__right">
        <div className="coremenu-wrap">
          <button
            className={"corebtn " + (menuOpen ? "corebtn--open" : "")}
            onClick={() => setMenuOpen(!menuOpen)}
            title="AURA core settings">
            <span className="corebtn__orb" />
            <span className="corebtn__label">Core</span>
            <span className="corebtn__caret">{menuOpen ? "▴" : "▾"}</span>
          </button>

          {menuOpen && (
            <div className="coremenu">
              <div className="coremenu__head">
                <span>CORE ADJUST</span>
                {editing && <em className="coremenu__editing">editing</em>}
              </div>

              <label className="coremenu__row">
                <span>Size</span>
                <input
                  type="range" min={50} max={150} step={5} value={scale}
                  disabled={!editing}
                  onChange={(e) => setCfg({ scale: Number(e.target.value) })}
                />
                <em>{scale}%</em>
              </label>
              <label className="coremenu__row">
                <span>Glow</span>
                <input
                  type="range" min={40} max={160} step={5} value={glow}
                  disabled={!editing}
                  onChange={(e) => setCfg({ glow: Number(e.target.value) })}
                />
                <em>{glow}%</em>
              </label>

              {editing && <p className="coremenu__hint">Drag the black hole to reposition it.</p>}

              <div className="coremenu__actions">
                {!editing ? (
                  <button className="coremenu__btn coremenu__btn--primary" onClick={startEdit}>
                    Edit
                  </button>
                ) : (
                  <>
                    <button className="coremenu__btn coremenu__btn--primary" onClick={save}>
                      Save
                    </button>
                    <button className="coremenu__btn" onClick={cancel}>
                      Cancel
                    </button>
                    <button className="coremenu__btn" onClick={resetSpec}>
                      Reset
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="coremenu-wrap">
          <button
            className={"corebtn " + (pMenuOpen ? "corebtn--open" : "")}
            onClick={() => pSetMenuOpen(!pMenuOpen)}
            title="Planet system settings"
          >
            <span className="corebtn__orb corebtn__orb--planet" />
            <span className="corebtn__label">Planets</span>
            <span className="corebtn__caret">{pMenuOpen ? "▴" : "▾"}</span>
          </button>

          {pMenuOpen && (
            <div className="coremenu">
              <div className="coremenu__head">
                <span>PLANET ADJUST</span>
                {pEditing && <em className="coremenu__editing">editing</em>}
              </div>

              <label className="coremenu__row">
                <span>Orbit</span>
                <input
                  type="range" min={20} max={300} step={5} value={pOrbit}
                  disabled={!pEditing}
                  onChange={(e) => pSetCfg({ orbit: Number(e.target.value) })}
                />
                <em>{pOrbit}%</em>
              </label>
              <label className="coremenu__row">
                <span>Size</span>
                <input
                  type="range" min={50} max={600} step={10} value={pSize}
                  disabled={!pEditing}
                  onChange={(e) => pSetCfg({ size: Number(e.target.value) })}
                />
                <em>{pSize}%</em>
              </label>
              <label className="coremenu__row">
                <span>Speed</span>
                <input
                  type="range" min={25} max={300} step={5} value={pSpeed}
                  disabled={!pEditing}
                  onChange={(e) => pSetCfg({ speed: Number(e.target.value) })}
                />
                <em>{pSpeed}%</em>
              </label>
              <label className="coremenu__row">
                <span>Rings</span>
                <input
                  type="range" min={60} max={300} step={10} value={pRingsV}
                  disabled={!pEditing}
                  onChange={(e) => pSetCfg({ rings: Number(e.target.value) })}
                />
                <em>{pRingsV}%</em>
              </label>

              {pEditing && (
                <>
                  <p className="coremenu__hint">
                    Drag a planet onto any orbit — one planet per orbit, the old
                    tenant swaps to the vacated one.
                  </p>
                  <div className="coremenu__planets">
                    {MODELS.map((m) => (
                      <div key={m.id} className="coremenu__planetrow">
                        <span className="coremenu__dot" style={{ background: m.color }} />
                        <input
                          className="coremenu__namein"
                          value={pMeta[m.id]?.name ?? m.name}
                          onChange={(e) => pSetMeta(m.id, { name: e.target.value })}
                          placeholder={m.name}
                          title="Planet name"
                        />
                        <input
                          className="coremenu__rolein"
                          value={pMeta[m.id]?.role ?? m.role}
                          onChange={(e) => pSetMeta(m.id, { role: e.target.value })}
                          placeholder={m.role}
                          title="What this planet is for"
                        />
                      </div>
                    ))}
                  </div>
                </>
              )}

              <div className="coremenu__actions">
                {!pEditing ? (
                  <button className="coremenu__btn coremenu__btn--primary" onClick={pStartEdit}>
                    Edit
                  </button>
                ) : (
                  <>
                    <button className="coremenu__btn coremenu__btn--primary" onClick={pSave}>
                      Save
                    </button>
                    <button className="coremenu__btn" onClick={pCancel}>
                      Cancel
                    </button>
                    <button className="coremenu__btn" onClick={pResetSpec}>
                      Reset
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="coremenu-wrap">
          <button
            className={"bell" + (bellOpen ? " bell--open" : "")}
            onClick={() => setBellOpen(!bellOpen)}
            title="Notifications"
          >
            {"🔔"}
            {unread > 0 && <span className="bell__badge">{unread > 9 ? "9+" : unread}</span>}
          </button>

          {bellOpen && (
            <div className="coremenu bellmenu">
              <div className="coremenu__head">
                <span>NOTIFICATIONS</span>
                {notices.length > 0 && (
                  <button className="bellmenu__clear" onClick={clearNotices}>clear</button>
                )}
              </div>
              <div className="bellmenu__list">
                {notices.length === 0 && (
                  <p className="bellmenu__empty">All quiet — AURA will log what she does here.</p>
                )}
                {notices.slice(0, 30).map((n) => (
                  <div key={n.id} className={"bellmenu__row" + (n.read ? "" : " bellmenu__row--new")}>
                    <span className="bellmenu__icon">{KIND_ICON[n.kind] ?? "◎"}</span>
                    <span className="bellmenu__text">{n.text}</span>
                    <span className="bellmenu__when">{timeAgo(n.ts)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <button
          className={"focus " + (focus ? "focus--on" : "")}
          onClick={() => setFocus((f) => !f)}
        >
          <span className="focus__icon">{"✧"}</span>
          <div className="focus__text">
            <span className="focus__label">Focus Mode</span>
            <span className="focus__state">{focus ? "● ON" : "● OFF"}</span>
          </div>
        </button>

        <div className="winctl">
          <button className="winctl__btn" title="Minimize" onClick={() => window.aura?.minimize?.()}>
            {"—"}
          </button>
          <button className="winctl__btn winctl__btn--close" title="Close" onClick={() => window.aura?.close?.()}>
            {"✕"}
          </button>
        </div>
      </div>
    </header>
  );
}
