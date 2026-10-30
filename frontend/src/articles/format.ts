import type { Language } from "../i18n/dictionaries";

/**
 * Helpers for untrusted article data: nothing here creates markup, and only
 * http(s) URLs become links.
 */

/** The URL if it is an absolute http(s) URL, otherwise `null`. */
export function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/**
 * Plain text of a feed excerpt that may contain HTML. The HTML is parsed into
 * an inert document (no scripts run, nothing is inserted into the page) and
 * only its text content is used.
 */
export function plainText(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** Locale-aware date and time, or `null` for a missing/invalid value. */
export function formatDateTime(value: string | null, lang: Language): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(lang === "de" ? "de-DE" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/** Start or end of a local calendar day (`YYYY-MM-DD`) as an ISO timestamp. */
export function dayBoundary(day: string, edge: "start" | "end"): string | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!match) {
    return undefined;
  }
  const [, year, month, date] = match.map(Number) as [number, number, number, number];
  const local =
    edge === "start"
      ? new Date(year, month - 1, date, 0, 0, 0, 0)
      : new Date(year, month - 1, date, 23, 59, 59, 999);
  return Number.isNaN(local.getTime()) ? undefined : local.toISOString();
}
