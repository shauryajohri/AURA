import { useMemo, useRef, useState } from "react";
import { NODE_META, type NodeType } from "../../../brainApi";
import { useBrainStore } from "../../../stores/brainStore";
import NoProject from "./NoProject";

// ============================================================================
// Module 12 — the Knowledge Graph.
//
// Layout is deliberately layered rather than a physics blob: the columns ARE
// the lifecycle (idea → discussion → decision → feature → task → commit →
// file), so left-to-right reading order tells the story of how a thought became
// shipped code. A force simulation looks impressive and explains nothing.
//
// Zero dependencies: plain SVG, wheel to zoom, drag to pan, click to open the
// node drawer. Large columns are capped so a repo with 500 commits still opens.
// ============================================================================

const ORDER: NodeType[] = [
  "project", "idea", "discussion", "decision", "feature",
  "task", "milestone", "test", "commit", "file",
];

const COL_W = 208;
const ROW_H = 46;
const TOP = 54;
const CAP = 40;          // per column, before "+N more"

export default function GraphView() {
  const activeId = useBrainStore((s) => s.activeId);
  const nodes = useBrainStore((s) => s.nodes);
  const edges = useBrainStore((s) => s.edges);
  const openNode = useBrainStore((s) => s.openNode);

  const [hidden, setHidden] = useState<Set<NodeType>>(new Set(["file"]));
  const [showAll, setShowAll] = useState<Set<NodeType>>(new Set());
  const [hover, setHover] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  const present = useMemo(() => {
    const set = new Set<NodeType>();
    for (const n of nodes) set.add(n.type);
    return ORDER.filter((t) => set.has(t));
  }, [nodes]);

  const layout = useMemo(() => {
    const cols = present.filter((t) => !hidden.has(t));
    const pos: Record<string, { x: number; y: number; type: NodeType; title: string }> = {};
    const overflow: Partial<Record<NodeType, number>> = {};
    cols.forEach((type, ci) => {
      const all = nodes.filter((n) => n.type === type);
      const limit = showAll.has(type) ? all.length : CAP;
      if (all.length > limit) overflow[type] = all.length - limit;
      all.slice(0, limit).forEach((n, ri) => {
        pos[n.id] = { x: ci * COL_W + 90, y: TOP + ri * ROW_H, type, title: n.title };
      });
    });
    const height = Math.max(
      ...cols.map((t) => {
        const c = nodes.filter((n) => n.type === t).length;
        return TOP + Math.min(showAll.has(t) ? c : Math.min(c, CAP), c) * ROW_H;
      }),
      320
    );
    return { cols, pos, overflow, width: Math.max(cols.length * COL_W + 120, 640), height: height + 40 };
  }, [nodes, present, hidden, showAll]);

  const visibleEdges = useMemo(
    () => edges.filter((e) => layout.pos[e.src] && layout.pos[e.dst]),
    [edges, layout]
  );

  const neighbours = useMemo(() => {
    if (!hover) return null;
    const s = new Set<string>([hover]);
    for (const e of visibleEdges) {
      if (e.src === hover) s.add(e.dst);
      if (e.dst === hover) s.add(e.src);
    }
    return s;
  }, [hover, visibleEdges]);

  if (!activeId) return <NoProject what="explore the knowledge graph" />;

  const toggleType = (t: NodeType) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(t)) n.delete(t); else n.add(t);
      return n;
    });

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.min(2.4, Math.max(0.35, z * (e.deltaY > 0 ? 0.9 : 1.1))));
  };
  const onDown = (e: React.MouseEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
  };
  const onMove = (e: React.MouseEvent) => {
    const d = drag.current;
    if (!d) return;
    setPan({ x: d.px + (e.clientX - d.x), y: d.py + (e.clientY - d.y) });
  };
  const onUp = () => { drag.current = null; };

  return (
    <div className="brgraph">
      <header className="brdash__head">
        <div>
          <h2 className="brproj__title">KNOWLEDGE GRAPH</h2>
          <p className="brproj__sub">
            {nodes.length} nodes · {edges.length} links. Left to right is the lifecycle:
            an idea becomes a decision, a feature, tasks, then commits and files.
          </p>
        </div>
        <div className="brdash__acts">
          <button className="brbtn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset view</button>
        </div>
      </header>

      <div className="brgraph__legend">
        {present.map((t) => (
          <button
            key={t}
            className={"brlegend" + (hidden.has(t) ? " brlegend--off" : "")}
            style={{ borderColor: NODE_META[t].color }}
            onClick={() => toggleType(t)}
            title={hidden.has(t) ? "Show " + NODE_META[t].label : "Hide " + NODE_META[t].label}
          >
            <span style={{ color: NODE_META[t].color }}>{NODE_META[t].icon}</span>
            {NODE_META[t].label}
            <span className="brdim">{nodes.filter((n) => n.type === t).length}</span>
          </button>
        ))}
      </div>

      {nodes.length === 0 ? (
        <p className="brdim">
          The graph is empty. Import a folder or say something in Brainstorm and it fills in.
        </p>
      ) : (
        <div
          className="brgraph__stage"
          onWheel={onWheel}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
        >
          <svg
            className="brgraph__svg"
            width="100%"
            height="100%"
            viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${layout.width / zoom} ${layout.height / zoom}`}
            preserveAspectRatio="xMinYMin meet"
          >
            {/* column headers */}
            {layout.cols.map((t, ci) => (
              <text
                key={t}
                x={ci * COL_W + 90}
                y={26}
                className="brgraph__colhead"
                fill={NODE_META[t].color}
              >
                {NODE_META[t].label.toUpperCase()}
              </text>
            ))}

            {/* edges */}
            {visibleEdges.map((e) => {
              const a = layout.pos[e.src];
              const b = layout.pos[e.dst];
              const dim = neighbours && !(neighbours.has(e.src) && neighbours.has(e.dst));
              const mx = (a.x + b.x) / 2;
              return (
                <path
                  key={e.id}
                  d={`M ${a.x} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x} ${b.y}`}
                  className={"brgraph__edge" + (dim ? " brgraph__edge--dim" : "")}
                />
              );
            })}

            {/* nodes */}
            {Object.entries(layout.pos).map(([id, p]) => {
              const dim = neighbours && !neighbours.has(id);
              return (
                <g
                  key={id}
                  className={"brgraph__node" + (dim ? " brgraph__node--dim" : "")}
                  onMouseEnter={() => setHover(id)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => openNode(id)}
                >
                  <circle cx={p.x} cy={p.y} r={6} fill={NODE_META[p.type].color} />
                  <text x={p.x + 12} y={p.y + 4} className="brgraph__label">
                    {p.title.length > 26 ? p.title.slice(0, 25) + "…" : p.title}
                  </text>
                </g>
              );
            })}

            {/* overflow notes */}
            {layout.cols.map((t, ci) =>
              layout.overflow[t] ? (
                <text
                  key={"o" + t}
                  x={ci * COL_W + 90}
                  y={TOP + CAP * ROW_H + 18}
                  className="brgraph__more"
                  onClick={() => setShowAll((s) => new Set(s).add(t))}
                >
                  +{layout.overflow[t]} more — show all
                </text>
              ) : null
            )}
          </svg>
        </div>
      )}
    </div>
  );
}
