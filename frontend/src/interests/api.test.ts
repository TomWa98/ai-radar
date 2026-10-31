import { afterEach, describe, expect, it, vi } from "vitest";
import { json, stubApi } from "../test/fetch";
import {
  addInterest,
  fetchInterests,
  fetchPreferences,
  parseInterest,
  parsePreferences,
  removeInterest,
  resetPreferences,
  setInterestWeight,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

const STORED = {
  id: 3,
  topic: "Agents",
  weight: "high",
  created_at: "2026-10-30T12:00:00Z",
  updated_at: "2026-10-30T12:00:00Z",
};

describe("parseInterest", () => {
  it("maps an interest", () => {
    expect(parseInterest(STORED)).toEqual({ id: 3, topic: "Agents", weight: "high" });
  });

  it.each([
    { ...STORED, id: "3" },
    { ...STORED, topic: null },
    { ...STORED, weight: "urgent" },
    null,
    [],
  ])("rejects an unexpected interest %#", (value) => {
    expect(() => parseInterest(value)).toThrow("Unexpected interests response");
  });
});

describe("parsePreferences", () => {
  const learned = { topic: "agents", score: -1, relevant: 1, irrelevant: 2, ratings: 3 };

  it("maps learned preferences and the last reset", () => {
    expect(parsePreferences({ learned: [learned], last_reset_at: null })).toEqual({
      learned: [learned],
      lastResetAt: null,
    });
  });

  it.each([
    { learned: [{ ...learned, relevant: -1 }], last_reset_at: null },
    { learned: [{ ...learned, score: 1.5 }], last_reset_at: null },
    { learned: [{ ...learned, topic: 1 }], last_reset_at: null },
    { learned: {}, last_reset_at: null },
    { learned: [], last_reset_at: 5 },
  ])("rejects an unexpected response %#", (value) => {
    expect(() => parsePreferences(value)).toThrow("Unexpected interests response");
  });
});

describe("requests", () => {
  it("uses the interests and preferences endpoints", async () => {
    const calls = stubApi((url, init) => {
      const method = init?.method ?? "GET";
      if (url.pathname === "/api/interests") {
        return method === "POST" ? json(STORED, 201) : json([STORED]);
      }
      if (url.pathname === "/api/interests/3") {
        return method === "PATCH" ? json(STORED) : new Response(null, { status: 204 });
      }
      if (url.pathname === "/api/preferences") {
        return method === "DELETE"
          ? new Response(null, { status: 204 })
          : json({ learned: [], last_reset_at: "2026-10-30T12:00:00Z" });
      }
      return undefined;
    });

    await expect(fetchInterests()).resolves.toHaveLength(1);
    await expect(addInterest("Agents", "high")).resolves.toMatchObject({ id: 3 });
    await expect(setInterestWeight(3, "high")).resolves.toMatchObject({ weight: "high" });
    await expect(removeInterest(3)).resolves.toBeUndefined();
    await expect(fetchPreferences()).resolves.toEqual({
      learned: [],
      lastResetAt: "2026-10-30T12:00:00Z",
    });
    await expect(resetPreferences()).resolves.toBeUndefined();

    expect(calls.map(({ method, url, body }) => [method, url, body])).toEqual([
      ["GET", "/api/interests", undefined],
      ["POST", "/api/interests", JSON.stringify({ topic: "Agents", weight: "high" })],
      ["PATCH", "/api/interests/3", JSON.stringify({ weight: "high" })],
      ["DELETE", "/api/interests/3", undefined],
      ["GET", "/api/preferences", undefined],
      ["DELETE", "/api/preferences", undefined],
    ]);
  });

  it("rejects a non-list interests response", async () => {
    stubApi((url) => (url.pathname === "/api/interests" ? json({}) : undefined));
    await expect(fetchInterests()).rejects.toThrow("Unexpected interests response");
  });
});
