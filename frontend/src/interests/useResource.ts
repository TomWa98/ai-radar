import { useCallback, useEffect, useState } from "react";
import type { QueryState } from "../api/useLocalizedQuery";

export interface Resource<T> {
  state: QueryState<T>;
  /** Load again, showing the loading state. */
  reload: () => void;
  /** Replace the loaded data, e.g. after a successful change. */
  update: (change: (data: T) => T) => void;
}

/**
 * Load language-independent data once, with a manual reload. Callers must
 * keep `load` stable (e.g. module-level or useCallback).
 */
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const [state, setState] = useState<QueryState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    load(controller.signal).then(
      (data) => setState({ status: "success", data }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: "error", error });
        }
      },
    );
    return () => controller.abort();
  }, [load, attempt]);

  const reload = useCallback(() => setAttempt((count) => count + 1), []);
  const update = useCallback(
    (change: (data: T) => T) =>
      setState((current) =>
        current.status === "success" ? { status: "success", data: change(current.data) } : current,
      ),
    [],
  );
  return { state, reload, update };
}
