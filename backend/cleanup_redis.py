#!/usr/bin/env python3
"""
Clean up all Redis data to free memory.
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

def cleanup_all_redis_data():
    """Clean up all Redis data."""
    try:
        from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
        from integrations.cosmos.v1.cosmos.config import initialize_configuration
        
        logger.info("Cleaning up all Redis data...")
        
        # Initialize configuration
        config = initialize_configuration()
        
        # Create Redis cache instance
        redis_cache = SmartRedisCache()
        
        # List all cached repositories
        repos = redis_cache.list_cached_repositories()
        logger.info(f"Found {len(repos)} cached repositories to clean up")
        
        # Clean up each repository
        for repo in repos:
            repo_name = repo['name']
            logger.info(f"Deleting repository: {repo_name}")
            
            success = redis_cache.smart_invalidate(repo_name)
            if success:
                logger.info(f"✅ Deleted {repo_name}")
            else:
                logger.error(f"❌ Failed to delete {repo_name}")
        
        # Also clean up any remaining keys
        logger.info("Cleaning up any remaining repository keys...")
        
        # Get all keys matching repo pattern
        all_keys = redis_cache._client.keys("repo:*")
        if all_keys:
            logger.info(f"Found {len(all_keys)} additional keys to clean up")
            
            # Delete in batches
            batch_size = 100
            for i in range(0, len(all_keys), batch_size):
                batch = all_keys[i:i + batch_size]
                deleted = redis_cache._client.delete(*batch)
                logger.info(f"Deleted {deleted} keys from batch {i//batch_size + 1}")
        
        # Check memory after cleanup
        info = redis_cache._client.info()
        used_memory_human = info.get('used_memory_human', 'Unknown')
        logger.info(f"Memory usage after cleanup: {used_memory_human}")
        
        # Verify no repositories remain
        remaining_repos = redis_cache.list_cached_repositories()
        logger.info(f"Remaining repositories: {len(remaining_repos)}")
        
        logger.info("✅ Redis cleanup completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to cleanup Redis data: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    logger.info("Starting Redis cleanup...")
    
    if not cleanup_all_redis_data():
        logger.error("Redis cleanup failed")
        sys.exit(1)
    
    logger.info("Redis cleanup completed successfully")