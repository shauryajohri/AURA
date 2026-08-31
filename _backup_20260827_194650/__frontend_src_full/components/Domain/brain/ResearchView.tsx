import { useEffect, useMemo, useRef, useState } from "react";
import { NODE_META, type CaptureResult } from "../../../brainApi";
import { useBrainStore } from "../../../stores/brainStore";
import { useDomainStore } from "../../../stores/domainStore";

// ============================================================================
// RESEARCH — where a project gets thought about.
//
// Two panes, and the split is the whole idea: pick a project on the left, talk
// about it on the right. Nothing here is a form. Every utterance goes to
// /capture, which decides whether it was a feature, a decision, an edit to
// existing work, or a note, and folds it into that project's knowledge graph.
//
// The receipt under each turn is deliberate: extraction must never be invisible.
// You always see what AURA understood, can open it, and can push a generated
// task further down into subtasks on the spot.
//
// (This replaced the separate Brainstorm section — one discussion surface, with
// the project chooser attached, beats two half-surfaces.)
// ============================================================================

interface Turn {
  id: string;
  mine: boolean;
  text: string;
  result?: CaptureResult;
}

const KIND_LABEL: Record<string, string> = {
  feature: "Feature captured",
  decision: "Decision recorded",
  edit: "Existing work updated",
  note: "Noted",
};

