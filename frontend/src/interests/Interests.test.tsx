import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LanguageProvider } from "../i18n/language";
import { json, stubApi, type Call, type Route } from "../test/fetch";
import { Interests } from "./Interests";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function english() {
  vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
}

function renderView() {
  return render(
    <LanguageProvider>
      <Interests />
    </LanguageProvider>,
  );
}

interface StoredInterest {
  id: number;
  topic: string;
  weight: string;
}

interface StoredLearned {
  topic: string;
  score: number;
  relevant: number;
  irrelevant: number;
  ratings: number;
}

function interest(id: number, topic: string, weight = "medium") {
  return {
    id,
    topic,
    weight,
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:00:00Z",
  };
}

const LEARNED: StoredLearned[] = [
  { topic: "agents", score: 3, relevant: 3, irrelevant: 0, ratings: 3 },
  { topic: "crypto", score: -2, relevant: 1, irrelevant: 3, ratings: 4 },
];

/**
 * A small in-memory backend for `/api/interests` and `/api/preferences`.
 * `fail` makes the named request answer with an error instead.
 */
function backend(
  options: {
    interests?: StoredInterest[];
    learned?: StoredLearned[];
    lastResetAt?: string | null;
    fail?: (method: string, path: string) => Response | undefined;
  } = {},
): Route {
  let interests = [...(options.interests ?? [])];
  let learned = [...(options.learned ?? [])];
  let lastResetAt = options.lastResetAt ?? null;
  let nextId = 100;

  return (url, init) => {
    const method = init?.method ?? "GET";
    const path = url.pathname;
    if (!path.startsWith("/api/interests") && path !== "/api/preferences") {
      return undefined;
    }
    const failure = options.fail?.(method, path);
    if (failure) return failure;
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string>) : {};

    if (path === "/api/preferences") {
      if (method === "DELETE") {
        learned = [];
        lastResetAt = "2026-10-30T13:00:00Z";
        return new Response(null, { status: 204 });
      }
      return json({ learned, last_reset_at: lastResetAt });
    }
    if (path === "/api/interests") {
      if (method === "POST") {
        if (interests.some((item) => item.topic === body.topic)) {
          return json({ detail: "An interest with this topic already exists" }, 409);
        }
        const created = interest(nextId++, body.topic!, body.weight);
        interests.push(created);
        return json(created, 201);
      }
      return json(interests.map((item) => interest(item.id, item.topic, item.weight)));
    }
    const id = Number(path.split("/").pop());
    const existing = interests.find((item) => item.id === id);
    if (!existing) return json({ detail: "Interest not found" }, 404);
    if (method === "PATCH") {
      existing.weight = body.weight!;
      return json(interest(existing.id, existing.topic, existing.weight));
    }
    if (method === "DELETE") {
      interests = interests.filter((item) => item.id !== id);
      return new Response(null, { status: 204 });
    }
    return undefined;
  };
}

function writes(calls: Call[]) {
  return calls.filter((call) => call.method !== "GET");
}

function manual() {
  return within(screen.getByRole("region", { name: "Manual interests" }));
}

function learnedSection() {
  return within(screen.getByRole("region", { name: "Learned preferences" }));
}

