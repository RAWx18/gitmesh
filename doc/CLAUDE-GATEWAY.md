# Claude Code Multi-Provider Adapter

**No separate proxy process needed.** The `claude_gateway` adapter is a built-in GitMesh adapter that seamlessly routes Claude Code API calls to your preferred provider: Anthropic, MiniMax, or any Anthropic-compatible endpoint.

## What's Different from `claude_local`?

| Feature | `claude_local` | `claude_gateway` |
|---------|---|---|
| **Provider** | Anthropic only (official) | Multi-provider (Anthropic, MiniMax, custom) |
| **Setup** | Select in GitMesh UI, uses $ANTHROPIC_API_KEY | Select in GitMesh UI, specify provider & API key in config |
| **Environment** | Single environment auth | Per-agent provider config |
| **Use case** | Simple Anthropic-only setup | Try multiple providers, per-project routing |

## Quick Start

### 1. Create an Agent with `claude_gateway`

In the GitMesh UI at "Create your first agent" → Choose adapter:

**Select:** `Claude Code (Multi-Provider)` (instead of `Claude Code (local)`)

### 2. Configure Provider

In the agent configuration YAML, specify your provider:

#### **Official Anthropic**
```yaml
provider: anthropic
apiKey: ${ANTHROPIC_API_KEY}
model: claude-opus-4-6
```

#### **MiniMax**
```yaml
provider: minimax
apiKey: ${MINIMAX_API_KEY}
model: MiniMax-M2.7
modelMap:
  MiniMax-M2.7: minimax/MiniMax-M2.7
```

#### **Custom Anthropic-Compatible Provider**
```yaml
provider: custom
baseUrl: https://your-custom-api.example.com/v1
apiKey: ${YOUR_API_KEY}
model: your-model-id
```

### 3. Set Environment Variables

Store your API keys in GitMesh secrets or environment:

```bash
# For MiniMax
export MINIMAX_API_KEY="your-minimax-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-anthropic-key"

# For custom provider
export YOUR_API_KEY="custom-provider-key"
```

### 4. Test the Agent

Run the adapter environment check via GitMesh UI (yellow "Test now" button):
- Validates provider configuration
- Checks API key is valid
- Probes Claude Code connectivity to the provider

✅ **No manual scripts, no proxy management, no environment variable juggling outside of GitMesh.**

## Full Configuration Reference

```yaml
adapter: claude_gateway

# **Required**: Provider configuration
provider: minimax                                    # "anthropic" | "minimax" | or custom name
apiKey: ${MINIMAX_API_KEY}                          # API key for the provider
baseUrl: https://api.minimax.io/anthropic           # (optional) Override default endpoint

# **Model selection**
model: MiniMax-M2.7                                 # Model ID (provider-specific)
modelMap:                                           # (optional) Map model names
  MiniMax-M2.7: minimax/MiniMax-M2.7               # Show `MiniMax-M2.7` to Claude; send `minimax/MiniMax-M2.7` to provider

# **Claude execution**
cwd: /path/to/workspace                            # Working directory (optional)
instructionsFilePath: /path/to/instructions.md     # Custom Claude instructions (optional)
effort: medium                                      # "low" | "medium" | "high" (optional)
chrome: false                                       # Enable Chrome integration (optional)
maxTurnsPerRun: 10                                 # Max Claude turns per run (optional)
dangerouslySkipPermissions: false                  # Skip permission checks (optional)
extraArgs:                                          # Additional Claude CLI args (optional)
  - --verbose

# **Timeouts**
timeoutSec: 120                                    # Adapter timeout in seconds (optional)
graceSec: 20                                       # SIGTERM grace period (optional)

# **Additional environment** (don't set ANTHROPIC_API_KEY or ANTHROPIC_BASE_URL here)
env:
  CUSTOM_VAR: value
  MY_SECRET: ${ANOTHER_ENV_VAR}
```

## Supported Providers

### Anthropic (Official)
- **Base URL:** `https://api.anthropic.com`
- **Models:** `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-6`, etc.
- **Auth:** API key (Bearer token)

### MiniMax
- **Base URL:** `https://api.minimax.io/anthropic`
- **Models:** `MiniMax-M2.7`, `MiniMax-M3`, etc.
- **Auth:** API key (x-api-key header)
- **Note:** Requires model name mapping if provider sends different model IDs

### Custom Anthropic-Compatible
- **Base URL:** Your endpoint (e.g., `https://your-api.example.com/v1`)
- **Models:** Provider-specific
- **Auth:** API key (configurable)

## Model Name Mapping

