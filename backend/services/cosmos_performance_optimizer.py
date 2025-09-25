"""
Cosmos Performance Optimizer

Provides performance optimization features for the OptimizedCosmosWrapper:
- Connection pooling for Redis operations
- Response caching for frequently accessed data
- Memory usage monitoring and cleanup automation
- Performance metrics collection and reporting

Requirements: 2.1, 2.2, 2.4, 2.5
"""

import os
import time
import asyncio
import logging
import threading
import weakref
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
import hashlib
import json

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - memory monitoring will be limited")

try:
    import redis
    from redis.connection import ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    timestamp: datetime
    response_time: float
    memory_usage_mb: float
    redis_operations: int
    cache_hits: int
    cache_misses: int
    files_accessed: int
    concurrent_requests: int
    error_count: int
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0


@dataclass
class ResourceUsage:
    """System resource usage information."""
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_io_read: int
    disk_io_write: int
    network_io_sent: int
    network_io_recv: int
    timestamp: datetime


class LRUCache:
    """
    Thread-safe LRU cache for response caching.
    
    Provides efficient caching with automatic eviction of least recently used items.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items to cache
            ttl_seconds: Time-to-live for cached items in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        with self._lock:
            # Check if key exists and is not expired
            if key in self._cache:
                timestamp = self._timestamps.get(key)
                if timestamp and datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                    # Move to end (most recently used)
                    value = self._cache.pop(key)
                    self._cache[key] = value
                    self._hits += 1
                    return value
                else:
                    # Expired, remove from cache
                    self._cache.pop(key, None)
                    self._timestamps.pop(key, None)
            
            self._misses += 1
            return None
    
    def put(self, key: str, value: Any):
        """Put item in cache."""
        with self._lock:
            # Remove if already exists
            if key in self._cache:
                self._cache.pop(key)
            
            # Add new item
            self._cache[key] = value
            self._timestamps[key] = datetime.now()
            
            # Evict oldest items if over capacity
            while len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)
                self._timestamps.pop(oldest_key, None)
    
    def clear(self):
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "ttl_seconds": self.ttl_seconds
            }


class ConnectionPoolManager:
    """
    Redis connection pool manager with optimization features.
    
    Manages Redis connection pools for different repositories and provides
    connection reuse and monitoring.
    """
    
    def __init__(self, max_connections: int = 50):
        """
        Initialize connection pool manager.
        
        Args:
            max_connections: Maximum connections per pool
        """
        self.max_connections = max_connections
        self._pools: Dict[str, ConnectionPool] = {}
        self._pool_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "created": 0,
            "in_use": 0,
            "available": 0,
            "total_requests": 0
        })
        self._lock = threading.RLock()
    
    def get_pool(self, redis_url: str) -> ConnectionPool:
        """Get or create connection pool for Redis URL."""
        with self._lock:
            if redis_url not in self._pools:
                if REDIS_AVAILABLE:
                    self._pools[redis_url] = ConnectionPool.from_url(
                        redis_url,
                        max_connections=self.max_connections,
                        retry_on_timeout=True,
                        socket_keepalive=True,
                        socket_keepalive_options={},
                        health_check_interval=30
                    )
                    self._pool_stats[redis_url]["created"] = 1
                    logger.info(f"Created Redis connection pool for {redis_url}")
                else:
                    raise RuntimeError("Redis not available")
            
            self._pool_stats[redis_url]["total_requests"] += 1
            return self._pools[redis_url]
    
    def get_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all connection pools."""
        with self._lock:
            stats = {}
            for url, pool in self._pools.items():
                pool_info = self._pool_stats[url].copy()
                if hasattr(pool, 'created_connections'):
                    pool_info["created_connections"] = pool.created_connections
                if hasattr(pool, 'available_connections'):
                    pool_info["available_connections"] = len(pool.available_connections)
                if hasattr(pool, 'in_use_connections'):
                    pool_info["in_use_connections"] = len(pool.in_use_connections)
                
                stats[url] = pool_info
            
            return stats
    
    def cleanup(self):
        """Clean up all connection pools."""
        with self._lock:
            for url, pool in self._pools.items():
                try:
                    pool.disconnect()
                    logger.debug(f"Disconnected pool for {url}")
                except Exception as e:
                    logger.warning(f"Error disconnecting pool for {url}: {e}")
            
            self._pools.clear()
            self._pool_stats.clear()


