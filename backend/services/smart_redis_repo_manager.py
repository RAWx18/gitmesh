"""
Smart Redis Repository Manager

Optimized Redis operations with connection pooling, batch processing,
intelligent data parsing for gitingest format, and chunked data handling
for large repositories.

This implementation provides enhanced performance for the Cosmos optimization
by leveraging Redis cache efficiently with proper error handling and retry logic.
"""

import os
import re
import time
import hashlib
import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from urllib.parse import urlparse
from pathlib import Path, PurePosixPath
import json

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
    raise ImportError("Redis package is required. Install with: pip install redis")

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class FileLocation:
    """File location information for indexing."""
    start_offset: int
    end_offset: int
    size: int
    checksum: str


@dataclass
class RepositoryContext:
    """Comprehensive repository context from Redis cache data."""
    repo_url: str
    repo_name: str
    summary: str
    content: str
    tree_structure: str
    metadata: Dict[str, Any]
    file_index: Dict[str, FileLocation]
    total_files: int
    total_size: int


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
        import random
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add jitter: ±25% of the calculated delay
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


class SmartRedisRepoManager:
    """
    Smart Redis Repository Manager with optimized operations.
    
    Features:
    - Connection pooling for efficient Redis operations
    - Batch operations for multiple file access
    - Retry logic with exponential backoff (no infinite loops)
    - Efficient parsing of gitingest data format
    - Intelligent data chunking and reconstruction
    - Data integrity validation and checksum verification
    """
    
    def __init__(
        self, 
        redis_url: Optional[str] = None,
        max_connections: int = 20,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize Smart Redis Repository Manager.
        
        Args:
            redis_url: Redis connection URL (defaults to environment variable)
            max_connections: Maximum connections in pool
            retry_config: Retry configuration for operations
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL')
        if not self.redis_url:
            raise ValueError("Redis URL must be provided or set in REDIS_URL environment variable")
        
        self.max_connections = max_connections
        self.retry_config = retry_config or RetryConfig()
        
        # Initialize connection pool
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._initialize_connection()
        
        # Cache for parsed data
        self._repo_contexts: Dict[str, RepositoryContext] = {}
        self._file_content_cache: Dict[str, str] = {}
        
        # Initialize chunked data manager
        self.chunked_data_manager = ChunkedDataManager()
        
        # Initialize repository context builder
        self.context_builder = RepositoryContextBuilder(self)
        
        logger.info(f"SmartRedisRepoManager initialized with {max_connections} max connections")
    
    def _initialize_connection(self) -> None:
        """Initialize Redis connection with optimized pooling."""
        try:
            # Parse Redis URL to determine SSL settings
            parsed_url = urlparse(self.redis_url)
            ssl_enabled = parsed_url.scheme == 'rediss'
            
            # Connection pool configuration
            pool_kwargs = {
                'max_connections': self.max_connections,
                'socket_timeout': 5.0,
                'socket_connect_timeout': 5.0,
                'socket_keepalive': True,
                'retry_on_timeout': True,
                'health_check_interval': 30,
                'decode_responses': True,
                'encoding': 'utf-8',
            }
            
            # Add SSL configuration if needed
            if ssl_enabled:
                import ssl
                pool_kwargs.update({
                    'ssl_cert_reqs': ssl.CERT_NONE,  # For Redis Cloud compatibility
                    'ssl_check_hostname': False,
                })
            
            # Create connection pool
            self._pool = ConnectionPool.from_url(self.redis_url, **pool_kwargs)
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            self._client.ping()
            logger.info("Redis connection pool initialized successfully")
            
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
                # Non-retryable errors
                logger.error(f"Non-retryable Redis error: {e}")
                last_exception = e
                break
        
        # If we get here, all retries failed
        raise RedisError(f"Operation failed after {self.retry_config.max_retries} retries: {last_exception}")
    
    def get_repository_context(self, repo_url: str) -> Optional[RepositoryContext]:
        """
        Get comprehensive repository context from Redis cache.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            RepositoryContext object or None if not found
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            
            # Check cache first
            if repo_name in self._repo_contexts:
                return self._repo_contexts[repo_name]
            
            # Get repository data from Redis
            repo_data = self._get_repository_data_batch(repo_name)
            if not repo_data:
                logger.warning(f"No repository data found for {repo_name}")
                return None
            
            # Build repository context using the context builder
            context = self.context_builder.build_context(repo_url, repo_name, repo_data)
            if context:
                # Cache the context
                self._repo_contexts[repo_name] = context
                logger.info(f"Built repository context for {repo_name}: {context.total_files} files")
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting repository context for {repo_url}: {e}")
            return None
    
    def get_file_content(self, repo_url: str, file_path: str) -> Optional[str]:
        """
        Get file content from repository context with caching.
        
        Args:
            repo_url: Repository URL
            file_path: Path to the file
            
        Returns:
            File content or None if not found
        """
        try:
            cache_key = f"{repo_url}:{file_path}"
            
            # Check cache first
            if cache_key in self._file_content_cache:
                return self._file_content_cache[cache_key]
            
            # Get repository context
            context = self.get_repository_context(repo_url)
            if not context:
                return None
            
            # Extract file content using index
            content = self._extract_file_content_indexed(context, file_path)
            
            if content is not None:
                # Cache the result
                self._file_content_cache[cache_key] = content
                logger.debug(f"Retrieved file content: {file_path}")
            
            return content
            
        except Exception as e:
            logger.error(f"Error getting file content for {file_path}: {e}")
            return None
    
    def get_file_metadata(self, repo_url: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata from repository context.
        
        Args:
            repo_url: Repository URL
            file_path: Path to the file
            
        Returns:
            File metadata dictionary or None if not found
        """
        try:
            context = self.get_repository_context(repo_url)
            if not context or file_path not in context.file_index:
                return None
            
            file_location = context.file_index[file_path]
            content = self.get_file_content(repo_url, file_path)
            
            return {
                'path': file_path,
                'name': os.path.basename(file_path),
                'size': file_location.size,
                'checksum': file_location.checksum,
                'language': self._detect_language(file_path),
                'content_available': content is not None
            }
            
        except Exception as e:
            logger.error(f"Error getting file metadata for {file_path}: {e}")
            return None
    
    def get_directory_structure(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """
        Get directory structure from repository context.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Directory structure dictionary or None if not found
        """
        try:
            context = self.get_repository_context(repo_url)
            if not context:
                return None
            
            return {
                'tree_structure': context.tree_structure,
                'total_files': context.total_files,
                'total_size': context.total_size,
                'file_list': list(context.file_index.keys())
            }
            
        except Exception as e:
            logger.error(f"Error getting directory structure for {repo_url}: {e}")
            return None
    
    def batch_get_files(self, repo_url: str, file_paths: List[str]) -> Dict[str, Optional[str]]:
        """
        Get multiple file contents in a batch operation.
        
        Args:
            repo_url: Repository URL
            file_paths: List of file paths to retrieve
            
        Returns:
            Dictionary mapping file paths to their content (or None if not found)
        """
        try:
            results = {}
            context = self.get_repository_context(repo_url)
            
            if not context:
                return {path: None for path in file_paths}
            
            # Process files in batch
            for file_path in file_paths:
                cache_key = f"{repo_url}:{file_path}"
                
                # Check cache first
                if cache_key in self._file_content_cache:
                    results[file_path] = self._file_content_cache[cache_key]
                else:
                    # Extract content
                    content = self._extract_file_content_indexed(context, file_path)
                    results[file_path] = content
                    
                    # Cache if found
                    if content is not None:
                        self._file_content_cache[cache_key] = content
            
            logger.info(f"Batch retrieved {len([r for r in results.values() if r is not None])}/{len(file_paths)} files")
            return results
            
        except Exception as e:
            logger.error(f"Error in batch file retrieval: {e}")
            return {path: None for path in file_paths}
    
    def _get_repository_data_batch(self, repo_name: str) -> Optional[Dict[str, str]]:
        """
        Get repository data using batch operations with chunked data reconstruction.
        
        Args:
            repo_name: Repository name
            
        Returns:
            Dictionary with repository data or None if not found
        """
        try:
            def _get_metadata():
                """Get metadata to determine chunked types."""
                metadata_key = f"repo:{repo_name}:metadata"
                return self._client.get(metadata_key)
            
            # Get metadata first
            metadata_raw = self._execute_with_retry(_get_metadata)
            if not metadata_raw:
                logger.warning(f"No metadata found for repository {repo_name}")
                return None
            
            # Parse metadata
            metadata = {}
            chunked_types = []
            
            if isinstance(metadata_raw, bytes):
                metadata_raw = metadata_raw.decode('utf-8')
            
            for pair in metadata_raw.split(','):
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    metadata[key.strip()] = value.strip()
            
            if 'chunked_types' in metadata:
                chunked_types = [t.strip() for t in metadata['chunked_types'].split(',') if t.strip()]
            
            # Get regular data using pipeline
            def _get_regular_data():
                pipe = self._client.pipeline()
                regular_types = [t for t in ['content', 'tree', 'summary'] if t not in chunked_types]
                
                for data_type in regular_types:
                    key = f"repo:{repo_name}:{data_type}"
                    pipe.get(key)
                
                return pipe.execute(), regular_types
            
            regular_results, regular_types = self._execute_with_retry(_get_regular_data)
            
            # Build result data
            result_data = {}
            for i, data_type in enumerate(regular_types):
                if regular_results[i] is not None:
                    content = regular_results[i]
                    result_data[data_type] = content.decode('utf-8') if isinstance(content, bytes) else content
            
            # Get chunked data
            for data_type in chunked_types:
                if data_type in ['content', 'tree', 'summary']:
                    chunked_content = self._get_chunked_data(repo_name, data_type)
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
            logger.info(f"Retrieved repository data for {repo_name} (chunked: {chunked_types})")
            return result_data
            
        except Exception as e:
            logger.error(f"Error getting repository data for {repo_name}: {e}")
            return None
    
    def _get_chunked_data(self, repo_name: str, data_type: str) -> Optional[str]:
        """
        Reconstruct chunked data using ChunkedDataManager.
        
        Args:
            repo_name: Repository name
            data_type: Data type (content, tree, summary)
            
        Returns:
            Reconstructed data or None if failed
        """
        try:
            return self._execute_with_retry(
                self.chunked_data_manager.reconstruct_chunked_data,
                self._client, repo_name, data_type
            )
            
        except Exception as e:
            logger.error(f"Failed to reconstruct chunked data for {data_type}: {e}")
            return None
    
    def rebuild_repository_context(self, repo_url: str, force: bool = False) -> Optional[RepositoryContext]:
        """
        Rebuild repository context, optionally forcing a complete rebuild.
        
        Args:
            repo_url: Repository URL
            force: Force complete rebuild including cache clearing
            
        Returns:
            Rebuilt RepositoryContext or None if failed
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            
            if force:
                # Clear all caches
                self.clear_cache(repo_url)
                self.context_builder._clear_repository_cache(repo_name)
            
            # Get fresh repository data
            repo_data = self._get_repository_data_batch(repo_name)
            if not repo_data:
                logger.error(f"No repository data available for rebuild: {repo_name}")
                return None
            
            # Build context with force rebuild flag
            context = self.context_builder.build_context(repo_url, repo_name, repo_data, force_rebuild=True)
            
            if context:
                # Update cache
                self._repo_contexts[repo_name] = context
                logger.info(f"Successfully rebuilt context for {repo_name}")
            
            return context
            
        except Exception as e:
            logger.error(f"Error rebuilding repository context for {repo_url}: {e}")
            return None    

    def validate_repository_context(self, repo_url: str) -> Dict[str, Any]:
        """
        Validate repository context and return detailed validation results.
        
        Args:
            repo_url: Repository URL to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            context = self.get_repository_context(repo_url)
            if not context:
                return {
                    'valid': False,
                    'error': 'No context available',
                    'details': {}
                }
            
            is_valid = self.context_builder._validate_context(context)
            
            # Get detailed statistics
            stats = self.context_builder._calculate_repository_stats(
                context.file_index, 
                context.content, 
                context.tree_structure
            )
            
            return {
                'valid': is_valid,
                'context_stats': {
                    'total_files': context.total_files,
                    'total_size': context.total_size,
                    'indexed_files': len(context.file_index),
                    'content_size': len(context.content),
                    'tree_size': len(context.tree_structure),
                    'summary_size': len(context.summary)
                },
                'detailed_stats': stats,
                'metadata': context.metadata
            }
            
        except Exception as e:
            logger.error(f"Error validating repository context for {repo_url}: {e}")
            return {
                'valid': False,
                'error': str(e),
                'details': {}
            }
    
    def _extract_file_content_indexed(
        self, 
        context: RepositoryContext, 
        file_path: str
    ) -> Optional[str]:
        """
        Extract file content using pre-built index for fast access.
        
        Args:
            context: Repository context with file index
            file_path: Path to the file
            
        Returns:
            File content or None if not found
        """
        try:
            # Normalize file path
            normalized_path = self._normalize_path(file_path)
            
            # Check direct match first
            if normalized_path in context.file_index:
                return self._extract_content_by_location(
                    context.content, 
                    context.file_index[normalized_path]
                )
            
            # Try fuzzy matching for different path formats
            for indexed_path in context.file_index.keys():
                if (indexed_path.endswith(normalized_path) or 
                    normalized_path.endswith(indexed_path) or
                    os.path.basename(indexed_path) == os.path.basename(normalized_path)):
                    
                    return self._extract_content_by_location(
                        context.content, 
                        context.file_index[indexed_path]
                    )
            
            logger.debug(f"File not found in index: {file_path}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting indexed file content for {file_path}: {e}")
            return None
    
    def _extract_content_by_location(
        self, 
        content_md: str, 
        location: FileLocation
    ) -> Optional[str]:
        """
        Extract file content using FileLocation information.
        
        Args:
            content_md: Full content.md string
            location: FileLocation with offset information
            
        Returns:
            File content or None if extraction failed
        """
        try:
            lines = content_md.split('\n')
            
            if location.start_offset >= len(lines) or location.end_offset > len(lines):
                logger.error(f"Invalid file location offsets: {location.start_offset}-{location.end_offset}")
                return None
            
            # Extract content lines
            content_lines = []
            in_code_block = False
            
            for i in range(location.start_offset, location.end_offset):
                if i >= len(lines):
                    break
                
                line = lines[i]
                
                # Handle code blocks
                if line.strip().startswith('```'):
                    if not in_code_block:
                        in_code_block = True
                        continue
                    else:
                        in_code_block = False
                        break
                
                # Collect content
                if in_code_block:
                    content_lines.append(line)
                elif line.strip():
                    content_lines.append(line)
            
            extracted_content = '\n'.join(content_lines)
            
            # Validate checksum
            calculated_checksum = hashlib.md5(extracted_content.encode('utf-8')).hexdigest()
            if calculated_checksum != location.checksum:
                logger.warning(f"Checksum mismatch for file content (expected: {location.checksum}, got: {calculated_checksum})")
            
            return extracted_content
            
        except Exception as e:
            logger.error(f"Error extracting content by location: {e}")
            return None    

    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repository name from GitHub URL."""
        try:
            # Handle SSH URLs like git@github.com:owner/repo.git
            if repo_url.startswith('git@'):
                if ':' in repo_url:
                    path_part = repo_url.split(':', 1)[1]
                    path_parts = [part for part in path_part.strip('/').split('/') if part]
                else:
                    raise ValueError("Invalid SSH URL format")
            else:
                # Handle HTTPS URLs
                path = urlparse(repo_url).path
                path_parts = [part for part in path.strip('/').split('/') if part]
            
            if len(path_parts) < 2:
                raise ValueError("URL must contain owner and repository name")
            
            # Create full repo identifier with owner for uniqueness
            repo_name = path_parts[1].replace('.git', '')
            full_repo_name = f"{path_parts[0]}/{repo_name}"
            return full_repo_name
            
        except Exception as e:
            raise ValueError(f"Could not determine repository name from URL '{repo_url}': {e}")
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalize file path for consistent handling.
        
        Args:
            path: File path to normalize
            
        Returns:
            Normalized path
        """
        try:
            if not path:
                return ""
            
            # Convert backslashes to forward slashes
            normalized = path.replace('\\', '/')
            
            # Convert to PurePosixPath for consistent handling
            normalized = str(PurePosixPath(normalized))
            
            # Remove leading ./ if present
            if normalized.startswith('./'):
                normalized = normalized[2:]
            
            # Handle case where path becomes just "." after normalization
            if normalized == ".":
                return ""
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing path {path}: {e}")
            return path
    
    def _detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language name
        """
        extension_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.jsx': 'javascript', '.tsx': 'typescript', '.java': 'java',
            '.cpp': 'cpp', '.c': 'c', '.h': 'c', '.hpp': 'cpp',
            '.cs': 'csharp', '.php': 'php', '.rb': 'ruby', '.go': 'go',
            '.rs': 'rust', '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
            '.sh': 'bash', '.bash': 'bash', '.zsh': 'zsh', '.fish': 'fish',
            '.ps1': 'powershell', '.html': 'html', '.css': 'css',
            '.scss': 'scss', '.sass': 'sass', '.less': 'less',
            '.xml': 'xml', '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
            '.toml': 'toml', '.ini': 'ini', '.cfg': 'ini', '.conf': 'conf',
            '.md': 'markdown', '.rst': 'rst', '.txt': 'text', '.sql': 'sql',
            '.r': 'r', '.R': 'r', '.m': 'matlab', '.pl': 'perl',
            '.lua': 'lua', '.vim': 'vim', '.dockerfile': 'dockerfile',
            '.gitignore': 'gitignore', '.env': 'env'
        }
        
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        
        # Check for special filenames
        filename = os.path.basename(file_path.lower())
        if filename in ['dockerfile', 'makefile', 'rakefile', 'gemfile']:
            return filename
        
        return extension_map.get(ext, 'text')
    
    def clear_cache(self, repo_url: Optional[str] = None) -> None:
        """
        Clear cached data.
        
        Args:
            repo_url: Specific repository URL to clear, or None to clear all
        """
        try:
            if repo_url:
                repo_name = self._extract_repo_name(repo_url)
                if repo_name in self._repo_contexts:
                    del self._repo_contexts[repo_name]
                
                # Clear file content cache for this repo
                keys_to_remove = [key for key in self._file_content_cache.keys() if key.startswith(f"{repo_url}:")]
                for key in keys_to_remove:
                    del self._file_content_cache[key]
                
                logger.info(f"Cleared cache for repository: {repo_name}")
            else:
                self._repo_contexts.clear()
                self._file_content_cache.clear()
                logger.info("Cleared all cached data")
                
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Redis connection and cache status.
        
        Returns:
            Dictionary with health check results
        """
        try:
            # Test Redis connection
            start_time = time.time()
            self._execute_with_retry(self._client.ping)
            ping_time = time.time() - start_time
            
            # Get connection info
            info = self._execute_with_retry(self._client.info)
            
            # Get cache statistics
            cache_stats = {
                'cached_repositories': len(self._repo_contexts),
                'cached_files': len(self._file_content_cache),
                'memory_usage_mb': sum(len(str(v)) for v in self._file_content_cache.values()) / (1024 * 1024)
            }
            
            return {
                'healthy': True,
                'ping_time_ms': ping_time * 1000,
                'redis_version': info.get('redis_version', 'Unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'Unknown'),
                'cache_stats': cache_stats,
                'pool_connections': {
                    'created': self._pool.created_connections if self._pool else 0,
                    'available': len(self._pool._available_connections) if self._pool else 0,
                    'max': self.max_connections
                }
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'cache_stats': {
                    'cached_repositories': len(self._repo_contexts),
                    'cached_files': len(self._file_content_cache)
                }
            }
    
    def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        try:
            if self._client:
                self._client.close()
            if self._pool:
                self._pool.disconnect()
            
            # Clear caches
            self._repo_contexts.clear()
            self._file_content_cache.clear()
            
            logger.info("SmartRedisRepoManager closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing SmartRedisRepoManager: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

class ChunkedDataManager:
    """
    Manages intelligent data chunking and reconstruction for large repository content.
    
    Features:
    - Chunked storage for large repository content
    - Efficient reconstruction of chunked data
    - Data integrity validation and checksum verification
    - Memory usage optimization during data processing
    """
    
    def __init__(self, chunk_size: int = 1024 * 1024):  # 1MB default chunk size
        """
        Initialize ChunkedDataManager.
        
        Args:
            chunk_size: Size of each chunk in bytes
        """
        self.chunk_size = chunk_size
        self.logger = logging.getLogger(f"{__name__}.ChunkedDataManager")
    
    def should_chunk_data(self, data: str) -> bool:
        """
        Determine if data should be chunked based on size.
        
        Args:
            data: Data to check
            
        Returns:
            True if data should be chunked
        """
        return len(data.encode('utf-8')) > self.chunk_size
    
    def chunk_data(self, data: str, data_type: str) -> Tuple[List[bytes], Dict[str, Any]]:
        """
        Split large data into chunks with integrity validation.
        
        Args:
            data: Data to chunk
            data_type: Type of data (content, tree, summary)
            
        Returns:
            Tuple of (chunks list, metadata dict)
        """
        try:
            data_bytes = data.encode('utf-8')
            chunks = []
            
            # Split into chunks
            for i in range(0, len(data_bytes), self.chunk_size):
                chunk = data_bytes[i:i + self.chunk_size]
                chunks.append(chunk)
            
            # Calculate overall checksum for integrity
            overall_checksum = hashlib.sha256(data_bytes).hexdigest()
            
            # Create metadata
            metadata = {
                'total_size': len(data_bytes),
                'chunk_count': len(chunks),
                'chunk_size': self.chunk_size,
                'checksum': overall_checksum,
                'data_type': data_type,
                'chunked_at': time.time()
            }
            
            self.logger.info(f"Chunked {data_type}: {len(data_bytes)} bytes -> {len(chunks)} chunks")
            return chunks, metadata
            
        except Exception as e:
            self.logger.error(f"Error chunking data for {data_type}: {e}")
            raise
    
    def store_chunked_data(
        self, 
        redis_client: redis.Redis, 
        repo_name: str, 
        data_type: str, 
        chunks: List[bytes], 
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Store chunked data in Redis with metadata.
        
        Args:
            redis_client: Redis client instance
            repo_name: Repository name
            data_type: Data type (content, tree, summary)
            chunks: List of data chunks
            metadata: Chunk metadata
            
        Returns:
            True if successful
        """
        try:
            pipe = redis_client.pipeline()
            
            # Store chunk count and metadata
            chunk_count_key = f"repo:{repo_name}:{data_type}:chunk_count"
            metadata_key = f"repo:{repo_name}:{data_type}:chunk_metadata"
            
            pipe.set(chunk_count_key, len(chunks))
            pipe.set(metadata_key, json.dumps(metadata))
            
            # Store each chunk with individual checksum
            for i, chunk in enumerate(chunks):
                chunk_key = f"repo:{repo_name}:{data_type}:chunk:{i}"
                chunk_checksum_key = f"repo:{repo_name}:{data_type}:chunk:{i}:checksum"
                
                chunk_checksum = hashlib.md5(chunk).hexdigest()
                pipe.set(chunk_key, chunk)
                pipe.set(chunk_checksum_key, chunk_checksum)
            
            # Execute all operations
            results = pipe.execute()
            
            # Verify all operations succeeded
            if all(results):
                self.logger.info(f"Successfully stored {len(chunks)} chunks for {data_type}")
                return True
            else:
                self.logger.error(f"Some chunk storage operations failed for {data_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error storing chunked data for {data_type}: {e}")
            return False
    
    def reconstruct_chunked_data(
        self, 
        redis_client: redis.Redis, 
        repo_name: str, 
        data_type: str
    ) -> Optional[str]:
        """
        Reconstruct chunked data with integrity validation.
        
        Args:
            redis_client: Redis client instance
            repo_name: Repository name
            data_type: Data type (content, tree, summary)
            
        Returns:
            Reconstructed data or None if failed
        """
        try:
            # Get chunk metadata
            metadata_key = f"repo:{repo_name}:{data_type}:chunk_metadata"
            metadata_raw = redis_client.get(metadata_key)
            
            if not metadata_raw:
                self.logger.warning(f"No chunk metadata found for {data_type}")
                return None
            
            metadata = json.loads(metadata_raw.decode('utf-8') if isinstance(metadata_raw, bytes) else metadata_raw)
            chunk_count = metadata['chunk_count']
            expected_checksum = metadata['checksum']
            
            # Get all chunks and their checksums using pipeline
            pipe = redis_client.pipeline()
            
            for i in range(chunk_count):
                chunk_key = f"repo:{repo_name}:{data_type}:chunk:{i}"
                chunk_checksum_key = f"repo:{repo_name}:{data_type}:chunk:{i}:checksum"
                pipe.get(chunk_key)
                pipe.get(chunk_checksum_key)
            
            results = pipe.execute()
            
            # Validate and reconstruct
            chunks = []
            for i in range(chunk_count):
                chunk_data = results[i * 2]
                expected_chunk_checksum = results[i * 2 + 1]
                
                if chunk_data is None:
                    self.logger.error(f"Missing chunk {i} for {data_type}")
                    return None
                
                # Validate chunk integrity
                if expected_chunk_checksum:
                    actual_chunk_checksum = hashlib.md5(chunk_data).hexdigest()
                    expected_chunk_checksum = expected_chunk_checksum.decode('utf-8') if isinstance(expected_chunk_checksum, bytes) else expected_chunk_checksum
                    
                    if actual_chunk_checksum != expected_chunk_checksum:
                        self.logger.error(f"Chunk {i} integrity check failed for {data_type}")
                        return None
                
                chunks.append(chunk_data)
            
            # Reconstruct data
            reconstructed_bytes = b''.join(chunks)
            
            # Validate overall integrity
            actual_checksum = hashlib.sha256(reconstructed_bytes).hexdigest()
            if actual_checksum != expected_checksum:
                self.logger.error(f"Overall data integrity check failed for {data_type}")
                self.logger.error(f"Expected: {expected_checksum}, Got: {actual_checksum}")
                return None
            
            reconstructed_data = reconstructed_bytes.decode('utf-8')
            
            self.logger.info(f"Successfully reconstructed {data_type}: {len(reconstructed_data)} chars from {chunk_count} chunks")
            return reconstructed_data
            
        except Exception as e:
            self.logger.error(f"Error reconstructing chunked data for {data_type}: {e}")
            return None
    
    def cleanup_chunked_data(
        self, 
        redis_client: redis.Redis, 
        repo_name: str, 
        data_type: str
    ) -> bool:
        """
        Clean up all chunks and metadata for a data type.
        
        Args:
            redis_client: Redis client instance
            repo_name: Repository name
            data_type: Data type to clean up
            
        Returns:
            True if successful
        """
        try:
            # Get chunk count first
            chunk_count_key = f"repo:{repo_name}:{data_type}:chunk_count"
            chunk_count = redis_client.get(chunk_count_key)
            
            if chunk_count:
                chunk_count = int(chunk_count)
                
                # Collect all keys to delete
                keys_to_delete = [
                    chunk_count_key,
                    f"repo:{repo_name}:{data_type}:chunk_metadata"
                ]
                
                for i in range(chunk_count):
                    keys_to_delete.extend([
                        f"repo:{repo_name}:{data_type}:chunk:{i}",
                        f"repo:{repo_name}:{data_type}:chunk:{i}:checksum"
                    ])
                
                # Delete in batches
                batch_size = 50
                total_deleted = 0
                
                for i in range(0, len(keys_to_delete), batch_size):
                    batch = keys_to_delete[i:i + batch_size]
                    deleted = redis_client.delete(*batch)
                    total_deleted += deleted
                
                self.logger.info(f"Cleaned up {total_deleted} keys for chunked {data_type}")
                return True
            else:
                self.logger.info(f"No chunked data found to clean up for {data_type}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error cleaning up chunked data for {data_type}: {e}")
            return False
    
    def get_chunk_info(
        self, 
        redis_client: redis.Redis, 
        repo_name: str, 
        data_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about chunked data.
        
        Args:
            redis_client: Redis client instance
            repo_name: Repository name
            data_type: Data type
            
        Returns:
            Dictionary with chunk information or None
        """
        try:
            metadata_key = f"repo:{repo_name}:{data_type}:chunk_metadata"
            metadata_raw = redis_client.get(metadata_key)
            
            if not metadata_raw:
                return None
            
            metadata = json.loads(metadata_raw.decode('utf-8') if isinstance(metadata_raw, bytes) else metadata_raw)
            
            # Add current status
            chunk_count_key = f"repo:{repo_name}:{data_type}:chunk_count"
            current_chunk_count = redis_client.get(chunk_count_key)
            
            metadata['current_chunk_count'] = int(current_chunk_count) if current_chunk_count else 0
            metadata['is_complete'] = metadata['current_chunk_count'] == metadata['chunk_count']
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error getting chunk info for {data_type}: {e}")
            return None
    
    def store_repository_data(
        self, 
        repo_url: str, 
        data: Dict[str, str]
    ) -> bool:
        """
        Store repository data with intelligent chunking for large content.
        
        Args:
            repo_url: Repository URL
            data: Dictionary with keys 'content', 'tree', 'summary', 'metadata'
            
        Returns:
            True if successful
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            
            # Determine which data types need chunking
            chunked_types = []
            regular_data = {}
            
            for data_type, content in data.items():
                if data_type in ['content', 'tree', 'summary'] and isinstance(content, str):
                    if self.chunked_data_manager.should_chunk_data(content):
                        chunked_types.append(data_type)
                        logger.info(f"Will chunk {data_type}: {len(content.encode('utf-8'))} bytes")
                    else:
                        regular_data[data_type] = content
                else:
                    regular_data[data_type] = content
            
            # Clean up existing data first
            self._cleanup_existing_repository_data(repo_name)
            
            # Store chunked data
            for data_type in chunked_types:
                content = data[data_type]
                chunks, metadata = self.chunked_data_manager.chunk_data(content, data_type)
                
                success = self._execute_with_retry(
                    self.chunked_data_manager.store_chunked_data,
                    self._client, repo_name, data_type, chunks, metadata
                )
                
                if not success:
                    logger.error(f"Failed to store chunked data for {data_type}")
                    return False
            
            # Store regular data using pipeline
            if regular_data or chunked_types:
                success = self._store_regular_repository_data(repo_name, regular_data, chunked_types)
                if not success:
                    return False
            
            # Clear cache to force reload
            self.clear_cache(repo_url)
            
            logger.info(f"Successfully stored repository data for {repo_name} (chunked: {chunked_types})")
            return True
            
        except Exception as e:
            logger.error(f"Error storing repository data for {repo_url}: {e}")
            return False
    
    def _cleanup_existing_repository_data(self, repo_name: str) -> None:
        """
        Clean up existing repository data including chunks.
        
        Args:
            repo_name: Repository name
        """
        try:
            # Clean up chunked data for each type
            for data_type in ['content', 'tree', 'summary']:
                self.chunked_data_manager.cleanup_chunked_data(self._client, repo_name, data_type)
            
            # Clean up regular keys
            regular_keys = [
                f"repo:{repo_name}:content",
                f"repo:{repo_name}:tree",
                f"repo:{repo_name}:summary",
                f"repo:{repo_name}:metadata"
            ]
            
            def _delete_regular_keys():
                return self._client.delete(*regular_keys)
            
            deleted = self._execute_with_retry(_delete_regular_keys)
            logger.debug(f"Cleaned up {deleted} regular keys for {repo_name}")
            
        except Exception as e:
            logger.error(f"Error cleaning up existing data for {repo_name}: {e}")
    
    def _store_regular_repository_data(
        self, 
        repo_name: str, 
        regular_data: Dict[str, str], 
        chunked_types: List[str]
    ) -> bool:
        """
        Store regular (non-chunked) repository data.
        
        Args:
            repo_name: Repository name
            regular_data: Regular data to store
            chunked_types: List of data types that were chunked
            
        Returns:
            True if successful
        """
        try:
            def _store_pipeline():
                pipe = self._client.pipeline()
                
                # Store regular data
                for data_type, content in regular_data.items():
                    if data_type in ['content', 'tree', 'summary']:
                        key = f"repo:{repo_name}:{data_type}"
                        pipe.set(key, content)
                
                # Store metadata with chunking information
                metadata_key = f"repo:{repo_name}:metadata"
                metadata_value = (
                    f"stored_at:{time.time()},"
                    f"repo_name:{repo_name},"
                    f"data_types:{','.join(list(regular_data.keys()) + chunked_types)},"
                    f"chunked_types:{','.join(chunked_types)}"
                )
                pipe.set(metadata_key, metadata_value)
                
                return pipe.execute()
            
            results = self._execute_with_retry(_store_pipeline)
            
            if all(results):
                logger.info(f"Successfully stored regular data for {repo_name}")
                return True
            else:
                logger.error(f"Some regular data storage operations failed for {repo_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error storing regular repository data for {repo_name}: {e}")
            return False
    
    def get_repository_storage_info(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """
        Get information about how repository data is stored (chunked vs regular).
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Dictionary with storage information
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            
            # Get metadata
            metadata_key = f"repo:{repo_name}:metadata"
            metadata_raw = self._execute_with_retry(self._client.get, metadata_key)
            
            if not metadata_raw:
                return None
            
            # Parse metadata
            metadata = {}
            if isinstance(metadata_raw, bytes):
                metadata_raw = metadata_raw.decode('utf-8')
            
            for pair in metadata_raw.split(','):
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    metadata[key.strip()] = value.strip()
            
            chunked_types = []
            if 'chunked_types' in metadata:
                chunked_types = [t.strip() for t in metadata['chunked_types'].split(',') if t.strip()]
            
            # Get chunk information for each chunked type
            chunk_info = {}
            for data_type in chunked_types:
                info = self.chunked_data_manager.get_chunk_info(self._client, repo_name, data_type)
                if info:
                    chunk_info[data_type] = info
            
            return {
                'repo_name': repo_name,
                'stored_at': metadata.get('stored_at'),
                'data_types': metadata.get('data_types', '').split(','),
                'chunked_types': chunked_types,
                'chunk_info': chunk_info,
                'total_chunks': sum(info.get('chunk_count', 0) for info in chunk_info.values()),
                'total_chunked_size': sum(info.get('total_size', 0) for info in chunk_info.values())
            }
            
        except Exception as e:
            logger.error(f"Error getting repository storage info for {repo_url}: {e}")
            return None
class RepositoryContextBuilder:
    """
    Builds comprehensive repository context from Redis cache data.
    
    Features:
    - Combines summary, tree, content, and metadata efficiently
    - Handles incomplete cache data with automatic cleanup and re-fetch
    - Context validation and error handling
    - Memory-efficient processing
    """
    
    def __init__(self, redis_manager: 'SmartRedisRepoManager'):
        """
        Initialize RepositoryContextBuilder.
        
        Args:
            redis_manager: SmartRedisRepoManager instance
        """
        self.redis_manager = redis_manager
        self.logger = logging.getLogger(f"{__name__}.RepositoryContextBuilder")
    
    def build_context(
        self, 
        repo_url: str, 
        repo_name: str, 
        repo_data: Dict[str, str],
        force_rebuild: bool = False
    ) -> Optional[RepositoryContext]:
        """
        Build comprehensive repository context with validation.
        
        Args:
            repo_url: Repository URL
            repo_name: Repository name
            repo_data: Raw repository data from Redis
            force_rebuild: Force rebuild even if cached
            
        Returns:
            RepositoryContext object or None if failed
        """
        try:
            # Check if we already have a valid context cached
            if not force_rebuild and repo_name in self.redis_manager._repo_contexts:
                cached_context = self.redis_manager._repo_contexts[repo_name]
                if self._validate_context(cached_context):
                    self.logger.debug(f"Using cached context for {repo_name}")
                    return cached_context
                else:
                    self.logger.warning(f"Cached context invalid for {repo_name}, rebuilding")
            
            # Validate input data completeness
            validation_result = self._validate_repository_data(repo_data)
            if not validation_result['is_complete']:
                self.logger.warning(f"Incomplete repository data for {repo_name}: {validation_result['missing_keys']}")
                
                # Attempt to handle incomplete data
                if validation_result['is_recoverable']:
                    self.logger.info(f"Attempting to recover incomplete data for {repo_name}")
                    recovered_data = self._handle_incomplete_data(repo_url, repo_name, repo_data, validation_result)
                    if recovered_data:
                        repo_data = recovered_data
                    else:
                        self.logger.error(f"Failed to recover incomplete data for {repo_name}")
                        return None
                else:
                    self.logger.error(f"Repository data is not recoverable for {repo_name}")
                    return None
            
            # Extract and validate components
            content = repo_data.get('content', '')
            tree_structure = repo_data.get('tree', '')
            summary = repo_data.get('summary', '')
            metadata = repo_data.get('metadata', {})
            
            if not content:
                self.logger.error(f"No content data found for {repo_name}")
                return None
            
            # Build file index with progress tracking
            self.logger.info(f"Building file index for {repo_name}...")
            file_index = self._build_comprehensive_file_index(content)
            
            if not file_index:
                self.logger.error(f"Failed to build file index for {repo_name}")
                return None
            
            # Calculate comprehensive statistics
            stats = self._calculate_repository_stats(file_index, content, tree_structure)
            
            # Create context with validation
            context = RepositoryContext(
                repo_url=repo_url,
                repo_name=repo_name,
                summary=summary,
                content=content,
                tree_structure=tree_structure,
                metadata=metadata if isinstance(metadata, dict) else self._parse_metadata_string(metadata),
                file_index=file_index,
                total_files=stats['total_files'],
                total_size=stats['total_size']
            )
            
            # Final validation
            if not self._validate_context(context):
                self.logger.error(f"Built context failed validation for {repo_name}")
                return None
            
            self.logger.info(
                f"Built repository context for {repo_name}: "
                f"{context.total_files} files, {context.total_size} bytes, "
                f"{len(context.file_index)} indexed files"
            )
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error building repository context for {repo_name}: {e}")
            return None
    
    def _validate_repository_data(self, repo_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate repository data completeness and quality.
        
        Args:
            repo_data: Repository data to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            required_keys = ['content', 'tree', 'summary']
            missing_keys = [key for key in required_keys if not repo_data.get(key)]
            
            # Check data quality
            quality_issues = []
            
            if repo_data.get('content'):
                content = repo_data['content']
                if len(content) < 100:  # Suspiciously small content
                    quality_issues.append('content_too_small')
                if 'FILE:' not in content and '##' not in content:  # No file markers
                    quality_issues.append('no_file_markers')
            
            if repo_data.get('tree'):
                tree = repo_data['tree']
                if len(tree) < 50:  # Suspiciously small tree
                    quality_issues.append('tree_too_small')
            
            # Determine if data is recoverable
            is_recoverable = (
                len(missing_keys) <= 1 and  # At most one missing key
                'content' not in missing_keys and  # Content must be present
                len(quality_issues) <= 2  # Limited quality issues
            )
            
            return {
                'is_complete': len(missing_keys) == 0 and len(quality_issues) == 0,
                'missing_keys': missing_keys,
                'quality_issues': quality_issues,
                'is_recoverable': is_recoverable,
                'data_sizes': {key: len(str(value)) for key, value in repo_data.items()}
            }
            
        except Exception as e:
            self.logger.error(f"Error validating repository data: {e}")
            return {
                'is_complete': False,
                'missing_keys': ['validation_error'],
                'quality_issues': ['validation_failed'],
                'is_recoverable': False,
                'data_sizes': {}
            }
    
    def _handle_incomplete_data(
        self, 
        repo_url: str, 
        repo_name: str, 
        repo_data: Dict[str, str], 
        validation_result: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Handle incomplete cache data by clearing and attempting re-fetch.
        
        Args:
            repo_url: Repository URL
            repo_name: Repository name
            repo_data: Current repository data
            validation_result: Validation results
            
        Returns:
            Recovered repository data or None if failed
        """
        try:
            self.logger.info(f"Handling incomplete data for {repo_name}")
            
            # Clear existing cache data
            self.logger.info(f"Clearing incomplete cache data for {repo_name}")
            self._clear_repository_cache(repo_name)
            
            # Clear local caches
            self.redis_manager.clear_cache(repo_url)
            
            # Check if we have a fetch mechanism available
            if hasattr(self.redis_manager, '_fetch_repository_data'):
                self.logger.info(f"Attempting to re-fetch repository data for {repo_name}")
                success = self.redis_manager._fetch_repository_data(repo_url)
                
                if success:
                    # Try to get the data again
                    new_repo_data = self.redis_manager._get_repository_data_batch(repo_name)
                    if new_repo_data:
                        new_validation = self._validate_repository_data(new_repo_data)
                        if new_validation['is_complete']:
                            self.logger.info(f"Successfully recovered data for {repo_name}")
                            return new_repo_data
                        else:
                            self.logger.warning(f"Re-fetched data still incomplete for {repo_name}")
                    else:
                        self.logger.error(f"No data available after re-fetch for {repo_name}")
                else:
                    self.logger.error(f"Failed to re-fetch repository data for {repo_name}")
            else:
                self.logger.warning(f"No fetch mechanism available for {repo_name}")
            
            # If re-fetch failed, try to work with partial data if possible
            if validation_result['is_recoverable'] and repo_data.get('content'):
                self.logger.info(f"Attempting to work with partial data for {repo_name}")
                
                # Fill in missing components with defaults
                recovered_data = repo_data.copy()
                
                if 'tree' not in recovered_data or not recovered_data['tree']:
                    recovered_data['tree'] = self._generate_tree_from_content(recovered_data['content'])
                
                if 'summary' not in recovered_data or not recovered_data['summary']:
                    recovered_data['summary'] = f"Repository: {repo_name} (partial data recovery)"
                
                return recovered_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error handling incomplete data for {repo_name}: {e}")
            return None
    
    def _clear_repository_cache(self, repo_name: str) -> None:
        """
        Clear all cache data for a repository.
        
        Args:
            repo_name: Repository name to clear
        """
        try:
            # Clear chunked data
            for data_type in ['content', 'tree', 'summary']:
                self.redis_manager.chunked_data_manager.cleanup_chunked_data(
                    self.redis_manager._client, repo_name, data_type
                )
            
            # Clear regular keys
            regular_keys = [
                f"repo:{repo_name}:content",
                f"repo:{repo_name}:tree",
                f"repo:{repo_name}:summary",
                f"repo:{repo_name}:metadata"
            ]
            
            def _delete_keys():
                return self.redis_manager._client.delete(*regular_keys)
            
            deleted = self.redis_manager._execute_with_retry(_delete_keys)
            self.logger.info(f"Cleared {deleted} cache keys for {repo_name}")
            
        except Exception as e:
            self.logger.error(f"Error clearing repository cache for {repo_name}: {e}")
    
    def _generate_tree_from_content(self, content: str) -> str:
        """
        Generate a basic tree structure from content data.
        
        Args:
            content: Repository content
            
        Returns:
            Generated tree structure
        """
        try:
            file_paths = []
            
            # Extract file paths from content
            file_header_patterns = [
                r'^FILE: (.+)$',
                r'^## (.+)$',
                r'^### (.+)$',
                r'^# (.+)$',
                r'^File: (.+)$'
            ]
            
            for line in content.split('\n'):
                line = line.strip()
                for pattern in file_header_patterns:
                    match = re.match(pattern, line)
                    if match:
                        file_path = match.group(1).strip()
                        if file_path and file_path not in file_paths:
                            file_paths.append(file_path)
                        break
            
            # Generate simple tree structure
            if file_paths:
                tree_lines = ["Repository structure:"]
                for file_path in sorted(file_paths):
                    tree_lines.append(f"├── {file_path}")
                
                return '\n'.join(tree_lines)
            else:
                return "No files found in repository content"
                
        except Exception as e:
            self.logger.error(f"Error generating tree from content: {e}")
            return "Error generating tree structure" 
   
    def _build_comprehensive_file_index(self, content_md: str) -> Dict[str, FileLocation]:
        """
        Build comprehensive file index with enhanced parsing and validation.
        
        Args:
            content_md: Content.md string from GitIngest
            
        Returns:
            Dictionary mapping file paths to FileLocation objects
        """
        try:
            file_index = {}
            lines = content_md.split('\n')
            
            # Enhanced GitIngest format patterns
            file_header_patterns = [
                (r'^FILE: (.+)$', 'gitingest'),  # GitIngest format
                (r'^## (.+)$', 'markdown_h2'),
                (r'^### (.+)$', 'markdown_h3'),
                (r'^# (.+)$', 'markdown_h1'),
                (r'^File: (.+)$', 'file_colon'),
                (r'^(.+):$', 'path_colon')
            ]
            
            i = 0
            processed_files = 0
            
            while i < len(lines):
                line = lines[i].strip()
                file_path = None
                format_type = None
                
                # Check for file header
                for pattern, fmt_type in file_header_patterns:
                    match = re.match(pattern, line)
                    if match:
                        file_path = match.group(1).strip()
                        format_type = fmt_type
                        break
                
                if file_path and file_path not in file_index:
                    # Find content boundaries
                    content_start = i + 1
                    content_lines = []
                    in_code_block = False
                    code_block_lang = None
                    
                    # Look for content
                    j = content_start
                    while j < len(lines):
                        content_line = lines[j]
                        
                        # Check for next file header
                        is_next_file = False
                        for pattern, _ in file_header_patterns:
                            if re.match(pattern, content_line.strip()) and not in_code_block:
                                is_next_file = True
                                break
                        
                        if is_next_file:
                            break
                        
                        # Handle code blocks
                        if content_line.strip().startswith('```'):
                            if not in_code_block:
                                in_code_block = True
                                code_block_lang = content_line.strip()[3:].strip()
                                j += 1
                                continue
                            else:
                                in_code_block = False
                                j += 1
                                break
                        
                        # Collect content
                        if in_code_block:
                            content_lines.append(content_line)
                        elif content_line.strip():
                            content_lines.append(content_line)
                        
                        j += 1
                    
                    # Create file location entry with validation
                    if content_lines:
                        file_content = '\n'.join(content_lines)
                        file_bytes = file_content.encode('utf-8')
                        
                        # Validate file content
                        if len(file_bytes) > 0:
                            file_index[file_path] = FileLocation(
                                start_offset=content_start,
                                end_offset=j,
                                size=len(file_bytes),
                                checksum=hashlib.md5(file_bytes).hexdigest()
                            )
                            processed_files += 1
                            
                            if processed_files % 100 == 0:
                                self.logger.debug(f"Processed {processed_files} files in index")
                    
                    i = j
                else:
                    i += 1
            
            self.logger.info(f"Built comprehensive file index with {len(file_index)} files")
            return file_index
            
        except Exception as e:
            self.logger.error(f"Error building comprehensive file index: {e}")
            return {}
    
    def _calculate_repository_stats(
        self, 
        file_index: Dict[str, FileLocation], 
        content: str, 
        tree_structure: str
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive repository statistics.
        
        Args:
            file_index: File index dictionary
            content: Repository content
            tree_structure: Tree structure
            
        Returns:
            Dictionary with repository statistics
        """
        try:
            total_files = len(file_index)
            total_size = sum(loc.size for loc in file_index.values())
            
            # Calculate file type distribution
            file_types = {}
            for file_path in file_index.keys():
                ext = os.path.splitext(file_path)[1].lower()
                if not ext:
                    ext = 'no_extension'
                file_types[ext] = file_types.get(ext, 0) + 1
            
            # Calculate size distribution
            size_ranges = {
                'small': 0,    # < 1KB
                'medium': 0,   # 1KB - 100KB
                'large': 0,    # 100KB - 1MB
                'xlarge': 0    # > 1MB
            }
            
            for loc in file_index.values():
                if loc.size < 1024:
                    size_ranges['small'] += 1
                elif loc.size < 102400:
                    size_ranges['medium'] += 1
                elif loc.size < 1048576:
                    size_ranges['large'] += 1
                else:
                    size_ranges['xlarge'] += 1
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'content_size': len(content.encode('utf-8')),
                'tree_size': len(tree_structure.encode('utf-8')),
                'file_types': file_types,
                'size_distribution': size_ranges,
                'avg_file_size': total_size / total_files if total_files > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating repository stats: {e}")
            return {
                'total_files': len(file_index),
                'total_size': sum(loc.size for loc in file_index.values()),
                'content_size': 0,
                'tree_size': 0,
                'file_types': {},
                'size_distribution': {},
                'avg_file_size': 0
            }
    
    def _validate_context(self, context: RepositoryContext) -> bool:
        """
        Validate repository context for completeness and consistency.
        
        Args:
            context: Repository context to validate
            
        Returns:
            True if context is valid
        """
        try:
            # Basic field validation
            if not all([
                context.repo_url,
                context.repo_name,
                context.content,
                isinstance(context.file_index, dict),
                context.total_files >= 0,
                context.total_size >= 0
            ]):
                self.logger.error("Context failed basic field validation")
                return False
            
            # Consistency checks
            if len(context.file_index) != context.total_files:
                self.logger.error(f"File index count mismatch: {len(context.file_index)} vs {context.total_files}")
                return False
            
            calculated_size = sum(loc.size for loc in context.file_index.values())
            if abs(calculated_size - context.total_size) > 1024:  # Allow 1KB tolerance
                self.logger.error(f"Size calculation mismatch: {calculated_size} vs {context.total_size}")
                return False
            
            # Content validation
            if len(context.content) < 100:
                self.logger.error("Content too small to be valid")
                return False
            
            # File index validation
            if context.total_files > 0 and not context.file_index:
                self.logger.error("No file index despite having files")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating context: {e}")
            return False
    
    def _parse_metadata_string(self, metadata_str: str) -> Dict[str, Any]:
        """
        Parse metadata string into dictionary.
        
        Args:
            metadata_str: Metadata string to parse
            
        Returns:
            Parsed metadata dictionary
        """
        try:
            metadata = {}
            
            if isinstance(metadata_str, str):
                for pair in metadata_str.split(','):
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        metadata[key.strip()] = value.strip()
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error parsing metadata string: {e}")
            return {}