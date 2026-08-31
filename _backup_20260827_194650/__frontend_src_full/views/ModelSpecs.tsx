import { useEffect, useState } from "react";
import { api, type ModelInfo } from "../api";
import { MODELS } from "../data/models";

/**
 * The model spec sheet — every planet's real numbers side by side.
 * Provider · status · speed · context · purpose · cost · usage · routing
 * priority. Lock state comes from the backend (model_lock), so locking here
 * genuinely removes a model from the routing chain.
 */

interface Props {
  activeModelId?: string | null;
}

export default function ModelSpecs({ activeModelId = null }: Props) {
  const [info, setInfo] = useState<ModelInfo[] | null>(null);
  const [offline, setOffline] = useState(false);
  const [usage, setUsage] = useState<Record<string, number>>({});

  const load = () =>
    api.getModels()
      .then((r) => { setInfo(r.models); setOffline(false); })
      .catch(() => setOffline(true));

  useEffect(() => { load(); }, []);

  // Usage is counted locally per session — every time a planet answers, the
  // socket sets activeModelId, so this is an honest "answers this session"
  // rather than a number the backend doesn't actually track yet.
  useEffect(() => {
    if (!activeModelId) return;
    setUsage((u) => ({ ...u, [activeModelId]: (u[activeModelId] ?? 0) + 1 }));
  }, [activeModelId]);

  const lockedOf = (name: string) => info?.find((m) => m.name === name)?.locked ?? false;

  return (
    <div className="specs">
      {offline && <p className="pane-note">Brain offline — lock state and live status need server.py.</p>}
      <div className="specs__grid">
        {[...MODELS].sort((a, b) => a.priority - b.priority).map((m) => {
          const locked = lockedOf(m.name);
          const active = activeModelId === m.id;
          return (
            <article
              key={m.id}
              className={"speccard" + (active ? " speccard--active" : "") + (locked ? " speccard--locked" : "")}
              style={{ ["--accent" as string]: m.color }}
            >
              <header className="speccard__head">
                <span className="speccard__orb" style={{ background: m.color }} />
                <div className="speccard__id">
                  <h4>{m.name}</h4>
                  <span>{m.provider} · {m.role}</span>
                </div>
                <span className={"speccard__status" + (locked ? " speccard__status--locked" : active ? " speccard__status--on" : "")}>
                  {locked ? "LOCKED" : active ? "ACTIVE" : "STANDBY"}
                </span>
              </header>

              <p className="speccard__purpose">{m.purpose}</p>

              <div className="speccard__speed">
                <span>speed</span>
                <div className="taskboard__track"><span style={{ width: m.speed + "%" }} /></div>
                <em>{m.speed}</em>
              </div>

              <dl className="speccard__specs">
                <div><dt>Context</dt><dd>{m.context}</dd></div>
                <div><dt>Cost</dt><dd>{m.cost}</dd></div>
                <div><dt>Priority</dt><dd>#{m.priority}</dd></div>
                <div><dt>Used</dt><dd>{usage[m.id] ?? 0}×</dd></div>
              </dl>

              <footer className="speccard__foot">
                <span className="speccard__nature">{m.nature}</span>
                <button
                  className={"speccard__lock" + (locked ? " speccard__lock--on" : "")}
                  disabled={offline}
                  onClick={() => api.toggleLock(m.name).then(load).catch(() => {})}
                >
                  {locked ? "Unlock" : "Lock"}
                </button>
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
