import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../i18n/language";
import { article, page } from "../test/articles";
import { json, stubApi, type Call } from "../test/fetch";
import type { Rating } from "./api";
import { FeedbackControls } from "./FeedbackControls";
import { Overview } from "./Overview";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function english() {
  vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
}

function renderControls(feedback: Rating | null, articleId = 7) {
  const view = render(
    <LanguageProvider>
      <FeedbackControls articleId={articleId} feedback={feedback} />
    </LanguageProvider>,
  );
  return {
    ...view,
    group: () => within(screen.getByRole("group", { name: "Relevance feedback" })),
    rerenderWith: (next: Rating | null) =>
      view.rerender(
        <LanguageProvider>
          <FeedbackControls articleId={articleId} feedback={next} />
        </LanguageProvider>,
      ),
  };
}

/** Answers PUT/DELETE on the feedback endpoint of article 7. */
function feedbackRoute(answer: (method: string, body: unknown) => Response | Promise<Response>) {
  return (url: URL, init?: RequestInit) =>
    url.pathname === "/api/articles/7/feedback"
      ? answer(init?.method ?? "GET", init?.body ? JSON.parse(String(init.body)) : undefined)
      : undefined;
}

function stored(rating: Rating) {
  return json({
    article_id: 7,
    rating,
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:00:00Z",
  });
}

/** Stores whatever rating was sent. */
function echo(_method: string, body: unknown) {
  return stored((body as { rating: Rating }).rating);
}

function writes(calls: Call[]) {
  return calls
    .filter((call) => call.method !== "GET")
    .map(({ url, method, body }) => ({ url, method, body }));
}

function pressed(button: HTMLElement) {
  return button.getAttribute("aria-pressed");
}

