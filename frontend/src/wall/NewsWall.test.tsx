import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseArticlePage } from "../articles/api";
import { LANGUAGE_STORAGE_KEY, LanguageProvider, useLanguage } from "../i18n/language";
import { analysis, article, page, type ArticleFixture } from "../test/articles";
import { json, stubApi, type Call } from "../test/fetch";
import { NewsWall } from "./NewsWall";
import {
  HIGHLIGHT_WINDOW_MS,
  POLL_INTERVAL_MS,
  ROTATION_INTERVAL_MS,
  SETTINGS_IDLE_MS,
  isHighlighted,
} from "./rules";
import { MIN_RELEVANCE_STORAGE_KEY } from "./settings";

const NOW = new Date("2026-10-30T12:00:00Z");
const HOUR = 60 * 60 * 1000;

function ago(ms: number): string {
  return new Date(NOW.getTime() - ms).toISOString();
}

function many(count: number): ArticleFixture[] {
  return Array.from({ length: count }, (_, index) =>
    article({ id: index + 1, title: `Story ${index + 1}` }),
  );
}

function articlesRoute(items: () => ArticleFixture[] | Response) {
  return (url: URL) => {
    if (url.pathname !== "/api/articles") return undefined;
    const value = items();
    return value instanceof Response ? value : json(page(value));
  };
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function renderWall(): Promise<void> {
  render(
    <LanguageProvider>
      <NewsWall />
    </LanguageProvider>,
  );
  await advance(0);
}

function titles(): string[] {
  return screen.getAllByRole("article").map((card) => within(card).getByRole("heading").textContent ?? "");
}

function articleRequests(calls: Call[]): URL[] {
  return calls
    .map((call) => new URL(call.url, "http://127.0.0.1"))
    .filter((url) => url.pathname === "/api/articles");
}

function setup() {
  const advanceTimers = vi.advanceTimersByTime.bind(vi);
  // Testing Library only detects fake timers through a global `jest`; without
  // it, its wrapper around user events waits for a timer that never fires.
  vi.stubGlobal("jest", { advanceTimersByTime: advanceTimers });
  return userEvent.setup({ advanceTimers });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  window.localStorage.clear();
  vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("loading articles", () => {
  it("requests the articles sorted by personal relevance", async () => {
    const calls = stubApi(articlesRoute(() => many(1)));
    await renderWall();

    const [request] = articleRequests(calls);
    expect(request?.searchParams.get("sort")).toBe("relevance");
    expect(request?.searchParams.get("min_relevance")).toBe("1");
    expect(request?.searchParams.get("lang")).toBe("en");
  });

  it("shows no controls in normal operation beyond the hidden settings trigger", async () => {
    stubApi(articlesRoute(() => many(3)));
    await renderWall();

    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button").className).toBe("wall__trigger");
  });

  it("shows a loading state, then an empty state", async () => {
    stubApi(articlesRoute(() => []));
    render(
      <LanguageProvider>
        <NewsWall />
      </LanguageProvider>,
    );
    expect(screen.getByText("Loading news…")).toBeTruthy();

    await advance(0);

    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("No articles to show");
  });

  it("renders untrusted article text as text", async () => {
    const payload = '<img src=x onerror="alert(1)">';
    stubApi(articlesRoute(() => [article({ id: 1, title: payload })]));
    await renderWall();

    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(payload);
    expect(document.querySelector("img")).toBeNull();
  });

  it("distinguishes personal relevance from importance", async () => {
    stubApi(
      articlesRoute(() => [
        article({ id: 1, analysis: analysis({ relevance: 5, importance: 2 }) }),
      ]),
    );
    await renderWall();

    const card = screen.getByRole("article");
    expect(card.textContent).toContain("Personal relevance");
    expect(card.textContent).toContain("5 of 5");
    expect(card.textContent).toContain("Importance");
    expect(card.textContent).toContain("2 of 5");
  });
});

describe("rotation", () => {
  it("shows at most nine cards and changes the page every 20 seconds", async () => {
    stubApi(articlesRoute(() => many(20)));
    await renderWall();

    expect(titles()).toHaveLength(9);
    expect(titles()[0]).toBe("Story 1");
    expect(screen.getByText("Page 1 of 3")).toBeTruthy();

    await advance(ROTATION_INTERVAL_MS - 1);
    expect(titles()[0]).toBe("Story 1");

    await advance(1);
    expect(titles()[0]).toBe("Story 10");
    expect(titles()).toHaveLength(9);

    await advance(ROTATION_INTERVAL_MS);
    expect(titles()).toEqual(["Story 19", "Story 20"]);

    await advance(ROTATION_INTERVAL_MS);
    expect(titles()[0]).toBe("Story 1");
  });

  it("stays on valid pages when an update shrinks the list", async () => {
    let items = many(20);
    stubApi(articlesRoute(() => items));
    await renderWall();
    await advance(ROTATION_INTERVAL_MS * 2);
    expect(screen.getByText("Page 3 of 3")).toBeTruthy();

    items = many(4);
    await advance(POLL_INTERVAL_MS - ROTATION_INTERVAL_MS * 2);

    expect(titles()).toHaveLength(4);
    expect(screen.queryByText(/^Page /)).toBeNull();
  });
});

describe("highlighting", () => {
  const parsed = (fixture: ArticleFixture) => parseArticlePage(page([fixture])).items[0]!;
  const now = NOW.getTime();

  it("requires an age below three hours and relevance of at least 4", () => {
    const fresh = { published_at: ago(HIGHLIGHT_WINDOW_MS - 1) };
    expect(isHighlighted(parsed(article({ ...fresh, analysis: analysis({ relevance: 4 }) })), now)).toBe(true);
    expect(isHighlighted(parsed(article({ ...fresh, analysis: analysis({ relevance: 3 }) })), now)).toBe(false);
    expect(
      isHighlighted(
        parsed(article({ published_at: ago(HIGHLIGHT_WINDOW_MS), analysis: analysis({ relevance: 5 }) })),
        now,
      ),
    ).toBe(false);
  });

  it("falls back to the collection time for a missing or future date", () => {
    const relevant = { analysis: analysis({ relevance: 5 }) };
    expect(
      isHighlighted(parsed(article({ ...relevant, published_at: null, collected_at: ago(HOUR) })), now),
    ).toBe(true);
    expect(
      isHighlighted(
        parsed(
          article({
            ...relevant,
            published_at: new Date(now + 24 * HOUR).toISOString(),
            collected_at: ago(5 * HOUR),
          }),
        ),
        now,
      ),
    ).toBe(false);
  });

  it("marks highlighted cards in text and drops the mark as time passes", async () => {
    stubApi(
      articlesRoute(() => [
        article({ id: 1, published_at: ago(3 * HOUR - 10_000), analysis: analysis({ relevance: 5 }) }),
        article({ id: 2, published_at: ago(5 * HOUR), analysis: analysis({ relevance: 5 }) }),
      ]),
    );
    await renderWall();

    const [fresh, old] = screen.getAllByRole("article");
    expect(fresh?.textContent).toContain("New & relevant");
    expect(old?.textContent).not.toContain("New & relevant");

    await advance(ROTATION_INTERVAL_MS);

    expect(screen.queryByText("New & relevant")).toBeNull();
  });
});

describe("updates", () => {
  it("checks for updates every 60 seconds and shows new articles", async () => {
    let items = [article({ id: 1, title: "Old" })];
    const calls = stubApi(articlesRoute(() => items));
    await renderWall();
    expect(articleRequests(calls)).toHaveLength(1);

    items = [article({ id: 2, title: "Fresh" })];
    await advance(POLL_INTERVAL_MS - 1);
    expect(articleRequests(calls)).toHaveLength(1);

    await advance(1);
    expect(articleRequests(calls)).toHaveLength(2);
    expect(titles()).toEqual(["Fresh"]);
  });

  it("keeps the last data with a hint on API errors and recovers", async () => {
    let failing = false;
    stubApi(
      articlesRoute(() => (failing ? json({ detail: "boom" }, 500) : [article({ id: 1, title: "Kept" })])),
    );
    await renderWall();
    expect(screen.getByRole("status").textContent).toBe("");

    failing = true;
    await advance(POLL_INTERVAL_MS);
    expect(titles()).toEqual(["Kept"]);
    expect(screen.getByRole("status").textContent).toMatch(/^Update failed\. Showing data from /);

    failing = false;
    await advance(POLL_INTERVAL_MS);
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("retries by itself after a failed first load", async () => {
    let failing = true;
    stubApi(
      articlesRoute(() => (failing ? json({ detail: "boom" }, 500) : [article({ id: 1, title: "Back" })])),
    );
    await renderWall();
    expect(screen.getByRole("alert").textContent).toBe(
      "News could not be loaded. Trying again automatically.",
    );

    failing = false;
    await advance(POLL_INTERVAL_MS);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(titles()).toEqual(["Back"]);
  });

  it("treats a request that never answers as failed", async () => {
    let hanging = false;
    stubApi((url) => {
      if (url.pathname !== "/api/articles") return undefined;
      if (hanging) return new Promise<Response>(() => undefined);
      return json(page([article({ id: 1, title: "Kept" })]));
    });
    await renderWall();

    hanging = true;
    await advance(POLL_INTERVAL_MS); // starts the request that hangs
    expect(screen.getByRole("status").textContent).toBe("");

    await advance(POLL_INTERVAL_MS);
    expect(titles()).toEqual(["Kept"]);
    expect(screen.getByRole("status").textContent).toMatch(/^Update failed/);
  });

  it("catches up when the tab becomes visible, but not while hidden", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const calls = stubApi(articlesRoute(() => many(1)));
    await renderWall();
    expect(articleRequests(calls)).toHaveLength(1);

    document.dispatchEvent(new Event("visibilitychange"));
    await advance(0);
    expect(articleRequests(calls)).toHaveLength(1);

    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await advance(0);
    expect(articleRequests(calls)).toHaveLength(2);
  });

  it("stops polling after unmounting", async () => {
    const calls = stubApi(articlesRoute(() => many(1)));
    const { unmount } = render(
      <LanguageProvider>
        <NewsWall />
      </LanguageProvider>,
    );
    await advance(0);
    unmount();

    await advance(POLL_INTERVAL_MS * 2);

    expect(articleRequests(calls)).toHaveLength(1);
  });
});

describe("language", () => {
  it("follows the stored language setting", async () => {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "de");
    const calls = stubApi(
      articlesRoute(() => [
        article({ id: 1, published_at: ago(HOUR), analysis: analysis({ relevance: 5 }) }),
      ]),
    );
    await renderWall();

    expect(articleRequests(calls)[0]?.searchParams.get("lang")).toBe("de");
    expect(screen.getByText("Neu & relevant")).toBeTruthy();
    expect(screen.getByRole("article").textContent).toContain("Persönliche Relevanz");
  });
});

describe("language change", () => {
  function SwitchToGerman() {
    const { setLanguage } = useLanguage();
    return <button onClick={() => setLanguage("de")}>switch</button>;
  }

  it("reloads the articles in the new language while running", async () => {
    const calls = stubApi(articlesRoute(() => many(1)));
    render(
      <LanguageProvider>
        <NewsWall />
        <SwitchToGerman />
      </LanguageProvider>,
    );
    await advance(0);
    expect(articleRequests(calls).at(-1)?.searchParams.get("lang")).toBe("en");

    fireEvent.click(screen.getByRole("button", { name: "switch" }));
    await advance(0);

    expect(articleRequests(calls).at(-1)?.searchParams.get("lang")).toBe("de");
    expect(screen.getByRole("article").textContent).toContain("Persönliche Relevanz");
  });
});

describe("settings overlay", () => {
  it("is reachable by keyboard and returns focus when closed", async () => {
    stubApi(articlesRoute(() => many(1)));
    const user = setup();
    await renderWall();
    const trigger = screen.getByRole("button", { name: "Wall settings" });

    await user.tab();
    expect(document.activeElement).toBe(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    await user.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog", { name: "Wall settings" });
    expect(document.activeElement).toBe(within(dialog).getByLabelText("Minimum relevance"));
    expect(trigger.getAttribute("aria-expanded")).toBe("true");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("stores the minimum relevance and reloads with it", async () => {
    const calls = stubApi(articlesRoute(() => many(1)));
    const user = setup();
    await renderWall();

    await user.tab();
    await user.keyboard("{Enter}");
    fireEvent.change(screen.getByLabelText("Minimum relevance"), { target: { value: "4" } });
    await advance(0);

    expect(window.localStorage.getItem(MIN_RELEVANCE_STORAGE_KEY)).toBe("4");
    expect(articleRequests(calls).at(-1)?.searchParams.get("min_relevance")).toBe("4");
  });

  it.each([
    ["3", "3"],
    ["9", "1"],
    ["abc", "1"],
  ])("starts from the stored value %s as %s", async (stored, expected) => {
    window.localStorage.setItem(MIN_RELEVANCE_STORAGE_KEY, stored);
    const calls = stubApi(articlesRoute(() => many(1)));
    await renderWall();

    expect(articleRequests(calls)[0]?.searchParams.get("min_relevance")).toBe(expected);
  });

  it("offers a way back to the dashboard", async () => {
    stubApi(articlesRoute(() => many(1)));
    const user = setup();
    await renderWall();

    await user.tab();
    await user.keyboard("{Enter}");

    expect(screen.getByRole("link", { name: "Exit News Wall" }).getAttribute("href")).toBe(
      "#/overview",
    );
  });

  it("toggles when the wall is clicked", async () => {
    stubApi(articlesRoute(() => many(1)));
    await renderWall();

    fireEvent.click(screen.getByRole("article"));
    expect(screen.getByRole("dialog")).toBeTruthy();

    fireEvent.click(screen.getByRole("article"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("hides itself after being idle, without bringing the trigger back", async () => {
    stubApi(articlesRoute(() => many(1)));
    await renderWall();
    fireEvent.click(screen.getByRole("article"));

    await advance(SETTINGS_IDLE_MS - 1);
    fireEvent.keyDown(document, { key: "ArrowDown" }); // activity restarts the wait
    await advance(SETTINGS_IDLE_MS - 1);
    expect(screen.getByRole("dialog")).toBeTruthy();

    await advance(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(document.body);
  });

  it("releases focus from an idle trigger", async () => {
    stubApi(articlesRoute(() => many(1)));
    const user = setup();
    await renderWall();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button"));

    await advance(SETTINGS_IDLE_MS);

    expect(document.activeElement).toBe(document.body);
  });

  it("keeps rotating while open", async () => {
    stubApi(articlesRoute(() => many(20)));
    await renderWall();
    fireEvent.click(screen.getByRole("article", { name: "Story 1" }));

    await advance(ROTATION_INTERVAL_MS);

    expect(titles()[0]).toBe("Story 10");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});
