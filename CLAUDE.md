# CLAUDE.md

@AGENTS.md

All project instructions for coding agents live in `AGENTS.md`, imported
above. **Edit `AGENTS.md`, not this file**, so every agent (Claude Code,
Codex, Cursor, Copilot, …) stays in sync. This shim is the exact pattern
GitMesh compiles for its own users — see `doc/pivot/pivot.md` §8.2 and finding
GM010.

Claude-specific notes:

- Repo-local skills live in `.claude/skills/` — use them when relevant.
- Always sign off commits (`git commit -s`); DCO is enforced on every commit.