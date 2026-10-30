/**
 * DE/EN dictionaries for all UI texts (FR-35; D8: own dictionaries, no i18n
 * library). `Dictionary` is derived from the English texts, so TypeScript
 * reports any key missing from or added to the German dictionary; a test
 * checks the same at runtime.
 */

export const LANGUAGES = ["de", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

const en = {
  productName: "AI Radar",
  skipToContent: "Skip to content",
  mainNavigation: "Main navigation",
  notAvailableYet: "Not available yet",
  noViewTitle: "No view available yet",
  noViewText: "The views of AI Radar are added step by step.",
  backend: {
    checking: "Checking backend…",
    reachable: "Backend reachable",
    unreachable: "Backend unreachable",
  },
  nav: {
    overview: "Overview",
    interests: "Interests",
    sources: "Sources",
    newsWall: "News Wall",
  },
  language: {
    label: "Language",
    de: "Deutsch",
    en: "English",
  },
  categories: {
    releases: "Releases",
    features: "Features",
    security: "Security",
    useCases: "Use cases",
    other: "Other",
  },
  overview: {
    title: "Overview",
    intro: "Prioritized AI and technology news from your sources.",
    filtersLabel: "Search and filters",
    search: "Search",
    searchSubmit: "Search",
    category: "Category",
    allCategories: "All categories",
    minRelevance: "Minimum relevance",
    anyRelevance: "Any",
    from: "Published from",
    to: "Published until",
    sort: "Sort by",
    sortRecent: "Newest first",
    sortRelevance: "Most relevant first",
    resetFilters: "Reset filters",
    invalidPeriod: "The start date must not be after the end date.",
    loading: "Loading articles…",
    count: "{count} articles",
    countOne: "1 article",
    emptyTitle: "No articles yet",
    emptyText: "Articles appear here as soon as your sources have been fetched.",
    noResults: "No articles match the current search and filters.",
    error: "Articles could not be loaded.",
    retry: "Try again",
    stale: "Updating failed. Showing the last loaded articles.",
    pages: "Pages",
    previous: "Previous page",
    next: "Next page",
    pageOf: "Page {page} of {pages}",
  },
  article: {
    aiSummary: "AI summary",
    excerpt: "Excerpt from the source",
    relevance: "Personal relevance",
    importance: "Importance",
    score: "{score} of 5",
    reason: "Why relevant",
    basisFullText: "Analysis based on the full text",
    basisExcerpt: "Analysis based on the feed excerpt",
    collected: "Collected {date}",
    noDate: "Date unknown",
    also: "Also: {categories}",
    opensInNewTab: "(opens in a new tab)",
    status: {
      new: "Not analyzed yet",
      processing: "Analysis in progress",
      failed: "Analysis failed",
    },
  },
} as const;

type Texts<T> = { readonly [K in keyof T]: T[K] extends string ? string : Texts<T[K]> };
export type Dictionary = Texts<typeof en>;

const de: Dictionary = {
  productName: "AI Radar",
  skipToContent: "Zum Inhalt springen",
  mainNavigation: "Hauptnavigation",
  notAvailableYet: "Noch nicht verfügbar",
  noViewTitle: "Noch keine Ansicht verfügbar",
  noViewText: "Die Ansichten von AI Radar werden schrittweise ergänzt.",
  backend: {
    checking: "Backend wird geprüft …",
    reachable: "Backend erreichbar",
    unreachable: "Backend nicht erreichbar",
  },
  nav: {
    overview: "Übersicht",
    interests: "Interessen",
    sources: "Quellen",
    newsWall: "News-Wall",
  },
  language: {
    label: "Sprache",
    de: "Deutsch",
    en: "English",
  },
  categories: {
    releases: "Releases",
    features: "Funktionen",
    security: "Sicherheit",
    useCases: "Anwendungsfälle",
    other: "Sonstiges",
  },
  overview: {
    title: "Übersicht",
    intro: "Priorisierte KI- und Technologienachrichten aus Ihren Quellen.",
    filtersLabel: "Suche und Filter",
    search: "Suche",
    searchSubmit: "Suchen",
    category: "Kategorie",
    allCategories: "Alle Kategorien",
    minRelevance: "Mindest-Relevanz",
    anyRelevance: "Beliebig",
    from: "Veröffentlicht ab",
    to: "Veröffentlicht bis",
    sort: "Sortierung",
    sortRecent: "Neueste zuerst",
    sortRelevance: "Relevanteste zuerst",
    resetFilters: "Filter zurücksetzen",
    invalidPeriod: "Das Startdatum darf nicht nach dem Enddatum liegen.",
    loading: "Artikel werden geladen …",
    count: "{count} Artikel",
    countOne: "1 Artikel",
    emptyTitle: "Noch keine Artikel",
    emptyText: "Artikel erscheinen hier, sobald Ihre Quellen abgerufen wurden.",
    noResults: "Keine Artikel passen zur aktuellen Suche und zu den Filtern.",
    error: "Die Artikel konnten nicht geladen werden.",
    retry: "Erneut versuchen",
    stale: "Aktualisierung fehlgeschlagen. Angezeigt werden die zuletzt geladenen Artikel.",
    pages: "Seiten",
    previous: "Vorherige Seite",
    next: "Nächste Seite",
    pageOf: "Seite {page} von {pages}",
  },
  article: {
    aiSummary: "KI-Zusammenfassung",
    excerpt: "Auszug aus der Quelle",
    relevance: "Persönliche Relevanz",
    importance: "Bedeutung",
    score: "{score} von 5",
    reason: "Warum relevant",
    basisFullText: "Analyse auf Basis des Volltexts",
    basisExcerpt: "Analyse auf Basis des Feed-Auszugs",
    collected: "Abgerufen {date}",
    noDate: "Datum unbekannt",
    also: "Außerdem: {categories}",
    opensInNewTab: "(öffnet in neuem Tab)",
    status: {
      new: "Noch nicht analysiert",
      processing: "Analyse läuft",
      failed: "Analyse fehlgeschlagen",
    },
  },
};

export const DICTIONARIES: Readonly<Record<Language, Dictionary>> = { de, en };

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (LANGUAGES as readonly string[]).includes(value);
}

/** Replace `{name}` placeholders in a dictionary text. */
export function fill(text: string, values: Readonly<Record<string, string | number>>): string {
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}
