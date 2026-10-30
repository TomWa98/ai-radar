import { defineConfig } from "vitest/config";

// Backend runs locally (D9). The dev server proxies API calls so the browser
// only talks to one origin: no CORS needed (D8).
const BACKEND = "http://127.0.0.1:8000";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": BACKEND,
      "/health": BACKEND,
    },
  },
  preview: {
    host: "127.0.0.1",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Process tokens.css so its contrast test can read it via `?raw`.
    css: { include: [/tokens\.css/] },
    restoreMocks: true,
  },
});
