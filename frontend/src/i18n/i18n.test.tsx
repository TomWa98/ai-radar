import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { apiGet } from "../api/client";
import { useLocalizedQuery } from "../api/useLocalizedQuery";
import { DICTIONARIES, LANGUAGES, type Language } from "./dictionaries";
import { LANGUAGE_STORAGE_KEY, LanguageProvider, initialLanguage } from "./language";
import { LanguageSwitch } from "./LanguageSwitch";

type Calls = { url: string; method: string }[];

function stubFetch(): Calls {
  const calls: Calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? "GET" });
      const body = String(input).startsWith("/health")
        ? { status: "ok" }
        : { items: [], total: 0, limit: 25, offset: 0, next_since: "2026-10-30T12:00:00Z" };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

function setBrowserLanguage(language: string) {
  vi.spyOn(navigator, "language", "get").mockReturnValue(language);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** All key paths with their values, e.g. ["nav.overview", "Overview"]. */
function entries(value: unknown, prefix = ""): [string, unknown][] {
  if (typeof value !== "object" || value === null) {
    return [[prefix, value]];
  }
  return Object.entries(value).flatMap(([key, inner]) =>
    entries(inner, prefix ? `${prefix}.${key}` : key),
  );
}

describe("dictionaries", () => {
  it("have the same keys in German and English", () => {
    const keys = (lang: Language) => entries(DICTIONARIES[lang]).map(([key]) => key).sort();
    expect(keys("de")).toEqual(keys("en"));
  });

  it.each(LANGUAGES)("%s has a non-empty text for every key", (lang) => {
    for (const [key, value] of entries(DICTIONARIES[lang])) {
      expect(typeof value, key).toBe("string");
      expect(String(value).trim(), key).not.toBe("");
    }
  });

  it("are really translated", () => {
    expect(DICTIONARIES.de.nav.overview).toBe("Übersicht");
    expect(DICTIONARIES.en.nav.overview).toBe("Overview");
  });
});

describe("initial language", () => {
  it("uses a stored choice", () => {
    setBrowserLanguage("en-US");
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "de");
    expect(initialLanguage()).toBe("de");
  });

  it.each([
    ["de-DE", "de"],
    ["de", "de"],
    ["en-GB", "en"],
    ["fr-FR", "en"],
  ])("falls back to the browser language %s → %s", (browser, expected) => {
    setBrowserLanguage(browser);
    expect(initialLanguage()).toBe(expected);
  });

  it("ignores an invalid stored value", () => {
    setBrowserLanguage("de-AT");
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "fr");
    expect(initialLanguage()).toBe("de");
  });

  it("works when storage is unavailable", () => {
    setBrowserLanguage("en-US");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(initialLanguage()).toBe("en");
  });
});

describe("language switch", () => {
  it("switches the UI texts, stores the choice, and sets <html lang>", async () => {
    setBrowserLanguage("en-US");
    stubFetch();
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Overview");
    expect(document.documentElement.lang).toBe("en");
    const deutsch = screen.getByRole("button", { name: "DE – Deutsch" });
    expect(deutsch.getAttribute("aria-pressed")).toBe("false");

    await user.click(deutsch);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Übersicht");
    expect(screen.getByRole("link", { name: "Übersicht" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Hauptnavigation" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Sprache" })).toBeTruthy();
    expect(deutsch.getAttribute("aria-pressed")).toBe("true");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("de");
    expect(document.documentElement.lang).toBe("de");
    await screen.findByText("Backend erreichbar");
  });

  it("keeps the stored choice after a reload", async () => {
    setBrowserLanguage("en-US");
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, "de");
    stubFetch();
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Übersicht");
    await screen.findByText("Backend erreichbar");
  });

  it("names each option starting with its visible label", () => {
    setBrowserLanguage("en-US");
    render(
      <LanguageProvider>
        <LanguageSwitch />
      </LanguageProvider>,
    );

    for (const button of screen.getAllByRole("button")) {
      const visible = button.textContent ?? "";
      expect(button.getAttribute("aria-label")?.startsWith(visible)).toBe(true);
    }
  });

  it("can be operated with the keyboard", async () => {
    setBrowserLanguage("de-DE");
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <LanguageSwitch />
      </LanguageProvider>,
    );

    await user.tab();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "EN – English" }));
    await user.keyboard("{Enter}");

    expect(screen.getByRole("group", { name: "Language" })).toBeTruthy();
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("still switches when the choice cannot be stored", async () => {
    setBrowserLanguage("en-US");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <LanguageSwitch />
      </LanguageProvider>,
    );

    await user.click(screen.getByRole("button", { name: "DE – Deutsch" }));

    expect(screen.getByRole("group", { name: "Sprache" })).toBeTruthy();
  });
});

describe("localized API queries", () => {
  function Articles() {
    const load = useCallback(
      (lang: Language, signal: AbortSignal) =>
        apiGet("/api/articles", { signal, query: { lang } }),
      [],
    );
    const state = useLocalizedQuery(load);
    return <p>{state.status}</p>;
  }

  it("passes lang and only repeats the read request on a language switch", async () => {
    setBrowserLanguage("en-US");
    const calls = stubFetch();
    const user = userEvent.setup();
    render(
      <LanguageProvider>
        <LanguageSwitch />
        <Articles />
      </LanguageProvider>,
    );
    await screen.findByText("success");
    expect(calls).toEqual([{ url: "/api/articles?lang=en", method: "GET" }]);

    await user.click(screen.getByRole("button", { name: "DE – Deutsch" }));
    await screen.findByText("success");

    // Exactly one further request: a GET with the new language. No refresh,
    // no analysis, no other write request.
    expect(calls).toEqual([
      { url: "/api/articles?lang=en", method: "GET" },
      { url: "/api/articles?lang=de", method: "GET" },
    ]);
  });

  it("shows loading while the new language is fetched", async () => {
    setBrowserLanguage("en-US");
    let release: () => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(new Response("{}", { status: 200 }));
          }),
      ),
    );
    render(
      <LanguageProvider>
        <Articles />
      </LanguageProvider>,
    );

    expect(screen.getByText("loading")).toBeTruthy();
    act(() => release());
    await waitFor(() => expect(screen.getByText("success")).toBeTruthy());
  });

  it("reports errors", async () => {
    setBrowserLanguage("en-US");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    render(
      <LanguageProvider>
        <Articles />
      </LanguageProvider>,
    );

    await screen.findByText("error");
  });
});
