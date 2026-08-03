import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // Without this, the default glob also picks up the compiled copies in
    // dist/, so the suite would run twice and depend on build state.
    include: ["src/**/*.test.ts"],
  },
});
