import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiSend, getHealth, withQuery } from "./client";

function mockFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  const fetchMock = vi.fn(impl);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getHealth", () => {
  it("returns the backend status", async () => {
    const fetchMock = mockFetch(async () => json({ status: "ok" }));

    await expect(getHealth()).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/health", expect.objectContaining({
      headers: { Accept: "application/json" },
    }));
  });

  it("rejects an unexpected body", async () => {
    mockFetch(async () => json({ healthy: true }));

    await expect(getHealth()).rejects.toMatchObject({
      name: "ApiError",
      message: "Unexpected health response",
    });
  });
});

describe("apiGet errors", () => {
  it("uses the API's detail message for HTTP errors", async () => {
    mockFetch(async () => json({ detail: "Feed not found" }, 404));

    const error = await apiGet("/api/feeds/9").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: "Feed not found", status: 404 });
  });

  it("joins the messages of a FastAPI validation error", async () => {
    mockFetch(async () =>
      json(
        {
          detail: [
            { loc: ["body", "url"], msg: "Value error, Unsupported URL scheme: ftp" },
            { loc: ["body", "name"], msg: "String should have at most 200 characters" },
            { loc: ["body"], msg: 7 },
          ],
        },
        422,
      ),
    );

    await expect(apiSend("POST", "/api/feeds", {})).rejects.toMatchObject({
      message:
        "Value error, Unsupported URL scheme: ftp; String should have at most 200 characters",
      status: 422,
    });
  });

  it("falls back to the status for a validation error without messages", async () => {
    mockFetch(async () => json({ detail: [{ loc: ["body"] }] }, 422));

    await expect(apiSend("POST", "/api/feeds", {})).rejects.toMatchObject({
      message: "HTTP 422",
    });
  });

  it("falls back to the status for non-JSON errors", async () => {
    mockFetch(async () => new Response("Internal Server Error", { status: 500 }));

    await expect(apiGet("/health")).rejects.toMatchObject({
      message: "HTTP 500",
      status: 500,
    });
  });

  it("reports network failures without a status", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(apiGet("/health")).rejects.toMatchObject({
      message: "Network error",
      status: null,
    });
  });

  it("reports invalid JSON in a successful response", async () => {
    mockFetch(async () => new Response("<html>", { status: 200 }));

    await expect(apiGet("/health")).rejects.toMatchObject({
      message: "Invalid JSON response",
    });
  });

  it("passes cancellation through instead of reporting an error", async () => {
    const controller = new AbortController();
    const abort = new DOMException("Aborted", "AbortError");
    mockFetch(async () => {
      controller.abort();
      throw abort;
    });

    await expect(apiGet("/health", { signal: controller.signal })).rejects.toBe(abort);
  });
});

describe("withQuery", () => {
  it("appends defined parameters URL-encoded", () => {
    expect(withQuery("/api/articles", { lang: "de", q: "a&b c", limit: 20 })).toBe(
      "/api/articles?lang=de&q=a%26b+c&limit=20",
    );
  });

  it("skips undefined values and empty queries", () => {
    expect(withQuery("/api/articles", { lang: "en", q: undefined })).toBe(
      "/api/articles?lang=en",
    );
    expect(withQuery("/health")).toBe("/health");
    expect(withQuery("/health", {})).toBe("/health");
  });

  it("is used by apiGet", async () => {
    const fetchMock = mockFetch(async () => json({}));
    await apiGet("/api/articles", { query: { lang: "en" } });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/articles?lang=en");
  });
});

describe("apiSend", () => {
  it("sends a JSON body and returns the JSON response", async () => {
    const fetchMock = mockFetch(async () => json({ ok: true }));

    await expect(
      apiSend("PUT", "/api/articles/1/feedback", { rating: "relevant" }),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/articles/1/feedback", {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ rating: "relevant" }),
    });
  });

  it("returns null for 204 No Content and sends no body without one", async () => {
    const fetchMock = mockFetch(async () => new Response(null, { status: 204 }));

    await expect(apiSend("DELETE", "/api/articles/1/feedback")).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledWith("/api/articles/1/feedback", {
      method: "DELETE",
      headers: { Accept: "application/json" },
      body: undefined,
    });
  });

  it("reports HTTP and network errors like apiGet", async () => {
    mockFetch(async () => json({ detail: "Article not found" }, 404));
    await expect(apiSend("DELETE", "/api/articles/9/feedback")).rejects.toMatchObject({
      message: "Article not found",
      status: 404,
    });

    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(apiSend("DELETE", "/api/articles/9/feedback")).rejects.toMatchObject({
      message: "Network error",
      status: null,
    });
  });
});
