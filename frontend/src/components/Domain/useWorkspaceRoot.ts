import { useEffect } from "react";
import { create } from "zustand";
import { domainApi } from "../../domainApi";

/**
 * The one folder the developer tools operate on.
 *
 * Git, Build, Code and the prompt bar all need to agree on "which project am
 * I in", and asking four times would be absurd. It's persisted in localStorage
 * so the choice survives a restart, and defaults to the first filesystem root
 * the backend reports.
 *
 * Shared, not per-component: opening a repo from Sources has to move Code with
 * it, and a hook holding its own useState would leave each view pointed at a
 * different folder until the next reload.
 */

const KEY = "aura.domain.workspaceRoot";
const LABEL_KEY = "aura.domain.workspaceLabel";

interface WorkspaceStore {
  root: string;
  /** What to call it on screen — a repo's full name, or the folder's name. */
  label: string;
  ready: boolean;
  setRoot: (path: string, label?: string) => void;
  setReady: (ready: boolean) => void;
}

const read = (key: string) => {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
};

const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  root: read(KEY),
  label: read(LABEL_KEY),
  ready: false,
  setRoot: (path, label) => {
    const name = label ?? path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() ?? path;
    try {
      localStorage.setItem(KEY, path);
      localStorage.setItem(LABEL_KEY, name);
    } catch { /* quota */ }
    set({ root: path, label: name, ready: true });
  },
  setReady: (ready) => set({ ready }),
}));

/** Point the whole Domain at a folder from anywhere — including outside React. */
export const setWorkspace = (path: string, label?: string) =>
  useWorkspaceStore.getState().setRoot(path, label);

export function useWorkspaceRoot() {
  const root = useWorkspaceStore((s) => s.root);
  const label = useWorkspaceStore((s) => s.label);
  const ready = useWorkspaceStore((s) => s.ready);
  const setRoot = useWorkspaceStore((s) => s.setRoot);
  const setReady = useWorkspaceStore((s) => s.setReady);

  useEffect(() => {
    if (root || ready) { if (!ready) setReady(true); return; }
    let cancelled = false;
    domainApi.roots()
      .then((r) => {
        if (cancelled) return;
        const first = r.roots?.[0]?.path || "";
        if (first) setRoot(first);
      })
      .catch(() => {})
      .finally(() => !cancelled && setReady(true));
    return () => { cancelled = true; };
  }, [root, ready, setRoot, setReady]);

  return { root, label, setRoot, ready };
}