class MemoryMonitor:
    """
    Memory usage monitor with automatic cleanup.
    
    Monitors memory usage and triggers cleanup when thresholds are exceeded.
    """
    
    def __init__(self, warning_threshold_mb: int = 500, critical_threshold_mb: int = 1000):
        """
        Initialize memory monitor.
        
        Args:
            warning_threshold_mb: Warning threshold in MB
            critical_threshold_mb: Critical threshold in MB for automatic cleanup
        """
        self.warning_threshold_mb = warning_threshold_mb
        self.critical_threshold_mb = critical_threshold_mb
        self._cleanup_callbacks: List[callable] = []
        self._monitoring = False
        self._monitor_thread = None
        self._usage_history: List[ResourceUsage] = []
    
    def add_cleanup_callback(self, callback: callable):
        """Add cleanup callback to be called when memory threshold exceeded."""
        self._cleanup_callbacks.append(callback)
    
    def get_current_usage(self) -> ResourceUsage:
        """Get current system resource usage."""
        if PSUTIL_AVAILABLE:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            # System-wide stats
            system_memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()
            
            return ResourceUsage(
                cpu_percent=cpu_percent,
                memory_percent=system_memory.percent,
                memory_mb=memory_info.rss / 1024 / 1024,
                disk_io_read=disk_io.read_bytes if disk_io else 0,
                disk_io_write=disk_io.write_bytes if disk_io else 0,
                network_io_sent=network_io.bytes_sent if network_io else 0,
                network_io_recv=network_io.bytes_recv if network_io else 0,
                timestamp=datetime.now()
            )
        else:
            # Fallback without psutil
            import os
            import resource
            
            memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Convert to MB (ru_maxrss is in KB on Linux, bytes on macOS)
            if os.name == 'posix':
                memory_mb = memory_usage / 1024  # Linux: KB to MB
            else:
                memory_mb = memory_usage / 1024 / 1024  # macOS: bytes to MB
            
            return ResourceUsage(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_mb=memory_mb,
                disk_io_read=0,
                disk_io_write=0,
                network_io_sent=0,
                network_io_recv=0,
                timestamp=datetime.now()
            )
    
    def check_memory_usage(self) -> bool:
        """
        Check current memory usage and trigger cleanup if needed.
        
        Returns:
            True if cleanup was triggered, False otherwise
        """
        usage = self.get_current_usage()
        self._usage_history.append(usage)
        
        # Keep only last 100 measurements
        if len(self._usage_history) > 100:
            self._usage_history = self._usage_history[-100:]
        
        if usage.memory_mb > self.critical_threshold_mb:
            logger.warning(f"Critical memory usage: {usage.memory_mb:.1f}MB - triggering cleanup")
            self._trigger_cleanup()
            return True
        elif usage.memory_mb > self.warning_threshold_mb:
            logger.info(f"High memory usage warning: {usage.memory_mb:.1f}MB")
        
        return False
    
    def _trigger_cleanup(self):
        """Trigger all registered cleanup callbacks."""
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in cleanup callback: {e}")
    
    def start_monitoring(self, interval_seconds: int = 30):
        """Start background memory monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        
        def monitor_loop():
            while self._monitoring:
                try:
                    self.check_memory_usage()
                    time.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Error in memory monitoring loop: {e}")
                    time.sleep(interval_seconds)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Started memory monitoring with {interval_seconds}s interval")
    
    def stop_monitoring(self):
        """Stop background memory monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Stopped memory monitoring")
    
    def get_usage_history(self) -> List[Dict[str, Any]]:
        """Get memory usage history."""
        return [asdict(usage) for usage in self._usage_history]


