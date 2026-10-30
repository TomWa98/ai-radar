import type { Dictionary } from "../i18n/dictionaries";
import type { Category } from "./api";

const KEYS: Record<Category, keyof Dictionary["categories"]> = {
  Releases: "releases",
  Features: "features",
  Security: "security",
  "Use Cases": "useCases",
  Other: "other",
};

export function categoryLabel(category: Category, t: Dictionary): string {
  return t.categories[KEYS[category]];
}
