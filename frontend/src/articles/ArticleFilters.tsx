import { useId, useState, type FormEvent } from "react";
import { useLanguage } from "../i18n/language";
import { CATEGORIES, type Category, type SortOrder } from "./api";
import { categoryLabel } from "./categories";
import type { ArticleFilters as Filters } from "./useArticles";

interface Props {
  value: Filters;
  onChange: (filters: Filters) => void;
}

export const MAX_SEARCH_LENGTH = 200;

/**
 * Search, filters, and sort order. Selects apply immediately; the search
 * applies on submit; a period applies only when it is valid.
 */
export function ArticleFilters({ value, onChange }: Props) {
  const { t } = useLanguage();
  const id = useId();
  const [query, setQuery] = useState(value.q);
  const [from, setFrom] = useState(value.from ?? "");
  const [to, setTo] = useState(value.to ?? "");
  const invalidPeriod = from !== "" && to !== "" && from > to;

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    onChange({ ...value, q: query });
  }

  function changePeriod(nextFrom: string, nextTo: string) {
    setFrom(nextFrom);
    setTo(nextTo);
    if (nextFrom === "" || nextTo === "" || nextFrom <= nextTo) {
      onChange({ ...value, from: nextFrom || undefined, to: nextTo || undefined });
    }
  }

  function reset() {
    setQuery("");
    setFrom("");
    setTo("");
    onChange({ q: "", sort: value.sort });
  }

  return (
    <form
      className="filters"
      role="search"
      aria-label={t.overview.filtersLabel}
      onSubmit={submitSearch}
    >
      <div className="filters__search">
        <label htmlFor={`${id}-q`}>{t.overview.search}</label>
        <div className="filters__search-row">
          <input
            id={`${id}-q`}
            className="control"
            type="search"
            maxLength={MAX_SEARCH_LENGTH}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" className="button button--primary">
            {t.overview.searchSubmit}
          </button>
        </div>
      </div>

      <div className="filters__field">
        <label htmlFor={`${id}-category`}>{t.overview.category}</label>
        <select
          id={`${id}-category`}
          className="control"
          value={value.category ?? ""}
          onChange={(event) =>
            onChange({ ...value, category: (event.target.value as Category) || undefined })
          }
        >
          <option value="">{t.overview.allCategories}</option>
          {CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {categoryLabel(category, t)}
            </option>
          ))}
        </select>
      </div>

      <div className="filters__field">
        <label htmlFor={`${id}-relevance`}>{t.overview.minRelevance}</label>
        <select
          id={`${id}-relevance`}
          className="control"
          value={value.minRelevance ?? ""}
          onChange={(event) =>
            onChange({
              ...value,
              minRelevance: event.target.value ? Number(event.target.value) : undefined,
            })
          }
        >
          <option value="">{t.overview.anyRelevance}</option>
          {[1, 2, 3, 4, 5].map((score) => (
            <option key={score} value={score}>
              {`≥ ${score}`}
            </option>
          ))}
        </select>
      </div>

      <div className="filters__field">
        <label htmlFor={`${id}-from`}>{t.overview.from}</label>
        <input
          id={`${id}-from`}
          className="control"
          type="date"
          value={from}
          aria-invalid={invalidPeriod || undefined}
          aria-describedby={invalidPeriod ? `${id}-period-error` : undefined}
          onChange={(event) => changePeriod(event.target.value, to)}
        />
      </div>

      <div className="filters__field">
        <label htmlFor={`${id}-to`}>{t.overview.to}</label>
        <input
          id={`${id}-to`}
          className="control"
          type="date"
          value={to}
          aria-invalid={invalidPeriod || undefined}
          aria-describedby={invalidPeriod ? `${id}-period-error` : undefined}
          onChange={(event) => changePeriod(from, event.target.value)}
        />
      </div>

      <div className="filters__field">
        <label htmlFor={`${id}-sort`}>{t.overview.sort}</label>
        <select
          id={`${id}-sort`}
          className="control"
          value={value.sort}
          onChange={(event) => onChange({ ...value, sort: event.target.value as SortOrder })}
        >
          <option value="recent">{t.overview.sortRecent}</option>
          <option value="relevance">{t.overview.sortRelevance}</option>
        </select>
      </div>

      <div className="filters__actions">
        <button type="button" className="button" onClick={reset}>
          {t.overview.resetFilters}
        </button>
      </div>

      {invalidPeriod && (
        <p id={`${id}-period-error`} className="filters__error" role="alert">
          {t.overview.invalidPeriod}
        </p>
      )}
    </form>
  );
}
