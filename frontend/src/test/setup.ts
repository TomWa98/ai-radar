import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount rendered components after every test (no Vitest globals in use)
// and forget a stored language choice.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
  document.documentElement.lang = "";
});
