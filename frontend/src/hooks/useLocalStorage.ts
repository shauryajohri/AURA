import { useCallback, useState } from "react";

// Persist a bit of UI state (panel widths, collapse flags) across sessions.
// localStorage is fine here - this is a real Electron renderer, not a sandbox.
export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          /* ignore quota / private-mode errors */
        }
        return resolved;
      });
    },
    [key]
  );

  return [value, set] as const;
}