Some providers use different model naming schemes. Use `modelMap` to translate:

```yaml
provider: minimax
apiKey: ${MINIMAX_API_KEY}
modelMap:
  # GitMesh shows left side, sends right side to provider
  MiniMax-M2.7: minimax/MiniMax-M2.7
  MiniMax-M3: minimax/MiniMax-M3
```

This allows GitMesh UI to display user-friendly names while sending provider-specific model IDs.

## Switching Between Providers

Want to test multiple providers? Create separate agents:

```yaml
# Agent 1: Anthropic
Agent: PR Review (Anthropic)
adapter: claude_gateway
provider: anthropic
apiKey: ${ANTHROPIC_API_KEY}

# Agent 2: MiniMax
Agent: PR Review (MiniMax)
adapter: claude_gateway
provider: minimax
apiKey: ${MINIMAX_API_KEY}
```

Then assign different roles or trigger conditions to each agent.

## Troubleshooting

### "Provider is required"
**Error:** Configuration validation failed.  
**Fix:** Add `provider: minimax` (or your provider name) to agent config.

### "API key is required"
**Error:** Configuration validation failed or probe fails.  
**Fix:** Add `apiKey: ${YOUR_API_KEY}` and ensure the env var is set.

### "Auth failed" or "Unauthorized"
**Error:** Claude probe fails after configuration checks.  
**Fix:**
- Verify API key is correct and not expired
- Check provider endpoint is accessible from GitMesh server
- Confirm provider still supports the API endpoint (especially for custom providers)

### "Provider endpoint unreachable"
**Error:** Probe times out.  
**Fix:**
- Verify network/firewall access from GitMesh server to provider
- If using custom provider, test with `curl https://your-api.example.com/v1/models`
- If using MiniMax behind a proxy, set `baseUrl` explicitly

### "Model not found"
**Error:** Claude runs but provider returns 404 on model.  
**Fix:**
- Check model name is correct for the provider
- If model name differs from what Claude expects, add to `modelMap`
- Example: MiniMax might require `minimax/MiniMax-M2.7` format

## Security Notes

- **API keys in config:** Use environment variable references (`${MINIMAX_API_KEY}`) instead of hardcoding
- **Exposed keys:** If you accidentally commit an API key, rotate it immediately via your provider's dashboard
- **GitMesh secrets:** Prefer storing API keys in GitMesh's secret management rather than shell environment
- **Network:** Ensure GitMesh server → provider endpoint connection is secured (use HTTPS/TLS)

## Advanced Use Cases

### Per-Project Provider Routing
Create agents with different providers based on project needs:
- Security review agent → Anthropic (official, trusted)
- Experimental experiments → MiniMax (cost-effective)
- Compliance audit → Custom provider (on-premise)

### Model Selection per Role
```yaml
# Triage agent (fast, cheap)
model: MiniMax-M2.7

# PR review (thorough, expensive)
model: claude-opus-4-6

# Documentation (balanced)
model: claude-sonnet-4-6
```

### Fallback via External Proxy
If you need request-level routing (e.g., failover to Anthropic if MiniMax is down), consider running the standalone proxy server from [doc/CLAUDE-PROXY.md](CLAUDE-PROXY.md) alongside GitMesh agents:

1. Start proxy: `CLAUDE_PROXY_PORT=8765 MINIMAX_API_KEY=... pnpm claude:proxy:start`
2. Configure agent: `baseUrl: http://localhost:8765`

This gives you request-level control beyond what `claude_gateway` provides.

## Comparison: `claude_gateway` vs Standalone Proxy

| Aspect | `claude_gateway` adapter | Standalone proxy (docs/CLAUDE-PROXY.md) |
|--------|---|---|
| **Integration** | Built into GitMesh UI | Separate process |
| **Per-agent config** | ✅ Yes | ❌ No (global config) |
| **Per-request routing** | ✅ Built-in | ✅ Full control |
| **Complexity** | Simple | More setup |
| **Use case** | Multi-provider agents | Complex request routing, fallback logic |

**Recommendation:** Use `claude_gateway` adapter for simplicity. Use standalone proxy if you need request-level failover or routing logic beyond per-agent provider selection.

## Next Steps

1. ✅ Create an agent in GitMesh UI with `claude_gateway` adapter
2. ✅ Configure provider and API key
3. ✅ Run adapter environment check
4. ✅ Trigger a test run (e.g., PR review)
5. ✅ Check logs in GitMesh dashboard for any provider-specific errors

**Questions?** See agent configuration doc: `/llms/agent-configuration/claude_gateway.txt`
