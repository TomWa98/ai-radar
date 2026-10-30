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
};

export const DICTIONARIES: Readonly<Record<Language, Dictionary>> = { de, en };

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (LANGUAGES as readonly string[]).includes(value);
}
