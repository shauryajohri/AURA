import { useCallback, useEffect, useState } from "react";
import { domainApi, type FsEntry } from "../../../domainApi";
import { fileIcon } from "./icons";

// ============================================================================
// Explorer tree — VS Code's multi-root model.
//
// Each folder you picked into the working set is a root, expandable in place.
// Children load lazily on first expand and are cached, so reopening a folder
// is instant. Expansion state is keyed by path and survives switching views.
// ============================================================================

interface Props {
  root: { path: string; name: string; dir: boolean };
  activePath: string | null;
  expanded: Set<string>;
  onToggleExpand: (path: string) => void;
  onOpenFile: (e: { path: string; name: string }) => void;
  onContext: (e: React.MouseEvent, entry: { path: string; name: string; dir: boolean }) => void;
  depth?: number;
  refreshToken?: number;
}

export default function FileTree({
  root, activePath, expanded, onToggleExpand, onOpenFile, onContext,
  depth = 0, refreshToken = 0,
}: Props) {
  const [kids, setKids] = useState<FsEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const open = expanded.has(root.path);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await domainApi.list(root.path, false);
    setLoading(false);
    if (!r.ok) { setErr(r.error ?? "unreadable"); setKids([]); return; }
    setErr("");
    setKids(r.entries);
  }, [root.path]);

  // load on first expand, and again whenever the tree is told to refresh
  useEffect(() => {
    if (open && (kids === null || refreshToken > 0)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, refreshToken]);

  if (!root.dir) {
    return (
      <button
        className={"vsc-tree__row" + (activePath === root.path ? " vsc-tree__row--on" : "")}
        style={{ paddingLeft: 8 + depth * 11 }}
        onClick={() => onOpenFile(root)}
        onContextMenu={(e) => onContext(e, root)}
        title={root.path}
      >
        <span className="vsc-tree__ico">{fileIcon(root.name)}</span>
        <span className="vsc-tree__name">{root.name}</span>
      </button>
    );
  }

  return (
    <>
      <button
        className={"vsc-tree__row vsc-tree__row--dir" + (open ? " is-open" : "")}
        style={{ paddingLeft: 4 + depth * 11 }}
        onClick={() => onToggleExpand(root.path)}
        onContextMenu={(e) => onContext(e, root)}
        title={root.path}
      >
        <span className="vsc-tree__chev">{open ? "⌄" : "›"}</span>
        <span className="vsc-tree__ico">{open ? "📂" : "📁"}</span>
        <span className="vsc-tree__name">{root.name}</span>
      </button>

      {open && loading && kids === null && (
        <div className="vsc-tree__hint" style={{ paddingLeft: 22 + depth * 11 }}>loading…</div>
      )}
      {open && err && (
        <div className="vsc-tree__hint vsc-tree__hint--err" style={{ paddingLeft: 22 + depth * 11 }}>
          {err}
        </div>
      )}
      {open && kids?.length === 0 && !err && (
        <div className="vsc-tree__hint" style={{ paddingLeft: 22 + depth * 11 }}>empty</div>
      )}

      {open &&
        kids?.map((k) => (
          <FileTree
            key={k.path}
            root={{ path: k.path, name: k.name, dir: k.dir }}
            activePath={activePath}
            expanded={expanded}
            onToggleExpand={onToggleExpand}
            onOpenFile={onOpenFile}
            onContext={onContext}
            depth={depth + 1}
            refreshToken={refreshToken}
          />
        ))}
    </>
  );
}
