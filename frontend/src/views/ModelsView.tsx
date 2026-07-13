import { useEffect, useState } from "react";
import { api, type ModelInfo } from "../api";

export default function ModelsView() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [last, setLast] = useState("");

  const load = () => api.getModels().then((r) => { setModels(r.models); setLast(r.last_model); });
  useEffect(() => { load(); }, []);

  const toggle = async (m: ModelInfo) => {
    await api.toggleLock(m.name);
    load();
  };

  return (
    <div className="view">
      <div className="view__head">
        <h2>Models</h2>
        {last && <span className="view__count">last answered: {last}</span>}
      </div>
      <p className="view__hint">Locked models are never used by the router. Click a model to lock or unlock it.</p>

      <ul className="modellist">
        {models.map((m) => (
          <li key={m.id} className={"modelrow " + (m.locked ? "modelrow--locked" : "")}>
            <span className="modelrow__orb" />
            <span className="modelrow__name">{m.name}</span>
            <button className={"modelrow__lock " + (m.locked ? "modelrow__lock--on" : "")} onClick={() => toggle(m)}>
              {m.locked ? "Locked" : "Active"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
