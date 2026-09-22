import { useCallback, useEffect, useState } from "react";
import { upgrades, type ProposalRow } from "../systemApi";
import ProposalCard from "../components/Upgrade/ProposalCard";

/**
 * Upgrade — AURA rewriting AURA.
 *
 * You say what you want changed; AURA reads its own source, works out which
 * files that touches, and writes them. Then it stops and shows you the diff.
 * Nothing reaches disk until you approve it, and anything applied can be put
 * back exactly as it was, so saying yes is never a one-way door.
 */

const EXAMPLES = [
  "Add a keyboard shortcut that opens Saved Info",
  "Make the sidebar remember which page I was on",
  "Add a 'copy reply' button to every message in the chat",
  "Show the model that answered under each reply",
];

export default function UpgradePage() {
  const [rows, setRows] = useState<ProposalRow[]>([]);
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [offline, setOffline] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await upgrades.list("self"));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = request.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    setNote("");
    const res = await upgrades
      .propose({ request: text, scope: "self" })
      .catch(() => ({ ok: false, error: "the brain didn't answer — is server.py running?" } as
        Awaited<ReturnType<typeof upgrades.propose>>));
    setBusy(false);
    if (!res.ok) { setError(res.error || "that didn't work"); return; }
    setRequest("");
    setNote("Written. Read the diff before you approve it.");
    void load();
  };

  const pending = rows.filter((r) => r.status === "pending");
  const history = rows.filter((r) => r.status !== "pending");

  return (
    <div className="uppage">
      <header className="pagehead">
        <h2>Upgrade</h2>
      </header>

      <section className="uppage__ask">
        <p className="uppage__lede">
          Tell me what to change about myself. I'll read my own source, write the
          change, and show you exactly what it does — nothing is saved until you
          say yes, and anything I apply I can undo.
        </p>

        <form onSubmit={submit} className="uppage__form">
          <textarea
            className="uppage__input"
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            placeholder="What should I be able to do?"
            rows={3}
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e as unknown as React.FormEvent);
            }}
          />
          <div className="uppage__formrow">
            <span className="uppage__hint">⌘/Ctrl + Enter</span>
            <button className="btn btn--primary" disabled={busy || !request.trim()}>
              {busy ? "Reading my own code…" : "Write the change"}
            </button>
          </div>
        </form>

        {!request && !busy && (
          <div className="uppage__examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} className="uppage__example" onClick={() => setRequest(ex)}>
                {ex}
              </button>
            ))}
          </div>
        )}

        {busy && (
          <p className="uppage__working">
            Working through the files this touches. Big changes take a minute.
          </p>
        )}
        {error && <p className="uppage__err">{error}</p>}
        {note && <p className="uppage__note">{note}</p>}
        {offline && (
          <p className="uppage__err">Brain offline — start server.py and this page fills in.</p>
        )}
      </section>

      {pending.length > 0 && (
        <section className="uppage__section">
          <h3 className="memtl__title">Waiting on you</h3>
          {pending.map((r) => (
            <ProposalCard key={r.id} row={r} onChanged={(n) => { if (n) setNote(n); void load(); }} />
          ))}
        </section>
      )}

      {history.length > 0 && (
        <section className="uppage__section">
          <h3 className="memtl__title">Everything I've changed</h3>
          {history.map((r) => (
            <ProposalCard key={r.id} row={r} onChanged={(n) => { if (n) setNote(n); void load(); }} />
          ))}
        </section>
      )}

      {!rows.length && !offline && !busy && (
        <p className="uppage__empty">
          Nothing yet. Ask for something above and I'll write it.
        </p>
      )}
    </div>
  );
}
