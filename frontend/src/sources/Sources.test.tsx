import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../i18n/language";
import { RefreshProvider } from "../refresh/RefreshContext";
import { json, stubApi, type Call } from "../test/fetch";
import { Sources } from "./Sources";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function english() {
  vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
}

interface StoredFeed {
  id: number;
  url: string;
  name: string | null;
  enabled: boolean;
  fetch_full_text: boolean;
  created_at: string;
  updated_at: string;
  last_fetched_at: string | null;
  last_error: string | null;
}

function feed(id: number, fields: Partial<StoredFeed> = {}): StoredFeed {
  return {
    id,
    url: `https://feed${id}.example/rss`,
    name: null,
    enabled: true,
    fetch_full_text: false,
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:00:00Z",
    last_fetched_at: null,
    last_error: null,
    ...fields,
  };
}

interface RefreshState {
  running: boolean;
  last_started_at: string | null;
  last_finished_at: string | null;
}

/**
 * A small in-memory backend for `/api/feeds` and `/api/refresh`. `answers`
 * overrides the answer to "METHOD /path" requests.
 */
function backend(
  options: {
    feeds?: StoredFeed[];
    refresh?: RefreshState;
    answers?: Record<string, () => Response | Promise<Response>>;
  } = {},
) {
  const feeds = [...(options.feeds ?? [])];
  const refresh: RefreshState = options.refresh ?? {
    running: false,
    last_started_at: null,
    last_finished_at: null,
  };
  let nextId = 100;
  const calls: Call[] = stubApi((url, init) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${url.pathname}`;
    const override = options.answers?.[key];
    if (override) return override();
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as Partial<StoredFeed>) : {};
    if (key === "GET /api/feeds") return json(feeds);
    if (key === "POST /api/feeds") {
      const created = feed(nextId++, body);
      feeds.push(created);
      return json(created, 201);
    }
    const match = /^\/api\/feeds\/(\d+)$/.exec(url.pathname);
    if (match) {
      const index = feeds.findIndex((item) => item.id === Number(match[1]));
      const current = feeds[index];
      if (!current) return json({ detail: "Feed not found" }, 404);
      if (method === "PATCH") {
        const changed: StoredFeed = { ...current, ...body, id: current.id };
        feeds[index] = changed;
        return json(changed);
      }
      if (method === "DELETE") {
        feeds.splice(index, 1);
        return new Response(null, { status: 204 });
      }
    }
    if (key === "GET /api/refresh") return json(refresh);
    if (key === "POST /api/refresh") {
      refresh.running = true;
      refresh.last_started_at = "2026-10-30T12:10:00Z";
      return json({ status: "started" }, 202);
    }
    return undefined;
  });
  return { calls, feeds, refresh };
}

function renderView(props: { idlePollMs?: number; runningPollMs?: number } = {}) {
  return render(
    <LanguageProvider>
      <RefreshProvider {...props}>
        <Sources />
      </RefreshProvider>
    </LanguageProvider>,
  );
}

function writes(calls: Call[]) {
  return calls.filter((call) => call.method !== "GET");
}

/** The JSON body of the first write request. */
function firstWriteBody(calls: Call[]): unknown {
  return JSON.parse(writes(calls)[0]?.body ?? "{}");
}

function feedsPanel() {
  return screen.getByRole("region", { name: "Feeds" });
}

describe("Sources: feed list", () => {
  it("shows each feed with status, last fetch, and last error as text", async () => {
    english();
    backend({
      feeds: [
        feed(1, {
          name: "OpenAI News",
          last_fetched_at: "2026-10-30T12:00:00Z",
        }),
        feed(2, {
          enabled: false,
          fetch_full_text: true,
          last_fetched_at: "2026-10-30T13:00:00Z",
          last_error: "<img src=x onerror=alert(1)> HTTP 500",
        }),
      ],
    });
    renderView();

    const items = await within(feedsPanel()).findAllByRole("listitem", { name: undefined });
    const first = items.find((item) => item.textContent?.includes("OpenAI News"));
    expect(first?.textContent).toContain("https://feed1.example/rss");
    expect(first?.textContent).toContain("Enabled");
    expect(first?.textContent).toContain("Feed excerpt only");
    expect(first?.textContent).toContain("Last fetched: 30 Oct 2026");

    const second = items.find((item) => item.textContent?.includes("feed2.example"));
    expect(second?.textContent).toContain("Disabled");
    expect(second?.textContent).toContain("Full text");
    const error = within(second!).getByText(/^Last error:/);
    expect(error.textContent).toBe("Last error: <img src=x onerror=alert(1)> HTTP 500");
    expect(document.querySelector("img")).toBeNull(); // rendered as text only
  });

  it("marks feeds that were never fetched", async () => {
    english();
    backend({ feeds: [feed(1)] });
    renderView();

    expect(await screen.findByText("Not fetched yet")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    english();
    backend();
    renderView();

    expect(await screen.findByText("No feeds yet. Add an RSS or Atom feed above.")).toBeTruthy();
  });

  it("shows an error with retry when the list cannot be loaded", async () => {
    english();
    let fail = true;
    backend({
      answers: {
        "GET /api/feeds": () => (fail ? json({ detail: "boom" }, 500) : json([feed(1)])),
      },
    });
    const user = userEvent.setup();
    renderView();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Feeds could not be loaded.");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("https://feed1.example/rss")).toBeTruthy();
  });
});

describe("Sources: adding feeds", () => {
  it("adds a feed with name, enabled state, and full-text opt-in", async () => {
    english();
    const { calls } = backend();
    const user = userEvent.setup();
    renderView();
    await screen.findByText(/No feeds yet/);

    await user.type(screen.getByLabelText("Feed URL"), "  https://new.example/rss ");
    await user.type(screen.getByLabelText("Name (optional)"), "New");
    await user.click(screen.getByLabelText("Fetch full text"));
    await user.click(screen.getByRole("button", { name: "Add feed" }));

    expect(await screen.findByText("“New” added.")).toBeTruthy();
    expect(firstWriteBody(calls)).toEqual({
      url: "https://new.example/rss",
      name: "New",
      enabled: true,
      fetch_full_text: true,
    });
    expect(within(feedsPanel()).getByText("New")).toBeTruthy();
    expect((screen.getByLabelText("Feed URL") as HTMLInputElement).value).toBe("");
  });

  it("shows the terms-of-use hint only while full text is opted in", async () => {
    english();
    backend();
    const user = userEvent.setup();
    renderView();
    const checkbox = screen.getByLabelText("Fetch full text");
    const hint = /terms of use/;

    expect(screen.queryByText(hint)).toBeNull();
    await user.click(checkbox);
    const shown = screen.getByText(hint);
    expect(checkbox.getAttribute("aria-describedby")).toBe(shown.id);
    await user.click(checkbox);
    expect(screen.queryByText(hint)).toBeNull();
  });

  it("requires a URL without calling the API", async () => {
    english();
    const { calls } = backend();
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole("button", { name: "Add feed" }));

    expect(screen.getByRole("alert").textContent).toContain("Enter a feed URL.");
    expect(screen.getByLabelText("Feed URL").getAttribute("aria-invalid")).toBe("true");
    expect(writes(calls)).toHaveLength(0);
  });

  it("shows the API's validation message as text", async () => {
    english();
    backend({
      answers: {
        "POST /api/feeds": () =>
          json(
            { detail: [{ loc: ["body", "url"], msg: "Value error, Unsupported URL scheme: ftp" }] },
            422,
          ),
      },
    });
    const user = userEvent.setup();
    renderView();

    await user.type(screen.getByLabelText("Feed URL"), "ftp://example.com/rss");
    await user.click(screen.getByRole("button", { name: "Add feed" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The feed could not be added.");
    expect(alert.textContent).toContain("Value error, Unsupported URL scheme: ftp");
    expect(screen.getByLabelText("Feed URL").getAttribute("aria-invalid")).toBe("true");
  });

  it("explains a duplicate URL", async () => {
    english();
    backend({
      answers: {
        "POST /api/feeds": () => json({ detail: "A feed with this URL already exists" }, 409),
      },
    });
    const user = userEvent.setup();
    renderView();

    await user.type(screen.getByLabelText("Feed URL"), "https://dup.example/rss");
    await user.click(screen.getByRole("button", { name: "Add feed" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "A feed with this URL already exists.",
    );
  });
});

describe("Sources: editing feeds", () => {
  it("edits name, enabled state, and full-text opt-in", async () => {
    english();
    const { calls } = backend({ feeds: [feed(1, { name: "Old" })] });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Edit “Old”" }));
    const form = screen.getByRole("form", { name: "Edit “Old”" });
    const name = within(form).getByLabelText("Name (optional)");
    expect(document.activeElement).toBe(name);
    await user.clear(name);
    await user.type(name, "Renamed");
    await user.click(within(form).getByLabelText("Enabled"));
    await user.click(within(form).getByLabelText("Fetch full text"));
    expect(within(form).getByText(/terms of use/)).toBeTruthy();
    await user.click(within(form).getByRole("button", { name: "Save" }));

    expect(await screen.findByText("“Renamed” saved.")).toBeTruthy();
    expect(writes(calls)[0]).toMatchObject({ method: "PATCH", url: "/api/feeds/1" });
    expect(firstWriteBody(calls)).toEqual({
      name: "Renamed",
      enabled: false,
      fetch_full_text: true,
    });
    expect(screen.queryByRole("form", { name: /Edit/ })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit “Renamed”" }));
    expect(within(feedsPanel()).getByText("Disabled")).toBeTruthy();
  });

  it("clears the name when the field is emptied", async () => {
    english();
    const { calls } = backend({ feeds: [feed(1, { name: "Old" })] });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Edit “Old”" }));
    await user.clear(screen.getByLabelText("Name (optional)", { selector: "form[aria-label] input" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(firstWriteBody(calls)).toMatchObject({ name: null });
  });

  it("shows validation errors and keeps the form open", async () => {
    english();
    backend({
      feeds: [feed(1, { name: "Old" })],
      answers: {
        "PATCH /api/feeds/1": () =>
          json({ detail: [{ msg: "String should have at most 200 characters" }] }, 422),
      },
    });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Edit “Old”" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The feed could not be saved.");
    expect(alert.textContent).toContain("String should have at most 200 characters");
    expect(screen.getByRole("form", { name: "Edit “Old”" })).toBeTruthy();
  });

  it("cancels with Escape without saving", async () => {
    english();
    const { calls } = backend({ feeds: [feed(1, { name: "Old" })] });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Edit “Old”" }));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("form", { name: /Edit/ })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit “Old”" }));
    expect(writes(calls)).toHaveLength(0);
  });
});

describe("Sources: removing feeds", () => {
  it("removes a feed after confirmation", async () => {
    english();
    const { calls } = backend({ feeds: [feed(1, { name: "Gone" }), feed(2)] });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Remove “Gone”" }));
    const confirm = screen.getByRole("group", {
      name: "Remove “Gone”? Articles already collected from it are kept.",
    });
    expect(document.activeElement).toBe(within(confirm).getByRole("button", { name: "Cancel" }));
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));

    expect(await screen.findByText("“Gone” removed.")).toBeTruthy();
    expect(writes(calls)).toEqual([{ url: "/api/feeds/1", method: "DELETE", body: undefined }]);
    expect(within(feedsPanel()).queryByText("Gone")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Feeds" }));
  });

  it("cancels the removal with Escape", async () => {
    english();
    const { calls } = backend({ feeds: [feed(1, { name: "Kept" })] });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Remove “Kept”" }));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("group")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Remove “Kept”" }));
    expect(writes(calls)).toHaveLength(0);
  });

  it("reports a failed removal and keeps the feed", async () => {
    english();
    backend({
      feeds: [feed(1, { name: "Kept" })],
      answers: { "DELETE /api/feeds/1": () => json({ detail: "boom" }, 500) },
    });
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Remove “Kept”" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect((await screen.findByRole("alert")).textContent).toBe("The feed could not be removed.");
    expect(within(feedsPanel()).getByText("Kept")).toBeTruthy();
  });
});

describe("Sources: manual refresh", () => {
  it("starts a refresh with POST /api/refresh and shows it running", async () => {
    english();
    const { calls } = backend();
    const user = userEvent.setup();
    renderView();
    await screen.findByText("Last completed refresh: none yet");

    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    expect(
      await screen.findByText("Refresh started. The feeds below update when it has finished."),
    ).toBeTruthy();
    expect(writes(calls)).toEqual([{ url: "/api/refresh", method: "POST", body: undefined }]);
    expect(await screen.findByText("A refresh is running…")).toBeTruthy();
  });

  it("explains that a refresh is already running (409)", async () => {
    english();
    backend({
      answers: {
        "POST /api/refresh": () => json({ detail: "A refresh is already running" }, 409),
      },
    });
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    expect(
      await screen.findByText("A refresh is already running. Please wait until it has finished."),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports a failed start", async () => {
    english();
    backend({ answers: { "POST /api/refresh": () => json({ detail: "boom" }, 500) } });
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The refresh could not be started.",
    );
  });

  it("reloads the feeds when the refresh has finished", async () => {
    english();
    const { refresh, feeds } = backend({ feeds: [feed(1)] });
    renderView({ runningPollMs: 20, idlePollMs: 60_000 });
    const user = userEvent.setup();
    expect(await screen.findByText("Not fetched yet")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Refresh now" }));
    await screen.findByText("A refresh is running…");
    act(() => {
      feeds[0] = { ...feed(1), last_fetched_at: "2026-10-30T12:11:00Z", last_error: "Timeout" };
      refresh.running = false;
      refresh.last_finished_at = "2026-10-30T12:11:00Z";
    });

    expect(await screen.findByText("Last error: Timeout")).toBeTruthy();
    expect(screen.getByText(/^Last fetched: 30 Oct 2026/)).toBeTruthy();
    expect(screen.queryByText("A refresh is running…")).toBeNull();
  });
});

describe("Sources: background reload", () => {
  it("keeps an open edit form when a refresh finishes", async () => {
    english();
    let stored = [feed(1, { name: "Old" })];
    // Answer with a delay, as a real network would, so a reload that shows
    // the loading state would unmount the form.
    const { refresh } = backend({
      answers: {
        "GET /api/feeds": () =>
          new Promise((resolve) => setTimeout(() => resolve(json(stored)), 30)),
      },
    });
    renderView({ runningPollMs: 20, idlePollMs: 20 });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Edit “Old”" }));
    const name = screen.getByRole("form", { name: "Edit “Old”" }).querySelector("input");
    await user.clear(name!);
    await user.type(name!, "Draft");
    act(() => {
      stored = [{ ...feed(1, { name: "Old" }), last_error: "HTTP 503" }];
      refresh.last_finished_at = "2026-10-30T12:11:00Z";
    });

    expect(await screen.findByText("Last error: HTTP 503")).toBeTruthy();
    expect(screen.queryByText("Loading feeds…")).toBeNull();
    const form = screen.getByRole("form", { name: "Edit “Old”" });
    expect((within(form).getByLabelText("Name (optional)") as HTMLInputElement).value).toBe(
      "Draft",
    );
  });
});

describe("Sources: German texts", () => {
  it("uses German labels", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("de-DE");
    backend({ feeds: [feed(1, { last_error: "HTTP 404" })] });
    renderView();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Quellen");
    expect(screen.getByRole("button", { name: "Jetzt abrufen" })).toBeTruthy();
    expect(await screen.findByText("Letzter Fehler: HTTP 404")).toBeTruthy();
    expect(screen.getByText("Letzter abgeschlossener Abruf: noch keiner")).toBeTruthy();
  });
});
