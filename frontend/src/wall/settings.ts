/** localStorage key for the wall's minimum relevance score (FR-27). */
export const MIN_RELEVANCE_STORAGE_KEY = "ai-radar.wall.min-relevance";
export const MIN_RELEVANCE_OPTIONS = [1, 2, 3, 4, 5] as const;
/** Hides nothing that has an analysis until the user chooses otherwise. */
export const DEFAULT_MIN_RELEVANCE = 1;

export function loadMinRelevance(): number {
  try {
    const value = window.localStorage.getItem(MIN_RELEVANCE_STORAGE_KEY);
    return value !== null && /^[1-5]$/.test(value) ? Number(value) : DEFAULT_MIN_RELEVANCE;
  } catch {
    return DEFAULT_MIN_RELEVANCE; // storage unavailable (e.g. blocked)
  }
}

export function saveMinRelevance(value: number): void {
  try {
    window.localStorage.setItem(MIN_RELEVANCE_STORAGE_KEY, String(value));
  } catch {
    // Not persisted; the choice still applies for this session.
  }
}
