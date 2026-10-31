import { vi } from "vitest";

/** One recorded request. */
export interface Call {
  url: string;
  method: string;
  body?: string;
}

export type Route = (
  url: URL,
  init?: RequestInit,
) => Response | Promise<Response> | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const IDLE_REFRESH = {
  running: false,
  last_started_at: null,
  last_finished_at: null,
};

export const EMPTY_PAGE = {
  items: [],
  total: 0,
  limit: 25,
  offset: 0,
  next_since: "2026-10-30T12:00:00+00:00",
};

/**
 * Stub `fetch` for the app: `/health` is healthy, `/api/articles` returns
 * an empty page, and `/api/refresh` reports no refresh yet, unless a route
 * answers first. Returns the recorded calls.
 */
export function stubApi(...routes: Route[]): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const raw = String(input);
      const body = typeof init?.body === "string" ? init.body : undefined;
      calls.push({ url: raw, method: init?.method ?? "GET", body });
      const url = new URL(raw, "http://127.0.0.1");
      for (const route of routes) {
        const response = await route(url, init);
        if (response) return response;
      }
      if (url.pathname === "/health") return json({ status: "ok" });
      if (url.pathname === "/api/articles") return json(EMPTY_PAGE);
      if (url.pathname === "/api/refresh" && (init?.method ?? "GET") === "GET") {
        return json(IDLE_REFRESH);
      }
      return json({ detail: "Not found" }, 404);
    }),
  );
  return calls;
}
