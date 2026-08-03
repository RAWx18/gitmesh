export const type = "claude_gateway";
export const label = "Claude Code (Multi-Provider)";

export const models = [
  { id: "claude-opus-4-6", label: "Claude Opus 4.6" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { id: "claude-haiku-4-6", label: "Claude Haiku 4.6" },
  { id: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" },
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
  { id: "MiniMax-M2.7", label: "MiniMax M2.7" },
  { id: "MiniMax-M3", label: "MiniMax M3" },
];

export const agentConfigurationDoc = `# claude_gateway agent configuration

Adapter: claude_gateway

**Multi-Provider Claude Code Support**: Use official Anthropic Claude, MiniMax, or other Anthropic-compatible providers.

Core provider selection fields:
- provider (string, required): Provider name. Options:
  - "anthropic": Official Anthropic Claude API
  - "minimax": MiniMax Anthropic-compatible API (https://api.minimax.io/anthropic)
  - Or any other Anthropic-compatible endpoint
- apiKey (string, required): API key for the selected provider
- baseUrl (string, optional): Custom base URL for Anthropic-compatible providers (default inferred from provider)

Claude execution fields:
- cwd (string, optional): default absolute working directory fallback for the agent process (created if missing when possible)
- instructionsFilePath (string, optional): absolute path to a markdown instructions file injected at runtime
- model (string, optional): Claude model id or provider-specific model name
- effort (string, optional): reasoning effort passed via --effort (low|medium|high)
- chrome (boolean, optional): pass --chrome when running Claude
- promptTemplate (string, optional): run prompt template
- maxTurnsPerRun (number, optional): max turns for one run
- dangerouslySkipPermissions (boolean, optional): pass --dangerously-skip-permissions to claude
- command (string, optional): defaults to "claude"
- extraArgs (string[], optional): additional CLI args
- env (object, optional): Additional environment variables. Do NOT set ANTHROPIC_API_KEY or ANTHROPIC_BASE_URL here; use provider/apiKey/baseUrl instead.

Model name mapping (optional):
- modelMap (object, optional): Map model IDs to provider-specific names. Example:
  \`\`\`yaml
  provider: minimax
  apiKey: \${MINIMAX_API_KEY}
  modelMap:
    MiniMax-M2.7: minimax/MiniMax-M2.7
  \`\`\`

Operational fields:
- timeoutSec (number, optional): run timeout in seconds
- graceSec (number, optional): SIGTERM grace period in seconds

## Provider Examples

### Official Anthropic
\`\`\`yaml
provider: anthropic
apiKey: \${ANTHROPIC_API_KEY}
model: claude-opus-4-6
\`\`\`

### MiniMax
\`\`\`yaml
provider: minimax
apiKey: \${MINIMAX_API_KEY}
model: MiniMax-M2.7
modelMap:
  MiniMax-M2.7: minimax/MiniMax-M2.7
\`\`\`

### Custom Anthropic-Compatible Provider
\`\`\`yaml
provider: custom
apiKey: \${CUSTOM_API_KEY}
baseUrl: https://your-api.example.com/v1
model: your-model-id
\`\`\`

## Notes
- The adapter internally translates all configuration to \\\`ANTHROPIC_API_KEY\\\` and \\\`ANTHROPIC_BASE_URL\\\` for Claude Code consumption
- Model name mapping allows displaying one name in GitMesh while sending a different name to the provider
- Use environment variables (e.g., \\\`\${MINIMAX_API_KEY}\\\`) to avoid exposing secrets in agent config
`;
