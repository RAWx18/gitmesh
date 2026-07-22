# gitmesh-agents

## 0.3.0

### Minor Changes

- d7e6275: Add the new `gitmesh` CLI entry with scaffold subcommands (doctor, init, migrate, apply, check, policy) and the full legacy command surface under `gitmesh legacy`; `gitmesh-agents` keeps its existing behavior unchanged (pivot T0.3).

### Patch Changes

- 5c6dedb: Add the publishable `gitmesh-cli` npm package (pivot T0.6): a small self-contained bundle of the `gitmesh` CLI entry (single runtime dependency, no server/database code — `gitmesh legacy` prints install guidance instead of bundling the legacy tree), with a manifest-drift guard in the build, npm provenance publishing under the `next` dist-tag via the new release workflow, and a clean-install smoke test in CI. The `gitmesh` bin moves out of `gitmesh-agents` (which keeps the legacy bin and full legacy commands), and `--version` now reports the installed package's manifest version. The unscoped npm name `gitmesh` is owned by an unrelated project, so the package name is `gitmesh-cli`; the installed binary remains `gitmesh` (see ADR-005).
  - @gitmesh/adapter-sdk@0.3.0
  - @gitmesh/adapter-claude-local@0.3.0
  - @gitmesh/adapter-codex-local@0.3.0
  - @gitmesh/adapter-cursor-local@0.3.0
  - @gitmesh/adapter-gateway@0.3.0
  - @gitmesh/adapter-opencode-local@0.3.0
  - @gitmesh/adapter-pi-local@0.3.0
  - @gitmesh/core@0.3.0
  - @gitmesh/data@0.3.0
  - @gitmesh/server@0.3.0

## 0.2.7

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.7
  - @gitmesh/adapter-sdk@0.2.7
  - @gitmesh/data@0.2.7
  - @gitmesh/adapter-claude-local@0.2.7
  - @gitmesh/adapter-codex-local@0.2.7
  - @gitmesh/adapter-gateway@0.2.7
  - @gitmesh/server@0.2.7

## 0.2.6

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.6
  - @gitmesh/adapter-sdk@0.2.6
  - @gitmesh/data@0.2.6
  - @gitmesh/adapter-claude-local@0.2.6
  - @gitmesh/adapter-codex-local@0.2.6
  - @gitmesh/adapter-gateway@0.2.6
  - @gitmesh/server@0.2.6

## 0.2.5

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.5
  - @gitmesh/adapter-sdk@0.2.5
  - @gitmesh/data@0.2.5
  - @gitmesh/adapter-claude-local@0.2.5
  - @gitmesh/adapter-codex-local@0.2.5
  - @gitmesh/adapter-gateway@0.2.5
  - @gitmesh/server@0.2.5

## 0.2.4

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.4
  - @gitmesh/adapter-sdk@0.2.4
  - @gitmesh/data@0.2.4
  - @gitmesh/adapter-claude-local@0.2.4
  - @gitmesh/adapter-codex-local@0.2.4
  - @gitmesh/adapter-gateway@0.2.4
  - @gitmesh/server@0.2.4

## 0.2.3

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.3
  - @gitmesh/adapter-sdk@0.2.3
  - @gitmesh/data@0.2.3
  - @gitmesh/adapter-claude-local@0.2.3
  - @gitmesh/adapter-codex-local@0.2.3
  - @gitmesh/adapter-gateway@0.2.3
  - @gitmesh/server@0.2.3

## 0.2.2

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.2
  - @gitmesh/adapter-sdk@0.2.2
  - @gitmesh/data@0.2.2
  - @gitmesh/adapter-claude-local@0.2.2
  - @gitmesh/adapter-codex-local@0.2.2
  - @gitmesh/adapter-gateway@0.2.2
  - @gitmesh/server@0.2.2

## 0.2.1

### Patch Changes

- Version bump (patch)
- Updated dependencies
  - @gitmesh/core@0.2.1
  - @gitmesh/adapter-sdk@0.2.1
  - @gitmesh/data@0.2.1
  - @gitmesh/adapter-claude-local@0.2.1
  - @gitmesh/adapter-codex-local@0.2.1
  - @gitmesh/adapter-gateway@0.2.1
  - @gitmesh/server@0.2.1
