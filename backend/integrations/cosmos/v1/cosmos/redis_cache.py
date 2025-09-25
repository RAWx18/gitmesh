"""
Smart Redis Cache implementation for GitHub repository caching.

This module provides intelligent Redis caching with optimized connection pooling,
pipeline operations, retry logic, and SSL/TLS support for secure cloud connections.
"""

import os
import time
import random
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from urllib.parse import urlparse

try:
    import redis
    from redis.connection import ConnectionPool
    from redis.exceptions import (
        ConnectionError, 
        TimeoutError, 
        RedisError,
        ResponseError
    )
except ImportError:
    raise ImportError(
        "Redis package is required. Install with: pip install redis"
    )

# Configure logging
logger = logging.getLogger(__name__)


# Import the production-ready configuration
try:
    from .config import get_config, RedisCloudConfig
    from .monitoring import MonitoredOperation, get_system_monitor
except ImportError:
    from config import get_config, RedisCloudConfig
    from monitoring import MonitoredOperation, get_system_monitor


class RetryConfig:
    """Configuration for retry logic with exponential backoff."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add jitter: ±25% of the calculated delay
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


class SmartRedisCache:
    """
    Smart Redis cache with optimized connection pooling, pipeline operations,
    intelligent retry logic, and SSL/TLS support.
    """
    
    def __init__(
        self, 
        config: Optional[RedisCloudConfig] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize SmartRedisCache.
        
        Args:
            config: Redis configuration. If None, loads from global config.
            retry_config: Retry configuration. If None, uses defaults.
        """
        if config is None:
            # Use the global production configuration
            global_config = get_config()
            self.config = global_config.redis
        else:
            self.config = config
            
        self.retry_config = retry_config or RetryConfig()
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._last_health_check = 0
        
        # Initialize connection
        self._initialize_connection()
    
    def _initialize_connection(self) -> None:
        """Initialize Redis connection with optimized pooling and SSL/TLS support."""
        try:
            # Use from_url method which handles SSL automatically for rediss:// URLs
            connection_kwargs = {
                'db': self.config.db,
                'socket_timeout': self.config.socket_timeout,
                'socket_connect_timeout': self.config.socket_connect_timeout,
                'socket_keepalive': self.config.socket_keepalive,
                'retry_on_timeout': self.config.retry_on_timeout,
                'health_check_interval': self.config.health_check_interval,
                'decode_responses': self.config.decode_responses,
                'encoding': self.config.encoding,
            }
            
            # Add SSL configuration if enabled
            if self.config.ssl_enabled:
                import ssl
                cert_reqs_map = {
                    'none': ssl.CERT_NONE,
                    'optional': ssl.CERT_OPTIONAL,
                    'required': ssl.CERT_REQUIRED
                }
                
                connection_kwargs.update({
                    'ssl_cert_reqs': cert_reqs_map.get(self.config.ssl_cert_reqs, ssl.CERT_NONE),
                    'ssl_check_hostname': self.config.ssl_check_hostname,
                })
            
            # Override password if provided separately
            if self.config.password:
                connection_kwargs['password'] = self.config.password
            
            self._client = redis.from_url(self.config.url, **connection_kwargs)
            
            # Test connection
            self._client.ping()
            logger.info("Redis connection initialized successfully with production configuration")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            raise ConnectionError(f"Redis initialization failed: {e}")
    
    def _execute_with_retry(self, operation, *args, **kwargs) -> Any:
        """
        Execute Redis operation with intelligent retry logic.
        
        Args:
            operation: Redis operation to execute
            *args: Operation arguments
            **kwargs: Operation keyword arguments
            
        Returns:
            Operation result
            
        Raises:
            RedisError: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return operation(*args, **kwargs)
                
            except (ConnectionError, TimeoutError) as e:
                last_exception = e
                
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(
                        f"Redis operation failed (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    
                    # Try to reconnect on connection errors
                    if isinstance(e, ConnectionError):
                        try:
                            self._initialize_connection()
                        except Exception as reconnect_error:
                            logger.error(f"Reconnection failed: {reconnect_error}")
                else:
                    logger.error(f"All retry attempts failed: {e}")
                    break
                    
            except Exception as e:
                # Non-retryable errors - but don't re-raise immediately, let it fall through
                logger.error(f"Non-retryable Redis error: {e}")
                last_exception = e
                break
        
        # If we get here, all retries failed
        raise RedisError(f"Operation failed after {self.retry_config.max_retries} retries: {last_exception}")
    
    def health_check(self, force: bool = False) -> bool:
        """
        Perform health check on Redis connection.
        
        Args:
            force: Force health check even if within interval
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            current_time = time.time()
            
            # Skip check if within interval and not forced
            if (not force and 
                current_time - self._last_health_check < self.config.health_check_interval and 
                self._last_health_check > 0):
                return True
            
            self._execute_with_retry(self._client.ping)
            self._last_health_check = current_time
            return True
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def store_repository_batch(self, repo_name: str, data: Dict[str, str]) -> bool:
        """
        Store repository data using optimized pipeline operations with chunking for large data.
        
        Args:
            repo_name: Repository name for key generation
            data: Dictionary with keys 'content', 'tree', 'summary', 'metadata'
            
        Returns:
            True if successful, False otherwise
        """
        with MonitoredOperation("redis_store_repository_batch", {"repo": repo_name}):
            try:
                # Ensure health check
                if not self.health_check():
                    raise ConnectionError("Redis health check failed")
                
                # Check data sizes and use chunked storage for large content
                CHUNK_SIZE = 1024 * 1024  # 1MB chunks
                large_data_keys = []
                
                for data_type, content in data.items():
                    if isinstance(content, str) and len(content.encode('utf-8')) > CHUNK_SIZE:
                        large_data_keys.append(data_type)
                        logger.info(f"Large data detected for {data_type}: {len(content.encode('utf-8'))} bytes, will use chunked storage")
                
                def _cleanup_existing_keys():
                    """Clean up existing keys before storing new data"""
                    cleanup_keys = []
                    for data_type in ['content', 'tree', 'summary', 'metadata']:
                        cleanup_keys.append(f"repo:{repo_name}:{data_type}")
                        # Also clean up potential chunks
                        if data_type in large_data_keys:
                            for i in range(100):  # Clean up to 100 potential chunks
                                cleanup_keys.append(f"repo:{repo_name}:{data_type}:chunk:{i}")
                    
                    # Delete in batches to avoid timeout
                    batch_size = 50
                    for i in range(0, len(cleanup_keys), batch_size):
                        batch = cleanup_keys[i:i + batch_size]
                        try:
                            self._client.delete(*batch)
                        except:
                            pass  # Ignore errors during cleanup
                
                def _store_chunked_data(data_type: str, content: str):
                    """Store large data in chunks"""
                    content_bytes = content.encode('utf-8')
                    chunks = []
                    
                    # Split into chunks
                    for i in range(0, len(content_bytes), CHUNK_SIZE):
                        chunk = content_bytes[i:i + CHUNK_SIZE]
                        chunks.append(chunk)
                    
                    # Store chunks using pipeline
                    pipe = self._client.pipeline()
                    
                    # Store chunk count first
                    chunk_count_key = f"repo:{repo_name}:{data_type}:chunk_count"
                    pipe.set(chunk_count_key, len(chunks))
                    
                    # Store each chunk
                    for i, chunk in enumerate(chunks):
                        chunk_key = f"repo:{repo_name}:{data_type}:chunk:{i}"
                        pipe.set(chunk_key, chunk)
                    
                    # Execute chunk storage
                    pipe.execute()
                    logger.info(f"Stored {data_type} in {len(chunks)} chunks")
                
                def _store_regular_data():
                    """Store regular-sized data using pipeline"""
                    pipe = self._client.pipeline()
                    
                    # Store non-chunked data
                    for data_type, content in data.items():
                        if data_type not in large_data_keys:
                            key = f"repo:{repo_name}:{data_type}"
                            pipe.set(key, content)
                    
                    # Add metadata with timestamp
                    metadata_key = f"repo:{repo_name}:metadata"
                    metadata_value = f"stored_at:{time.time()},repo_name:{repo_name},data_types:{','.join(data.keys())},chunked_types:{','.join(large_data_keys)}"
                    pipe.set(metadata_key, metadata_value)
                    
                    # Execute regular data storage
                    return pipe.execute()
                
                # Step 1: Clean up existing keys
                logger.info(f"Cleaning up existing keys for {repo_name}")
                self._execute_with_retry(_cleanup_existing_keys)
                
                # Step 2: Store chunked data for large items
                for data_type in large_data_keys:
                    logger.info(f"Storing chunked data for {data_type}")
                    self._execute_with_retry(_store_chunked_data, data_type, data[data_type])
                
                # Step 3: Store regular data
                logger.info(f"Storing regular data for {repo_name}")
                result = self._execute_with_retry(_store_regular_data)
                
                logger.info(f"Successfully stored repository data for {repo_name} (chunked: {large_data_keys})")
                return True
                
            except Exception as e:
                logger.error(f"Failed to store repository data for {repo_name}: {e}")
                return False
    
    def get_repository_data_cached(self, repo_name: str) -> Optional[Dict[str, str]]:
        """
        Get repository data with smart caching and chunked data reconstruction.
        
        Args:
            repo_name: Repository name
            
        Returns:
            Dictionary with repository data or None if not found
        """
        with MonitoredOperation("redis_get_repository_data", {"repo": repo_name}):
            try:
                if not self.health_check():
                    raise ConnectionError("Redis health check failed")
                
                def _get_metadata():
                    """Get metadata to determine which data types are chunked"""
                    metadata_key = f"repo:{repo_name}:metadata"
                    metadata_raw = self._client.get(metadata_key)
                    
                    metadata = {}
                    chunked_types = []
                    
                    if metadata_raw:
                        if isinstance(metadata_raw, bytes):
                            metadata_raw = metadata_raw.decode('utf-8')
                        
                        # Parse "key:value,key:value" format
                        for pair in metadata_raw.split(','):
                            if ':' in pair:
                                key, value = pair.split(':', 1)
                                metadata[key.strip()] = value.strip()
                        
                        # Extract chunked types
                        if 'chunked_types' in metadata:
                            chunked_types = [t.strip() for t in metadata['chunked_types'].split(',') if t.strip()]
                    
                    return metadata, chunked_types
                
                def _get_chunked_data(data_type: str) -> Optional[str]:
                    """Reconstruct chunked data"""
                    try:
                        # Get chunk count
                        chunk_count_key = f"repo:{repo_name}:{data_type}:chunk_count"
                        chunk_count = self._client.get(chunk_count_key)
                        
                        if not chunk_count:
                            return None
                        
                        chunk_count = int(chunk_count)
                        
                        # Get all chunks using pipeline
                        pipe = self._client.pipeline()
                        for i in range(chunk_count):
                            chunk_key = f"repo:{repo_name}:{data_type}:chunk:{i}"
                            pipe.get(chunk_key)
                        
                        chunks = pipe.execute()
                        
                        # Reconstruct data
                        if all(chunk is not None for chunk in chunks):
                            content_bytes = b''.join(chunks)
                            return content_bytes.decode('utf-8')
                        else:
                            logger.warning(f"Missing chunks for {data_type}")
                            return None
                            
                    except Exception as e:
                        logger.error(f"Failed to reconstruct chunked data for {data_type}: {e}")
                        return None
                
                def _get_regular_data(data_types: List[str]) -> Dict[str, str]:
                    """Get regular (non-chunked) data"""
                    pipe = self._client.pipeline()
                    
                    for data_type in data_types:
                        key = f"repo:{repo_name}:{data_type}"
                        pipe.get(key)
                    
                    results = pipe.execute()
                    
                    data = {}
                    for i, data_type in enumerate(data_types):
                        if results[i] is not None:
                            content = results[i]
                            data[data_type] = content.decode('utf-8') if isinstance(content, bytes) else content
                    
                    return data
                
                # Step 1: Get metadata and determine chunked types
                metadata, chunked_types = self._execute_with_retry(_get_metadata)
                
                if not metadata:
                    logger.warning(f"No metadata found for repository {repo_name}")
                    return None
                
                # Step 2: Get regular data
                regular_types = [t for t in ['content', 'tree', 'summary'] if t not in chunked_types]
                regular_data = self._execute_with_retry(_get_regular_data, regular_types)
                
                # Step 3: Get chunked data
                result_data = regular_data.copy()
                for data_type in chunked_types:
                    if data_type in ['content', 'tree', 'summary']:
                        chunked_content = self._execute_with_retry(_get_chunked_data, data_type)
                        if chunked_content is not None:
                            result_data[data_type] = chunked_content
                        else:
                            logger.error(f"Failed to retrieve chunked data for {data_type}")
                            return None
                
                # Verify we have all required data
                required_keys = ['content', 'tree', 'summary']
                if not all(key in result_data for key in required_keys):
                    missing_keys = [key for key in required_keys if key not in result_data]
                    logger.warning(f"Missing required data for {repo_name}: {missing_keys}")
                    return None
                
                result_data['metadata'] = metadata
                logger.info(f"Successfully retrieved repository data for {repo_name} (chunked: {chunked_types})")
                return result_data
                
            except Exception as e:
                logger.error(f"Failed to get repository data for {repo_name}: {e}")
                return None
    
    def exists_with_metadata(self, repo_name: str) -> Dict[str, Any]:
        """
        Check if repository exists and return metadata in a single operation.
        
        Args:
            repo_name: Repository name
            
        Returns:
            Dictionary with 'exists' boolean and 'metadata' dict
        """
        try:
            if not self.health_check():
                raise ConnectionError("Redis health check failed")
            
            def _check_existence():
                pipe = self._client.pipeline()
                
                # Check existence of key data types
                for key_suffix in ['content', 'tree', 'summary']:
                    key = f"repo:{repo_name}:{key_suffix}"
                    pipe.exists(key)
                
                # Get metadata
                metadata_key = f"repo:{repo_name}:metadata"
                pipe.get(metadata_key)
                
                return pipe.execute()
            
            results = self._execute_with_retry(_check_existence)
            content_exists, tree_exists, summary_exists, metadata_raw = results
            
            exists = all([content_exists, tree_exists, summary_exists])
            
            # Parse metadata string format
            metadata = {}
            if metadata_raw:
                if isinstance(metadata_raw, bytes):
                    metadata_raw = metadata_raw.decode('utf-8')
                
                # Parse "key:value,key:value" format
                for pair in metadata_raw.split(','):
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        metadata[key.strip()] = value.strip()
            
            return {
                'exists': exists,
                'metadata': metadata,
                'partial': any([content_exists, tree_exists, summary_exists]) and not exists
            }
            
        except Exception as e:
            logger.error(f"Failed to check existence for {repo_name}: {e}")
            return {'exists': False, 'metadata': {}, 'partial': False}
    
    def pipeline_operations(self, operations: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple Redis operations in a single pipeline.
        
        Args:
            operations: List of operation dictionaries with 'method', 'args', 'kwargs'
            
        Returns:
            List of operation results
        """
        try:
            if not self.health_check():
                raise ConnectionError("Redis health check failed")
            
            def _execute_pipeline():
                pipe = self._client.pipeline()
                
                for op in operations:
                    method = getattr(pipe, op['method'])
                    args = op.get('args', [])
                    kwargs = op.get('kwargs', {})
                    method(*args, **kwargs)
                
                return pipe.execute()
            
            return self._execute_with_retry(_execute_pipeline)
            
        except Exception as e:
            logger.error(f"Pipeline operations failed: {e}")
            raise
    
    def list_cached_repositories(self) -> List[Dict[str, Any]]:
        """
        List all cached repositories with their metadata.
        
        Returns:
            List of dictionaries with repository information
        """
        try:
            if not self.health_check():
                raise ConnectionError("Redis health check failed")
            
            def _list_repos():
                # Get all repository keys
                repo_keys = self._client.keys("repo:*:metadata")
                
                if not repo_keys:
                    return []
                
                # Extract repository names
                repo_names = []
                for key in repo_keys:
                    # Extract repo name from "repo:name:metadata"
                    parts = key.split(':')
                    if len(parts) >= 3:
                        repo_name = ':'.join(parts[1:-1])  # Handle repo names with colons
                        repo_names.append(repo_name)
                
                # Get metadata for each repository
                pipe = self._client.pipeline()
                for repo_name in repo_names:
                    metadata_key = f"repo:{repo_name}:metadata"
                    pipe.get(metadata_key)
                
                metadata_results = pipe.execute()
                
                repositories = []
                for i, repo_name in enumerate(repo_names):
                    metadata_raw = metadata_results[i]
                    if metadata_raw:
                        # Parse simple metadata string format
                        metadata = {}
                        if isinstance(metadata_raw, bytes):
                            metadata_raw = metadata_raw.decode('utf-8')
                        
                        # Parse "key:value,key:value" format
                        for pair in metadata_raw.split(','):
                            if ':' in pair:
                                key, value = pair.split(':', 1)
                                metadata[key.strip()] = value.strip()
                        
                        repositories.append({
                            'name': repo_name,
                            'metadata': metadata,
                            'stored_at': metadata.get('stored_at', 'unknown'),
                            'data_types': metadata.get('data_types', '').split(',') if metadata.get('data_types') else []
                        })
                
                return repositories
            
            return self._execute_with_retry(_list_repos)
            
        except Exception as e:
            logger.error(f"Failed to list cached repositories: {e}")
            return []
    
    def smart_invalidate(self, repo_name: str) -> bool:
        """
        Intelligently invalidate repository cache including chunked data.
        
        Args:
            repo_name: Repository name to invalidate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.health_check():
                raise ConnectionError("Redis health check failed")
            
            def _get_all_keys_to_delete():
                """Get all keys related to the repository including chunks"""
                keys_to_delete = [
                    f"repo:{repo_name}:content",
                    f"repo:{repo_name}:tree", 
                    f"repo:{repo_name}:summary",
                    f"repo:{repo_name}:metadata"
                ]
                
                # Add chunk-related keys
                for data_type in ['content', 'tree', 'summary']:
                    # Add chunk count key
                    keys_to_delete.append(f"repo:{repo_name}:{data_type}:chunk_count")
                    
                    # Add potential chunk keys (up to 100 chunks)
                    for i in range(100):
                        keys_to_delete.append(f"repo:{repo_name}:{data_type}:chunk:{i}")
                
                return keys_to_delete
            
            def _invalidate():
                keys_to_delete = _get_all_keys_to_delete()
                
                # Delete in batches to avoid timeout
                batch_size = 50
                total_deleted = 0
                
                for i in range(0, len(keys_to_delete), batch_size):
                    batch = keys_to_delete[i:i + batch_size]
                    try:
                        deleted = self._client.delete(*batch)
                        total_deleted += deleted
                    except Exception as e:
                        logger.warning(f"Failed to delete batch {i//batch_size + 1}: {e}")
                
                return total_deleted
            
            deleted_count = self._execute_with_retry(_invalidate)
            
            logger.info(f"Invalidated {deleted_count} keys for repository {repo_name} (including chunks)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {repo_name}: {e}")
            return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get Redis connection information for monitoring.
        
        Returns:
            Dictionary with connection details
        """
        try:
            info = self._execute_with_retry(self._client.info)
            
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'Unknown'),
                'redis_version': info.get('redis_version', 'Unknown'),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0),
                'pool_created_connections': self._pool.created_connections if self._pool else 0,
                'pool_available_connections': len(self._pool._available_connections) if self._pool else 0,
            }
            
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            return {}
    
    def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        try:
            if self._client:
                self._client.close()
            if self._pool:
                self._pool.disconnect()
            logger.info("Redis connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")