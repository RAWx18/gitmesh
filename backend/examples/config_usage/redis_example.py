"""
Example: Using unified config for Redis operations
"""
import redis.asyncio as redis
from config.unified_config import get_config

async def create_redis_client():
    config = get_config()
    
    # Instead of hardcoded connection
    # client = redis.from_url("redis://...")
    
    # Use unified config
    client = redis.from_url(
        config.get_redis_url(),
        socket_timeout=config.redis.socket_timeout,
        socket_connect_timeout=config.redis.connect_timeout,
        max_connections=config.redis.max_connections,
        decode_responses=config.redis.decode_responses
    )
    return client
