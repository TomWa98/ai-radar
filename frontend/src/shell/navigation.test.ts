import { describe, expect, it } from "vitest";
import { NAV_ITEMS, hrefFor, routeFromHash, type NavItem } from "./navigation";

const ITEMS: NavItem[] = [
  { id: "overview", labelKey: "overview", available: true },
  { id: "interests", labelKey: "interests", available: true },
  { id: "sources", labelKey: "sources", available: false },
];

describe("routeFromHash", () => {
  it("returns the named available route", () => {
    expect(routeFromHash("#/interests", ITEMS)).toBe("interests");
  });

  it("falls back to the first available route", () => {
    expect(routeFromHash("", ITEMS)).toBe("overview");
    expect(routeFromHash("#/unknown", ITEMS)).toBe("overview");
    expect(routeFromHash("#/sources", ITEMS)).toBe("overview"); // not available
  });

  it("returns null when nothing is available", () => {
    const none = ITEMS.map((item) => ({ ...item, available: false }));
    expect(routeFromHash("#/overview", none)).toBeNull();
  });

  it("makes only Overview available so far", () => {
    expect(NAV_ITEMS.filter((item) => item.available).map((item) => item.id)).toEqual([
      "overview",
    ]);
    expect(routeFromHash("", NAV_ITEMS)).toBe("overview");
  });
});

describe("navigation items", () => {
  it("lists the designed destinations without Articles", () => {
    expect(NAV_ITEMS.map((item) => item.id)).toEqual([
      "overview",
      "interests",
      "sources",
      "news-wall",
    ]);
  });

  it("builds hash links", () => {
    expect(hrefFor("news-wall")).toBe("#/news-wall");
  });
});
