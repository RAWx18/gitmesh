---
"gitmesh-cli": minor
"gitmesh-agents": patch
---

Add the publishable `gitmesh-cli` npm package (pivot T0.6): a small self-contained bundle of the `gitmesh` CLI entry (single runtime dependency, no server/database code — `gitmesh legacy` prints install guidance instead of bundling the legacy tree), with a manifest-drift guard in the build, npm provenance publishing under the `next` dist-tag via the new release workflow, and a clean-install smoke test in CI. The `gitmesh` bin moves out of `gitmesh-agents` (which keeps the legacy bin and full legacy commands), and `--version` now reports the installed package's manifest version. The unscoped npm name `gitmesh` is owned by an unrelated project, so the package name is `gitmesh-cli`; the installed binary remains `gitmesh` (see ADR-005).