describe("Interests view", () => {
  it("shows the area title and separate sections for manual and learned interests", async () => {
    english();
    stubApi(
      backend({
        interests: [interest(1, "LLM security", "high")],
        learned: LEARNED,
        lastResetAt: "2026-10-01T08:30:00Z",
      }),
    );
    renderView();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Interests & personalization",
    );
    expect(await manual().findByText("LLM security")).toBeTruthy();
    const select = manual().getByRole("combobox", { name: "Weight of “LLM security”" });
    expect((select as HTMLSelectElement).value).toBe("high");

    expect(await learnedSection().findByText("agents")).toBeTruthy();
    expect(learnedSection().getByText("Score +3")).toBeTruthy();
    expect(learnedSection().getByText("3 × relevant, 0 × not relevant (3 ratings)")).toBeTruthy();
    expect(learnedSection().getByText("Score -2")).toBeTruthy();
    expect(learnedSection().getByText("1 × relevant, 3 × not relevant (4 ratings)")).toBeTruthy();
    expect(learnedSection().getByText(/^Last reset: /)).toBeTruthy();
    // Learned topics are not listed as manual interests, and vice versa.
    expect(manual().queryByText("agents")).toBeNull();
    expect(learnedSection().queryByText("LLM security")).toBeNull();
  });

  it("shows loading states while the data is requested", () => {
    english();
    stubApi((url) =>
      url.pathname === "/api/interests" || url.pathname === "/api/preferences"
        ? new Promise<Response>(() => {})
        : undefined,
    );
    renderView();

    expect(manual().getByText("Loading interests…")).toBeTruthy();
    expect(learnedSection().getByText("Loading learned preferences…")).toBeTruthy();
  });

  it("shows empty states without a reset button", async () => {
    english();
    stubApi(backend());
    renderView();

    expect(await manual().findByText("No manual interests yet. Add a topic above.")).toBeTruthy();
    expect(await learnedSection().findByText(/^No learned preferences yet\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reset learned preferences" })).toBeNull();
  });

  it("shows error states and loads again on retry", async () => {
    english();
    let broken = true;
    stubApi(
      backend({
        interests: [interest(1, "Agents")],
        learned: LEARNED,
        fail: (method) => (broken && method === "GET" ? json({ detail: "boom" }, 500) : undefined),
      }),
    );
    const user = userEvent.setup();
    renderView();

    expect((await manual().findByRole("alert")).textContent).toContain(
      "Interests could not be loaded.",
    );
    expect((await learnedSection().findByRole("alert")).textContent).toContain(
      "Learned preferences could not be loaded.",
    );

    broken = false;
    await user.click(manual().getByRole("button", { name: "Try again" }));
    expect(await manual().findByText("Agents")).toBeTruthy();
    await user.click(learnedSection().getByRole("button", { name: "Try again" }));
    expect(await learnedSection().findByText("agents")).toBeTruthy();
  });

  it("uses German texts for a German browser", async () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("de-DE");
    stubApi(backend({ interests: [interest(1, "Agenten", "low")] }));
    renderView();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Interessen & Personalisierung",
    );
    const select = await screen.findByRole("combobox", { name: "Gewichtung von „Agenten“" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Niedrig", "Mittel", "Hoch"]);
  });
});

describe("manual interests", () => {
  it("adds an interest with the chosen weight by keyboard", async () => {
    english();
    const calls = stubApi(backend({ interests: [interest(1, "Agents")] }));
    const user = userEvent.setup();
    renderView();
    await manual().findByText("Agents");

    await user.selectOptions(manual().getByRole("combobox", { name: "Weight" }), "high");
    await user.type(
      manual().getByRole("textbox", { name: "Topic" }),
      "  Open   source models {Enter}",
    );

    expect(await manual().findByText("Open source models")).toBeTruthy();
    expect(writes(calls)).toEqual([
      {
        url: "/api/interests",
        method: "POST",
        body: JSON.stringify({ topic: "Open source models", weight: "high" }),
      },
    ]);
    expect(
      (
        manual().getByRole("combobox", {
          name: "Weight of “Open source models”",
        }) as HTMLSelectElement
      ).value,
    ).toBe("high");
    expect(manual().getByText("“Open source models” added.")).toBeTruthy();
    expect((manual().getByRole("textbox", { name: "Topic" }) as HTMLInputElement).value).toBe("");
    expect((manual().getByRole("combobox", { name: "Weight" }) as HTMLSelectElement).value).toBe(
      "medium",
    );
  });

  it("loads the list after adding while it could not be loaded", async () => {
    english();
    let broken = true;
    stubApi(
      backend({
        fail: (method, path) =>
          broken && method === "GET" && path === "/api/interests"
            ? json({ detail: "boom" }, 500)
            : undefined,
      }),
    );
    const user = userEvent.setup();
    renderView();
    await manual().findByText("Interests could not be loaded.");

    broken = false;
    await user.type(manual().getByRole("textbox", { name: "Topic" }), "Agents{Enter}");

    expect(await manual().findByRole("combobox", { name: "Weight of “Agents”" })).toBeTruthy();
    expect(manual().queryByText("Interests could not be loaded.")).toBeNull();
  });

  it("requires a topic and sends nothing without one", async () => {
    english();
    const calls = stubApi(backend());
    const user = userEvent.setup();
    renderView();
    await manual().findByText(/^No manual interests yet/);

    await user.type(manual().getByRole("textbox", { name: "Topic" }), "   ");
    await user.click(manual().getByRole("button", { name: "Add interest" }));

    expect(manual().getByRole("alert").textContent).toBe("Enter a topic.");
    const input = manual().getByRole("textbox", { name: "Topic" });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(writes(calls)).toEqual([]);
  });

  it("reports a duplicate topic", async () => {
    english();
    stubApi(backend({ interests: [interest(1, "Agents")] }));
    const user = userEvent.setup();
    renderView();
    await manual().findByText("Agents");

    await user.type(manual().getByRole("textbox", { name: "Topic" }), "Agents{Enter}");

    expect((await manual().findByRole("alert")).textContent).toBe("This interest already exists.");
    expect(manual().getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows the API's validation message when adding fails with 422", async () => {
    english();
    stubApi(
      backend({
        fail: (method) =>
          method === "POST"
            ? json({ detail: "At most 100 interests are allowed" }, 422)
            : undefined,
      }),
    );
    const user = userEvent.setup();
    renderView();
    await manual().findByText(/^No manual interests yet/);

    await user.type(manual().getByRole("textbox", { name: "Topic" }), "Agents{Enter}");

    const alert = await manual().findByRole("alert");
    expect(alert.textContent).toContain("The interest could not be added.");
    expect(alert.textContent).toContain("At most 100 interests are allowed");
  });

  it("changes the weight of an interest", async () => {
    english();
    const calls = stubApi(backend({ interests: [interest(1, "Agents", "low")] }));
    const user = userEvent.setup();
    renderView();
    const select = await manual().findByRole("combobox", { name: "Weight of “Agents”" });

    await user.selectOptions(select, "high");

    await waitFor(() => expect(writes(calls)).toHaveLength(1));
    expect(writes(calls)[0]).toEqual({
      url: "/api/interests/1",
      method: "PATCH",
      body: JSON.stringify({ weight: "high" }),
    });
    await waitFor(() => expect(manual().queryByText("Saving…")).toBeNull());
    expect((select as HTMLSelectElement).value).toBe("high");
  });

  it("shows the stored weight again when saving fails", async () => {
    english();
    stubApi(
      backend({
        interests: [interest(1, "Agents", "low")],
        fail: (method) => (method === "PATCH" ? json({ detail: "boom" }, 500) : undefined),
      }),
    );
    const user = userEvent.setup();
    renderView();
    const select = await manual().findByRole("combobox", { name: "Weight of “Agents”" });

    await user.selectOptions(select, "high");

    expect((await manual().findByRole("alert")).textContent).toBe(
      "The weight could not be saved. The stored weight is shown.",
    );
    expect((select as HTMLSelectElement).value).toBe("low");
  });

  it("removes an interest and moves focus to the section heading", async () => {
    english();
    const calls = stubApi(backend({ interests: [interest(1, "Agents"), interest(2, "Robotics")] }));
    const user = userEvent.setup();
    renderView();
    await manual().findByText("Agents");

    await user.click(manual().getByRole("button", { name: "Remove “Agents”" }));

    await waitFor(() => expect(manual().queryByText("Agents")).toBeNull());
    expect(manual().getByText("Robotics")).toBeTruthy();
    expect(writes(calls)).toEqual([{ url: "/api/interests/1", method: "DELETE", body: undefined }]);
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Manual interests" }));
    expect(manual().getByText("“Agents” removed.")).toBeTruthy();
  });

  it("keeps an interest when removing fails", async () => {
    english();
    stubApi(
      backend({
        interests: [interest(1, "Agents")],
        fail: (method) => (method === "DELETE" ? json({ detail: "boom" }, 500) : undefined),
      }),
    );
    const user = userEvent.setup();
    renderView();
    await manual().findByText("Agents");

    await user.click(manual().getByRole("button", { name: "Remove “Agents”" }));

    expect((await manual().findByRole("alert")).textContent).toBe(
      "The interest could not be removed.",
    );
    expect(manual().getByText("Agents")).toBeTruthy();
  });

  it("renders topics as text, not markup", async () => {
    english();
    stubApi(backend({ interests: [interest(1, "<img src=x onerror=alert(1)>")] }));
    renderView();

    expect(await manual().findByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("resetting learned preferences", () => {
  it("asks for confirmation in the page, not with a browser dialog", async () => {
    english();
    const confirmSpy = vi.spyOn(window, "confirm");
    const calls = stubApi(backend({ learned: LEARNED }));
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Reset learned preferences" }));

    const dialog = screen.getByRole("group", {
      name: "Reset all learned preferences? Your manual interests are kept.",
    });
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(writes(calls)).toEqual([]);
  });

  it("cancels with Escape or Cancel and returns focus to the reset button", async () => {
    english();
    const calls = stubApi(backend({ learned: LEARNED }));
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Reset learned preferences" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("group", { name: /^Reset all learned preferences/ })).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Reset learned preferences" }),
    );

    await user.keyboard("{Enter}");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Reset learned preferences" }),
    );
    expect(writes(calls)).toEqual([]);
    expect(learnedSection().getByText("agents")).toBeTruthy();
  });

  it("resets learned preferences after confirmation and keeps manual interests", async () => {
    english();
    const calls = stubApi(
      backend({ interests: [interest(1, "LLM security", "high")], learned: LEARNED }),
    );
    const user = userEvent.setup();
    renderView();
    await manual().findByText("LLM security");

    await user.click(await screen.findByRole("button", { name: "Reset learned preferences" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));

    expect(await learnedSection().findByText(/^No learned preferences yet\./)).toBeTruthy();
    expect(writes(calls)).toEqual([{ url: "/api/preferences", method: "DELETE", body: undefined }]);
    expect(learnedSection().getByText("Learned preferences have been reset.")).toBeTruthy();
    expect(learnedSection().getByText(/^Last reset: /)).toBeTruthy();
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Learned preferences" }),
    );
    expect(manual().getByText("LLM security")).toBeTruthy();
  });

  it("reports a failed reset and keeps the learned preferences", async () => {
    english();
    stubApi(
      backend({
        learned: LEARNED,
        fail: (method, path) =>
          method === "DELETE" && path === "/api/preferences"
            ? json({ detail: "boom" }, 500)
            : undefined,
      }),
    );
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByRole("button", { name: "Reset learned preferences" }));
    await user.click(screen.getByRole("button", { name: "Reset" }));

    expect((await learnedSection().findByRole("alert")).textContent).toBe(
      "Learned preferences could not be reset.",
    );
    expect(learnedSection().getByText("agents")).toBeTruthy();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Reset learned preferences" }),
    );
  });
});
