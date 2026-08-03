# Maintainer Outreach Plan (Workstream 5)

## Why this exists

The four engineering workstreams (60-second connect, policy library, attestation) compound only if real maintainers are using them. Without three reference deployments by week 14, the engineering output is unvalidated. This file is the discipline tracker: a checklist + paper-cut log that runs in parallel with the engineering work, **starting in week 1, not after**.

The user's wedge for GitMesh is outbound governance - governing the agents the maintainer enabled, not filtering inbound contributor slop. That decision narrows the pitch and raises the cost of being wrong about whether maintainers actually want this. Real users tell you whether attestation matters or whether the templates ship the right slice of policy. No engineering output passes the "good" bar without that signal.

## Hard gate

By the end of **week 14**, three real maintainer deployments running real workflows. If three deployments are not running by week 14:

- **Pause workstream 4** (attestation). It is the longest engineering stretch and the most attestation-flavoured output of the mentorship; shipping it without users is the failure mode.
- Diagnose the wedge. Either the pitch isn't sharp, the install path is broken, or the audience is wrong. Not "the product needs more features."

## Target shape

Repos in the **500–5 000 star range**, maintained by **1–3 people**, ideally already experimenting with Claude Code or similar. Avoid:

- Mega-projects (Kubernetes, React, Next.js) - platform teams own tooling decisions; they will not deploy.
- Tiny projects (< 100 stars) - the AI-slop pain isn't lived yet.

## Schedule

### Week 1 - Open five outreach issues

- [ ] Repo 1: ___
- [ ] Repo 2: ___
- [ ] Repo 3: ___
- [ ] Repo 4: ___
- [ ] Repo 5: ___

Issue template (use the same wording across the five):

> Hi - I'm working on a [LFDT-hosted](https://github.com/LF-Decentralized-Trust-labs/gitmesh) policy/audit layer for AI agents on OSS projects. Before I ship more I'd love a 30 minute call to understand how you handle AI-assisted PRs and bot trust today. No pitch, just listening. Are you up for one this week or next?

### Week 2–3 - Discovery calls (5 maintainers)

Don't pitch. Ask:

1. What do you do when an AI-assisted PR comes in?
2. How do you decide whether to trust an agent on your repo?
3. Have you ever wished you could write down rules for what bots can and cannot do?

Log verbatim phrases in the table below - those become the marketing copy.

| Maintainer | Repo | Date | Phrase 1 | Phrase 2 | Phrase 3 |
|---|---|---|---|---|---|
|   |   |   |   |   |   |

### Week 4–5 - Reference deployment #1 (Zoom-watched install)

Pick one maintainer from the calls. Offer:

- Free install on their repo
- Co-author their first three policies on a shared call
- Weekly check-ins for 4 weeks

**Do not fix anything in the moment.** Watch them set up; write down every paper cut. That's the entire value of this week.

| Step | Where it broke | Time wasted | Fix |
|---|---|---|---|
| OAuth handshake |   |   |   |
| Webhook registration |   |   |   |
| First policy install |   |   |   |
| First agent run |   |   |   |
| First attestation badge |   |   |   |

### Week 6–7 - Fix paper cuts; deployments #2 and #3

Fix every paper cut from week 4–5. Repeat with maintainers #2 and #3 - the second and third installs should hit progressively fewer cuts. By end of week 7, three deployments running.

### Week 8–14 - Steady state

Weekly check-ins with all three maintainers. Track:

- What policies are they actually using?
- What policies do they wish existed?
- Is the attestation feature even on their radar?

If a maintainer says "honestly the attestation thing is theoretical for me, what I really want is X" - listen. The mentorship issue calls for verifiable trust but real user data trumps proposal text.

## Paper-cut log (cumulative across all three deployments)

| Date | Maintainer | Friction | Severity | Status |
|---|---|---|---|---|
|   |   |   |   |   |

## Rules of engagement

- **Don't pitch.** Listen. The pitch comes from their own phrases.
- **Don't fix in the moment** during a setup call - watch and log.
- **Don't add features outside the four workstreams** to win a maintainer over. Write requests down; ship after the mentorship if they survive that filter.
- **The hardest version of the rule:** if no maintainer wants to install GitMesh after you've offered to do all the work, that's the product telling you the wedge isn't sharp enough. Adding attestation will not change that.

## Outputs of this workstream

- 5 verbatim quotes (week 2–3)
- 1 paper-cut log per deployment (week 4–7)
- 3 case studies for the LFDT mentorship presentation (week 23–26)
- 1 go/no-go decision on workstream 4 (week 14)
