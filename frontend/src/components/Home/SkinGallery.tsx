import { useEffect, useState } from "react";
import type { AuraState } from "../../types";
import SkinPreview from "../SkinPreview";
import { useSettingsStore } from "../../stores/settingsStore";
import {
  BACKDROPS, CORE_FORMS, SKINS, resolveSkin, type BackdropId, type CoreFormId,
} from "../../skins/skins";

/** The three skin settings, as stored ("" overrides = match the skin). */
export interface SkinChoice {
  "skin.id": string;
  "skin.core": string;
  "skin.backdrop": string;
}

interface Props {
  value: SkinChoice;
  onChange: (patch: Partial<SkinChoice>) => void;
}

const STATES: Array<{ id: AuraState; label: string }> = [
  { id: "idle", label: "Idle" },
  { id: "thinking", label: "Thinking" },
  { id: "speaking", label: "Speaking" },
];

/** The skin's three signature colours, for the swatch row. */
const swatches = (id: string) => {
  const p = SKINS.find((s) => s.id === id)!.pal;
  return [p.main, p.photon, p.accent];
};

/**
 * Skins — the gallery inside Settings → Skins.
 *
 * Top: "your world", a large live preview of exactly what will render (skin
 * + any overrides), with Idle/Thinking/Speaking so the design can be seen
 * reacting. Then one card per skin, each a running miniature of that design.
 * Then mix & match: any background and any core on top of the chosen skin.
 *
 * While this is open the whole app wears the draft (via the store's
 * skinPreview), so the glass and colours behind the panel change too.
 * Closing without saving drops the preview.
 */
export default function SkinGallery({ value, onChange }: Props) {
  const [state, setState] = useState<AuraState>("idle");
  const setPreview = useSettingsStore((s) => s.setSkinPreview);
  const resolved = resolveSkin(value["skin.id"], value["skin.core"], value["skin.backdrop"]);

  useEffect(() => {
    setPreview({ ...value });
  }, [value, setPreview]);
  useEffect(() => () => setPreview(null), [setPreview]);

  const skinName = resolved.skin.name;
  const ownBackdrop = BACKDROPS.find((b) => b.id === resolved.skin.backdrop)!.name;
  const ownCore = CORE_FORMS.find((c) => c.id === resolved.skin.core)!.name;

  return (
    <div className="skins">
      <div className="skins__hero">
        <SkinPreview
          skin={resolved.skin}
          core={resolved.core}
          backdrop={resolved.backdrop}
          state={state}
          density={0.8}
          className="skins__heroprev"
        />
        <div className="skins__herobar">
          <span className="skins__heroname">
            {skinName}
            {(value["skin.core"] || value["skin.backdrop"]) && <em> · your mix</em>}
          </span>
          <span className="skins__states" role="group" aria-label="Preview state">
            {STATES.map((s) => (
              <button
                key={s.id}
                className={"setov__stylebtn" + (state === s.id ? " setov__stylebtn--on" : "")}
                onClick={() => setState(s.id)}
              >
                {s.label}
              </button>
            ))}
          </span>
        </div>
      </div>

      <div className="skins__grid">
        {SKINS.map((sk) => {
          const on = sk.id === resolved.skin.id;
          return (
            <button
              key={sk.id}
              className={"skincard" + (on ? " skincard--on" : "")}
              onClick={() => onChange({ "skin.id": sk.id })}
              aria-pressed={on}
              title={sk.tagline}
            >
              <SkinPreview skin={sk} core={sk.core} backdrop={sk.backdrop} className="skincard__prev" />
              <span className="skincard__meta">
                <span className="skincard__name">{sk.name}</span>
                <span className="skincard__sw">
                  {swatches(sk.id).map((c, i) => <i key={i} style={{ background: `rgb(${c})` }} />)}
                </span>
              </span>
              <span className="skincard__tag">{sk.tagline}</span>
              {on && <span className="skincard__badge">wearing</span>}
            </button>
          );
        })}
      </div>

      <div className="skins__mix">
        <div className="skins__mixrow">
          <span className="setov__label">Background</span>
          <span className="skins__chips">
            <button
              className={"setov__stylebtn" + (!value["skin.backdrop"] ? " setov__stylebtn--on" : "")}
              onClick={() => onChange({ "skin.backdrop": "" })}
              title={`Use ${skinName}'s own background`}
            >
              Match skin ({ownBackdrop})
            </button>
            {BACKDROPS.map((b) => (
              <button
                key={b.id}
                className={"setov__stylebtn" + (value["skin.backdrop"] === b.id ? " setov__stylebtn--on" : "")}
                onClick={() => onChange({ "skin.backdrop": b.id as BackdropId })}
                title={b.desc}
              >
                {b.name}
              </button>
            ))}
          </span>
        </div>
        <div className="skins__mixrow">
          <span className="setov__label">Core</span>
          <span className="skins__chips">
            <button
              className={"setov__stylebtn" + (!value["skin.core"] ? " setov__stylebtn--on" : "")}
              onClick={() => onChange({ "skin.core": "" })}
              title={`Use ${skinName}'s own core`}
            >
              Match skin ({ownCore})
            </button>
            {CORE_FORMS.map((c) => (
              <button
                key={c.id}
                className={"setov__stylebtn" + (value["skin.core"] === c.id ? " setov__stylebtn--on" : "")}
                onClick={() => onChange({ "skin.core": c.id as CoreFormId })}
                title={c.desc}
              >
                {c.name}
              </button>
            ))}
          </span>
        </div>
        <p className="setov__hint">
          A skin sets everything at once. Pick a different background or core here to mix
          designs; the skin's colours carry across whatever you choose.
        </p>
      </div>
    </div>
  );
}
