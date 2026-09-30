import { useCoreStore } from "../stores/coreStore";
import { usePlanetStore } from "../stores/planetStore";
import { useNotifyStore } from "../stores/notifyStore";
import { useRoster } from "../stores/rosterStore";
import Icon, { type IconName } from "./Icon";

/**
 * The few controls that sit on the edges of the window, each where it acts:
 * the core and orbit tuners on the sky, the bell in the rail, and the window
 * buttons in the top-right corner of every page.
 */

const KIND_ICON: Record<string, IconName> = {
  route: "models", memory: "memory", task: "tasks", quest: "spark", build: "domain", done: "check", info: "spark",
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

function Slider({ label, value, min, max, step, disabled, onChange }: {
  label: string; value: number; min: number; max: number; step: number; disabled: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <label className="menu__row">
      <span>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
             onChange={(e) => onChange(Number(e.target.value))} />
      <em>{value}%</em>
    </label>
  );
}

function EditActions({ editing, onEdit, onSave, onCancel, onReset }: {
  editing: boolean; onEdit: () => void; onSave: () => void; onCancel: () => void; onReset: () => void;
}) {
  return (
    <div className="menu__actions">
      {!editing ? (
        <button className="btn btn--primary" onClick={onEdit}>Edit</button>
      ) : (
        <>
          <button className="btn btn--primary" onClick={onSave}>Save</button>
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn--quiet" onClick={onReset}>Reset</button>
        </>
      )}
    </div>
  );
}

/** Core and orbit tuners — top-right of the sky, over the thing they change. */
export function StageTools() {
  const roster = useRoster();

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

  // one menu at a time (the bell lives in the rail but follows the same rule)
  const setBellOpen = useNotifyStore((s) => s.setOpen);
  const open = (which: "core" | "planets") => {
    setMenuOpen(which === "core" ? !menuOpen : false);
    pSetMenuOpen(which === "planets" ? !pMenuOpen : false);
    setBellOpen(false);
  };

  return (
    <div className="stagetools">
      <div className="menuwrap">
        <button className={"ghostbtn" + (menuOpen ? " ghostbtn--on" : "")} onClick={() => open("core")}
                aria-expanded={menuOpen} aria-label="Adjust the core" data-tip="Core">
          <Icon name="core" size={18} />
        </button>
        {menuOpen && (
          <div className="menu" role="dialog" aria-label="Core">
            <div className="menu__head">
              <span>Core</span>
              {editing && <em className="menu__flag">Editing</em>}
            </div>
            <Slider label="Size" value={scale} min={50} max={150} step={5} disabled={!editing}
                    onChange={(v) => setCfg({ scale: v })} />
            <Slider label="Glow" value={glow} min={40} max={160} step={5} disabled={!editing}
                    onChange={(v) => setCfg({ glow: v })} />
            {editing && <p className="menu__hint">Drag the black hole to move it.</p>}
            <EditActions editing={editing} onEdit={startEdit} onSave={save} onCancel={cancel} onReset={resetSpec} />
          </div>
        )}
      </div>

      <div className="menuwrap">
        <button className={"ghostbtn" + (pMenuOpen ? " ghostbtn--on" : "")} onClick={() => open("planets")}
                aria-expanded={pMenuOpen} aria-label="Adjust the planets" data-tip="Orbits">
          <Icon name="models" size={18} />
        </button>
        {pMenuOpen && (
          <div className="menu" role="dialog" aria-label="Planets">
            <div className="menu__head">
              <span>Orbits</span>
              {pEditing && <em className="menu__flag">Editing</em>}
            </div>
            <Slider label="Orbit" value={pOrbit} min={20} max={300} step={5} disabled={!pEditing}
                    onChange={(v) => pSetCfg({ orbit: v })} />
            <Slider label="Size" value={pSize} min={50} max={600} step={10} disabled={!pEditing}
                    onChange={(v) => pSetCfg({ size: v })} />
            <Slider label="Speed" value={pSpeed} min={25} max={300} step={5} disabled={!pEditing}
                    onChange={(v) => pSetCfg({ speed: v })} />
            <Slider label="Rings" value={pRingsV} min={60} max={300} step={10} disabled={!pEditing}
                    onChange={(v) => pSetCfg({ rings: v })} />
            {pEditing && (
              <>
                <p className="menu__hint">
                  Drag a planet onto any orbit. If one already lives there, they swap.
                </p>
                <div className="menu__planets">
                  {roster.map((m) => (
                    <div key={m.id} className="menu__planetrow">
                      <span className="menu__dot" style={{ background: m.color }} />
                      <input className="menu__name" value={pMeta[m.id]?.name ?? m.name}
                             onChange={(e) => pSetMeta(m.id, { name: e.target.value })}
                             placeholder={m.name} aria-label={`Name for ${m.name}`} />
                      <input className="menu__role" value={pMeta[m.id]?.role ?? m.role}
                             onChange={(e) => pSetMeta(m.id, { role: e.target.value })}
                             placeholder={m.role} aria-label={`What ${m.name} is for`} />
                    </div>
                  ))}
                </div>
              </>
            )}
            <EditActions editing={pEditing} onEdit={pStartEdit} onSave={pSave} onCancel={pCancel} onReset={pResetSpec} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Notifications — a rail item; its list opens beside the rail. */
export function NotifyBell({ slim }: { slim: boolean }) {
  const notices = useNotifyStore((s) => s.notices);
  const bellOpen = useNotifyStore((s) => s.open);
  const setBellOpen = useNotifyStore((s) => s.setOpen);
  const clearNotices = useNotifyStore((s) => s.clear);
  const setCoreMenu = useCoreStore((s) => s.setMenuOpen);
  const setPlanetMenu = usePlanetStore((s) => s.setMenuOpen);
  const unread = notices.filter((n) => !n.read).length;

  const toggle = () => {
    setCoreMenu(false);
    setPlanetMenu(false);
    setBellOpen(!bellOpen);
  };

  return (
    <div className="menuwrap">
      <button className={"rail__item" + (bellOpen ? " rail__item--open" : "")} onClick={toggle}
              aria-expanded={bellOpen} aria-label={`Notifications${unread ? `, ${unread} new` : ""}`}
              data-tip={slim && !bellOpen ? "Notifications" : undefined}>
        <span className="rail__iconwrap">
          <Icon name="bell" size={19} />
          {unread > 0 && <span className="rail__badge">{unread > 9 ? "9+" : unread}</span>}
        </span>
        <span className="rail__label">Notifications</span>
      </button>
      {bellOpen && (
        <div className="menu menu--wide menu--side" role="dialog" aria-label="Notifications">
          <div className="menu__head">
            <span>Notifications</span>
            {notices.length > 0 && <button className="menu__clear" onClick={clearNotices}>Clear all</button>}
          </div>
          <div className="notes">
            {notices.length === 0 && <p className="notes__empty">Nothing yet. What AURA does in the background shows up here.</p>}
            {notices.slice(0, 30).map((n) => (
              <div key={n.id} className={"notes__row" + (n.read ? "" : " notes__row--new")}>
                <Icon name={KIND_ICON[n.kind] ?? "spark"} size={14} className="notes__icon" />
                <span className="notes__text">{n.text}</span>
                <span className="notes__when">{timeAgo(n.ts)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Minimize and close — the same corner on every page. */
export function WindowControls() {
  return (
    <div className="winbar">
      <button className="winbar__btn" aria-label="Minimize" onClick={() => window.aura?.minimize?.()}>
        <Icon name="minimize" size={16} />
      </button>
      <button className="winbar__btn winbar__btn--close" aria-label="Close" onClick={() => window.aura?.close?.()}>
        <Icon name="close" size={16} />
      </button>
    </div>
  );
}
