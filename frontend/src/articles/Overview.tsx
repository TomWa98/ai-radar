import { useEffect, useRef, useState, type RefObject } from "react";
import { ApiError } from "../api/client";
import { fill } from "../i18n/dictionaries";
import { useLanguage } from "../i18n/language";
import { ArticleCard } from "./ArticleCard";
import { ArticleFilters } from "./ArticleFilters";
import {
  PAGE_SIZE,
  useArticles,
  type ArticleFilters as Filters,
  type ArticlesState,
} from "./useArticles";

const NO_FILTERS: Filters = { q: "", sort: "recent" };

function filtersActive(filters: Filters): boolean {
  return Boolean(
    filters.q.trim() || filters.category || filters.minRelevance || filters.from || filters.to,
  );
}

/**
 * Overview: the Editorial Grid (docs/frontend-design.md, 4). On the first
 * page the first article of the chosen sort order is the lead story.
 */
export function Overview({ pollInterval }: { pollInterval?: number }) {
  const { t } = useLanguage();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(0);
  const { state, retry } = useArticles(filters, page, pollInterval);
  // Remount the form on reset so its draft fields clear as well.
  const [formKey, setFormKey] = useState(0);
  // After a page change, focus moves to the result count once the new page
  // is shown, so keyboard users keep their place (the Next/Previous button
  // may become disabled).
  const countRef = useRef<HTMLParagraphElement>(null);
  const focusAfterPageChange = useRef(false);

  useEffect(() => {
    if (focusAfterPageChange.current && state.status !== "loading") {
      focusAfterPageChange.current = false;
      countRef.current?.focus();
      countRef.current?.scrollIntoView?.({ block: "start" });
    }
  }, [state]);

  function changePage(next: number) {
    focusAfterPageChange.current = true;
    setPage(next);
  }

  function apply(next: Filters) {
    setFilters(next);
    setPage(0);
  }

  function reset() {
    apply({ ...NO_FILTERS, sort: filters.sort });
    setFormKey((key) => key + 1);
  }

  return (
    <section className="overview" aria-labelledby="overview-title">
      <div className="overview__header">
        <h1 id="overview-title">{t.overview.title}</h1>
        <p className="overview__intro">{t.overview.intro}</p>
      </div>
      <ArticleFilters key={formKey} value={filters} onChange={apply} />
      <Results
        state={state}
        page={page}
        filtered={filtersActive(filters)}
        countRef={countRef}
        onPage={changePage}
        onRetry={retry}
        onReset={reset}
      />
    </section>
  );
}

interface ResultsProps {
  state: ArticlesState;
  page: number;
  filtered: boolean;
  countRef: RefObject<HTMLParagraphElement | null>;
  onPage: (page: number) => void;
  onRetry: () => void;
  onReset: () => void;
}

function Results({ state, page, filtered, countRef, onPage, onRetry, onReset }: ResultsProps) {
  const { t } = useLanguage();

  if (state.status === "loading") {
    return (
      <p className="results__message" role="status">
        {t.overview.loading}
      </p>
    );
  }

  if (state.status === "error") {
    // 422 details come from the API's input validation and are plain text.
    const detail =
      state.error instanceof ApiError && state.error.status === 422 ? state.error.message : null;
    return (
      <div className="results__message results__message--error" role="alert">
        <p>{t.overview.error}</p>
        {detail && <p className="results__detail">{detail}</p>}
        <button type="button" className="button" onClick={onRetry}>
          {t.overview.retry}
        </button>
      </div>
    );
  }

  const { items, total } = state.page;
  if (total === 0 || items.length === 0) {
    return filtered ? (
      <div className="results__message" role="status">
        <p>{t.overview.noResults}</p>
        <button type="button" className="button" onClick={onReset}>
          {t.overview.resetFilters}
        </button>
      </div>
    ) : (
      <div className="results__message" role="status">
        <h2>{t.overview.emptyTitle}</h2>
        <p>{t.overview.emptyText}</p>
      </div>
    );
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const [lead, ...rest] = page === 0 ? items : [undefined, ...items];

  return (
    <>
      <div className="results__bar">
        <p className="results__count" role="status" tabIndex={-1} ref={countRef}>
          {total === 1 ? t.overview.countOne : fill(t.overview.count, { count: total })}
        </p>
        {state.stale && (
          <p className="results__stale" role="status">
            {t.overview.stale}
          </p>
        )}
      </div>
      {lead && <ArticleCard article={lead} lead />}
      {rest.length > 0 && (
        <ul className="grid" aria-label={t.overview.title}>
          {rest.map((article) =>
            article ? (
              <li key={article.id}>
                <ArticleCard article={article} />
              </li>
            ) : null,
          )}
        </ul>
      )}
      {pages > 1 && (
        <nav className="pagination" aria-label={t.overview.pages}>
          <button
            type="button"
            className="button"
            disabled={page === 0}
            onClick={() => onPage(page - 1)}
          >
            {t.overview.previous}
          </button>
          <span>{fill(t.overview.pageOf, { page: page + 1, pages })}</span>
          <button
            type="button"
            className="button"
            disabled={page + 1 >= pages}
            onClick={() => onPage(page + 1)}
          >
            {t.overview.next}
          </button>
        </nav>
      )}
    </>
  );
}
