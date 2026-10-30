import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LanguageSwitch } from "../i18n/LanguageSwitch";
import { LanguageProvider } from "../i18n/language";
import { analysis, article, page } from "../test/articles";
import { json, stubApi, type Call } from "../test/fetch";
import { Overview } from "./Overview";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderOverview(pollInterval = 60_000) {
  return render(
    <LanguageProvider>
      <LanguageSwitch />
      <Overview pollInterval={pollInterval} />
    </LanguageProvider>,
  );
}

/** Query parameters of the article requests (probes excluded). */
function pageRequests(calls: Call[]): Record<string, string>[] {
  return calls
    .map((call) => new URL(call.url, "http://127.0.0.1"))
    .filter((url) => url.pathname === "/api/articles" && !url.searchParams.has("since"))
    .map((url) => Object.fromEntries(url.searchParams));
}

function articlesRoute(body: unknown, status = 200) {
  return (url: URL) =>
    url.pathname === "/api/articles" && !url.searchParams.has("since")
      ? json(body, status)
      : undefined;
}

describe("Editorial Grid", () => {
  it("shows a lead story followed by a grid of cards", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(articlesRoute(page([article({ id: 1 }), article({ id: 2 }), article({ id: 3 })])));
    renderOverview();

    expect(screen.getByText("Loading articles…")).toBeTruthy();
    const lead = await screen.findByRole("article", { name: /Headline 1/ });
    expect(lead.className).toContain("card--lead");
    const grid = screen.getByRole("list", { name: "Overview" });
    expect(within(grid).getAllByRole("article").map((a) => a.className)).toEqual([
      "card",
      "card",
    ]);
    expect(screen.getByText("3 articles")).toBeTruthy();
  });

  it("shows category, source, date, AI summary, separate scores, and analysis basis", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(
      articlesRoute(
        page([
          article({
            id: 1,
            analysis: analysis({ relevance: 5, importance: 2, secondary_categories: ["Security"] }),
          }),
          article({ id: 2, analysis: analysis({ basis: "excerpt" }) }),
        ]),
      ),
    );
    renderOverview();

    const lead = await screen.findByRole("article", { name: /Headline 1/ });
    const card = within(lead);
    expect(card.getByText("Releases")).toBeTruthy();
    expect(card.getByText("Example Feed")).toBeTruthy();
    expect(card.getByText(/30 Oct 2026/).getAttribute("dateTime")).toBe("2026-10-30T10:00:00Z");
    expect(card.getByText("AI summary")).toBeTruthy();
    expect(card.getByText("A new model was released.")).toBeTruthy();
    expect(card.getByText("Personal relevance").nextElementSibling?.textContent).toBe("5 of 5");
    expect(card.getByText("Importance").nextElementSibling?.textContent).toBe("2 of 5");
    expect(card.getByText("Matches your interest in models.")).toBeTruthy();
    expect(card.getByText("Also: Security")).toBeTruthy();
    expect(card.getByText("Analysis based on the full text")).toBeTruthy();
    const second = screen.getByRole("article", { name: /Headline 2/ });
    expect(within(second).getByText("Analysis based on the feed excerpt")).toBeTruthy();
  });

  it("links titles to the source safely and opens them in a new tab", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(
      articlesRoute(
        page([
          article({ id: 1, url: "https://news.example/a" }),
          article({ id: 2, url: "javascript:alert(1)" }),
        ]),
      ),
    );
    renderOverview();

    const link = await screen.findByRole("link", { name: /Headline 1/ });
    expect(link.getAttribute("href")).toBe("https://news.example/a");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.textContent).toContain("(opens in a new tab)");
    // A non-http(s) URL is never a link; the title stays plain text.
    expect(screen.queryByRole("link", { name: /Headline 2/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "Headline 2" })).toBeTruthy();
  });

  it("renders untrusted article content only as text", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const marker = window as unknown as { pwned?: boolean };
    stubApi(
      articlesRoute(
        page([
          article({
            id: 1,
            title: '<img src=x onerror="window.pwned=true">Evil',
            analysis: analysis({ summary: "<b>bold</b> <script>window.pwned=true</script>" }),
          }),
          article({
            id: 2,
            status: "new",
            analysis: null,
            excerpt: '<p>Plain <img src=x onerror="window.pwned=true"> text</p>',
          }),
        ]),
      ),
    );
    const { container } = renderOverview();

    await screen.findByText('<img src=x onerror="window.pwned=true">Evil', { exact: false });
    expect(screen.getByText("<b>bold</b> <script>window.pwned=true</script>")).toBeTruthy();
    expect(screen.getByText("Plain text")).toBeTruthy();
    expect(container.querySelector("img, script, b")).toBeNull();
    expect(marker.pwned).toBeUndefined();
  });

  it("marks missing and failed analyses honestly and shows the source excerpt", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(
      articlesRoute(
        page([
          article({ id: 1 }),
          article({ id: 2, status: "new", analysis: null }),
          article({ id: 3, status: "failed", analysis: null, excerpt: null }),
          article({ id: 4, status: "processing", analysis: null, published_at: null }),
        ]),
      ),
    );
    renderOverview();

    const pending = within(await screen.findByRole("article", { name: /Headline 2/ }));
    expect(pending.getByText("Not analyzed yet")).toBeTruthy();
    expect(pending.getByText("Excerpt from the source")).toBeTruthy();
    expect(pending.getByText("Excerpt 2")).toBeTruthy();
    expect(pending.queryByText("AI summary")).toBeNull();
    const failed = within(screen.getByRole("article", { name: /Headline 3/ }));
    expect(failed.getByText("Analysis failed")).toBeTruthy();
    expect(failed.queryByText("Excerpt from the source")).toBeNull();
    const processing = within(screen.getByRole("article", { name: /Headline 4/ }));
    expect(processing.getByText("Analysis in progress")).toBeTruthy();
    expect(processing.getByText(/^Collected /)).toBeTruthy(); // no publication date
  });
});

