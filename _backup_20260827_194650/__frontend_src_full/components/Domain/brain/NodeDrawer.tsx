import { useEffect, useState } from "react";
import {
  NODE_META,
  TASK_META,
  brainApi,
  whenLabel,
  type AskResult,
  type RelatedResult,
  type TaskState,
  type WhyResult,
} from "../../../brainApi";
import { nodeById, useBrainStore } from "../../../stores/brainStore";

// ============================================================================
// Modules 5 + 9 — Project Memory and "Ask about anything".
//
// One drawer, opened from anywhere (graph, board, timeline, brainstorm receipt).
// It answers three questions about whatever you clicked:
//   why does this exist   → the causal chain back to the originating idea
//   what touches it       → one-hop neighbours grouped by relation
//   anything else         → a grounded question, answered from the graph only
// ============================================================================

const REL_LABEL: Record<string, string> = {
  led_to: "Came from / led to",
  belongs_to: "Belongs to",
  implements: "Implemented by",
  affects: "Affects",
  completes: "Completed by",
  depends_on: "Depends on",
  rejected_alt: "Rejected alternative",
  relates_to: "Related",
  authored: "Authored",
};

export default function NodeDrawer() {
  const pid = useBrainStore((s) => s.activeId);
  const nid = useBrainStore((s) => s.openNodeId);
  const nodes = useBrainStore((s) => s.nodes);
  const openNode = useBrainStore((s) => s.openNode);
  const setTaskStatus = useBrainStore((s) => s.setTaskStatus);
  const expandTask = useBrainStore((s) => s.expandTask);
  const useLlm = useBrainStore((s) => s.useLlm);

  const [why, setWhy] = useState<WhyResult | null>(null);
  const [rel, setRel] = useState<RelatedResult | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answers, setAnswers] = useState<{ q: string; a: AskResult }[]>([]);

  const node = nodeById(nodes, nid);

  useEffect(() => {
    if (!pid || !nid) { setWhy(null); setRel(null); setAnswers([]); return; }
    setAnswers([]);
    let dead = false;
    void brainApi.why(pid, nid).then((r) => !dead && setWhy(r)).catch(() => {});
    void brainApi.related(pid, nid).then((r) => !dead && setRel(r)).catch(() => {});
    return () => { dead = true; };
  }, [pid, nid]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && openNode(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openNode]);

  if (!nid || !pid) return null;

  const meta = node ? NODE_META[node.type] : NODE_META.idea;

  const ask = async () => {
    const q = question.trim();
    if (!q) return;
    setQuestion("");
    setAsking(true);
    try {
      const a = await brainApi.ask(pid, nid, q, useLlm);
      setAnswers((xs) => [...xs, { q, a }]);
    } catch {
      setAnswers((xs) => [...xs, { q, a: { ok: false, error: "brain offline" } }]);
    }
    setAsking(false);
  };

  return (
    <div className="brdrawer__backdrop" onClick={() => openNode(null)}>
      <aside className="brdrawer" onClick={(e) => e.stopPropagation()}>
        <header className="brdrawer__head">
          <span className="brdrawer__type" style={{ color: meta.color }}>
            {meta.icon} {meta.label}
          </span>
          <button className="brdrawer__x" onClick={() => openNode(null)}>✕</button>
        </header>

        <h3 className="brdrawer__title">{node?.title ?? why?.node?.title ?? nid}</h3>
        <div className="brdrawer__meta">
          {node?.status && <span className="brchip">{node.status}</span>}
          {node?.meta?.priority && <span className="brchip">priority: {node.meta.priority}</span>}
          {node?.meta?.category && <span className="brchip">{node.meta.category}</span>}
          {node?.created_at && <span className="brdrawer__when">{whenLabel(node.created_at)}</span>}
        </div>

        {node?.body && <p className="brdrawer__body">{node.body}</p>}

        {/* ---- task controls -------------------------------------------- */}
        {node?.type === "task" && (
          <section className="brdrawer__sec">
            <h4>Status</h4>
            <div className="brstates">
              {(Object.keys(TASK_META) as TaskState[])
                .filter((s) => s !== "planning")
                .map((s) => (
                  <button
                    key={s}
                    className={"brstate" + (node.status === s ? " brstate--on" : "")}
                    style={node.status === s ? { borderColor: TASK_META[s].color, color: TASK_META[s].color } : undefined}
                    onClick={() => setTaskStatus(node.id, s)}
                  >
                    {TASK_META[s].label}
                  </button>
                ))}
            </div>
            <button className="brlink" onClick={() => expandTask(node.id)}>
              Break this down into subtasks
            </button>
          </section>
        )}

        {/* ---- why (Module 5) ------------------------------------------- */}
        <section className="brdrawer__sec">
          <h4>Why this exists</h4>
          {!why && <p className="brdim">reading the chain…</p>}
          {why && !why.ok && <p className="brdim">{why.error}</p>}
          {why?.ok && (
            <>
              <ol className="brchain">
                {(why.chain ?? []).map((c) => (
                  <li key={c.id}>
                    <button className="brchain__link" onClick={() => openNode(c.id)}>
                      <span style={{ color: NODE_META[c.type].color }}>{NODE_META[c.type].icon}</span>{" "}
                      {c.title}
                    </button>
                    {c.meta?.reason && <span className="brchain__reason"> — {c.meta.reason}</span>}
                  </li>
                ))}
              </ol>
              {(why.chain ?? []).length === 0 && (
                <p className="brdim">{why.narrative}</p>
              )}
              {!!why.rejected_alternatives?.length && (
                <p className="brdim">
                  Rejected: {why.rejected_alternatives.join(", ")}
                </p>
              )}
            </>
          )}
        </section>

        {/* ---- related ------------------------------------------------- */}
        <section className="brdrawer__sec">
          <h4>Connected</h4>
          {!rel && <p className="brdim">looking…</p>}
          {rel && Object.keys(rel.related ?? {}).length === 0 && (
            <p className="brdim">Nothing linked yet.</p>
          )}
          {Object.entries(rel?.related ?? {}).map(([type, items]) => (
            <div key={type} className="brrel">
              <span className="brrel__label">{REL_LABEL[type] ?? type}</span>
              <div className="brrel__items">
                {items.map((it) => (
                  <button key={it.id} className="brrel__item" onClick={() => openNode(it.id)}>
                    <span style={{ color: NODE_META[it.type].color }}>{NODE_META[it.type].icon}</span>{" "}
                    {it.title}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>

        {/* ---- ask anything (Module 9) --------------------------------- */}
        <section className="brdrawer__sec">
          <h4>Ask about this</h4>
          <div className="brask">
            <input
              className="brinput brinput--sm"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="Why did we build this? What's left?"
            />
            <button className="brbtn" onClick={ask} disabled={asking || !question.trim()}>
              {asking ? "…" : "Ask"}
            </button>
          </div>
          {answers.map((x, i) => (
            <div key={i} className="brans">
              <p className="brans__q">{x.q}</p>
              <p className="brans__a">{x.a.answer ?? x.a.error}</p>
              {x.a.source === "context-only" && (
                <span className="brans__src">answered from the graph (model offline)</span>
              )}
            </div>
          ))}
        </section>
      </aside>
    </div>
  );
}
