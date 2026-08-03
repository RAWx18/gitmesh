---
"gitmesh-agents": patch
---

Fix the published `gitmesh-agents` manifest dropping its `@gitmesh/server`
dependency. `scripts/generate-npm-package-json.mjs` kept its own copy of the
bundled/external package lists from `cli/esbuild.config.mjs`, and that copy
still named the server package `@gitmesh/agents-server`. Because esbuild
leaves `@gitmesh/server` external and `cli/src/commands/run.ts` imports it
dynamically, the published package declared no way to resolve it. The lists
now live in `cli/esbuild.config.mjs` and are imported by the generator, so
the manifest always describes the bundle that was actually built.
