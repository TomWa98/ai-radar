import { useSyncExternalStore } from "react";
import { strings } from "../strings";

/**
 * Hash navigation (D8: no router library). Destinations that are not
 * implemented yet stay in the list as disabled entries; "Articles" is not
 * listed at all until an issue covers it (design decision 3).
 */
export type RouteId = "overview" | "interests" | "sources" | "news-wall";

export interface NavItem {
  id: RouteId;
  label: string;
  available: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { id: "overview", label: strings.nav.overview, available: false },
  { id: "interests", label: strings.nav.interests, available: false },
  { id: "sources", label: strings.nav.sources, available: false },
  { id: "news-wall", label: strings.nav.newsWall, available: false },
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
