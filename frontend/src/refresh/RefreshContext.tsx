import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "../api/client";
import { fetchRefreshStatus, startRefresh, type RefreshStatus } from "../sources/api";

/** How often `GET /api/refresh` is polled while idle and while a refresh runs. */
export const IDLE_POLL_MS = 60_000;
export const RUNNING_POLL_MS = 3_000;

export type StartResult = "started" | "conflict" | "failed";

interface RefreshContextValue {
  /** Last status from the API, or `null` before the first answer. */
  status: RefreshStatus | null;
  /** The last status request failed; `status` may be outdated. */
  failed: boolean;
  /** `POST /api/refresh`; a running refresh (409) resolves to "conflict". */
  start: () => Promise<StartResult>;
}

const RefreshContext = createContext<RefreshContextValue | null>(null);

interface RefreshProviderProps {
  children: ReactNode;
  idlePollMs?: number;
  runningPollMs?: number;
}

/**
 * Shares the refresh status between the top bar and the Sources view. The
 * status comes only from `GET /api/refresh` (no simulated progress); it is
 * polled more often while a refresh runs.
 */
export function RefreshProvider({
  children,
  idlePollMs = IDLE_POLL_MS,
  runningPollMs = RUNNING_POLL_MS,
}: RefreshProviderProps) {
  const [state, setState] = useState<{ status: RefreshStatus | null; failed: boolean }>({
    status: null,
    failed: false,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchRefreshStatus(controller.signal).then(
      (status) => setState({ status, failed: false }),
      () => {
        if (!controller.signal.aborted) {
          setState((current) => ({ ...current, failed: true }));
        }
      },
    );
    return () => controller.abort();
  }, [attempt]);

  // Each answer (a new `state` object) schedules the next poll.
  const running = state.status?.running ?? false;
  useEffect(() => {
    const timer = window.setTimeout(
      () => setAttempt((count) => count + 1),
      running ? runningPollMs : idlePollMs,
    );
    return () => window.clearTimeout(timer);
  }, [state, running, idlePollMs, runningPollMs]);

  const start = useCallback(async (): Promise<StartResult> => {
    let result: StartResult;
    try {
      await startRefresh();
      result = "started";
    } catch (error) {
      result = error instanceof ApiError && error.status === 409 ? "conflict" : "failed";
    }
    if (result !== "failed") {
      // Show "running" right away; the status request below confirms it.
      setState((current) => ({
        ...current,
        status: {
          lastStartedAt: current.status?.lastStartedAt ?? null,
          lastFinishedAt: current.status?.lastFinishedAt ?? null,
          running: true,
        },
      }));
    }
    setAttempt((count) => count + 1);
    return result;
  }, []);

  const value = useMemo(
    () => ({ status: state.status, failed: state.failed, start }),
    [state, start],
  );
  return <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>;
}

export function useRefresh(): RefreshContextValue {
  const value = useContext(RefreshContext);
  if (!value) {
    throw new Error("useRefresh must be used inside a RefreshProvider");
  }
  return value;
}
