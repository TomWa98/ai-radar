/**
 * UI texts in one place. The DE/EN dictionaries follow in #24 (D8: own
 * dictionaries, no i18n library).
 */
export const strings = {
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
} as const;