class CosmosPerformanceOptimizer:
    """
    Main performance optimizer for Cosmos operations.
    
    Coordinates all performance optimization features including caching,
    connection pooling, memory monitoring, and metrics collection.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize performance optimizer.
        
        Args:
            config: Configuration dictionary with optimization settings
        """
        config = config or {}
        
        # Initialize components
        self.response_cache = LRUCache(
            max_size=config.get("cache_max_size", 1000),
            ttl_seconds=config.get("cache_ttl_seconds", 3600)
        )
        
        self.connection_pool_manager = ConnectionPoolManager(
            max_connections=config.get("max_connections", 50)
        )
        
        self.memory_monitor = MemoryMonitor(
            warning_threshold_mb=config.get("memory_warning_mb", 500),
            critical_threshold_mb=config.get("memory_critical_mb", 1000)
        )
        
        # Performance tracking
        self._metrics_history: List[PerformanceMetrics] = []
        self._active_requests = 0
        self._total_requests = 0
        self._error_count = 0
        self._lock = threading.RLock()
        
        # Register cleanup callback
        self.memory_monitor.add_cleanup_callback(self._cleanup_caches)
        
        logger.info("CosmosPerformanceOptimizer initialized")
    
    def get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Get cached response if available."""
        return self.response_cache.get(cache_key)
    
    def cache_response(self, cache_key: str, response: Any):
        """Cache response for future use."""
        self.response_cache.put(cache_key, response)
    
    def create_cache_key(self, message: str, context: Dict[str, Any] = None, files: List[str] = None) -> str:
        """Create cache key for request."""
        # Create deterministic cache key from request parameters
        key_data = {
            "message": message,
            "context": context or {},
            "files": sorted(files or [])
        }
        
        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()[:16]
    
    def get_redis_pool(self, redis_url: str) -> ConnectionPool:
        """Get Redis connection pool."""
        return self.connection_pool_manager.get_pool(redis_url)
    
    def start_request(self) -> str:
        """Start tracking a new request."""
        with self._lock:
            self._active_requests += 1
            self._total_requests += 1
            request_id = f"req_{self._total_requests}_{int(time.time())}"
            return request_id
    
    def end_request(self, request_id: str, response_time: float, error: bool = False):
        """End request tracking and record metrics."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            if error:
                self._error_count += 1
        
        # Record performance metrics
        self._record_metrics(response_time, error)
    
    def _record_metrics(self, response_time: float, error: bool = False):
        """Record performance metrics."""
        usage = self.memory_monitor.get_current_usage()
        cache_stats = self.response_cache.get_stats()
        
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            response_time=response_time,
            memory_usage_mb=usage.memory_mb,
            redis_operations=0,  # Will be updated by Redis manager
            cache_hits=cache_stats["hits"],
            cache_misses=cache_stats["misses"],
            files_accessed=0,  # Will be updated by caller
            concurrent_requests=self._active_requests,
            error_count=1 if error else 0
        )
        
        self._metrics_history.append(metrics)
        
        # Keep only last 1000 metrics
        if len(self._metrics_history) > 1000:
            self._metrics_history = self._metrics_history[-1000:]
    
    def _cleanup_caches(self):
        """Clean up caches to free memory."""
        logger.info("Performing cache cleanup due to high memory usage")
        
        # Clear response cache
        self.response_cache.clear()
        
        # Clear old metrics
        if len(self._metrics_history) > 100:
            self._metrics_history = self._metrics_history[-100:]
        
        logger.info("Cache cleanup completed")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        with self._lock:
            if not self._metrics_history:
                return {"error": "No metrics available"}
            
            recent_metrics = self._metrics_history[-100:]  # Last 100 requests
            
            # Calculate averages
            avg_response_time = sum(m.response_time for m in recent_metrics) / len(recent_metrics)
            avg_memory_usage = sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
            avg_cache_hit_rate = sum(m.cache_hit_rate for m in recent_metrics) / len(recent_metrics)
            
            # Get current stats
            cache_stats = self.response_cache.get_stats()
            pool_stats = self.connection_pool_manager.get_pool_stats()
            memory_usage = self.memory_monitor.get_current_usage()
            
            return {
                "summary": {
                    "total_requests": self._total_requests,
                    "active_requests": self._active_requests,
                    "error_count": self._error_count,
                    "error_rate": (self._error_count / self._total_requests * 100) if self._total_requests > 0 else 0
                },
                "performance": {
                    "avg_response_time": avg_response_time,
                    "avg_memory_usage_mb": avg_memory_usage,
                    "avg_cache_hit_rate": avg_cache_hit_rate
                },
                "cache": cache_stats,
                "connection_pools": pool_stats,
                "memory": asdict(memory_usage),
                "timestamp": datetime.now().isoformat()
            }
    
    def start_monitoring(self):
        """Start background monitoring."""
        self.memory_monitor.start_monitoring()
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self.memory_monitor.stop_monitoring()
    
    def cleanup(self):
        """Clean up all resources."""
        logger.info("Cleaning up CosmosPerformanceOptimizer")
        
        # Stop monitoring
        self.stop_monitoring()
        
        # Clean up connection pools
        self.connection_pool_manager.cleanup()
        
        # Clear caches
        self.response_cache.clear()
        
        # Clear metrics
        self._metrics_history.clear()
        
        logger.info("CosmosPerformanceOptimizer cleanup completed")


# Global optimizer instance
_global_optimizer: Optional[CosmosPerformanceOptimizer] = None
_optimizer_lock = threading.Lock()


def get_performance_optimizer(config: Dict[str, Any] = None) -> CosmosPerformanceOptimizer:
    """
    Get global performance optimizer instance.
    
    Args:
        config: Configuration for optimizer (only used on first call)
        
    Returns:
        CosmosPerformanceOptimizer instance
    """
    global _global_optimizer
    
    with _optimizer_lock:
        if _global_optimizer is None:
            _global_optimizer = CosmosPerformanceOptimizer(config)
            _global_optimizer.start_monitoring()
        
        return _global_optimizer


def cleanup_global_optimizer():
    """Clean up global optimizer instance."""
    global _global_optimizer
    
    with _optimizer_lock:
        if _global_optimizer:
            _global_optimizer.cleanup()
            _global_optimizer = None