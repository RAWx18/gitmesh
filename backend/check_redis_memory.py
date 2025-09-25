#!/usr/bin/env python3
"""
Check Redis memory usage and clean up if needed.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_redis_memory():
    """Check Redis memory usage and clean up if needed."""
    try:
        from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
        from integrations.cosmos.v1.cosmos.config import initialize_configuration
        
        # logger.info("Checking Redis memory usage...")
        
        # Initialize configuration
        config = initialize_configuration()
        
        # Create Redis cache instance
        redis_cache = SmartRedisCache()
        
        # Get connection info
        conn_info = redis_cache.get_connection_info()
        # logger.info(f"Redis connection info: {conn_info}")
        
        # Get detailed Redis info
        info = redis_cache._client.info()
        
        # Memory information
        used_memory = info.get('used_memory', 0)
        used_memory_human = info.get('used_memory_human', 'Unknown')
        maxmemory = info.get('maxmemory', 0)
        maxmemory_human = info.get('maxmemory_human', 'Unknown')
        
        logger.info(f"Used memory: {used_memory_human} ({used_memory} bytes)")
        logger.info(f"Max memory: {maxmemory_human} ({maxmemory} bytes)")
        
        if maxmemory > 0:
            usage_percent = (used_memory / maxmemory) * 100
            logger.info(f"Memory usage: {usage_percent:.1f}%")
            
            if usage_percent > 90:
                logger.warning("⚠️  Redis memory usage is very high!")
                return cleanup_redis_data(redis_cache)
            elif usage_percent > 80:
                logger.warning("⚠️  Redis memory usage is high")
        
        # List cached repositories
        repos = redis_cache.list_cached_repositories()
        logger.info(f"Cached repositories: {len(repos)}")
        
        for repo in repos[:5]:  # Show first 5
            logger.info(f"  - {repo['name']} (stored: {repo['stored_at']})")
        
        if len(repos) > 5:
            logger.info(f"  ... and {len(repos) - 5} more")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to check Redis memory: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_redis_data(redis_cache):
    """Clean up old Redis data to free memory."""
    try:
        # logger.info("Starting Redis cleanup...")
        
        # List all cached repositories
        repos = redis_cache.list_cached_repositories()
        logger.info(f"Found {len(repos)} cached repositories")
        
        if not repos:
            # logger.info("No repositories to clean up")
            return True
        
        # Sort by stored_at timestamp (oldest first)
        repos_with_time = []
        for repo in repos:
            try:
                stored_at = float(repo['metadata'].get('stored_at', '0'))
                repos_with_time.append((repo, stored_at))
            except:
                repos_with_time.append((repo, 0))
        
        repos_with_time.sort(key=lambda x: x[1])
        
        # Clean up oldest repositories (keep only the 3 most recent)
        repos_to_keep = 3
        repos_to_delete = repos_with_time[:-repos_to_keep] if len(repos_with_time) > repos_to_keep else []
        
        if repos_to_delete:
            # logger.info(f"Cleaning up {len(repos_to_delete)} old repositories...")
            
            for repo, stored_at in repos_to_delete:
                repo_name = repo['name']
                # logger.info(f"Deleting repository: {repo_name}")
                
                success = redis_cache.smart_invalidate(repo_name)
                if success:
                    logger.info(f"✅ Deleted {repo_name}")
                else:
                    logger.error(f"❌ Failed to delete {repo_name}")
            
            logger.info("Cleanup completed")
        else:
            logger.info("No repositories need cleanup")
        
        # Check memory again
        info = redis_cache._client.info()
        used_memory_human = info.get('used_memory_human', 'Unknown')
        logger.info(f"Memory usage after cleanup: {used_memory_human}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to cleanup Redis data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # logger.info("Starting Redis memory check...")
    
    if not check_redis_memory():
        logger.error("Redis memory check failed")
        sys.exit(1)
    
    # logger.info("Redis memory check completed")