describe("states", () => {
  it("shows an empty state without filters", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(articlesRoute(page([])));
    renderOverview();

    expect(await screen.findByText("No articles yet")).toBeTruthy();
  });

  it("shows no results with filters and can reset them", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi(articlesRoute(page([])));
    renderOverview();
    await screen.findByText("No articles yet");

    await user.selectOptions(screen.getByLabelText("Category"), "Security");
    expect(
      await screen.findByText("No articles match the current search and filters."),
    ).toBeTruthy();
    const results = screen.getByText(/No articles match/).closest("div") as HTMLElement;
    await user.click(within(results).getByRole("button", { name: "Reset filters" }));

    await screen.findByText("No articles yet");
    expect(pageRequests(calls).at(-1)).not.toHaveProperty("category");
    expect((screen.getByLabelText("Category") as HTMLSelectElement).value).toBe("");
  });

  it("shows an error with retry", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    let fail = true;
    stubApi((url) =>
      url.pathname === "/api/articles"
        ? fail
          ? json({ detail: "boom" }, 500)
          : json(page([article({ id: 1 })]))
        : undefined,
    );
    renderOverview();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Articles could not be loaded.");
    expect(alert.textContent).not.toContain("boom"); // only validation details are shown
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("article", { name: /Headline 1/ })).toBeTruthy();
  });

  it("shows validation details from the API", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    stubApi(articlesRoute({ detail: "search must have at most 20 terms" }, 422));
    renderOverview();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "search must have at most 20 terms",
    );
  });
});

describe("search, filters, sorting, and pages", () => {
  it("sends search, filters, and sort order to the article API", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi(articlesRoute(page([article({ id: 1 })])));
    renderOverview();
    await screen.findByRole("article");

    await user.type(screen.getByLabelText("Search"), "open source");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.selectOptions(screen.getByLabelText("Category"), "Use Cases");
    await user.selectOptions(screen.getByLabelText("Minimum relevance"), "4");
    await user.selectOptions(screen.getByLabelText("Sort by"), "relevance");
    await user.type(screen.getByLabelText("Published from"), "2026-10-01");
    await user.type(screen.getByLabelText("Published until"), "2026-10-31");

    await waitFor(() =>
      expect(pageRequests(calls).at(-1)).toMatchObject({
        lang: "en",
        q: "open source",
        category: "Use Cases",
        min_relevance: "4",
        sort: "relevance",
        limit: "25",
      }),
    );
    const last = pageRequests(calls).at(-1) ?? {};
    expect(new Date(last.published_from ?? "").getDate()).toBe(1);
    expect(new Date(last.published_to ?? "").getDate()).toBe(31);
    expect(new Date(last.published_to ?? "").getHours()).toBe(23);
  });

  it("rejects an inverted period without querying it", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi(articlesRoute(page([article({ id: 1 })])));
    renderOverview();
    await screen.findByRole("article");

    await user.type(screen.getByLabelText("Published from"), "2026-10-31");
    await user.type(screen.getByLabelText("Published until"), "2026-10-01");

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The start date must not be after the end date.",
    );
    expect(screen.getByLabelText("Published until").getAttribute("aria-invalid")).toBe("true");
    expect(pageRequests(calls).some((params) => "published_to" in params)).toBe(false);
  });

  it("pages through results; only the first page has a lead story", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi((url) =>
      url.pathname === "/api/articles"
        ? json(page([article({ id: url.searchParams.get("offset") ? 30 : 1 })], 30))
        : undefined,
    );
    renderOverview();
    await screen.findByRole("article", { name: /Headline 1/ });
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(within(pages).getByText("Page 1 of 2")).toBeTruthy();
    expect(
      (within(pages).getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled,
    ).toBe(true);

    await user.click(within(pages).getByRole("button", { name: "Next page" }));

    const second = await screen.findByRole("article", { name: /Headline 30/ });
    expect(second.className).not.toContain("card--lead");
    expect(pageRequests(calls).at(-1)).toMatchObject({ offset: "25" });
    expect(screen.getByText("Page 2 of 2")).toBeTruthy();
  });

  it("keeps keyboard focus in the results after changing the page", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    stubApi((url) =>
      url.pathname === "/api/articles"
        ? json(page([article({ id: url.searchParams.get("offset") ? 30 : 1 })], 30))
        : undefined,
    );
    renderOverview();
    await screen.findByRole("article", { name: /Headline 1/ });

    screen.getByRole("button", { name: "Next page" }).focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("article", { name: /Headline 30/ });

    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByText("30 articles")),
    );
    expect(document.activeElement).not.toBe(document.body);
  });

  it("reloads in the new language when it is switched", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi(articlesRoute(page([article({ id: 1 })])));
    renderOverview();
    await screen.findByText("AI summary");

    await user.click(screen.getByRole("button", { name: "DE – Deutsch" }));

    expect(await screen.findByText("KI-Zusammenfassung")).toBeTruthy();
    expect(screen.getByText("Persönliche Relevanz")).toBeTruthy();
    expect(pageRequests(calls).map((params) => params.lang)).toEqual(["en", "de"]);
    expect(calls.every((call) => call.method === "GET")).toBe(true);
  });
});

