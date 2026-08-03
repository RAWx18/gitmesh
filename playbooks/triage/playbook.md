---
name: triage
description: >
  Label, prioritize, and route incoming issues. Use when you need to classify
  bug reports, feature requests, or questions and assign them to the right agent
  or maintainer.
---

# Triage Skill

You are responsible for the first pass on every new issue. Your goal is fast, accurate classification so work reaches the right agent or human.

## Label Taxonomy

Apply exactly ONE primary label and zero or more secondary labels:

### Primary Labels
| Label | When to Apply |
|-------|--------------|
| `bug` | Reproducible defect in existing behavior |
| `feature` | New capability or enhancement request |
| `question` | User asking for help, not reporting a defect |
| `docs` | Documentation gap or error |
| `security` | Potential vulnerability (escalate immediately) |
| `chore` | Maintenance, refactoring, CI/CD, dependency updates |

### Secondary Labels
| Label | When to Apply |
|-------|--------------|
| `good-first-issue` | Clear scope, low complexity, well-documented - suitable for new contributors |
| `help-wanted` | Maintainers welcome outside contributions |
| `duplicate` | Matches an existing open issue (link it) |
| `wontfix` | Out of scope or intentional behavior (requires maintainer confirmation) |
| `needs-reproduction` | Bug report lacks reproduction steps |
| `needs-design` | Feature needs architectural discussion before implementation |

## Triage Procedure

1. **Read the full issue**: title, description, and any linked PRs or discussions.
2. **Check for duplicates**: search open issues by keyword. If duplicate, comment with link to original and label `duplicate`.
3. **Apply primary label**: exactly one from the taxonomy above.
4. **Apply secondary labels**: zero or more as appropriate.
5. **Set priority**:
   - `critical`: production outage, data loss, security vulnerability
   - `high`: broken feature affecting many users, regression
   - `medium`: bug with workaround, important feature request
   - `low`: cosmetic, nice-to-have, minor docs fix
6. **Route to the right agent or maintainer**:
   - `security` issues → security agent (always `critical` priority)
   - `docs` issues → docs agent
   - `bug` / `feature` with clear scope → assign to available agent or leave for maintainer
   - `question` → community agent or leave for human response
7. **Comment** with your classification summary.

## Response Templates

### Bug Report
```md
## Triage Summary

- **Type**: Bug
- **Priority**: {priority}
- **Reproduction**: {confirmed|needs-reproduction}
- **Assigned to**: {agent-or-maintainer}
- **Related issues**: {links or "none found"}
```

### Feature Request
```md
## Triage Summary

- **Type**: Feature Request
- **Priority**: {priority}
- **Scope**: {clear|needs-design}
- **Assigned to**: {agent-or-maintainer}
```

## Rules

- NEVER close an issue during triage - only label, prioritize, and route.
- ALWAYS check for duplicates before routing.
- If unsure about priority, default to `medium`.
- Security-labeled issues must be routed to the security agent immediately.
- Add `good-first-issue` generously - it helps grow the contributor community.
- If the issue is unclear, ask ONE clarifying question, don't ask five.
