import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { analysis, article, page } from "../test/articles";
import { stubApi, json } from "../test/fetch";
import { clearFeedback, fetchArticles, parseArticlePage, setFeedback } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseArticlePage", () => {
  it("maps the API fields", () => {
    const parsed = parseArticlePage(
      page([article({ id: 7, analysis: analysis({ secondary_categories: ["Security"] }) })], 30),
    );

    expect(parsed.total).toBe(30);
    expect(parsed.nextSince).toBe("2026-10-30T12:00:00+00:00");
    expect(parsed.items[0]).toMatchObject({
      id: 7,
      title: "Headline 7",
      publishedAt: "2026-10-30T10:00:00Z",
      status: "analyzed",
      analysis: {
        primaryCategory: "Releases",
        secondaryCategories: ["Security"],
        relevance: 4,
        importance: 3,
        basis: "full_text",
        relevanceReason: "Matches your interest in models.",
      },
    });
  });

  it("accepts articles without analysis", () => {
    const parsed = parseArticlePage(page([article({ status: "new", analysis: null })]));
    expect(parsed.items[0]?.analysis).toBeNull();
  });

  it.each([
    ["missing items", { total: 0, next_since: "x" }],
    ["missing next_since", { items: [], total: 0 }],
    ["unknown status", page([article({ status: "deleted" })])],
    ["unknown category", page([article({ analysis: analysis({ primary_category: "Gossip" }) })])],
    ["score out of range", page([article({ analysis: analysis({ relevance: 6 }) })])],
    ["unknown basis", page([article({ analysis: analysis({ basis: "guess" }) })])],
    ["title not text", page([article({ title: 5 as unknown as string })])],
  ])("rejects a response with %s", (_name, body) => {
    expect(() => parseArticlePage(body)).toThrow(ApiError);
  });
});

describe("fetchArticles", () => {
  it("sends filters, sort, language, and paging as query parameters", async () => {
    const calls = stubApi(() => json(page([])));

    await fetchArticles({
      lang: "de",
      q: "open source",
      category: "Use Cases",
      minRelevance: 4,
      publishedFrom: "2026-10-01T00:00:00.000Z",
      publishedTo: "2026-10-31T23:59:59.999Z",
      sort: "relevance",
      limit: 25,
      offset: 50,
    });

    const url = new URL(calls[0]?.url ?? "", "http://127.0.0.1");
    expect(url.pathname).toBe("/api/articles");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      lang: "de",
      q: "open source",
      category: "Use Cases",
      min_relevance: "4",
      published_from: "2026-10-01T00:00:00.000Z",
      published_to: "2026-10-31T23:59:59.999Z",
      sort: "relevance",
      limit: "25",
      offset: "50",
    });
  });

  it("omits empty search and the first offset", async () => {
    const calls = stubApi(() => json(page([])));

    await fetchArticles({ lang: "en", q: "", limit: 25, offset: 0 });

    expect(calls[0]?.url).toBe("/api/articles?lang=en&limit=25");
  });
});

describe("feedback", () => {
  it("parses the stored feedback of an article", () => {
    const parsed = parseArticlePage(
      page([article({ id: 1, feedback: "relevant" }), article({ id: 2, feedback: null })]),
    );

    expect(parsed.items.map((item) => item.feedback)).toEqual(["relevant", null]);
  });

  it("rejects an unknown feedback value", () => {
    expect(() => parseArticlePage(page([article({ feedback: "maybe" })]))).toThrow(ApiError);
  });

  it("stores a rating and returns the stored rating", async () => {
    const calls = stubApi((url) =>
      url.pathname === "/api/articles/3/feedback"
        ? json({
            article_id: 3,
            rating: "irrelevant",
            created_at: "2026-10-30T12:00:00Z",
            updated_at: "2026-10-30T12:00:00Z",
          })
        : undefined,
    );

    await expect(setFeedback(3, "irrelevant")).resolves.toBe("irrelevant");
    expect(calls).toEqual([
      {
        url: "/api/articles/3/feedback",
        method: "PUT",
        body: JSON.stringify({ rating: "irrelevant" }),
      },
    ]);
  });

  it("rejects an unexpected feedback response", async () => {
    stubApi((url) =>
      url.pathname === "/api/articles/3/feedback"
        ? json({ article_id: 4, rating: "relevant" })
        : undefined,
    );

    await expect(setFeedback(3, "relevant")).rejects.toBeInstanceOf(ApiError);
  });

  it("removes feedback", async () => {
    const calls = stubApi((url) =>
      url.pathname === "/api/articles/3/feedback" ? new Response(null, { status: 204 }) : undefined,
    );

    await expect(clearFeedback(3)).resolves.toBeUndefined();
    expect(calls).toEqual([{ url: "/api/articles/3/feedback", method: "DELETE", body: undefined }]);
  });
});
