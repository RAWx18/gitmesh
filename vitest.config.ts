import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      "lib/data",
      "lib/workspace-core",
      "lib/workspace-adapters",
      "lib/adapters/opencode",
      "server",
      "ui",
      "cli",
      // Repo-level infrastructure tests (lint boundary guard, release smoke).
      {
        test: {
          name: "repo-infra",
          environment: "node",
          include: ["scripts/__tests__/**/*.test.ts"],
        },
      },
    ],
  },
});