describe("polling", () => {
  function probes(calls: Call[]) {
    return calls
      .map((call) => new URL(call.url, "http://127.0.0.1"))
      .filter((url) => url.searchParams.has("since"))
      .map((url) => Object.fromEntries(url.searchParams));
  }

  it("probes for changes and reloads the page only when something changed", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    let changed = false;
    let title = "Old headline";
    const calls = stubApi((url) => {
      if (url.pathname !== "/api/articles") return undefined;
      if (url.searchParams.has("since")) {
        return json(page(changed ? [article({ id: 9 })] : [], changed ? 1 : 0));
      }
      return json(page([article({ id: 1, title })]));
    });
    renderOverview(40);
    await screen.findByText("Old headline");

    await waitFor(() => expect(probes(calls).length).toBeGreaterThanOrEqual(2));
    expect(pageRequests(calls)).toHaveLength(1); // nothing changed: no reload
    expect(probes(calls)[0]).toMatchObject({
      since: "2026-10-30T12:00:00+00:00",
      limit: "1",
      lang: "en",
    });

    title = "New headline";
    changed = true;
    expect(await screen.findByText("New headline")).toBeTruthy();
  });

  it("pauses while the tab is hidden and checks again when it is visible", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const calls = stubApi(
      (url) => (url.searchParams.has("since") ? json(page([], 0)) : undefined),
      articlesRoute(page([article({ id: 1 })])),
    );
    renderOverview(30);
    await screen.findByRole("article");

    await act(() => new Promise((resolve) => setTimeout(resolve, 150)));
    expect(probes(calls)).toHaveLength(0);

    visibility.mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(probes(calls).length).toBeGreaterThanOrEqual(1));
  });

  it("keeps the shown articles and marks them stale when an update fails", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    let broken = false;
    stubApi((url) => {
      if (url.pathname !== "/api/articles") return undefined;
      if (broken) return json({ detail: "down" }, 503);
      return json(page([article({ id: 1 })]));
    });
    renderOverview(40);
    await screen.findByRole("article", { name: /Headline 1/ });

    broken = true;

    expect(
      await screen.findByText("Updating failed. Showing the last loaded articles."),
    ).toBeTruthy();
    expect(screen.getByRole("article", { name: /Headline 1/ })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("keyboard", () => {
  it("reaches search, filters, article links, and feedback in order", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    stubApi(articlesRoute(page([article({ id: 1 })], 30)));
    render(
      <LanguageProvider>
        <Overview />
      </LanguageProvider>,
    );
    await screen.findByRole("article");

    const order = [
      screen.getByLabelText("Search"),
      screen.getByRole("button", { name: "Search" }),
      screen.getByLabelText("Category"),
      screen.getByLabelText("Minimum relevance"),
      screen.getByLabelText("Published from"),
      screen.getByLabelText("Published until"),
      screen.getByLabelText("Sort by"),
      screen.getByRole("button", { name: "Reset filters" }),
      screen.getByRole("link", { name: /Headline 1/ }),
      screen.getByRole("button", { name: "Relevant" }),
      screen.getByRole("button", { name: "Not relevant" }),
      screen.getByRole("button", { name: "Undo" }),
      screen.getByRole("button", { name: "Next page" }),
    ];
    for (const element of order) {
      await user.tab();
      expect(document.activeElement).toBe(element);
    }
  });

  it("submits the search with Enter", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    const user = userEvent.setup();
    const calls = stubApi(articlesRoute(page([article({ id: 1 })])));
    render(
      <LanguageProvider>
        <Overview />
      </LanguageProvider>,
    );
    await screen.findByRole("article");

    await user.type(screen.getByLabelText("Search"), "agents{Enter}");

    await waitFor(() => expect(pageRequests(calls).at(-1)).toMatchObject({ q: "agents" }));
  });
});
