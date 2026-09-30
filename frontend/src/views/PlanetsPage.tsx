import { useEffect, useState } from "react";
import { useRoster } from "../stores/rosterStore";
import { skinFor, useSkinStore } from "../stores/skinStore";
import { SKINS, defaultSkin, skinById, skinUrl } from "../data/planetSkins";
import { sfx } from "../lib/sfx";

/**
 * Planets — every model is a world in orbit around AURA. Pick the model on
 * the left, then the world it should be; the orbit on Home changes at once.
 */
export default function PlanetsPage() {
  const roster = useRoster();
  const picks = useSkinStore((s) => s.picks);
  const pick = useSkinStore((s) => s.pick);
  const reset = useSkinStore((s) => s.reset);
  const focus = useSkinStore((s) => s.focus);
  const setFocus = useSkinStore((s) => s.setFocus);
  const [sel, setSel] = useState<string>(() => focus ?? roster[0]?.id ?? "");

  // Arriving from a click on a planet in orbit.
  useEffect(() => {
    if (focus) { setSel(focus); setFocus(null); }
  }, [focus, setFocus]);

  const idx = Math.max(0, roster.findIndex((m) => m.id === sel));
  const model = roster[idx];
  const current = model ? skinFor(picks, model.id, idx) : SKINS[0].id;
  const skin = skinById(current) ?? SKINS[0];
  const isDefault = model ? current === defaultSkin(model.id, idx) : true;

  return (
    <div className="planets">
      <header className="pagehead">
        <h2>Planets</h2>
      </header>

      <div className="planets__body">
        <nav className="planets__models" aria-label="Models">
          {roster.map((m, i) => {
            const s = skinFor(picks, m.id, i);
            return (
              <button
                key={m.id}
                className={"planets__model" + (m.id === sel ? " planets__model--on" : "")}
                onClick={() => setSel(m.id)}
                aria-pressed={m.id === sel}
              >
                <img src={skinUrl(s)} alt="" />
                <span>
                  <strong>{m.name}</strong>
                  <small>{m.role}</small>
                </span>
              </button>
            );
          })}
        </nav>

        <section className="planets__stage">
          {model && (
            <div className="planets__hero" style={{ "--glow": skin.glow } as React.CSSProperties}>
              <img key={skin.id} className="planets__big" src={skinUrl(skin.id)} alt={`${skin.name}, ${skin.about}`} />
              <div className="planets__caption">
                <h3>{model.name}</h3>
                <p className="planets__wears">lives on <strong>{skin.name}</strong></p>
                <p className="planets__about">{skin.about}.</p>
                <p className="planets__purpose">{model.purpose}</p>
                {!isDefault && (
                  <button className="btn btn--quiet" onClick={() => reset(model.id)}>
                    Back to its first world
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="planets__grid" role="radiogroup" aria-label={`World for ${model?.name ?? "this model"}`}>
            {SKINS.map((s) => {
              const on = s.id === current;
              const wornBy = roster.filter((m, i) => m.id !== sel && skinFor(picks, m.id, i) === s.id);
              return (
                <button
                  key={s.id}
                  role="radio"
                  aria-checked={on}
                  className={"planets__tile" + (on ? " planets__tile--on" : "")}
                  style={{ "--glow": s.glow } as React.CSSProperties}
                  onClick={() => { if (model) { pick(model.id, s.id); sfx.tap(); } }}
                  title={s.about}
                >
                  <img src={skinUrl(s.id)} alt="" loading="lazy" />
                  <span className="planets__name">{s.name}</span>
                  <span className="planets__worn">
                    {on ? "Chosen" : wornBy.length ? `Also ${wornBy.map((m) => m.short || m.name).join(", ")}` : " "}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
