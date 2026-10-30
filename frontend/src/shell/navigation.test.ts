import { describe, expect, it } from "vitest";
import { NAV_ITEMS, hrefFor, routeFromHash, type NavItem } from "./navigation";

const ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", available: true },
  { id: "interests", label: "Interests", available: true },
  { id: "sources", label: "Sources", available: false },
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
    expect(routeFromHash("#/overview", NAV_ITEMS)).toBeNull();
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
