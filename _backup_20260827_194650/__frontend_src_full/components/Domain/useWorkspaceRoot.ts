import { useCallback, useEffect, useState } from "react";
import { domainApi } from "../../domainApi";

/**
 * The one folder the developer tools operate on.
 *
 * Git, Build, Debug and Preview all need to agree on "which project am I in",
 * and asking four times would be absurd. It's persisted in localStorage so the
 * choice survives a restart, and defaults to the first filesystem root the
 * backend reports (usually the user's home / last project).
 */

const KEY = "aura.domain.workspaceRoot";

export function useWorkspaceRoot() {
  const [root, setRootState] = useState<string>(() => localStorage.getItem(KEY) || "");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (root) { setReady(true); return; }
    let cancelled = false;
    domainApi.roots()
      .then((r) => {
        if (cancelled) return;
        const first = r.roots?.[0]?.path || "";
        if (first) {
          setRootState(first);
          try { localStorage.setItem(KEY, first); } catch { /* quota */ }
        }
      })
      .catch(() => {})
      .finally(() => !cancelled && setReady(true));
    return () => { cancelled = true; };
  }, [root]);

  const setRoot = useCallback((p: string) => {
    setRootState(p);
    try { localStorage.setItem(KEY, p); } catch { /* quota */ }
  }, []);

  return { root, setRoot, ready };
}
