# @gitmesh/workspace-adapters

## 0.3.0

### Minor Changes

- 24ee6ce: Add the golden-fixture harness (pivot T0.5): `fixtures/<adapter>/<case>/{input-repo/, expected/}` discovery plus a byte-exact runner (`listGoldenCases`, `runGoldenCase`, `assertGoldenCase`) that every detector and emitter conformance suite builds on, with a dummy passing fixture and a seeded-drift negative fixture.
- 523744f: Add @gitmesh/workspace-adapters package with the AgentAdapter contract and a lazy adapter registry (pivot T0.2).

### Patch Changes

- Updated dependencies [7c5e885]
  - @gitmesh/workspace-core@0.3.0
