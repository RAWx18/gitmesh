"""
Cache Management Service for Redis cache lifecycle management.

This service handles Redis cache operations with proper TTL management,
health monitoring, and memory usage optimization for the Cosmos Web Chat integration.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, asdict
from redis import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError
from config.simple_config import get_config

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache statistics data class."""
    total_keys: int
    memory_usage_mb: float
    hit_rate: float
    miss_rate: float
    expired_keys: int
    user_cache_count: int
    repository_cache_count: int
    session_cache_count: int
    last_cleanup: Optional[datetime]


@dataclass
class CacheHealthStatus:
    """Cache health status data class."""
    is_healthy: bool
    connection_status: str
    memory_usage_percent: float
    response_time_ms: float
    error_count: int
    last_error: Optional[str]
    uptime_seconds: float


class CacheManagementService:
    """
    Service for managing Redis cache lifecycle with TTL management and health monitoring.
    
    Handles repository data caching, session management, and automatic cleanup
    based on user navigation patterns.
    """
    
    # Cache key prefixes
    REPO_PREFIX = "cosmos:repo:"
    SESSION_PREFIX = "cosmos:session:"
    USER_PREFIX = "cosmos:user:"
    CONTEXT_PREFIX = "cosmos:context:"
    STATS_PREFIX = "cosmos:stats:"
    
    # Default TTL values (in seconds) - Fixed for better memory management
    DEFAULT_REPO_TTL = 1800  # 30 minutes (reduced from 1 hour)
    DEFAULT_SESSION_TTL = 900   # 15 minutes (reduced from 30 minutes)
    DEFAULT_USER_TTL = 3600     # 1 hour (reduced from 2 hours)
    DEFAULT_CONTEXT_TTL = 600   # 10 minutes (reduced from 15 minutes)
    
    # Memory management thresholds
    MAX_MEMORY_MB = 100  # Maximum memory usage before cleanup
    CLEANUP_THRESHOLD_PERCENT = 80  # Trigger cleanup at 80% memory usage
    
    def __init__(self, user_id: str, redis_client: Optional[Redis] = None):
        """
        Initialize cache management service.
        
        Args:
            user_id: User identifier for scoped operations
            redis_client: Optional Redis client instance
        """
        self.user_id = user_id
        self.config = get_config()
        
        # Initialize Redis client
        if redis_client:
            self.redis_client = redis_client
        else:
            self.redis_client = self._create_redis_client()
        
        self.redis_available = self._test_redis_connection()
        
        # Cache statistics
        self._stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0,
            'last_cleanup': None
        }
        
        logger.info(f"CacheManagementService initialized for user: {user_id}")
    
    def _create_redis_client(self) -> Redis:
        """Create Redis client with configuration."""
        try:
            redis_url = self.config.get_redis_url()
            
            client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            return client
            
        except Exception as e:
            logger.error(f"Failed to create Redis client: {e}")
            raise
    
    def _test_redis_connection(self) -> bool:
        """Test Redis connection."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            return False
    
    def _get_cache_key(self, prefix: str, *args) -> str:
        """Generate cache key with prefix and arguments."""
        if args:
            key_parts = [prefix.rstrip(':')] + [str(arg) for arg in args]
            return ":".join(key_parts)
        return prefix.rstrip(':')
    
    def _should_cleanup_before_cache(self) -> bool:
        """Check if cleanup should be performed before caching new data."""
        try:
            if not self.redis_available:
                return False
            
            info = self.redis_client.info()
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            
            # Trigger cleanup if memory usage exceeds threshold
            return memory_usage_mb > (self.MAX_MEMORY_MB * self.CLEANUP_THRESHOLD_PERCENT / 100)
            
        except Exception as e:
            logger.warning(f"Error checking memory usage: {e}")
            return False
    
    def _get_memory_usage_mb(self) -> float:
        """Get current Redis memory usage in MB."""
        try:
            if not self.redis_available:
                return 0.0
            
            info = self.redis_client.info()
            return info.get('used_memory', 0) / (1024 * 1024)
            
        except Exception as e:
            logger.warning(f"Error getting memory usage: {e}")
            return 0.0
    
    def cache_repository_data(self, repo_url: str, data: Dict[str, Any], ttl: int = None) -> bool:
        """
        Cache repository data with TTL and memory management.
        
        Args:
            repo_url: Repository URL
            data: Repository data to cache
            ttl: Time to live in seconds (default: 30 minutes)
            
        Returns:
            True if cached successfully
        """
        if not self.redis_available:
            logger.warning("Redis not available, cannot cache repository data")
            return False
        
        try:
            # Check memory usage before caching
            if self._should_cleanup_before_cache():
                logger.info("Memory threshold reached, performing cleanup before caching")
                self.cleanup_expired_caches()
            
            cache_key = self._get_cache_key(self.REPO_PREFIX, repo_url)
            ttl = ttl or self.DEFAULT_REPO_TTL
            
            # Add metadata with size tracking
            cache_data = {
                **data,
                'cached_at': datetime.now().isoformat(),
                'cached_by': self.user_id,
                'ttl': ttl,
                'data_size': len(json.dumps(data))  # Track data size
            }
            
            # Cache with TTL
            success = self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data)
            )
            
            if success:
                logger.info(f"Repository data cached: {repo_url} (TTL: {ttl}s, size: {cache_data['data_size']} bytes)")
                return True
            else:
                logger.error(f"Failed to cache repository data: {repo_url}")
                return False
                
        except Exception as e:
            logger.error(f"Error caching repository data: {e}")
            self._stats['errors'] += 1
            return False
    
    def get_cached_repository(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """
        Get cached repository data.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Cached repository data or None
        """
        if not self.redis_available:
            return None
        
        try:
            cache_key = self._get_cache_key(self.REPO_PREFIX, repo_url)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                repo_data = json.loads(cached_data)
                
                # Check if cache is still valid
                cached_at = datetime.fromisoformat(repo_data.get('cached_at', ''))
                ttl = repo_data.get('ttl', self.DEFAULT_REPO_TTL)
                
                if datetime.now() - cached_at < timedelta(seconds=ttl):
                    self._stats['hits'] += 1
                    logger.debug(f"Cache hit for repository: {repo_url}")
                    return repo_data
                else:
                    # Cache expired, remove it
                    self.redis_client.delete(cache_key)
                    logger.debug(f"Cache expired for repository: {repo_url}")
                    self._stats['misses'] += 1
                    return None
            else:
                self._stats['misses'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached repository: {e}")
            self._stats['errors'] += 1
            return None
    
    def cache_session_data(self, session_id: str, data: Dict[str, Any], ttl: int = None) -> bool:
        """
        Cache session data with TTL.
        
        Args:
            session_id: Session identifier
            data: Session data to cache
            ttl: Time to live in seconds (default: 30 minutes)
            
        Returns:
            True if cached successfully
        """
        if not self.redis_available:
            return False
        
        try:
            cache_key = self._get_cache_key(self.SESSION_PREFIX, self.user_id, session_id)
            ttl = ttl or self.DEFAULT_SESSION_TTL
            
            cache_data = {
                **data,
                'cached_at': datetime.now().isoformat(),
                'user_id': self.user_id,
                'ttl': ttl
            }
            
            success = self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data)
            )
            
            if success:
                logger.debug(f"Session data cached: {session_id}")
                return True
            else:
                logger.error(f"Failed to cache session data: {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error caching session data: {e}")
            self._stats['errors'] += 1
            return False
    
    def get_cached_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached session data.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Cached session data or None
        """
        if not self.redis_available:
            return None
        
        try:
            cache_key = self._get_cache_key(self.SESSION_PREFIX, self.user_id, session_id)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                session_data = json.loads(cached_data)
                self._stats['hits'] += 1
                return session_data
            else:
                self._stats['misses'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Error getting cached session: {e}")
            self._stats['errors'] += 1
            return None
    
    def clear_user_repository_cache(self, user_id: str = None) -> bool:
        """
        Clear all repository cache for a user.
        
        Args:
            user_id: User ID (defaults to current user)
            
        Returns:
            True if cleared successfully
        """
        if not self.redis_available:
            return False
        
        target_user = user_id or self.user_id
        
        try:
            # Find all repository cache keys for the user
            pattern = f"{self.REPO_PREFIX}*"
            keys = self.redis_client.keys(pattern)
            
            user_repo_keys = []
            for key in keys:
                try:
                    cached_data = self.redis_client.get(key)
                    if cached_data:
                        repo_data = json.loads(cached_data)
                        if repo_data.get('cached_by') == target_user:
                            user_repo_keys.append(key)
                except (json.JSONDecodeError, KeyError):
                    # Invalid cache data, add to cleanup list
                    user_repo_keys.append(key)
            
            # Delete user's repository cache keys
            if user_repo_keys:
                deleted_count = self.redis_client.delete(*user_repo_keys)
                logger.info(f"Cleared {deleted_count} repository cache entries for user: {target_user}")
                return True
            else:
                logger.info(f"No repository cache entries found for user: {target_user}")
                return True
                
        except Exception as e:
            logger.error(f"Error clearing user repository cache: {e}")
            self._stats['errors'] += 1
            return False
    
    def clear_user_session_cache(self, user_id: str = None) -> bool:
        """
        Clear all session cache for a user.
        
        Args:
            user_id: User ID (defaults to current user)
            
        Returns:
            True if cleared successfully
        """
        if not self.redis_available:
            return False
        
        target_user = user_id or self.user_id
        
        try:
            pattern = f"{self.SESSION_PREFIX}{target_user}:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted_count = self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted_count} session cache entries for user: {target_user}")
                return True
            else:
                logger.info(f"No session cache entries found for user: {target_user}")
                return True
                
        except Exception as e:
            logger.error(f"Error clearing user session cache: {e}")
            self._stats['errors'] += 1
            return False
    
    def cleanup_on_navigation_change(self, from_page: str, to_page: str) -> bool:
        """
        Cleanup cache based on navigation changes.
        
        Args:
            from_page: Page user is leaving
            to_page: Page user is navigating to
            
        Returns:
            True if cleanup was successful
        """
        try:
            cleanup_performed = False
            
            # Clear repository cache when leaving /contribution for /hub
            if from_page.startswith('/contribution') and to_page.startswith('/hub'):
                logger.info(f"User navigating from {from_page} to {to_page}, clearing repository cache")
                self.clear_user_repository_cache()
                cleanup_performed = True
            
            # Clear session cache when leaving chat
            if from_page.startswith('/contribution/chat') and not to_page.startswith('/contribution/chat'):
                logger.info(f"User leaving chat, clearing session cache")
                self.clear_user_session_cache()
                cleanup_performed = True
            
            if cleanup_performed:
                self._stats['last_cleanup'] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"Error during navigation cleanup: {e}")
            self._stats['errors'] += 1
            return False
    
    def get_cache_stats(self) -> CacheStats:
        """
        Get cache statistics.
        
        Returns:
            CacheStats object with current statistics
        """
        try:
            if not self.redis_available:
                return CacheStats(
                    total_keys=0,
                    memory_usage_mb=0.0,
                    hit_rate=0.0,
                    miss_rate=0.0,
                    expired_keys=0,
                    user_cache_count=0,
                    repository_cache_count=0,
                    session_cache_count=0,
                    last_cleanup=self._stats.get('last_cleanup')
                )
            
            # Get Redis info
            info = self.redis_client.info()
            
            # Count keys by type
            repo_keys = len(self.redis_client.keys(f"{self.REPO_PREFIX}*"))
            session_keys = len(self.redis_client.keys(f"{self.SESSION_PREFIX}*"))
            user_keys = len(self.redis_client.keys(f"{self.USER_PREFIX}*"))
            total_keys = info.get('db0', {}).get('keys', 0)
            
            # Calculate hit/miss rates
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0.0
            miss_rate = (self._stats['misses'] / total_requests * 100) if total_requests > 0 else 0.0
            
            # Memory usage in MB
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            
            return CacheStats(
                total_keys=total_keys,
                memory_usage_mb=memory_usage_mb,
                hit_rate=hit_rate,
                miss_rate=miss_rate,
                expired_keys=info.get('expired_keys', 0),
                user_cache_count=user_keys,
                repository_cache_count=repo_keys,
                session_cache_count=session_keys,
                last_cleanup=self._stats.get('last_cleanup')
            )
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return CacheStats(
                total_keys=0,
                memory_usage_mb=0.0,
                hit_rate=0.0,
                miss_rate=0.0,
                expired_keys=0,
                user_cache_count=0,
                repository_cache_count=0,
                session_cache_count=0,
                last_cleanup=self._stats.get('last_cleanup')
            )
    
    def health_check(self) -> CacheHealthStatus:
        """
        Perform cache health check.
        
        Returns:
            CacheHealthStatus object with health information
        """
        start_time = time.time()
        
        try:
            # Test connection
            self.redis_client.ping()
            response_time_ms = (time.time() - start_time) * 1000
            
            # Get Redis info
            info = self.redis_client.info()
            
            # Calculate memory usage percentage (assuming 100MB max for basic health check)
            memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            memory_usage_percent = min((memory_usage_mb / 100) * 100, 100)
            
            # Determine health status
            is_healthy = (
                response_time_ms < 1000 and  # Response time under 1 second
                memory_usage_percent < 90 and  # Memory usage under 90%
                self._stats['errors'] < 10  # Less than 10 recent errors
            )
            
            return CacheHealthStatus(
                is_healthy=is_healthy,
                connection_status="connected",
                memory_usage_percent=memory_usage_percent,
                response_time_ms=response_time_ms,
                error_count=self._stats['errors'],
                last_error=None,
                uptime_seconds=info.get('uptime_in_seconds', 0)
            )
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            return CacheHealthStatus(
                is_healthy=False,
                connection_status="disconnected",
                memory_usage_percent=0.0,
                response_time_ms=response_time_ms,
                error_count=self._stats['errors'] + 1,
                last_error=error_msg,
                uptime_seconds=0
            )
    
    def cleanup_expired_caches(self) -> int:
        """
        Cleanup expired cache entries with improved TTL management.
        
        Returns:
            Number of entries cleaned up
        """
        if not self.redis_available:
            return 0
        
        try:
            cleaned_count = 0
            start_time = datetime.now()
            
            # Get all cache keys with batch processing
            all_patterns = [
                f"{self.REPO_PREFIX}*",
                f"{self.SESSION_PREFIX}*", 
                f"{self.USER_PREFIX}*",
                f"{self.CONTEXT_PREFIX}*"
            ]
            
            for pattern in all_patterns:
                keys = self.redis_client.keys(pattern)
                logger.debug(f"Processing {len(keys)} keys for pattern {pattern}")
                
                # Process keys in batches to avoid blocking Redis
                batch_size = 100
                for i in range(0, len(keys), batch_size):
                    batch_keys = keys[i:i + batch_size]
                    
                    for key in batch_keys:
                        try:
                            # Check if key exists and has TTL
                            ttl = self.redis_client.ttl(key)
                            
                            # Handle different TTL states
                            if ttl == -2:  # Key doesn't exist (expired)
                                cleaned_count += 1
                                continue
                            elif ttl == -1:  # No expiry set, check age and set appropriate TTL
                                cached_data = self.redis_client.get(key)
                                if cached_data:
                                    try:
                                        data = json.loads(cached_data)
                                        cached_at_str = data.get('cached_at', '')
                                        
                                        if cached_at_str:
                                            cached_at = datetime.fromisoformat(cached_at_str)
                                            age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                                            
                                            # Remove if too old
                                            if age_hours > 24:  # Max age 24 hours
                                                self.redis_client.delete(key)
                                                cleaned_count += 1
                                                continue
                                            
                                            # Set appropriate TTL based on key type and age
                                            remaining_ttl = self._calculate_remaining_ttl(key, age_hours)
                                            if remaining_ttl > 0:
                                                self.redis_client.expire(key, remaining_ttl)
                                                logger.debug(f"Set TTL {remaining_ttl}s for key {key}")
                                        else:
                                            # No timestamp, remove old data
                                            self.redis_client.delete(key)
                                            cleaned_count += 1
                                            
                                    except (json.JSONDecodeError, ValueError, KeyError):
                                        # Invalid data, remove it
                                        self.redis_client.delete(key)
                                        cleaned_count += 1
                                else:
                                    # Empty key, remove it
                                    self.redis_client.delete(key)
                                    cleaned_count += 1
                            elif ttl > 0 and ttl < 60:  # Keys expiring soon (< 1 minute)
                                # Check if we should extend TTL for active data
                                cached_data = self.redis_client.get(key)
                                if cached_data:
                                    try:
                                        data = json.loads(cached_data)
                                        # If data was accessed recently, extend TTL
                                        if self._should_extend_ttl(key, data):
                                            new_ttl = self._get_default_ttl_for_key(key)
                                            self.redis_client.expire(key, new_ttl)
                                            logger.debug(f"Extended TTL to {new_ttl}s for active key {key}")
                                    except (json.JSONDecodeError, ValueError, KeyError):
                                        # Let it expire naturally
                                        pass
                                        
                        except Exception as e:
                            logger.warning(f"Error processing key {key}: {e}")
                            continue
            
            cleanup_time = (datetime.now() - start_time).total_seconds()
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired cache entries in {cleanup_time:.2f}s")
                self._stats['last_cleanup'] = datetime.now()
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            self._stats['errors'] += 1
            return 0
    
    def _calculate_remaining_ttl(self, key: str, age_hours: float) -> int:
        """Calculate remaining TTL based on key type and age."""
        if self.REPO_PREFIX in key:
            max_ttl = self.DEFAULT_REPO_TTL
        elif self.SESSION_PREFIX in key:
            max_ttl = self.DEFAULT_SESSION_TTL
        elif self.CONTEXT_PREFIX in key:
            max_ttl = self.DEFAULT_CONTEXT_TTL
        else:
            max_ttl = self.DEFAULT_USER_TTL
        
        # Calculate remaining time based on age
        age_seconds = age_hours * 3600
        remaining = max_ttl - age_seconds
        
        return max(0, int(remaining))
    
    def _should_extend_ttl(self, key: str, data: Dict[str, Any]) -> bool:
        """Check if TTL should be extended for active data."""
        # For now, don't extend TTL - let data expire naturally
        # This can be enhanced with access tracking in the future
        return False
    
    def _get_default_ttl_for_key(self, key: str) -> int:
        """Get default TTL for a key based on its type."""
        if self.REPO_PREFIX in key:
            return self.DEFAULT_REPO_TTL
        elif self.SESSION_PREFIX in key:
            return self.DEFAULT_SESSION_TTL
        elif self.CONTEXT_PREFIX in key:
            return self.DEFAULT_CONTEXT_TTL
        else:
            return self.DEFAULT_USER_TTL
    
    def optimize_memory_usage(self) -> Dict[str, Any]:
        """
        Optimize memory usage by cleaning up old entries and compacting data.
        
        Returns:
            Dictionary with optimization results
        """
        try:
            initial_stats = self.get_cache_stats()
            initial_memory = initial_stats.memory_usage_mb
            
            # Cleanup expired entries
            cleaned_count = self.cleanup_expired_caches()
            
            # Get final stats
            final_stats = self.get_cache_stats()
            final_memory = final_stats.memory_usage_mb
            
            memory_saved = initial_memory - final_memory
            
            optimization_results = {
                'cleaned_entries': cleaned_count,
                'initial_memory_mb': initial_memory,
                'final_memory_mb': final_memory,
                'memory_saved_mb': memory_saved,
                'optimization_time': datetime.now().isoformat()
            }
            
            logger.info(f"Memory optimization completed: {optimization_results}")
            return optimization_results
            
        except Exception as e:
            logger.error(f"Error during memory optimization: {e}")
            return {
                'error': str(e),
                'cleaned_entries': 0,
                'memory_saved_mb': 0.0
            }


def create_cache_management_service(user_id: str, redis_client: Optional[Redis] = None) -> CacheManagementService:
    """
    Create a cache management service instance.
    
    Args:
        user_id: User identifier
        redis_client: Optional Redis client instance
        
    Returns:
        CacheManagementService instance
    """
    return CacheManagementService(user_id, redis_client)