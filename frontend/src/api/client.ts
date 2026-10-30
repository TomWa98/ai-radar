/**
 * Minimal API client. Requests go to fixed, same-origin paths (the Vite dev
 * server proxies them to the backend), so no user input ever forms a URL.
 */

export class ApiError extends Error {
  /** HTTP status, or `null` if no response was received. */
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
    ) {
      return body.detail;
    }
  } catch {
    // Not JSON: fall back to the status code.
  }
  return null;
}

export type QueryParams = Readonly<Record<string, string | number | undefined>>;

/** `path` with the defined `query` values appended (URL-encoded). */
export function withQuery(path: string, query?: QueryParams): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

export interface GetOptions {
  signal?: AbortSignal;
  /** Query parameters; language-dependent endpoints get `lang` (FR-35). */
  query?: QueryParams;
}

async function send(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (init.signal?.aborted) {
      throw error; // cancelled by the caller, not a failure to report
    }
    throw new ApiError("Network error", null);
  }
  if (!response.ok) {
    const detail = await errorDetail(response);
    throw new ApiError(detail ?? `HTTP ${response.status}`, response.status);
  }
  return response;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    throw new ApiError("Invalid JSON response", response.status);
  }
}

/** GET a JSON resource; throws {@link ApiError} for every failure. */
export async function apiGet(path: string, options: GetOptions = {}): Promise<unknown> {
  const { signal, query } = options;
  const response = await send(withQuery(path, query), {
    headers: { Accept: "application/json" },
    signal,
  });
  return readJson(response);
}

/**
 * PUT or DELETE a resource, with an optional JSON `body`. Returns the JSON
 * response, or `null` for `204 No Content`; throws {@link ApiError} for
 * every failure.
 */
export async function apiSend(
  method: "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<unknown> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await send(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.status === 204 ? null : readJson(response);
}

export interface Health {
  status: string;
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const body = await apiGet("/health", { signal });
  if (
    typeof body !== "object" ||
    body === null ||
    !("status" in body) ||
    typeof body.status !== "string"
  ) {
    throw new ApiError("Unexpected health response", 200);
  }
  return { status: body.status };
}
