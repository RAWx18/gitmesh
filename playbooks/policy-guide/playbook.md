---
name: policy-guide
description: >
  Meta-skill explaining the GitMesh Agents policy system. Teaches agents
  how to read policy.yaml, understand policy decisions, and respect defaults.
---

# Policy Guide Skill

This skill explains how the GitMesh Agents **policy system** works. Every agent should understand policies so they can respect project governance.

## What is a Policy?

A policy is a project-level rule that controls agent behavior. Policies are defined in `.gitmesh/policy.yaml` in the project repository and enforced by the GitMesh Agents server.

## Policy File Format

```yaml
# .gitmesh/policy.yaml
version: "1"

review:
  required_approvals: 1
  auto_merge: false
  require_ci_pass: true

security:
  auto_fix_dependencies: false
  advisory_approval_required: true
  disclosure_timeline_days: 90

triage:
  auto_label: true
  stale_days: 14
  auto_close_stale: false

release:
  cadence: "manual"  # manual | weekly | on-merge
  require_changelog: true
  require_approval: true

community:
  welcome_new_contributors: true
  response_time_hours: 24

agents:
  max_concurrent: 3
  budget_alert_percent: 80
  require_human_approval:
    - merge
    - release
    - security_advisory
    - agent_enable
```

## How Agents Use Policies

1. **Read policies** at startup or when they change. The server provides the current policy state via `GET /api/projects/{projectId}/policies`.
2. **Check before acting**: Before performing a gated action (merge, release, publish), check if policy requires human approval.
3. **Respect defaults**: If a policy key is missing, use the safe default (usually: require human approval, don't auto-merge, don't auto-close).
4. **Report violations**: If you detect a policy violation, escalate to maintainers. Don't attempt to fix policy files yourself.

## Safe Defaults

When a policy is not defined, always fall back to the safest option:

| Action | Default |
|--------|---------|
| Merge PRs | Require human approval |
| Publish releases | Require human approval |
| Security advisories | Require human approval |
| Enable new agents | Require human approval |
| Auto-label issues | Disabled |
| Auto-close stale | Disabled |
| Dependency auto-fix | Disabled |

## Policy Decision Flow

```
Agent wants to perform action
  → Is action gated by policy?
    → YES: Is policy defined?
      → YES: Follow policy rule
      → NO: Apply safe default (require approval)
    → NO: Proceed normally
```

## NEVER

- Never modify policy.yaml yourself - only human maintainers change policies.
- Never ignore a policy rule - if it blocks your action, escalate.
- Never assume a permissive policy when the policy file is missing or unreadable.

## Common Policy Checks

### Before Merging
```
policy.review.auto_merge === true && policy.review.require_ci_pass → CI passes
```

### Before Releasing  
```
policy.release.require_approval === true → escalate to maintainer
policy.release.require_changelog === true → ensure changelog exists
```

### Before Security Actions
```
policy.security.advisory_approval_required === true → draft only, escalate
```
