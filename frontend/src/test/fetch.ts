import { vi } from "vitest";

/** One recorded request. */
export interface Call {
  url: string;
  method: string;
}

export type Route = (url: URL) => Response | Promise<Response> | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const EMPTY_PAGE = {
  items: [],
  total: 0,
  limit: 25,
  offset: 0,
  next_since: "2026-10-30T12:00:00+00:00",
};

/**
 * Stub `fetch` for the app: `/health` is healthy and `/api/articles` returns
 * an empty page unless a route answers first. Returns the recorded calls.
 */
export function stubApi(...routes: Route[]): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const raw = String(input);
      calls.push({ url: raw, method: init?.method ?? "GET" });
      const url = new URL(raw, "http://127.0.0.1");
      for (const route of routes) {
        const response = await route(url);
        if (response) return response;
      }
      if (url.pathname === "/health") return json({ status: "ok" });
      if (url.pathname === "/api/articles") return json(EMPTY_PAGE);
      return json({ detail: "Not found" }, 404);
    }),
  );
  return calls;
}
