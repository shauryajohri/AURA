import { useEffect, useMemo, useRef, useState } from "react";
import { domainApi, type FsEntry } from "../../../domainApi";
import { fileIcon } from "./icons";

// ============================================================================
// Quick Open (Ctrl+P) — fuzzy jump to any file in the working set.
//
// Open editors match instantly from memory; folder roots are searched on the
// backend, debounced. Ranking prefers a filename hit over a path hit, and an
// earlier hit over a later one — the same instinct VS Code has.
// ============================================================================

export interface QuickItem {
  path: string;
  name: string;
  hint?: string;
  open?: boolean;
}

interface Props {
  roots: { path: string; name: string; dir: boolean }[];
  openTabs: { path: string; name: string }[];
  onPick: (item: { path: string; name: string }) => void;
  onClose: () => void;
}

/** Subsequence match — "dsp" hits "DomainScreen.tsx". Returns a score or -1. */
function fuzzy(needle: string, hay: string): number {
  if (!needle) return 0;
  const n = needle.toLowerCase();
  const h = hay.toLowerCase();
  const direct = h.indexOf(n);
  if (direct !== -1) return 1000 - direct * 2;   // contiguous always wins
  let score = 0;
  let hi = 0;
  let streak = 0;
  for (const ch of n) {
    const found = h.indexOf(ch, hi);
    if (found === -1) return -1;
    streak = found === hi ? streak + 1 : 0;
    score += 10 + streak * 4 - Math.min(found - hi, 12);
    hi = found + 1;
  }
  return score;
}

export default function QuickOpen({ roots, openTabs, onPick, onClose }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<FsEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // search the folder roots, debounced
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setHits([]); return; }
    let alive = true;
    setBusy(true);
    const t = setTimeout(async () => {
      const folders = roots.filter((r) => r.dir);
      const results = await Promise.all(
        folders.map((r) => domainApi.searchFiles(r.path, term).catch(() => ({ ok: false, hits: [] })))
      );
      if (!alive) return;
      const merged: FsEntry[] = [];
      const seen = new Set<string>();
      for (const res of results)
        for (const h of (res as { hits?: FsEntry[] }).hits ?? [])
          if (!seen.has(h.path)) { seen.add(h.path); merged.push(h); }
      setHits(merged);
      setBusy(false);
    }, 160);
    return () => { alive = false; clearTimeout(t); setBusy(false); };
  }, [q, roots]);

  const items = useMemo(() => {
    const pool: QuickItem[] = [
      ...openTabs.map((t) => ({ path: t.path, name: t.name, hint: "open", open: true })),
      ...roots.filter((r) => !r.dir).map((r) => ({ path: r.path, name: r.name, hint: "pinned" })),
      ...hits.map((h) => ({ path: h.path, name: h.name })),
    ];
    const seen = new Set<string>();
    const unique = pool.filter((p) => (seen.has(p.path) ? false : (seen.add(p.path), true)));

    if (!q.trim()) return unique.slice(0, 40);

    return unique
      .map((it) => {
        const nameScore = fuzzy(q.trim(), it.name);
        const pathScore = fuzzy(q.trim(), it.path);
        const score = Math.max(nameScore * 2, pathScore) + (it.open ? 40 : 0);
        return { it, score: nameScore === -1 && pathScore === -1 ? -1 : score };
      })
      .filter((x) => x.score >= 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 40)
      .map((x) => x.it);
  }, [q, hits, openTabs, roots]);

  useEffect(() => setSel(0), [q]);

  useEffect(() => {
    const el = listRef.current?.children[sel] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter") {
      e.preventDefault();
      const it = items[sel];
      if (it) { onPick(it); onClose(); }
    }
  };

  const dirOf = (p: string) => {
    const parts = p.split(/[\\/]/).filter(Boolean);
    return parts.slice(Math.max(0, parts.length - 3), -1).join("/");
  };

  return (
    <div className="vsc-qo__backdrop" onMouseDown={onClose}>
      <div className="vsc-qo" onMouseDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          placeholder="Go to file…  (type part of a name)"
        />
        <div className="vsc-qo__list" ref={listRef}>
          {items.length === 0 && (
            <div className="vsc-qo__none">
              {busy ? "searching…" : q.trim().length < 2 ? "Type at least two characters." : "No matching file."}
            </div>
          )}
          {items.map((it, i) => (
            <button
              key={it.path}
              className={"vsc-qo__item" + (i === sel ? " vsc-qo__item--on" : "")}
              onMouseEnter={() => setSel(i)}
              onClick={() => { onPick(it); onClose(); }}
            >
              <span className="vsc-qo__ico">{fileIcon(it.name)}</span>
              <span className="vsc-qo__name">{it.name}</span>
              <span className="vsc-qo__dir">{dirOf(it.path)}</span>
              {it.hint && <span className="vsc-qo__hint">{it.hint}</span>}
            </button>
          ))}
        </div>
        <div className="vsc-qo__foot">
          <span>↑↓ navigate</span><span>⏎ open</span><span>esc dismiss</span>
          {busy && <span className="vsc-qo__busy">searching…</span>}
        </div>
      </div>
    </div>
  );
}
