import { ApiError, apiGet, apiSend } from "../api/client";

/**
 * Types and client for manual interests, `/api/interests` (backend #18), and
 * learned preferences, `/api/preferences` (backend #20).
 */

export const WEIGHTS = ["low", "medium", "high"] as const;
export type Weight = (typeof WEIGHTS)[number];

/** Limits enforced by the API (`interests/repository.py`). */
export const MAX_TOPIC_LENGTH = 100;

/** A manual interest. The topic is user input and must be rendered as text. */
export interface Interest {
  id: number;
  topic: string;
  weight: Weight;
}

/**
 * A learned preference. The topic comes from LLM analyses (untrusted text);
 * the counts explain the score: each "relevant" rating counts +1, each
 * "not relevant" rating -1.
 */
export interface LearnedPreference {
  topic: string;
  score: number;
  relevant: number;
  irrelevant: number;
  ratings: number;
}

export interface Preferences {
  learned: LearnedPreference[];
  lastResetAt: string | null;
}

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isCount(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

export function isWeight(value: unknown): value is Weight {
  return (WEIGHTS as readonly unknown[]).includes(value);
}

function invalid(): never {
  throw new ApiError("Unexpected interests response", 200);
}

export function parseInterest(value: unknown): Interest {
  if (
    !isObject(value) ||
    !Number.isInteger(value.id) ||
    !isString(value.topic) ||
    !isWeight(value.weight)
  ) {
    return invalid();
  }
  return { id: value.id as number, topic: value.topic, weight: value.weight };
}

function parseLearned(value: unknown): LearnedPreference {
  if (
    !isObject(value) ||
    !isString(value.topic) ||
    !Number.isInteger(value.score) ||
    !isCount(value.relevant) ||
    !isCount(value.irrelevant) ||
    !isCount(value.ratings)
  ) {
    return invalid();
  }
  return {
    topic: value.topic,
    score: value.score as number,
    relevant: value.relevant,
    irrelevant: value.irrelevant,
    ratings: value.ratings,
  };
}

export function parsePreferences(body: unknown): Preferences {
  if (
    !isObject(body) ||
    !Array.isArray(body.learned) ||
    !(body.last_reset_at === null || isString(body.last_reset_at))
  ) {
    return invalid();
  }
  return { learned: body.learned.map(parseLearned), lastResetAt: body.last_reset_at };
}

export async function fetchInterests(signal?: AbortSignal): Promise<Interest[]> {
  const body = await apiGet("/api/interests", { signal });
  return Array.isArray(body) ? body.map(parseInterest) : invalid();
}

/** Add an interest; resolves to the interest the API stored. */
export async function addInterest(topic: string, weight: Weight): Promise<Interest> {
  return parseInterest(await apiSend("POST", "/api/interests", { topic, weight }));
}

/** Change the weight of an interest; resolves to the stored interest. */
export async function setInterestWeight(id: number, weight: Weight): Promise<Interest> {
  return parseInterest(await apiSend("PATCH", `/api/interests/${id}`, { weight }));
}

export async function removeInterest(id: number): Promise<void> {
  await apiSend("DELETE", `/api/interests/${id}`);
}

export async function fetchPreferences(signal?: AbortSignal): Promise<Preferences> {
  return parsePreferences(await apiGet("/api/preferences", { signal }));
}

/** Forget all learned preferences; manual interests and feedback stay. */
export async function resetPreferences(): Promise<void> {
  await apiSend("DELETE", "/api/preferences");
}
