---
"@gitmesh/workspace-adapters": minor
---

Add the golden-fixture harness (pivot T0.5): `fixtures/<adapter>/<case>/{input-repo/, expected/}` discovery plus a byte-exact runner (`listGoldenCases`, `runGoldenCase`, `assertGoldenCase`) that every detector and emitter conformance suite builds on, with a dummy passing fixture and a seeded-drift negative fixture.
