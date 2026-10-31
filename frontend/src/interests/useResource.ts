import { useCallback, useEffect, useRef, useState } from "react";
import type { QueryState } from "../api/useLocalizedQuery";

export interface Resource<T> {
  state: QueryState<T>;
  /** Load again, showing the loading state. */
  reload: () => void;
  /**
   * Load again in the background: the current data stays shown and is
   * replaced only by a successful answer; a failure keeps it.
   */
  revalidate: () => void;
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

  const background = useRef<AbortController | null>(null);
  useEffect(() => () => background.current?.abort(), []);
  const revalidate = useCallback(() => {
    background.current?.abort();
    const controller = new AbortController();
    background.current = controller;
    load(controller.signal).then(
      (data) =>
        setState((current) =>
          current.status === "success" && !controller.signal.aborted
            ? { status: "success", data }
            : current,
        ),
      () => {
        // Keep showing the current data.
      },
    );
  }, [load]);
  const update = useCallback(
    (change: (data: T) => T) =>
      setState((current) =>
        current.status === "success" ? { status: "success", data: change(current.data) } : current,
      ),
    [],
  );
  return { state, reload, revalidate, update };
}
