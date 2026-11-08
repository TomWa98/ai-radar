import type { Article } from "../articles/api";

/** D10: up to nine cards at once, next page every 20 seconds. */
export const CARDS_PER_PAGE = 9;
export const ROTATION_INTERVAL_MS = 20_000;
/** FR-29: check for updates at least every 60 seconds. */
export const POLL_INTERVAL_MS = 60_000;
/** The most relevant articles the wall rotates through (the API's page limit). */
export const MAX_ARTICLES = 100;
/** Idle time after which the settings overlay and its trigger hide again. */
export const SETTINGS_IDLE_MS = 30_000;

/** D10: "new and especially relevant". */
export const HIGHLIGHT_WINDOW_MS = 3 * 60 * 60 * 1000;
export const HIGHLIGHT_MIN_RELEVANCE = 4;

/**
 * When the article became news. A missing, invalid, or future publication date
 * (feeds do send those) falls back to when it was collected, so a bad date
 * cannot keep an article highlighted.
 */
function newsTime(article: Article, now: number): number {
  const published = article.publishedAt ? new Date(article.publishedAt).getTime() : NaN;
  return published <= now ? published : new Date(article.collectedAt).getTime();
}

/** Younger than three hours and personal relevance of at least 4 (D10). */
export function isHighlighted(article: Article, now: number): boolean {
  if (article.analysis === null || article.analysis.relevance < HIGHLIGHT_MIN_RELEVANCE) {
    return false;
  }
  return now - newsTime(article, now) < HIGHLIGHT_WINDOW_MS;
}
