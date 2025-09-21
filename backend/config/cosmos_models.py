"""
Cosmos Model Configuration
Extracted from Cosmos models.py to avoid circular imports.
"""

# Mapping of model aliases to their canonical names
MODEL_ALIASES = {
    # Claude models
    "sonnet": "anthropic/claude-sonnet-4-20250514",
    "haiku": "claude-3-5-haiku-20241022",
    "opus": "claude-opus-4-20250514",
    # GPT models
    "4": "gpt-4-0613",
    "4o": "gpt-4o",
    "4-turbo": "gpt-4-1106-preview",
    "35turbo": "gpt-3.5-turbo",
    "35-turbo": "gpt-3.5-turbo",
    "3": "gpt-3.5-turbo",
    # Other models
    "deepseek": "deepseek/deepseek-chat",
    "flash": "gemini/gemini-2.5-flash",
    "flash-lite": "gemini/gemini-2.5-flash-lite",
    "quasar": "openrouter/openrouter/quasar-alpha",
    "r1": "deepseek/deepseek-reasoner",
    "gemini-2.5-pro": "gemini/gemini-2.5-pro",
    "gemini": "gemini/gemini-2.5-pro",
    "gemini-exp": "gemini/gemini-2.5-pro-exp-03-25",
    "grok3": "xai/grok-3-beta",
    "optimus": "openrouter/openrouter/optimus-alpha",
}