export default function ResearchView() {
  const projects = useBrainStore((s) => s.projects);
  const activeId = useBrainStore((s) => s.activeId);
  const nodes = useBrainStore((s) => s.nodes);
  const progress = useBrainStore((s) => s.progress);
  const busy = useBrainStore((s) => s.busy);
  const error = useBrainStore((s) => s.error);
  const reachable = useBrainStore((s) => s.reachable);
  const useLlm = useBrainStore((s) => s.useLlm);
  const setUseLlm = useBrainStore((s) => s.setUseLlm);
  const loadProjects = useBrainStore((s) => s.loadProjects);
  const select = useBrainStore((s) => s.select);
  const createProject = useBrainStore((s) => s.createProject);
  const capture = useBrainStore((s) => s.capture);
  const expandTask = useBrainStore((s) => s.expandTask);
  const openNode = useBrainStore((s) => s.openNode);
  const clearError = useBrainStore((s) => s.clearError);
  const setSection = useDomainStore((s) => s.setSection);

  // conversations are kept per project, so switching back doesn't lose the thread
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [text, setText] = useState("");
  const [newName, setNewName] = useState("");
  const [expanded, setExpanded] = useState<Record<string, { id: string; title: string }[]>>({});
  const logRef = useRef<HTMLDivElement>(null);

  const turns = activeId ? threads[activeId] ?? [] : [];

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  /** What the project already knows — the context strip above the composer. */
  const known = useMemo(() => {
    const features = nodes.filter((n) => n.type === "feature").slice(-6).reverse();
    const decisions = nodes.filter((n) => n.type === "decision").slice(-4).reverse();
    return { features, decisions };
  }, [nodes]);

  const send = async () => {
    const t = text.trim();
    if (!t || busy || !activeId) return;
    const pid = activeId;
    const push = (turn: Turn) =>
      setThreads((th) => ({ ...th, [pid]: [...(th[pid] ?? []), turn] }));

    push({ id: "m" + Date.now(), mine: true, text: t });
    setText("");
    const res = await capture(t);
    push({ id: "a" + Date.now(), mine: false, text: "", result: res as CaptureResult });
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
  };

  const doExpand = async (tid: string) => {
    const r = await expandTask(tid);
    if (r?.ok && r.subtasks) setExpanded((m) => ({ ...m, [tid]: r.subtasks }));
  };

  const submitNew = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = newName.trim();
    if (!n) return;
    setNewName("");
    await createProject(n);
  };

  const receipt = (r: CaptureResult) => {
    if (!r.ok) return <p className="brrec__err">{r.error ?? "I couldn't place that."}</p>;

    if (r.kind === "feature" && r.feature) {
      return (
        <div className="brrec">
          <div className="brrec__head">
            <span className="brrec__kind" style={{ color: NODE_META.feature.color }}>
              {NODE_META.feature.icon} {KIND_LABEL.feature}
            </span>
            {r.source && <span className="brrec__src">{r.source}</span>}
          </div>
          <button className="brrec__title" onClick={() => openNode(r.feature!.id)}>
            {r.feature.title}
          </button>
          {r.feature.description && <p className="brrec__desc">{r.feature.description}</p>}
          <div className="brrec__chips">
            <span className="brchip">priority: {r.feature.priority}</span>
            <span className="brchip">{r.feature.category}</span>
          </div>
          {!!r.tasks?.length && (
            <ul className="brrec__tasks">
              {r.tasks.map((t) => (
                <li key={t.id}>
                  <span className="brrec__tick">□</span>
                  <button className="brrec__tasktitle" onClick={() => openNode(t.id)}>
                    {t.title}
                  </button>
                  <button className="brlink brlink--quiet" onClick={() => doExpand(t.id)}>
                    break down
                  </button>
                  {expanded[t.id] && (
                    <ul className="brrec__subs">
                      {expanded[t.id].map((s) => <li key={s.id}>↳ {s.title}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    }

    if (r.kind === "decision" && r.decision) {
      return (
        <div className="brrec">
          <div className="brrec__head">
            <span className="brrec__kind" style={{ color: NODE_META.decision.color }}>
              {NODE_META.decision.icon} {KIND_LABEL.decision}
            </span>
          </div>
          <button className="brrec__title" onClick={() => r.node_id && openNode(r.node_id)}>
            {r.decision.topic ? r.decision.topic + ": " : ""}{r.decision.choice}
          </button>
          {r.decision.reason && <p className="brrec__desc">Because {r.decision.reason}</p>}
        </div>
      );
    }

    if (r.kind === "edit") {
      return (
        <div className="brrec">
          <div className="brrec__head">
            <span className="brrec__kind">✎ {KIND_LABEL.edit}</span>
          </div>
          <p className="brrec__desc">
            {r.old ? <s>{r.old}</s> : null}
            {r.old && r.new ? " → " : null}
            <button className="brrec__tasktitle" onClick={() => r.task_id && openNode(r.task_id)}>
              {r.new ?? "updated"}
            </button>
          </p>
        </div>
      );
    }

    return (
      <div className="brrec">
        <div className="brrec__head">
          <span className="brrec__kind">❝ {KIND_LABEL.note}</span>
        </div>
        <p className="brrec__desc brrec__desc--dim">
          Kept in the project's memory. Ask about it any time.
        </p>
      </div>
    );
  };

  return (
    <div className="brres">
      <header className="brdash__head">
        <div>
          <h2 className="brproj__title">RESEARCH</h2>
          <p className="brproj__sub">
            Pick a project, then just talk about it. Every sentence becomes structure —
            features, decisions, tasks — not chat history.
          </p>
        </div>
        <label className="brtoggle" title="With the model off, extraction falls back to offline heuristics">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          <span>{useLlm ? "model on" : "offline mode"}</span>
        </label>
      </header>

      {!reachable && (
        <div className="brnote brnote--warn">
          The Project Brain isn't answering. Start AURA's server, then reload.
        </div>
      )}
      {error && (
        <div className="brnote brnote--warn">
          {error}
          <button className="brnote__x" onClick={clearError}>✕</button>
        </div>
      )}

      <div className="brres__split">
        {/* ---- the chooser ------------------------------------------------ */}
        <aside className="brres__rail">
          <span className="brpanel__title">PROJECTS</span>
          <div className="brres__list">
            {projects.map((p) => (
              <button
                key={p.id}
                className={"brres__proj" + (p.id === activeId ? " brres__proj--on" : "")}
                onClick={() => select(p.id)}
              >
                <span className="brres__pname">{p.name}</span>
                <span className="brres__pmeta">
                  {p.id === activeId && progress
                    ? `${progress.percent}% · ${progress.total} tasks`
                    : p.root
                      ? p.root.split(/[\\/]/).filter(Boolean).pop()
                      : "no folder"}
                </span>
              </button>
            ))}
            {projects.length === 0 && (
              <p className="brdim brdim--sm">Nothing yet — name one below.</p>
            )}
          </div>

          <form className="brres__new" onSubmit={submitNew}>
            <input
              className="brinput brinput--sm"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="New project…"
            />
            <button className="brbtn" type="submit" disabled={!newName.trim()}>＋</button>
          </form>
          <button className="brlink brlink--quiet" onClick={() => setSection("projects")}>
            Import a folder or repo →
          </button>
        </aside>

        {/* ---- the conversation ------------------------------------------- */}
        <section className="brres__talk">
          {!activeId ? (
            <div className="brempty brempty--big">
              <span className="brempty__icon">✧</span>
              <h3>Choose something to think about</h3>
              <p>
                Pick a project on the left — or name a new one — and start talking. AURA
                keeps the thread per project.
              </p>
            </div>
          ) : (
            <>
              <div className="brstorm__log" ref={logRef}>
                {turns.length === 0 && (
                  <div className="brstorm__seed">
                    <p>Say things the way you'd say them to a teammate:</p>
                    <ul>
                      <li>"The home page should feel like entering space."</li>
                      <li>"Let's use GitHub OAuth for login — developers already have accounts."</li>
                      <li>"Actually make the map 3D instead of flat."</li>
                    </ul>
                  </div>
                )}
                {turns.map((t) =>
                  t.mine ? (
                    <div key={t.id} className="brturn brturn--mine">{t.text}</div>
                  ) : (
                    <div key={t.id} className="brturn">{receipt(t.result!)}</div>
                  )
                )}
                {busy && <div className="brturn brturn--busy">{busy}</div>}
              </div>

              {(known.features.length > 0 || known.decisions.length > 0) && (
                <div className="brres__known">
                  <span className="brres__knownlabel">already known</span>
                  {known.features.map((f) => (
                    <button key={f.id} className="brrel__item" onClick={() => openNode(f.id)}>
                      <span style={{ color: NODE_META.feature.color }}>◆</span> {f.title}
                    </button>
                  ))}
                  {known.decisions.map((d) => (
                    <button key={d.id} className="brrel__item" onClick={() => openNode(d.id)}>
                      <span style={{ color: NODE_META.decision.color }}>⚖</span> {d.title}
                    </button>
                  ))}
                </div>
              )}

              <div className="brstorm__composer">
                <textarea
                  className="brtextarea"
                  value={text}
                  rows={2}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={onKey}
                  placeholder="Say what you're thinking…  (Enter to send, Shift+Enter for a new line)"
                />
                <button className="brbtn brbtn--go" onClick={send} disabled={!text.trim() || !!busy}>
                  Capture
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
