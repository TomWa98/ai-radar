import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { LanguageProvider } from "./i18n/language";
import { AppShell } from "./shell/AppShell";
import type { NavItem } from "./shell/navigation";
import { json, stubApi } from "./test/fetch";

function withLanguage(ui: ReactNode) {
  return <LanguageProvider>{ui}</LanguageProvider>;
}

/** The backend status shown in the top bar. */
function backendStatus(): string {
  return within(screen.getByRole("banner")).getByRole("status").textContent ?? "";
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("App shell", () => {
  it("has the top bar, labelled navigation, and main landmarks", async () => {
    stubApi();
    render(<App />);

    expect(screen.getByRole("banner").textContent).toContain("AI Radar");
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Overview");
    await screen.findByText("Backend reachable");
  });

  it("links Overview, disables the other destinations, and hides Articles", async () => {
    stubApi();
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Main navigation" });

    const overview = within(nav).getByRole("link", { name: "Overview" });
    expect(overview.getAttribute("href")).toBe("#/overview");
    expect(overview.getAttribute("aria-current")).toBe("page");
    for (const label of ["Interests", "Sources", "News Wall"]) {
      const item = within(nav).getByText(label).closest("[aria-disabled]");
      expect(item?.getAttribute("aria-disabled")).toBe("true");
    }
    expect(within(nav).getAllByRole("link")).toHaveLength(1);
    expect(within(nav).queryByText("Articles")).toBeNull();
    await screen.findByText("Backend reachable");
  });
});

describe("backend status", () => {
  it("reports a check in progress, then success", async () => {
    stubApi();
    render(<App />);

    expect(backendStatus()).toBe("Checking backend…");
    await waitFor(() => expect(backendStatus()).toBe("Backend reachable"));
  });

  it("reports an unreachable backend", async () => {
    stubApi((url) => {
      if (url.pathname === "/health") throw new TypeError("Failed to fetch");
      return undefined;
    });
    render(<App />);

    await waitFor(() => expect(backendStatus()).toBe("Backend unreachable"));
  });

  it("reports an error response as unreachable", async () => {
    stubApi((url) => (url.pathname === "/health" ? json({}, 503) : undefined));
    render(<App />);

    await waitFor(() => expect(backendStatus()).toBe("Backend unreachable"));
  });
});

describe("keyboard and focus", () => {
  const ITEMS: NavItem[] = [
    { id: "overview", labelKey: "overview", available: true },
    { id: "interests", labelKey: "interests", available: true },
    { id: "sources", labelKey: "sources", available: false },
  ];

  it("starts with a skip link that moves focus to the main area", async () => {
    stubApi();
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
    stubApi();
    const user = userEvent.setup();
    window.location.hash = "#/interests";
    render(withLanguage(<AppShell items={ITEMS} current="interests" />));

    await user.tab();
    await user.keyboard("{Enter}");

    expect(document.activeElement).toBe(screen.getByRole("main"));
    expect(window.location.hash).toBe("#/interests");
    await screen.findByText("Backend reachable");
  });

  it("reaches available destinations by Tab and skips disabled ones", async () => {
    stubApi();
    const user = userEvent.setup();
    render(withLanguage(<AppShell items={ITEMS} current="interests" />));

    await user.tab(); // skip link
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "DE – Deutsch" }));
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "EN – English" }));
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
    stubApi();
    const user = userEvent.setup();
    const { rerender } = render(withLanguage(<AppShell items={ITEMS} current="overview" />));

    await user.click(screen.getByRole("link", { name: "Interests" }));
    expect(window.location.hash).toBe("#/interests");
    rerender(withLanguage(<AppShell items={ITEMS} current="interests" />));
    expect(
      screen.getByRole("link", { name: "Interests" }).getAttribute("aria-current"),
    ).toBe("page");
    await screen.findByText("Backend reachable");
  });
});
