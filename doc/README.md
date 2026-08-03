# Internal engineering docs

`doc/` holds engineering documentation for people working **on** GitMesh.
User-facing documentation lives in [`docs/`](../docs) and is published with
Mintlify — edit that tree for anything an end user reads.

`doc/pivot/pivot.md` is the canonical plan; where it disagrees with anything
here, it wins. See [`AGENTS.md`](../AGENTS.md) for which parts of the
repository are active and which are frozen.

## Design and direction

| Document | Contents |
|---|---|
| [pivot/pivot.md](pivot/pivot.md) | Canonical pivot plan and task backlog |
| [pivot/research_results.md](pivot/research_results.md) | Market research backing the pivot |
| [adr/](adr/README.md) | Architecture decision records |
| [architecture.md](architecture.md) | Orchestration runtime architecture |
| [v1-spec.md](v1-spec.md) | V1 implementation spec |
| [vision.md](vision.md) | Product definition |
| [GOAL.md](GOAL.md) | Project goals |

## Building and running

| Document | Contents |
|---|---|
| [SETUP.md](SETUP.md) | Full setup guide: local, Docker Compose, and Docker CLI |
| [DEVELOPING.md](DEVELOPING.md) | Local development workflow |
| [DATABASE.md](DATABASE.md) | Embedded and external PostgreSQL |
| [DOCKER.md](DOCKER.md) | Container images and Compose files |
| [DEPLOYMENT-MODES.md](DEPLOYMENT-MODES.md) | Deployment and auth modes |
| [PUBLISHING.md](PUBLISHING.md) | npm release process |
| [CLI.md](CLI.md) | CLI reference |
| [OPERATOR-UI-GUIDE.md](OPERATOR-UI-GUIDE.md) | Maintainer UI walkthrough |

## Adapters

| Document | Contents |
|---|---|
| [CLAUDE-GATEWAY.md](CLAUDE-GATEWAY.md) | Claude Code multi-provider adapter |
| [CLAUDE-PROXY.md](CLAUDE-PROXY.md) | Claude Code dual-mode (official + proxy) setup |
| [gateway-setup.md](gateway-setup.md) | Gateway adapter setup |
| [plugins/PLUGIN_SPEC.md](plugins/PLUGIN_SPEC.md) | Plugin specification |

## History

[`plans/`](plans) and [`spec/`](spec) hold superseded design documents. They
record how decisions were reached and are not maintained.
