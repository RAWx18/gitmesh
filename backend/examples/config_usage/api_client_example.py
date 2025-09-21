"""
Example: Using unified config for API clients
"""
from config.unified_config import get_config
import httpx

def create_ai_client():
    config = get_config()
    
    # Instead of hardcoded API key
    # headers = {"Authorization": "Bearer sk-..."}
    
    # Use unified config
    api_key = config.get_ai_api_key()
    if not api_key:
        raise ValueError(f"No API key configured for provider: {config.ai.provider}")
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    client = httpx.AsyncClient(
        headers=headers,
        timeout=config.ai.timeout
    )
    return client
