"""
Performance Optimization Service

Implements response caching, connection pooling, request batching, and debouncing
for the Cosmos Web Chat Integration system.
"""

import asyncio
import hashlib
import json
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
from functools import wraps
import redis
from redis.connection import ConnectionPool

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..services.redis_repo_manager import RedisRepoManager
    from ..models.api.cosmos_response import ProcessedCosmosResponse
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from services.redis_repo_manager import RedisRepoManager
    from models.api.cosmos_response import ProcessedCosmosResponse

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int
    ttl_seconds: int
    size_bytes: int
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() > self.created_at + timedelta(seconds=self.ttl_seconds)
    
    def update_access(self) -> None:
        """Update access metadata."""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class BatchRequest:
    """Batched request item."""
    id: str
    operation: str
    args: Tuple
    kwargs: Dict[str, Any]
    callback: Optional[Callable] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking."""
    cache_hits: int = 0
    cache_misses: int = 0
    cache_size: int = 0
    avg_response_time_ms: float = 0.0
    total_requests: int = 0
    batched_requests: int = 0
    connection_pool_size: int = 0
    active_connections: int = 0
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0


class ConnectionPoolManager:
    """Manages Redis connection pools with optimization."""
    
    def __init__(self, settings):
        """Initialize connection pool manager."""
        self.settings = settings
        self._pools: Dict[str, ConnectionPool] = {}
        self._pool_stats: Dict[str, Dict[str, Any]] = {}
        
    def get_pool(self, pool_name: str = "default") -> ConnectionPool:
        """Get or create a connection pool."""
        if pool_name not in self._pools:
            self._create_pool(pool_name)
        return self._pools[pool_name]
    
    def _create_pool(self, pool_name: str) -> None:
        """Create a new connection pool."""
        try:
            # Optimized pool configuration
            pool_config = {
                'host': self.settings.redis_host,
                'port': self.settings.redis_port,
                'db': self.settings.redis_db,
                'username': self.settings.redis_username,
                'password': self.settings.redis_password,
                'decode_responses': True,
                'max_connections': 20,  # Increased for better concurrency
                'retry_on_timeout': True,
                'socket_timeout': 5,
                'socket_connect_timeout': 5,
                'socket_keepalive': True,
                'socket_keepalive_options': {},
                'health_check_interval': 30,
            }
            
            # Add SSL configuration if enabled
            if self.settings.redis_ssl:
                pool_config.update({
                    'ssl': True,
                    'ssl_cert_reqs': None,
                    'ssl_check_hostname': False,
                })
            
            # Use Redis URL if available (for cloud connections)
            if hasattr(self.settings, 'redis_url') and self.settings.redis_url:
                self._pools[pool_name] = ConnectionPool.from_url(
                    self.settings.redis_url,
                    **{k: v for k, v in pool_config.items() 
                       if k not in ['host', 'port', 'username', 'password']}
                )
            else:
                self._pools[pool_name] = ConnectionPool(**pool_config)
            
            self._pool_stats[pool_name] = {
                'created_at': datetime.now(),
                'connections_created': 0,
                'connections_in_use': 0,
                'total_requests': 0
            }
            
            logger.info(f"Created Redis connection pool: {pool_name}")
            
        except Exception as e:
            logger.error(f"Failed to create connection pool {pool_name}: {e}")
            raise
    
    def get_client(self, pool_name: str = "default") -> redis.Redis:
        """Get Redis client from pool."""
        pool = self.get_pool(pool_name)
        client = redis.Redis(connection_pool=pool)
        
        # Update stats
        if pool_name in self._pool_stats:
            self._pool_stats[pool_name]['total_requests'] += 1
        
        return client
    
    def get_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get connection pool statistics."""
        stats = {}
        for pool_name, pool in self._pools.items():
            pool_stats = self._pool_stats.get(pool_name, {})
            stats[pool_name] = {
                **pool_stats,
                'max_connections': pool.max_connections,
                'created_connections': pool.created_connections,
                'available_connections': len(pool._available_connections),
                'in_use_connections': len(pool._in_use_connections),
            }
        return stats
    
    def close_all(self) -> None:
        """Close all connection pools."""
        for pool_name, pool in self._pools.items():
            try:
                pool.disconnect()
                logger.info(f"Closed connection pool: {pool_name}")
            except Exception as e:
                logger.error(f"Error closing pool {pool_name}: {e}")
        
        self._pools.clear()
        self._pool_stats.clear()


