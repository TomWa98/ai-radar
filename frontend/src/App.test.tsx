import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { AppShell } from "./shell/AppShell";
import type { NavItem } from "./shell/navigation";

function stubHealth(response: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(response));
}

const healthy = () =>
  Promise.resolve(
    new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("App shell", () => {
  it("has the top bar, labelled navigation, and main landmarks", async () => {
    stubHealth(healthy);
    render(<App />);

    expect(screen.getByRole("banner").textContent).toContain("AI Radar");
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "No view available yet",
    );
    await screen.findByText("Backend reachable");
  });

  it("shows unimplemented destinations as disabled and hides Articles", async () => {
    stubHealth(healthy);
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Main navigation" });

    for (const label of ["Overview", "Interests", "Sources", "News Wall"]) {
      const item = within(nav).getByText(label).closest("[aria-disabled]");
      expect(item?.getAttribute("aria-disabled")).toBe("true");
    }
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
    expect(within(nav).queryByText("Articles")).toBeNull();
    await screen.findByText("Backend reachable");
  });
});

describe("backend status", () => {
  it("reports a check in progress, then success", async () => {
    stubHealth(healthy);
    render(<App />);

    expect(screen.getByRole("status").textContent).toBe("Checking backend…");
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Backend reachable"),
    );
  });

  it("reports an unreachable backend", async () => {
    stubHealth(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Backend unreachable"),
    );
  });

  it("reports an error response as unreachable", async () => {
    stubHealth(() => Promise.resolve(new Response("", { status: 503 })));
    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Backend unreachable"),
    );
  });
});

describe("keyboard and focus", () => {
  const ITEMS: NavItem[] = [
    { id: "overview", label: "Overview", available: true },
    { id: "interests", label: "Interests", available: true },
    { id: "sources", label: "Sources", available: false },
  ];

  it("starts with a skip link that moves focus to the main area", async () => {
    stubHealth(healthy);
    const user = userEvent.setup();
    render(<App />);

    await user.tab();
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(document.activeElement).toBe(skip);
    expect(skip.getAttribute("href")).toBe("#main");
    expect(screen.getByRole("main").id).toBe("main");
    expect(screen.getByRole("main").tabIndex).toBe(-1); // focusable target
    await screen.findByText("Backend reachable");
  });

  it("skip link focuses the main area without changing the view", async () => {
    stubHealth(healthy);
    const user = userEvent.setup();
    window.location.hash = "#/interests";
    render(<AppShell items={ITEMS} current="interests" />);

    await user.tab();
    await user.keyboard("{Enter}");

    expect(document.activeElement).toBe(screen.getByRole("main"));
    expect(window.location.hash).toBe("#/interests");
    await screen.findByText("Backend reachable");
  });

  it("reaches available destinations by Tab and skips disabled ones", async () => {
    stubHealth(healthy);
    const user = userEvent.setup();
    render(<AppShell items={ITEMS} current="interests" />);

    await user.tab(); // skip link
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("link", { name: "Overview" }));
    await user.tab();
    const interests = screen.getByRole("link", { name: "Interests" });
    expect(document.activeElement).toBe(interests);
    expect(interests.getAttribute("aria-current")).toBe("page");
    expect(interests.getAttribute("href")).toBe("#/interests");
    await user.tab();
    expect(document.activeElement).toBe(document.body); // "Sources" is not focusable
    await screen.findByText("Backend reachable");
  });

  it("follows the URL hash", async () => {
    stubHealth(healthy);
    const user = userEvent.setup();
    const { rerender } = render(<AppShell items={ITEMS} current="overview" />);

    await user.click(screen.getByRole("link", { name: "Interests" }));
    expect(window.location.hash).toBe("#/interests");
    rerender(<AppShell items={ITEMS} current="interests" />);
    expect(
      screen.getByRole("link", { name: "Interests" }).getAttribute("aria-current"),
    ).toBe("page");
    await screen.findByText("Backend reachable");
  });
});
