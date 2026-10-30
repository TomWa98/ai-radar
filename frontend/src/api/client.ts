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

/** GET a JSON resource; throws {@link ApiError} for every failure. */
export async function apiGet(path: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" }, signal });
  } catch (error) {
    if (signal?.aborted) {
      throw error; // cancelled by the caller, not a failure to report
    }
    throw new ApiError("Network error", null);
  }
  if (!response.ok) {
    const detail = await errorDetail(response);
    throw new ApiError(detail ?? `HTTP ${response.status}`, response.status);
  }
  try {
    return (await response.json()) as unknown;
  } catch {
    throw new ApiError("Invalid JSON response", response.status);
  }
}

export interface Health {
  status: string;
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const body = await apiGet("/health", signal);
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