class ResponseCache:
    """High-performance response cache with LRU eviction."""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """Initialize response cache."""
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: deque = deque()
        self._size_bytes = 0
        self._lock = asyncio.Lock()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        async with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Check expiration
            if entry.is_expired():
                await self._remove_entry(key)
                return None
            
            # Update access metadata
            entry.update_access()
            
            # Move to end of access order (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache."""
        async with self._lock:
            ttl = ttl or self.default_ttl
            
            # Calculate size
            try:
                size_bytes = len(json.dumps(value, default=str).encode())
            except:
                size_bytes = 1024  # Fallback estimate
            
            # Remove existing entry if present
            if key in self._cache:
                await self._remove_entry(key)
            
            # Ensure we have space
            while len(self._cache) >= self.max_size:
                await self._evict_lru()
            
            # Create new entry
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
                access_count=1,
                ttl_seconds=ttl,
                size_bytes=size_bytes
            )
            
            self._cache[key] = entry
            self._access_order.append(key)
            self._size_bytes += size_bytes
    
    async def _remove_entry(self, key: str) -> None:
        """Remove entry from cache."""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._size_bytes -= entry.size_bytes
            
            if key in self._access_order:
                self._access_order.remove(key)
    
    async def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if self._access_order:
            lru_key = self._access_order.popleft()
            await self._remove_entry(lru_key)
    
    async def clear_expired(self) -> int:
        """Clear expired entries and return count."""
        expired_keys = []
        
        async with self._lock:
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                await self._remove_entry(key)
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'size_bytes': self._size_bytes,
            'entries': [
                {
                    'key': entry.key,
                    'created_at': entry.created_at.isoformat(),
                    'last_accessed': entry.last_accessed.isoformat(),
                    'access_count': entry.access_count,
                    'size_bytes': entry.size_bytes,
                    'ttl_seconds': entry.ttl_seconds,
                    'is_expired': entry.is_expired()
                }
                for entry in list(self._cache.values())[:10]  # Show first 10 entries
            ]
        }


