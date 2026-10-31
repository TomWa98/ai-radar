import { ApiError, apiGet, apiSend } from "../api/client";

/**
 * Types and client for feeds, `/api/feeds` (backend #10), and the manual
 * refresh, `/api/refresh` (backend #13).
 */

/** Limits enforced by the API (`feeds/api.py`). */
export const MAX_URL_LENGTH = 2048;
export const MAX_NAME_LENGTH = 200;

/**
 * A stored feed. `url`, `name`, and `lastError` are user input or come from
 * fetching an external source and must be rendered as text only.
 */
export interface Feed {
  id: number;
  url: string;
  name: string | null;
  enabled: boolean;
  fetchFullText: boolean;
  lastFetchedAt: string | null;
  lastError: string | null;
}

/** The fields a user can set when adding a feed. */
export interface NewFeed {
  url: string;
  name: string | null;
  enabled: boolean;
  fetchFullText: boolean;
}

/** The fields a user can change on an existing feed (FR-01). */
export interface FeedChanges {
  name: string | null;
  enabled: boolean;
  fetchFullText: boolean;
}

export interface RefreshStatus {
  running: boolean;
  lastStartedAt: string | null;
  lastFinishedAt: string | null;
}

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isOptionalString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function invalid(what: string): never {
  throw new ApiError(`Unexpected ${what} response`, 200);
}

export function parseFeed(value: unknown): Feed {
  if (
    !isObject(value) ||
    !Number.isInteger(value.id) ||
    !isString(value.url) ||
    !isOptionalString(value.name) ||
    typeof value.enabled !== "boolean" ||
    typeof value.fetch_full_text !== "boolean" ||
    !isOptionalString(value.last_fetched_at) ||
    !isOptionalString(value.last_error)
  ) {
    return invalid("feed");
  }
  return {
    id: value.id as number,
    url: value.url,
    name: value.name,
    enabled: value.enabled,
    fetchFullText: value.fetch_full_text,
    lastFetchedAt: value.last_fetched_at,
    lastError: value.last_error,
  };
}

export function parseRefreshStatus(value: unknown): RefreshStatus {
  if (
    !isObject(value) ||
    typeof value.running !== "boolean" ||
    !isOptionalString(value.last_started_at) ||
    !isOptionalString(value.last_finished_at)
  ) {
    return invalid("refresh");
  }
  return {
    running: value.running,
    lastStartedAt: value.last_started_at,
    lastFinishedAt: value.last_finished_at,
  };
}

export async function fetchFeeds(signal?: AbortSignal): Promise<Feed[]> {
  const body = await apiGet("/api/feeds", { signal });
  return Array.isArray(body) ? body.map(parseFeed) : invalid("feeds");
}

/** Add a feed; resolves to the feed the API stored. */
export async function addFeed(feed: NewFeed): Promise<Feed> {
  return parseFeed(
    await apiSend("POST", "/api/feeds", {
      url: feed.url,
      name: feed.name,
      enabled: feed.enabled,
      fetch_full_text: feed.fetchFullText,
    }),
  );
}

/** Change name, enabled state, and full-text opt-in; resolves to the stored feed. */
export async function updateFeed(id: number, changes: FeedChanges): Promise<Feed> {
  return parseFeed(
    await apiSend("PATCH", `/api/feeds/${id}`, {
      name: changes.name,
      enabled: changes.enabled,
      fetch_full_text: changes.fetchFullText,
    }),
  );
}

/** Remove a feed; its articles are kept by the backend. */
export async function removeFeed(id: number): Promise<void> {
  await apiSend("DELETE", `/api/feeds/${id}`);
}

export async function fetchRefreshStatus(signal?: AbortSignal): Promise<RefreshStatus> {
  return parseRefreshStatus(await apiGet("/api/refresh", { signal }));
}

/** Start a refresh; rejects with an `ApiError` of status 409 if one is running. */
export async function startRefresh(): Promise<void> {
  await apiSend("POST", "/api/refresh");
}