describe("FeedbackControls", () => {
  it("shows the stored feedback", () => {
    english();
    stubApi();
    const { group } = renderControls("relevant");

    expect(pressed(group().getByRole("button", { name: "Relevant" }))).toBe("true");
    expect(pressed(group().getByRole("button", { name: "Not relevant" }))).toBe("false");
    expect(group().getByRole("status").textContent).toBe("Marked as relevant");
  });

  it("shows when there is no feedback and nothing to undo", () => {
    english();
    stubApi();
    const { group } = renderControls(null);

    expect(group().getByRole("status").textContent).toBe("No feedback yet");
    expect(group().getByRole("button", { name: "Undo" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
  });

  it("marks an article as not relevant", async () => {
    english();
    const calls = stubApi(feedbackRoute(echo));
    const user = userEvent.setup();
    const { group } = renderControls(null);

    await user.click(group().getByRole("button", { name: "Not relevant" }));

    await waitFor(() =>
      expect(group().getByRole("status").textContent).toBe("Marked as not relevant"),
    );
    expect(pressed(group().getByRole("button", { name: "Not relevant" }))).toBe("true");
    expect(writes(calls)).toEqual([
      {
        url: "/api/articles/7/feedback",
        method: "PUT",
        body: JSON.stringify({ rating: "irrelevant" }),
      },
    ]);
  });

  it("takes feedback back", async () => {
    english();
    const calls = stubApi(feedbackRoute(() => new Response(null, { status: 204 })));
    const user = userEvent.setup();
    const { group } = renderControls("relevant");

    await user.click(group().getByRole("button", { name: "Undo" }));

    await waitFor(() => expect(group().getByRole("status").textContent).toBe("No feedback yet"));
    expect(pressed(group().getByRole("button", { name: "Relevant" }))).toBe("false");
    expect(writes(calls)).toEqual([
      { url: "/api/articles/7/feedback", method: "DELETE", body: undefined },
    ]);
  });

  it("shows the choice while saving and ignores further clicks", async () => {
    english();
    let finish: (response: Response) => void = () => undefined;
    const calls = stubApi(
      feedbackRoute(() => new Promise<Response>((resolve) => (finish = resolve))),
    );
    const user = userEvent.setup();
    const { group } = renderControls(null);

    await user.click(group().getByRole("button", { name: "Relevant" }));

    expect(group().getByRole("status").textContent).toBe("Saving…");
    expect(pressed(group().getByRole("button", { name: "Relevant" }))).toBe("true");
    const other = group().getByRole("button", { name: "Not relevant" });
    expect(other.getAttribute("aria-disabled")).toBe("true");
    await user.click(other);
    expect(writes(calls)).toHaveLength(1);

    finish(stored("relevant"));
    await waitFor(() =>
      expect(group().getByRole("status").textContent).toBe("Marked as relevant"),
    );
    expect(other.getAttribute("aria-disabled")).toBeNull();
  });

  it("reports a failed save and returns to the stored state", async () => {
    english();
    stubApi(feedbackRoute(() => json({ detail: "Internal Server Error" }, 500)));
    const user = userEvent.setup();
    const { group } = renderControls("relevant");

    await user.click(group().getByRole("button", { name: "Not relevant" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Feedback could not be saved. The stored state is shown.",
    );
    expect(pressed(group().getByRole("button", { name: "Relevant" }))).toBe("true");
    expect(pressed(group().getByRole("button", { name: "Not relevant" }))).toBe("false");
    expect(group().getByRole("status").textContent).toBe("Marked as relevant");
  });

  it("reports a failed undo and keeps the stored feedback", async () => {
    english();
    stubApi(
      feedbackRoute(() => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const user = userEvent.setup();
    const { group } = renderControls("irrelevant");

    await user.click(group().getByRole("button", { name: "Undo" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(pressed(group().getByRole("button", { name: "Not relevant" }))).toBe("true");
  });

  it("clears the error after the next successful save", async () => {
    english();
    let fail = true;
    stubApi(
      feedbackRoute((method, body) => (fail ? json({ detail: "Boom" }, 500) : echo(method, body))),
    );
    const user = userEvent.setup();
    const { group } = renderControls(null);

    await user.click(group().getByRole("button", { name: "Relevant" }));
    await screen.findByRole("alert");
    fail = false;
    await user.click(group().getByRole("button", { name: "Relevant" }));

    await waitFor(() =>
      expect(group().getByRole("status").textContent).toBe("Marked as relevant"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("adopts a newer stored state from a reload", () => {
    english();
    stubApi();
    const { group, rerenderWith } = renderControls(null);

    rerenderWith("irrelevant");

    expect(pressed(group().getByRole("button", { name: "Not relevant" }))).toBe("true");
  });

  it("can be operated with the keyboard", async () => {
    english();
    const calls = stubApi(feedbackRoute(echo));
    const user = userEvent.setup();
    const { group } = renderControls(null);

    await user.tab();
    expect(document.activeElement).toBe(group().getByRole("button", { name: "Relevant" }));
    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(group().getByRole("status").textContent).toBe("Marked as relevant"),
    );
    expect(document.activeElement).toBe(group().getByRole("button", { name: "Relevant" }));
    await user.tab();
    await user.keyboard(" ");
    await waitFor(() =>
      expect(group().getByRole("status").textContent).toBe("Marked as not relevant"),
    );
    expect(writes(calls).map((call) => call.body)).toEqual([
      JSON.stringify({ rating: "relevant" }),
      JSON.stringify({ rating: "irrelevant" }),
    ]);
  });

  it("uses German labels", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("de-DE");
    stubApi();
    render(
      <LanguageProvider>
        <FeedbackControls articleId={7} feedback="irrelevant" />
      </LanguageProvider>,
    );

    const group = within(screen.getByRole("group", { name: "Relevanzfeedback" }));
    expect(pressed(group.getByRole("button", { name: "Nicht relevant" }))).toBe("true");
    expect(group.getByRole("button", { name: "Zurücknehmen" })).toBeTruthy();
    expect(group.getByRole("status").textContent).toBe("Als nicht relevant markiert");
  });
});

describe("feedback in the Editorial Grid", () => {
  it("shows the stored feedback on every card, also without analysis", async () => {
    english();
    stubApi((url) =>
      url.pathname === "/api/articles" && !url.searchParams.has("since")
        ? json(
            page([
              article({ id: 1, feedback: "relevant" }),
              article({ id: 2, status: "new", analysis: null }),
            ]),
          )
        : undefined,
    );
    render(
      <LanguageProvider>
        <Overview />
      </LanguageProvider>,
    );

    const lead = within(await screen.findByRole("article", { name: /Headline 1/ }));
    expect(pressed(lead.getByRole("button", { name: "Relevant" }))).toBe("true");
    expect(
      lead.getByRole("button", { name: "Undo" }).getAttribute("aria-describedby"),
    ).toBe("article-1-title");
    const other = within(screen.getByRole("article", { name: /Headline 2/ }));
    expect(other.getByRole("group", { name: "Relevance feedback" })).toBeTruthy();
    expect(pressed(other.getByRole("button", { name: "Relevant" }))).toBe("false");
  });
});