class RequestBatcher:
    """Batches similar requests for efficient processing."""
    
    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        """Initialize request batcher."""
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self._batches: Dict[str, List[BatchRequest]] = defaultdict(list)
        self._batch_timers: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._results: Dict[str, Any] = {}
    
    async def add_request(
        self, 
        operation: str, 
        *args, 
        callback: Optional[Callable] = None,
        **kwargs
    ) -> str:
        """Add request to batch."""
        request_id = f"{operation}_{int(time.time() * 1000000)}_{id(args)}"
        
        batch_request = BatchRequest(
            id=request_id,
            operation=operation,
            args=args,
            kwargs=kwargs,
            callback=callback
        )
        
        async with self._lock:
            self._batches[operation].append(batch_request)
            
            # Start timer if this is the first request for this operation
            if operation not in self._batch_timers:
                self._batch_timers[operation] = asyncio.create_task(
                    self._batch_timer(operation)
                )
            
            # Process immediately if batch is full
            if len(self._batches[operation]) >= self.batch_size:
                await self._process_batch(operation)
        
        return request_id
    
    async def _batch_timer(self, operation: str) -> None:
        """Timer to process batch after timeout."""
        await asyncio.sleep(self.batch_timeout)
        
        async with self._lock:
            if operation in self._batches and self._batches[operation]:
                await self._process_batch(operation)
    
    async def _process_batch(self, operation: str) -> None:
        """Process a batch of requests."""
        if operation not in self._batches or not self._batches[operation]:
            return
        
        batch = self._batches[operation].copy()
        self._batches[operation].clear()
        
        # Cancel timer
        if operation in self._batch_timers:
            self._batch_timers[operation].cancel()
            del self._batch_timers[operation]
        
        logger.info(f"Processing batch of {len(batch)} {operation} requests")
        
        # Process batch based on operation type
        try:
            if operation == "redis_get":
                await self._process_redis_get_batch(batch)
            elif operation == "redis_set":
                await self._process_redis_set_batch(batch)
            elif operation == "file_content":
                await self._process_file_content_batch(batch)
            else:
                # Process individually for unknown operations
                for request in batch:
                    if request.callback:
                        try:
                            result = await request.callback(*request.args, **request.kwargs)
                            self._results[request.id] = result
                        except Exception as e:
                            self._results[request.id] = {"error": str(e)}
        
        except Exception as e:
            logger.error(f"Error processing batch {operation}: {e}")
            # Set error results for all requests in batch
            for request in batch:
                self._results[request.id] = {"error": str(e)}
    
    async def _process_redis_get_batch(self, batch: List[BatchRequest]) -> None:
        """Process batch of Redis GET operations."""
        # This would be implemented with Redis pipeline
        # For now, placeholder implementation
        for request in batch:
            self._results[request.id] = {"status": "batched_redis_get"}
    
    async def _process_redis_set_batch(self, batch: List[BatchRequest]) -> None:
        """Process batch of Redis SET operations."""
        # This would be implemented with Redis pipeline
        # For now, placeholder implementation
        for request in batch:
            self._results[request.id] = {"status": "batched_redis_set"}
    
    async def _process_file_content_batch(self, batch: List[BatchRequest]) -> None:
        """Process batch of file content requests."""
        # Group by repository for efficient processing
        repo_groups = defaultdict(list)
        for request in batch:
            repo_key = request.args[0] if request.args else "unknown"
            repo_groups[repo_key].append(request)
        
        # Process each repository group
        for repo_key, requests in repo_groups.items():
            for request in requests:
                self._results[request.id] = {"status": "batched_file_content"}
    
    async def get_result(self, request_id: str, timeout: float = 5.0) -> Any:
        """Get result for a batched request."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if request_id in self._results:
                return self._results.pop(request_id)
            await asyncio.sleep(0.01)
        
        raise TimeoutError(f"Request {request_id} timed out")


class DebounceManager:
    """Manages debounced function calls."""
    
    def __init__(self):
        """Initialize debounce manager."""
        self._timers: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
    
    async def debounce(
        self, 
        key: str, 
        func: Callable, 
        delay: float, 
        *args, 
        **kwargs
    ) -> None:
        """Debounce a function call."""
        async with self._lock:
            # Cancel existing timer
            if key in self._timers:
                self._timers[key].cancel()
            
            # Create new timer
            self._timers[key] = asyncio.create_task(
                self._delayed_call(key, func, delay, *args, **kwargs)
            )
    
    async def _delayed_call(
        self, 
        key: str, 
        func: Callable, 
        delay: float, 
        *args, 
        **kwargs
    ) -> None:
        """Execute function after delay."""
        try:
            await asyncio.sleep(delay)
            
            # Remove from timers
            async with self._lock:
                if key in self._timers:
                    del self._timers[key]
            
            # Execute function
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)
                
        except asyncio.CancelledError:
            # Timer was cancelled, do nothing
            pass
        except Exception as e:
            logger.error(f"Error in debounced function {key}: {e}")


class PerformanceOptimizationService:
    """Main performance optimization service."""
    
    def __init__(self):
        """Initialize performance optimization service."""
        self.settings = get_settings()
        
        # Initialize components
        self.connection_pool_manager = ConnectionPoolManager(self.settings)
        self.response_cache = ResponseCache(
            max_size=1000,
            default_ttl=3600  # 1 hour default TTL
        )
        self.repo_map_cache = ResponseCache(
            max_size=100,
            default_ttl=7200  # 2 hours for repo maps
        )
        self.request_batcher = RequestBatcher(
            batch_size=10,
            batch_timeout=0.1
        )
        self.debounce_manager = DebounceManager()
        
        # Performance metrics
        self.metrics = PerformanceMetrics()
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_background_tasks()
    
    def _start_background_tasks(self) -> None:
        """Start background maintenance tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            try:
                # Clean expired cache entries
                response_expired = await self.response_cache.clear_expired()
                repo_expired = await self.repo_map_cache.clear_expired()
                
                if response_expired > 0 or repo_expired > 0:
                    logger.info(
                        f"Cleaned up {response_expired} response cache entries, "
                        f"{repo_expired} repo map cache entries"
                    )
                
                # Sleep for 5 minutes
                await asyncio.sleep(300)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def cache_response(
        self, 
        query_hash: str, 
        response: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """Cache a response."""
        await self.response_cache.set(query_hash, response, ttl)
    
    async def get_cached_response(self, query_hash: str) -> Optional[Any]:
        """Get cached response."""
        result = await self.response_cache.get(query_hash)
        
        if result is not None:
            self.metrics.cache_hits += 1
        else:
            self.metrics.cache_misses += 1
        
        return result
    
    async def cache_repo_map(
        self, 
        repo_name: str, 
        branch: str, 
        repo_map: str
    ) -> None:
        """Cache repository map."""
        key = f"repo_map:{repo_name}:{branch}"
        await self.repo_map_cache.set(key, repo_map, ttl=7200)  # 2 hours
    
    async def get_cached_repo_map(
        self, 
        repo_name: str, 
        branch: str
    ) -> Optional[str]:
        """Get cached repository map."""
        key = f"repo_map:{repo_name}:{branch}"
        return await self.repo_map_cache.get(key)
    
    def get_redis_client(self, pool_name: str = "default") -> redis.Redis:
        """Get optimized Redis client."""
        return self.connection_pool_manager.get_client(pool_name)
    
    async def batch_redis_operations(
        self, 
        operations: List[Dict[str, Any]]
    ) -> List[Any]:
        """Batch Redis operations for efficiency."""
        client = self.get_redis_client()
        
        try:
            pipe = client.pipeline()
            
            for op in operations:
                method = getattr(pipe, op['method'])
                args = op.get('args', [])
                kwargs = op.get('kwargs', {})
                method(*args, **kwargs)
            
            results = pipe.execute()
            self.metrics.batched_requests += len(operations)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch Redis operations: {e}")
            raise
    
    async def debounce_cache_update(
        self, 
        key: str, 
        update_func: Callable, 
        delay: float = 1.0,
        *args,
        **kwargs
    ) -> None:
        """Debounce cache update operations."""
        await self.debounce_manager.debounce(
            f"cache_update:{key}",
            update_func,
            delay,
            *args,
            **kwargs
        )
    
    def generate_query_hash(self, *args, **kwargs) -> str:
        """Generate hash for query caching."""
        return self.response_cache._generate_key(*args, **kwargs)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        pool_stats = self.connection_pool_manager.get_pool_stats()
        response_cache_stats = self.response_cache.get_stats()
        repo_cache_stats = self.repo_map_cache.get_stats()
        
        return {
            'cache_metrics': {
                'hits': self.metrics.cache_hits,
                'misses': self.metrics.cache_misses,
                'hit_rate': self.metrics.cache_hit_rate,
                'response_cache': response_cache_stats,
                'repo_map_cache': repo_cache_stats
            },
            'connection_pools': pool_stats,
            'request_metrics': {
                'total_requests': self.metrics.total_requests,
                'batched_requests': self.metrics.batched_requests,
                'avg_response_time_ms': self.metrics.avg_response_time_ms
            },
            'system_metrics': {
                'active_connections': sum(
                    stats.get('in_use_connections', 0) 
                    for stats in pool_stats.values()
                ),
                'total_connections': sum(
                    stats.get('created_connections', 0) 
                    for stats in pool_stats.values()
                )
            }
        }
    
    async def shutdown(self) -> None:
        """Shutdown performance optimization service."""
        try:
            # Cancel background tasks
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Close connection pools
            self.connection_pool_manager.close_all()
            
            logger.info("Performance optimization service shut down successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Global service instance
performance_service = PerformanceOptimizationService()


def cached_response(ttl: int = 3600):
    """Decorator for caching function responses."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = performance_service.generate_query_hash(
                func.__name__, *args, **kwargs
            )
            
            # Try to get from cache
            cached_result = await performance_service.get_cached_response(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000
            
            # Update metrics
            performance_service.metrics.total_requests += 1
            performance_service.metrics.avg_response_time_ms = (
                (performance_service.metrics.avg_response_time_ms * 
                 (performance_service.metrics.total_requests - 1) + execution_time) /
                performance_service.metrics.total_requests
            )
            
            # Cache result
            await performance_service.cache_response(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def get_performance_service() -> PerformanceOptimizationService:
    """Get the global performance optimization service."""
    return performance_service