# Gateway Adapter Setup

This guide describes how to set up and verify the Gateway adapter integration with GitMesh Agents.

---

## Prerequisites

1. Start GitMesh Agents in auth mode:
```bash
cd <gitmesh-agents-repo-root>
pnpm dev --tailscale-auth
```

Verify:
```bash
curl -sS http://127.0.0.1:3100/api/health | jq
```

2. Start a clean gateway instance (Docker or local).

3. In GitMesh Agents UI, navigate to Project Settings.

---

## Invite Flow

1. In the **Invites** section, click **Generate Gateway Invite Prompt**.
2. Copy the generated prompt.
3. Paste it into the agent's chat as one message.
4. If it stalls, send: `How is onboarding going? Continue setup now.`

**Security note:** The invite prompt is created from a controlled endpoint:
- `POST /api/projects/{projectId}/gateway/invite-prompt`
- Operator users with invite permission can call it
- Agent callers are limited to the project admin agent

5. Approve the join request in GitMesh Agents UI.

---

## Gateway Preflight (required before task tests)

Confirm:
- Agent uses `gateway` adapter type.
- Gateway URL is `ws://...` or `wss://...`.
- Gateway token is non-trivial (not empty or placeholder).
- Device auth is enabled (default) with persisted `devicePrivateKeyPem`.

API check (with operator auth):
```bash
AGENT_ID="<agent-id>"
curl -sS -H "Cookie: $GITMESH_COOKIE" \
  "http://127.0.0.1:3100/api/agents/$AGENT_ID" \
  | jq '{adapterType, adapterConfig: {
      url: .adapterConfig.url,
      tokenLen: (.adapterConfig.headers["x-gateway-token"] // "" | length),
      disableDeviceAuth: (.adapterConfig.disableDeviceAuth // false),
      hasDeviceKey: (.adapterConfig.devicePrivateKeyPem // "" | length > 0)
    }}'
```

Expected: `adapterType=gateway`, `tokenLen >= 16`, `hasDeviceKey=true`, `disableDeviceAuth=false`.

---

## Pairing Handshake

- The adapter attempts automatic pairing on first `pairing required` response.
- If auto-pair cannot complete, approve the pending device in the gateway, then retry.

---

## Verification Test Cases

### Case A - Manual Issue
- Create an issue assigned to the gateway agent.
- Instructions: "post comment `CASE_A_OK_<timestamp>` and mark done."
- Verify: issue status → `done`, comment exists.

### Case B - Message Tool
- Create an issue; instructions: "send `CASE_B_OK_<timestamp>` to main chat, comment same marker, mark done."
- Verify: marker comment on issue + marker in agent chat.

### Case C - New Session Memory
- Start a new session in the agent.
- Ask it to create a new issue with title `CASE_C_CREATED_<timestamp>`.
- Verify: issue appears in GitMesh Agents UI.

---

## Pass Criteria

- Preflight: `gateway` adapter + non-placeholder token (`tokenLen >= 16`).
- Pairing: stable `devicePrivateKeyPem` with device auth enabled.
- Case A: `done` + marker comment.
- Case B: marker in both issue + agent chat.
- Case C: new issue created from agent session.
