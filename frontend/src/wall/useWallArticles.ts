import { useEffect, useState } from "react";
import { fetchArticles, type Article } from "../articles/api";
import { useLanguage } from "../i18n/language";
import { MAX_ARTICLES, POLL_INTERVAL_MS } from "./rules";

export type WallState =
  | { status: "loading" }
  /** Nothing to show yet; the next poll tries again. */
  | { status: "error" }
  /** `stale`: the last update failed; `articles` are from `updatedAt`. */
  | { status: "ready"; articles: Article[]; updatedAt: number; stale: boolean };

/**
 * Keep the wall's articles current without any user action: the list is
 * reloaded every `pollInterval`. Unlike the dashboard there is no retry button,
 * so every failure, including the first load, is retried by the next poll.
 * Failed updates keep the last data. There is no request timeout, so a request
 * still open at the next poll counts as failed and is replaced.
 */
export function useWallArticles(
  minRelevance: number,
  pollInterval: number = POLL_INTERVAL_MS,
): WallState {
  const { lang } = useLanguage();
  const [state, setState] = useState<WallState>({ status: "loading" });

  useEffect(() => {
    let inFlight: AbortController | null = null;

    const markFailed = () =>
      setState((previous) =>
        previous.status === "ready" ? { ...previous, stale: true } : { status: "error" },
      );

    const load = () => {
      const abort = new AbortController();
      inFlight = abort;
      fetchArticles(
        { lang, minRelevance, sort: "relevance", limit: MAX_ARTICLES },
        abort.signal,
      ).then(
        (page) => {
          if (abort.signal.aborted) return;
          inFlight = null;
          setState({
            status: "ready",
            articles: page.items.filter((article) => article.analysis !== null),
            updatedAt: Date.now(),
            stale: false,
          });
        },
        () => {
          if (abort.signal.aborted) return;
          inFlight = null;
          markFailed();
        },
      );
    };

    const poll = () => {
      if (inFlight) {
        inFlight.abort();
        markFailed();
      }
      load();
    };

    // Browsers throttle timers in hidden tabs: catch up on return.
    const onVisible = () => {
      if (document.visibilityState === "visible" && !inFlight) load();
    };

    setState({ status: "loading" });
    load();
    const timer = window.setInterval(poll, pollInterval);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      inFlight?.abort();
    };
  }, [lang, minRelevance, pollInterval]);

  return state;
}
