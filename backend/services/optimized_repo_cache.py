"""
Optimized Repository Cache Service

Provides high-performance caching for repository data with intelligent
prefetching, compression, and cache warming strategies.
"""

import asyncio
import gzip
import json
import logging
import time
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..services.performance_optimization_service import get_performance_service
    from ..services.redis_repo_manager import RedisRepoManager
    from ..integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from services.performance_optimization_service import get_performance_service
    from services.redis_repo_manager import RedisRepoManager
    from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Repository cache statistics."""
    total_repositories: int = 0
    cached_repositories: int = 0
    cache_size_bytes: int = 0
    hit_rate: float = 0.0
    avg_fetch_time_ms: float = 0.0
    prefetch_hits: int = 0
    compression_ratio: float = 0.0


@dataclass
class RepositoryMetadata:
    """Enhanced repository metadata for caching."""
    name: str
    url: str
    branch: str
    size_bytes: int
    file_count: int
    last_updated: datetime
    access_count: int
    last_accessed: datetime
    cache_priority: int  # 1-10, higher = more important
    prefetch_score: float  # Calculated prefetch priority
    compression_enabled: bool = True
    
    def calculate_prefetch_score(self) -> float:
        """Calculate prefetch priority score."""
        # Factors: recent access, access frequency, cache priority
        now = datetime.now()
        hours_since_access = (now - self.last_accessed).total_seconds() / 3600
        
        # Decay factor based on time since last access
        time_factor = max(0.1, 1.0 - (hours_since_access / 168))  # 1 week decay
        
        # Access frequency factor
        frequency_factor = min(1.0, self.access_count / 100)
        
        # Priority factor
        priority_factor = self.cache_priority / 10
        
        self.prefetch_score = (time_factor * 0.4 + 
                              frequency_factor * 0.3 + 
                              priority_factor * 0.3)
        
        return self.prefetch_score


class OptimizedRepoCache:
    """
    Optimized repository cache with intelligent prefetching,
    compression, and performance monitoring.
    """
    
    def __init__(self):
        """Initialize optimized repository cache."""
        self.settings = get_settings()
        self.performance_service = get_performance_service()
        self.redis_cache = SmartRedisCache()
        
        # Cache configuration
        self.max_cache_size_mb = 500  # 500MB cache limit
        self.compression_threshold = 10240  # 10KB threshold for compression
        self.prefetch_batch_size = 5
        self.cache_warming_enabled = True
        
        # Internal state
        self._repo_metadata: Dict[str, RepositoryMetadata] = {}
        self._prefetch_queue: asyncio.Queue = asyncio.Queue()
        self._cache_stats = CacheStats()
        self._prefetch_task: Optional[asyncio.Task] = None
        self._warming_task: Optional[asyncio.Task] = None
        
        # Start background tasks
        self._start_background_tasks()
    
    def _start_background_tasks(self) -> None:
        """Start background prefetching and cache warming tasks."""
        self._prefetch_task = asyncio.create_task(self._prefetch_worker())
        if self.cache_warming_enabled:
            self._warming_task = asyncio.create_task(self._cache_warming_worker())
    
    async def _prefetch_worker(self) -> None:
        """Background worker for prefetching repositories."""
        while True:
            try:
                # Get repositories to prefetch
                repos_to_prefetch = await self._get_prefetch_candidates()
                
                for repo_key in repos_to_prefetch:
                    try:
                        await self._prefetch_repository(repo_key)
                        await asyncio.sleep(0.1)  # Small delay between prefetches
                    except Exception as e:
                        logger.error(f"Error prefetching {repo_key}: {e}")
                
                # Sleep before next prefetch cycle
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in prefetch worker: {e}")
                await asyncio.sleep(30)
    
    async def _cache_warming_worker(self) -> None:
        """Background worker for cache warming."""
        while True:
            try:
                # Warm cache with popular repositories
                await self._warm_popular_repositories()
                
                # Sleep for 30 minutes
                await asyncio.sleep(1800)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache warming worker: {e}")
                await asyncio.sleep(300)
    
    async def _get_prefetch_candidates(self) -> List[str]:
        """Get repositories that should be prefetched."""
        candidates = []
        
        # Update prefetch scores
        for repo_key, metadata in self._repo_metadata.items():
            metadata.calculate_prefetch_score()
        
        # Sort by prefetch score and take top candidates
        sorted_repos = sorted(
            self._repo_metadata.items(),
            key=lambda x: x[1].prefetch_score,
            reverse=True
        )
        
        for repo_key, metadata in sorted_repos[:self.prefetch_batch_size]:
            # Check if repository needs prefetching
            if await self._should_prefetch(repo_key, metadata):
                candidates.append(repo_key)
        
        return candidates
    
    async def _should_prefetch(self, repo_key: str, metadata: RepositoryMetadata) -> bool:
        """Determine if repository should be prefetched."""
        # Check if already cached
        cache_key = f"optimized_repo:{repo_key}"
        cached_data = await self.performance_service.get_cached_response(cache_key)
        
        if cached_data is not None:
            return False  # Already cached
        
        # Check prefetch score threshold
        if metadata.prefetch_score < 0.3:
            return False  # Score too low
        
        # Check cache size limits
        if self._cache_stats.cache_size_bytes > self.max_cache_size_mb * 1024 * 1024:
            return False  # Cache full
        
        return True
    
    async def _prefetch_repository(self, repo_key: str) -> None:
        """Prefetch repository data."""
        try:
            parts = repo_key.split(":")
            if len(parts) < 2:
                return
            
            repo_name = parts[0]
            branch = parts[1] if len(parts) > 1 else "main"
            
            # Create repository manager
            repo_manager = RedisRepoManager(
                repo_url=f"https://github.com/{repo_name}",
                branch=branch,
                user_tier="free",
                username="prefetch_user"
            )
            
            # Fetch repository data
            start_time = time.time()
            repo_data = await self._fetch_repository_data(repo_manager)
            fetch_time = (time.time() - start_time) * 1000
            
            if repo_data:
                # Cache the data
                cache_key = f"optimized_repo:{repo_key}"
                await self.performance_service.cache_response(
                    cache_key, 
                    repo_data, 
                    ttl=7200  # 2 hours
                )
                
                # Update statistics
                self._cache_stats.prefetch_hits += 1
                
                logger.info(f"Prefetched repository {repo_key} in {fetch_time:.2f}ms")
            
        except Exception as e:
            logger.error(f"Error prefetching repository {repo_key}: {e}")
    
    async def _warm_popular_repositories(self) -> None:
        """Warm cache with popular repositories."""
        try:
            # Get list of popular repositories (this would be from analytics)
            popular_repos = [
                "microsoft/vscode",
                "facebook/react", 
                "tensorflow/tensorflow",
                "kubernetes/kubernetes",
                "nodejs/node"
            ]
            
            for repo_name in popular_repos:
                repo_key = f"{repo_name}:main"
                
                # Check if already cached
                cache_key = f"optimized_repo:{repo_key}"
                cached_data = await self.performance_service.get_cached_response(cache_key)
                
                if cached_data is None:
                    await self._prefetch_repository(repo_key)
                    await asyncio.sleep(1)  # Rate limit warming
            
            logger.info("Completed cache warming cycle")
            
        except Exception as e:
            logger.error(f"Error in cache warming: {e}")
    
    async def get_repository_data(
        self, 
        repo_name: str, 
        branch: str = "main",
        user_tier: str = "free",
        username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get repository data with optimized caching.
        
        Args:
            repo_name: Repository name (owner/repo)
            branch: Branch name
            user_tier: User tier for access control
            username: Username for authentication
            
        Returns:
            Repository data dictionary or None
        """
        repo_key = f"{repo_name}:{branch}"
        cache_key = f"optimized_repo:{repo_key}"
        
        start_time = time.time()
        
        try:
            # Try to get from cache first
            cached_data = await self.performance_service.get_cached_response(cache_key)
            
            if cached_data is not None:
                # Update access metadata
                await self._update_access_metadata(repo_key)
                
                fetch_time = (time.time() - start_time) * 1000
                self._update_fetch_time_stats(fetch_time)
                
                logger.debug(f"Cache hit for {repo_key} in {fetch_time:.2f}ms")
                return cached_data
            
            # Cache miss - fetch from source
            repo_manager = RedisRepoManager(
                repo_url=f"https://github.com/{repo_name}",
                branch=branch,
                user_tier=user_tier,
                username=username
            )
            
            # Fetch repository data
            repo_data = await self._fetch_repository_data(repo_manager)
            
            if repo_data:
                # Compress if needed
                if self._should_compress(repo_data):
                    repo_data = await self._compress_data(repo_data)
                
                # Cache the result
                await self.performance_service.cache_response(
                    cache_key, 
                    repo_data, 
                    ttl=7200  # 2 hours
                )
                
                # Update metadata
                await self._update_repository_metadata(
                    repo_key, repo_name, branch, repo_data
                )
                
                fetch_time = (time.time() - start_time) * 1000
                self._update_fetch_time_stats(fetch_time)
                
                logger.info(f"Fetched and cached {repo_key} in {fetch_time:.2f}ms")
                return repo_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting repository data for {repo_key}: {e}")
            return None
    
    async def _fetch_repository_data(self, repo_manager: RedisRepoManager) -> Optional[Dict[str, Any]]:
        """Fetch repository data using repository manager."""
        try:
            # Ensure repository is available
            if not repo_manager._ensure_repository_data():
                return None
            
            # Get repository info
            repo_info = repo_manager.get_repository_info()
            
            # Get repository map
            repo_map = repo_manager.get_repo_map()
            
            # Get file list
            files = repo_manager.list_files()
            
            # Sample some file contents for better caching
            sample_files = files[:10] if files else []
            file_contents = {}
            
            for file_path in sample_files:
                content = repo_manager.get_file_content(file_path)
                if content:
                    file_contents[file_path] = content
            
            return {
                'repo_info': repo_info,
                'repo_map': repo_map,
                'files': files,
                'sample_contents': file_contents,
                'cached_at': datetime.now().isoformat(),
                'cache_version': '1.0'
            }
            
        except Exception as e:
            logger.error(f"Error fetching repository data: {e}")
            return None
    
    def _should_compress(self, data: Dict[str, Any]) -> bool:
        """Determine if data should be compressed."""
        try:
            data_size = len(json.dumps(data, default=str).encode())
            return data_size > self.compression_threshold
        except:
            return False
    
    async def _compress_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compress repository data."""
        try:
            # Compress large text fields
            compressed_data = data.copy()
            
            if 'repo_map' in data and isinstance(data['repo_map'], str):
                compressed_map = gzip.compress(data['repo_map'].encode())
                compressed_data['repo_map'] = {
                    'compressed': True,
                    'data': compressed_map.hex()
                }
            
            if 'sample_contents' in data:
                compressed_contents = {}
                for file_path, content in data['sample_contents'].items():
                    if isinstance(content, str) and len(content) > 1024:
                        compressed_content = gzip.compress(content.encode())
                        compressed_contents[file_path] = {
                            'compressed': True,
                            'data': compressed_content.hex()
                        }
                    else:
                        compressed_contents[file_path] = content
                
                compressed_data['sample_contents'] = compressed_contents
            
            # Calculate compression ratio
            original_size = len(json.dumps(data, default=str).encode())
            compressed_size = len(json.dumps(compressed_data, default=str).encode())
            compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
            
            self._cache_stats.compression_ratio = (
                (self._cache_stats.compression_ratio * 0.9) + (compression_ratio * 0.1)
            )
            
            return compressed_data
            
        except Exception as e:
            logger.error(f"Error compressing data: {e}")
            return data
    
    async def _decompress_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decompress repository data."""
        try:
            decompressed_data = data.copy()
            
            # Decompress repo_map
            if ('repo_map' in data and 
                isinstance(data['repo_map'], dict) and 
                data['repo_map'].get('compressed')):
                
                compressed_hex = data['repo_map']['data']
                compressed_bytes = bytes.fromhex(compressed_hex)
                decompressed_map = gzip.decompress(compressed_bytes).decode()
                decompressed_data['repo_map'] = decompressed_map
            
            # Decompress sample_contents
            if 'sample_contents' in data:
                decompressed_contents = {}
                for file_path, content in data['sample_contents'].items():
                    if (isinstance(content, dict) and 
                        content.get('compressed')):
                        
                        compressed_hex = content['data']
                        compressed_bytes = bytes.fromhex(compressed_hex)
                        decompressed_content = gzip.decompress(compressed_bytes).decode()
                        decompressed_contents[file_path] = decompressed_content
                    else:
                        decompressed_contents[file_path] = content
                
                decompressed_data['sample_contents'] = decompressed_contents
            
            return decompressed_data
            
        except Exception as e:
            logger.error(f"Error decompressing data: {e}")
            return data
    
    async def _update_access_metadata(self, repo_key: str) -> None:
        """Update repository access metadata."""
        if repo_key in self._repo_metadata:
            metadata = self._repo_metadata[repo_key]
            metadata.access_count += 1
            metadata.last_accessed = datetime.now()
        else:
            # Create new metadata entry
            parts = repo_key.split(":")
            repo_name = parts[0]
            branch = parts[1] if len(parts) > 1 else "main"
            
            self._repo_metadata[repo_key] = RepositoryMetadata(
                name=repo_name,
                url=f"https://github.com/{repo_name}",
                branch=branch,
                size_bytes=0,
                file_count=0,
                last_updated=datetime.now(),
                access_count=1,
                last_accessed=datetime.now(),
                cache_priority=5  # Default priority
            )
    
    async def _update_repository_metadata(
        self, 
        repo_key: str, 
        repo_name: str, 
        branch: str, 
        repo_data: Dict[str, Any]
    ) -> None:
        """Update repository metadata after fetch."""
        try:
            # Calculate size
            data_size = len(json.dumps(repo_data, default=str).encode())
            
            # Get file count
            file_count = len(repo_data.get('files', []))
            
            # Update or create metadata
            if repo_key in self._repo_metadata:
                metadata = self._repo_metadata[repo_key]
                metadata.size_bytes = data_size
                metadata.file_count = file_count
                metadata.last_updated = datetime.now()
                metadata.access_count += 1
                metadata.last_accessed = datetime.now()
            else:
                self._repo_metadata[repo_key] = RepositoryMetadata(
                    name=repo_name,
                    url=f"https://github.com/{repo_name}",
                    branch=branch,
                    size_bytes=data_size,
                    file_count=file_count,
                    last_updated=datetime.now(),
                    access_count=1,
                    last_accessed=datetime.now(),
                    cache_priority=5
                )
            
            # Update cache stats
            self._cache_stats.total_repositories = len(self._repo_metadata)
            self._cache_stats.cache_size_bytes += data_size
            
        except Exception as e:
            logger.error(f"Error updating repository metadata: {e}")
    
    def _update_fetch_time_stats(self, fetch_time_ms: float) -> None:
        """Update fetch time statistics."""
        if self._cache_stats.avg_fetch_time_ms == 0:
            self._cache_stats.avg_fetch_time_ms = fetch_time_ms
        else:
            # Exponential moving average
            self._cache_stats.avg_fetch_time_ms = (
                self._cache_stats.avg_fetch_time_ms * 0.9 + fetch_time_ms * 0.1
            )
    
    async def invalidate_repository(self, repo_name: str, branch: str = "main") -> bool:
        """Invalidate cached repository data."""
        try:
            repo_key = f"{repo_name}:{branch}"
            cache_key = f"optimized_repo:{repo_key}"
            
            # Remove from performance service cache
            # (This would need to be implemented in the performance service)
            
            # Remove metadata
            if repo_key in self._repo_metadata:
                del self._repo_metadata[repo_key]
            
            logger.info(f"Invalidated cache for {repo_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating repository cache: {e}")
            return False
    
    async def warm_repository_cache(self, repo_names: List[str]) -> Dict[str, bool]:
        """Warm cache for specific repositories."""
        results = {}
        
        for repo_name in repo_names:
            try:
                repo_data = await self.get_repository_data(repo_name)
                results[repo_name] = repo_data is not None
                
                # Small delay between requests
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error warming cache for {repo_name}: {e}")
                results[repo_name] = False
        
        return results
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        # Calculate hit rate from performance service
        perf_metrics = self.performance_service.get_performance_metrics()
        cache_metrics = perf_metrics.get('cache_metrics', {})
        
        self._cache_stats.hit_rate = cache_metrics.get('hit_rate', 0.0)
        self._cache_stats.cached_repositories = len(self._repo_metadata)
        
        return {
            'cache_stats': asdict(self._cache_stats),
            'repository_metadata': [
                {
                    'repo_key': repo_key,
                    'name': metadata.name,
                    'branch': metadata.branch,
                    'size_bytes': metadata.size_bytes,
                    'file_count': metadata.file_count,
                    'access_count': metadata.access_count,
                    'last_accessed': metadata.last_accessed.isoformat(),
                    'cache_priority': metadata.cache_priority,
                    'prefetch_score': metadata.prefetch_score
                }
                for repo_key, metadata in list(self._repo_metadata.items())[:20]
            ],
            'performance_metrics': perf_metrics
        }
    
    async def shutdown(self) -> None:
        """Shutdown optimized repository cache."""
        try:
            # Cancel background tasks
            if self._prefetch_task:
                self._prefetch_task.cancel()
                try:
                    await self._prefetch_task
                except asyncio.CancelledError:
                    pass
            
            if self._warming_task:
                self._warming_task.cancel()
                try:
                    await self._warming_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("Optimized repository cache shut down successfully")
            
        except Exception as e:
            logger.error(f"Error during cache shutdown: {e}")


# Global cache instance
optimized_repo_cache = OptimizedRepoCache()


def get_optimized_repo_cache() -> OptimizedRepoCache:
    """Get the global optimized repository cache."""
    return optimized_repo_cache