import { describe, expect, it } from "vitest";
import { dayBoundary, formatDateTime, plainText, safeHref } from "./format";

describe("safeHref", () => {
  it.each(["https://example.com/a?b=1", "http://example.com/"])("allows %s", (url) => {
    expect(safeHref(url)).toBe(new URL(url).href);
  });

  it.each([
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "ftp://example.com/file",
    "/relative/path",
    "not a url",
    "",
  ])("rejects %s", (url) => {
    expect(safeHref(url)).toBeNull();
  });
});

describe("plainText", () => {
  it("keeps only the text of HTML excerpts", () => {
    expect(plainText("<p>Hello <b>world</b> &amp; friends</p>")).toBe("Hello world & friends");
  });

  it("never runs scripts or event handlers", () => {
    const marker = window as unknown as { pwned?: boolean };
    const text = plainText(
      '<img src="x" onerror="window.pwned = true"><script>window.pwned = true</script>Safe',
    );
    expect(text).not.toContain("<");
    expect(marker.pwned).toBeUndefined();
    expect(document.querySelector("img")).toBeNull();
  });

  it("collapses whitespace", () => {
    expect(plainText("  a \n\n b  ")).toBe("a b");
  });
});

describe("formatDateTime", () => {
  const value = "2026-10-30T12:05:00Z";

  it("formats per language", () => {
    expect(formatDateTime(value, "de")).toMatch(/30\.10\.2026|30\. Okt\. 2026/);
    expect(formatDateTime(value, "en")).toMatch(/30 Oct 2026/);
  });

  it("returns null for missing or invalid values", () => {
    expect(formatDateTime(null, "en")).toBeNull();
    expect(formatDateTime("yesterday", "en")).toBeNull();
  });
});

describe("dayBoundary", () => {
  it("returns the local start and end of a day as ISO timestamps", () => {
    const start = new Date(dayBoundary("2026-10-30", "start") ?? "");
    const end = new Date(dayBoundary("2026-10-30", "end") ?? "");
    expect([start.getFullYear(), start.getMonth(), start.getDate(), start.getHours()]).toEqual([
      2026, 9, 30, 0,
    ]);
    expect([end.getDate(), end.getHours(), end.getMinutes()]).toEqual([30, 23, 59]);
  });

  it("ignores malformed days", () => {
    expect(dayBoundary("30.10.2026", "start")).toBeUndefined();
    expect(dayBoundary("", "end")).toBeUndefined();
  });
});
