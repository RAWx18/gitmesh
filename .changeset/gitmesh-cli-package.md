---
"gitmesh-cli": minor
"gitmesh-agents": patch
---

Add the publishable `gitmesh-cli` npm package (pivot T0.6): a self-contained bundle of the `gitmesh` CLI entry with a manifest-drift guard, published with npm provenance under the `next` dist-tag via the new release workflow, and clean-install smoke-tested in CI. The `gitmesh` bin moves out of `gitmesh-agents` (which keeps only the legacy `gitmesh-agents` bin), and `--version` now reports the installed package's manifest version instead of a hardcoded constant. The unscoped npm name `gitmesh` is owned by an unrelated project, so the package name is `gitmesh-cli`; the installed binary remains `gitmesh` (see ADR-005).
