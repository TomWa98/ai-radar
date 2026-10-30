import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLanguage } from "../i18n/language";
import {
  fetchArticles,
  type ArticlePage,
  type ArticleParams,
  type Category,
  type SortOrder,
} from "./api";
import { dayBoundary } from "./format";

export const PAGE_SIZE = 25;
/** FR-23: check for changes at least every 60 seconds. */
export const POLL_INTERVAL_MS = 60_000;

export interface ArticleFilters {
  q: string;
  category?: Category;
  minRelevance?: number;
  /** Local calendar days (`YYYY-MM-DD`), inclusive. */
  from?: string;
  to?: string;
  sort: SortOrder;
}

export type ArticlesState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  /** `stale`: the last background update failed; `page` is older data. */
  | { status: "ready"; page: ArticlePage; stale: boolean };

export function toParams(
  filters: ArticleFilters,
  pageIndex: number,
  lang: ArticleParams["lang"],
): ArticleParams {
  return {
    lang,
    q: filters.q.trim() || undefined,
    category: filters.category,
    minRelevance: filters.minRelevance,
    publishedFrom: filters.from ? dayBoundary(filters.from, "start") : undefined,
    publishedTo: filters.to ? dayBoundary(filters.to, "end") : undefined,
    sort: filters.sort,
    limit: PAGE_SIZE,
    offset: pageIndex * PAGE_SIZE,
  };
}

/**
 * Load one page of articles and keep it current.
 *
 * Every `pollInterval` a cheap probe asks the API whether *any* article
 * changed since the last load (`since`, `limit=1`, no filters); only then is
 * the visible page reloaded. While the tab is hidden the probe pauses and it
 * runs immediately when the tab becomes visible again, so polling never stops
 * for good. A failed background update keeps the shown data and marks it
 * stale. A language change only repeats these read requests (no LLM call).
 */
export function useArticles(
  filters: ArticleFilters,
  pageIndex: number,
  pollInterval: number = POLL_INTERVAL_MS,
): { state: ArticlesState; retry: () => void } {
  const { lang } = useLanguage();
  const [state, setState] = useState<ArticlesState>({ status: "loading" });
  // Compare filters by value: callers may pass a new object on every render.
  const filterKey = JSON.stringify(filters);
  const params = useMemo(
    () => toParams(JSON.parse(filterKey) as ArticleFilters, pageIndex, lang),
    [filterKey, pageIndex, lang],
  );
  const since = useRef<string | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const hasData = useRef(false);

  const load = useCallback(
    (background: boolean) => {
      const current = ++generation.current;
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      if (!background) {
        hasData.current = false;
        setState({ status: "loading" });
      }
      fetchArticles(params, abort.signal).then(
        (page) => {
          if (current !== generation.current) return;
          since.current = page.nextSince;
          hasData.current = true;
          setState({ status: "ready", page, stale: false });
        },
        (error: unknown) => {
          if (current !== generation.current || abort.signal.aborted) return;
          if (background && hasData.current) {
            setState((previous) =>
              previous.status === "ready" ? { ...previous, stale: true } : previous,
            );
          } else {
            setState({ status: "error", error });
          }
        },
      );
    },
    [params],
  );

  useEffect(() => {
    since.current = null;
    load(false);
    return () => {
      generation.current++;
      controller.current?.abort();
    };
  }, [load]);

  const check = useCallback(async () => {
    const changedSince = since.current;
    if (changedSince === null || document.visibilityState === "hidden") {
      return;
    }
    try {
      const probe = await fetchArticles({ lang, since: changedSince, limit: 1 });
      if (since.current !== changedSince) return; // a newer load happened
      if (probe.total > 0) {
        load(true);
      } else {
        since.current = probe.nextSince;
        setState((previous) =>
          previous.status === "ready" && previous.stale
            ? { ...previous, stale: false }
            : previous,
        );
      }
    } catch {
      if (since.current !== changedSince) return;
      setState((previous) =>
        previous.status === "ready" ? { ...previous, stale: true } : previous,
      );
    }
  }, [lang, load]);

  useEffect(() => {
    const timer = window.setInterval(() => void check(), pollInterval);
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [check, pollInterval]);

  const retry = useCallback(() => load(false), [load]);
  return { state, retry };
}
