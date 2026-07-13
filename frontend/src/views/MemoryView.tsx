import { useEffect, useState } from "react";
import { api, type Fact } from "../api";

export default function MemoryView() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [newFact, setNewFact] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => api.getFacts().then((f) => { setFacts(f); setLoading(false); }).catch(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFact.trim()) return;
    await api.addFact(newFact.trim());
    setNewFact("");
    load();
  };

  const saveEdit = async (id: number) => {
    await api.updateFact(id, editText.trim());
    setEditId(null);
    load();
  };

  return (
    <div className="view">
      <div className="view__head">
        <h2>Memory</h2>
        <span className="view__count">{facts.length} facts</span>
      </div>
      <p className="view__hint">What AURA remembers about you. Edit or delete anything.</p>

      <form className="taskadd" onSubmit={add}>
        <input value={newFact} onChange={(e) => setNewFact(e.target.value)} placeholder="Teach AURA a fact about you..." />
        <button type="submit">Save</button>
      </form>

      {loading && <p className="view__empty">Loading...</p>}
      {!loading && facts.length === 0 && <p className="view__empty">No facts stored yet.</p>}

      <ul className="factlist">
        {facts.map((f) => (
          <li key={f.id} className="factrow">
            {editId === f.id ? (
              <>
                <input className="factrow__edit" value={editText} onChange={(e) => setEditText(e.target.value)} autoFocus />
                <button className="factrow__btn" onClick={() => saveEdit(f.id)}>Save</button>
                <button className="factrow__btn" onClick={() => setEditId(null)}>Cancel</button>
              </>
            ) : (
              <>
                <span className="factrow__text">{f.fact}</span>
                <span className="factrow__cat">{f.category}</span>
                <button className="factrow__btn" onClick={() => { setEditId(f.id); setEditText(f.fact); }}>Edit</button>
                <button className="factrow__btn" onClick={() => api.deleteFact(f.id).then(load)}>{"×"}</button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
