import { useSyncExternalStore } from "react";
import type { Dictionary } from "../i18n/dictionaries";

/**
 * Hash navigation (D8: no router library). Destinations that are not
 * implemented yet stay in the list as disabled entries; "Articles" is not
 * listed at all until an issue covers it (design decision 3).
 */
export type RouteId = "overview" | "interests" | "sources" | "news-wall";

export interface NavItem {
  id: RouteId;
  labelKey: keyof Dictionary["nav"];
  available: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { id: "overview", labelKey: "overview", available: true },
  { id: "interests", labelKey: "interests", available: false },
  { id: "sources", labelKey: "sources", available: false },
  { id: "news-wall", labelKey: "newsWall", available: false },
];

export function hrefFor(id: RouteId): string {
  return `#/${id}`;
}

/** The available route named by `hash`, or the first available one. */
export function routeFromHash(
  hash: string,
  items: readonly NavItem[] = NAV_ITEMS,
): RouteId | null {
  const id = hash.replace(/^#\/?/, "");
  const available = items.filter((item) => item.available);
  return (available.find((item) => item.id === id) ?? available[0])?.id ?? null;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function useHashRoute(items: readonly NavItem[] = NAV_ITEMS): RouteId | null {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return routeFromHash(hash, items);
}
