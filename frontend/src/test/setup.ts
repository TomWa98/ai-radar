import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount rendered components after every test (no Vitest globals in use).
afterEach(() => {
  cleanup();
});
