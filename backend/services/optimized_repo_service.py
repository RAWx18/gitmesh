"""
Optimized Repository Service with Smart Caching and Fallback

This service implements the optimized flow:
1. First check Redis for repository data
2. If not found, use gitingest to fetch and store in Redis
3. Create virtual codebase mapping through content indexer
4. Provide efficient file access through the mapping

Key optimizations:
- Fast Redis lookups with connection pooling
- Intelligent fallback to gitingest
- Virtual file system mapping for O(1) file access
- Comprehensive error handling and monitoring
- Integration with KeyManager for secure GitHub token retrieval
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse

from config.key_manager import key_manager

# Configure logger first
logger = logging.getLogger(__name__)

# Initialize Cosmos configuration if available
try:
    from integrations.cosmos.v1.cosmos.config import initialize_configuration
    initialize_configuration()
    logger.info("Cosmos configuration initialized in optimized repo service")
except Exception as e:
    logger.warning(f"Could not initialize Cosmos configuration: {e}")

# Import Cosmos components
try:
    from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
    from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo, _get_repo_name_from_url
    from integrations.cosmos.v1.cosmos.content_indexer import ContentIndexer
    COSMOS_IMPORTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Cosmos imports not available: {e}")
    COSMOS_IMPORTS_AVAILABLE = False
    # We'll handle this in the class methods

# Optional monitoring import
try:
    from integrations.cosmos.v1.cosmos.monitoring import MonitoredOperation
except ImportError:
    # Fallback if monitoring is not available
    class MonitoredOperation:
        def __init__(self, operation_name, metadata=None):
            self.operation_name = operation_name
            self.metadata = metadata or {}
        
        def __enter__(self):
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass


class OptimizedRepoService:
    """
    Optimized repository service with smart caching and virtual file system.
    
    Implements the flow:
    1. Check Redis for cached repository data
    2. If not found, fetch using gitingest and cache in Redis
    3. Create virtual codebase mapping for efficient file access
    4. Provide O(1) file lookups through the mapping
    5. Use KeyManager for secure GitHub token retrieval
    """
    
    def __init__(self, user_login: Optional[str] = None):
        """
        Initialize the optimized repository service.
        
        Args:
            user_login: Username for GitHub token retrieval from KeyManager
        """
        self.storage_dir = os.getenv('STORAGE_DIR', '/tmp/repo_storage')
        self.user_login = user_login
        
        # Initialize Redis cache if available
        if COSMOS_IMPORTS_AVAILABLE:
            try:
                self.redis_cache = SmartRedisCache()
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis cache: {e}")
                self.redis_cache = None
        else:
            self.redis_cache = None
            logger.warning("Cosmos imports not available, Redis cache disabled")
        
        # Ensure storage directory exists
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Cache for content indexers to avoid recreating them
        self._indexer_cache: Dict[str, Any] = {}
        
        logger.info(f"OptimizedRepoService initialized for user: {user_login or 'anonymous'}")
    
    def get_repository_data(self, repo_url: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get repository data with optimized caching and fallback.
        
        Args:
            repo_url: Repository URL
            force_refresh: Force refresh from source (skip Redis cache)
            
        Returns:
            Repository data dictionary or None if failed
        """
        with MonitoredOperation("optimized_get_repository_data", {"repo_url": repo_url}):
            try:
                # Extract repository name
                repo_name = _get_repo_name_from_url(repo_url)
                logger.info(f"Getting repository data for: {repo_name}")
                
                # Step 1: Check Redis cache (unless force refresh)
                if not force_refresh:
                    cached_data = self._get_from_redis_fast(repo_name)
                    if cached_data:
                        logger.info(f"Repository {repo_name} found in Redis cache")
                        return cached_data
                
                # Step 2: Fallback to gitingest and cache in Redis
                logger.info(f"Repository {repo_name} not in cache, fetching with gitingest")
                if self._fetch_and_cache_repository(repo_url, repo_name):
                    # Try to get from Redis again after caching
                    cached_data = self._get_from_redis_fast(repo_name)
                    if cached_data:
                        return cached_data
                
                logger.error(f"Failed to get repository data for {repo_name}")
                return None
                
            except Exception as e:
                logger.error(f"Error getting repository data for {repo_url}: {e}")
                return None
    
    def get_file_content(self, repo_url: str, file_path: str) -> Optional[str]:
        """
        Get specific file content using virtual codebase mapping.
        
        Args:
            repo_url: Repository URL
            file_path: Path to the file within the repository
            
        Returns:
            File content as string or None if not found
        """
        with MonitoredOperation("optimized_get_file_content", {"repo_url": repo_url, "file_path": file_path}):
            try:
                repo_name = _get_repo_name_from_url(repo_url)
                
                # Ensure repository data is available
                repo_data = self.get_repository_data(repo_url)
                if not repo_data:
                    logger.warning(f"Repository {repo_name} not available for file access")
                    return None
                
                # Get content indexer for this repository
                indexer = self._get_content_indexer(repo_name)
                if not indexer:
                    logger.warning(f"Could not create content indexer for {repo_name}")
                    return None
                
                # Normalize file path for lookup
                normalized_path = self._normalize_file_path(file_path)
                
                # Try different path variations
                possible_paths = self._get_possible_file_paths(normalized_path, indexer.get_all_files())
                
                for path_variant in possible_paths:
                    content = indexer.get_file_content(path_variant)
                    if content is not None:
                        logger.info(f"Found file content for {path_variant} in {repo_name}")
                        return content
                
                logger.warning(f"File not found: {file_path} in repository {repo_name}")
                return None
                
            except Exception as e:
                logger.error(f"Error getting file content for {file_path} in {repo_url}: {e}")
                return None
    
    def list_repository_files(self, repo_url: str) -> List[str]:
        """
        List all files in the repository using virtual codebase mapping.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            List of file paths in the repository
        """
        try:
            repo_name = _get_repo_name_from_url(repo_url)
            
            # Ensure repository data is available
            repo_data = self.get_repository_data(repo_url)
            if not repo_data:
                logger.warning(f"No repository data available for {repo_url}")
                return []
            
            # Try content indexer first
            if COSMOS_IMPORTS_AVAILABLE:
                indexer = self._get_content_indexer(repo_name)
                if indexer:
                    try:
                        files = indexer.get_all_files()
                        if files:
                            logger.info(f"Found {len(files)} files using content indexer")
                            return files
                    except Exception as e:
                        logger.warning(f"Content indexer failed: {e}")
            
            # Fallback: Parse tree.txt directly
            if 'tree' in repo_data:
                files = self._parse_tree_txt(repo_data['tree'])
                logger.info(f"Found {len(files)} files by parsing tree.txt")
                return files
            
            # Last fallback: Parse content.md for file headers
            if 'content' in repo_data:
                files = self._parse_content_md_for_files(repo_data['content'])
                logger.info(f"Found {len(files)} files by parsing content.md")
                return files
            
            logger.warning(f"No files found for {repo_url}")
            return []
            
        except Exception as e:
            logger.error(f"Error listing files for {repo_url}: {e}")
            return []
    
    def _parse_tree_txt(self, tree_content: str) -> List[str]:
        """Parse tree.txt to extract file paths with improved logic."""
        files = []
        try:
            lines = tree_content.split('\n')
            current_path = []
            
            for line in lines:
                if not line.strip():
                    continue
                
                # Count indentation level
                original_line = line
                stripped_line = line.lstrip()
                
                # Remove tree drawing characters
                clean_line = stripped_line
                for char in ['├──', '└──', '├─', '└─', '│', '├', '└']:
                    clean_line = clean_line.replace(char, '')
                clean_line = clean_line.strip()
                
                if not clean_line:
                    continue
                
                # Skip directories (usually end with / or have no extension)
                if clean_line.endswith('/'):
                    continue
                
                # If it has a file extension, it's likely a file
                if '.' in clean_line:
                    # Check if it's a common file extension
                    common_extensions = ['.py', '.js', '.ts', '.html', '.css', '.md', '.txt', '.json', '.yml', '.yaml', '.xml', '.sh', '.bat', '.sql', '.php', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.swift', '.kt', '.scala', '.clj', '.hs', '.elm', '.vue', '.jsx', '.tsx', '.scss', '.less', '.styl', '.coffee', '.dart', '.r', '.m', '.mm', '.pl', '.pm', '.lua', '.vim', '.dockerfile', '.gitignore', '.env', '.ini', '.cfg', '.conf', '.toml']
                    
                    if any(clean_line.lower().endswith(ext) for ext in common_extensions):
                        files.append(clean_line)
                    elif '/' not in clean_line and '.' in clean_line:
                        # Simple filename with extension
                        files.append(clean_line)
                
        except Exception as e:
            logger.error(f"Error parsing tree.txt: {e}")
        
        return files
    
    def _parse_content_md_for_files(self, content_md: str) -> List[str]:
        """Parse content.md to extract file paths from FILE: headers."""
        files = []
        try:
            for line in content_md.split('\n'):
                if line.startswith('FILE: '):
                    file_path = line[6:].strip()  # Remove 'FILE: ' prefix
                    if file_path:
                        files.append(file_path)
        except Exception as e:
            logger.error(f"Error parsing content.md for files: {e}")
        return files
    
    def search_files(self, repo_url: str, pattern: str) -> List[str]:
        """
        Search for files matching a pattern in the repository.
        
        Args:
            repo_url: Repository URL
            pattern: Search pattern (supports wildcards)
            
        Returns:
            List of matching file paths
        """
        try:
            import fnmatch
            
            all_files = self.list_repository_files(repo_url)
            matching_files = []
            
            for file_path in all_files:
                if fnmatch.fnmatch(file_path.lower(), pattern.lower()):
                    matching_files.append(file_path)
            
            return matching_files
            
        except Exception as e:
            logger.error(f"Error searching files in {repo_url} with pattern {pattern}: {e}")
            return []
    
    def get_repository_stats(self, repo_url: str) -> Dict[str, Any]:
        """
        Get repository statistics and metadata.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Dictionary with repository statistics
        """
        try:
            repo_name = _get_repo_name_from_url(repo_url)
            
            # Get basic repository data
            repo_data = self.get_repository_data(repo_url)
            if not repo_data:
                return {"error": "Repository not available"}
            
            # Get indexer stats
            indexer = self._get_content_indexer(repo_name)
            if indexer:
                indexer_stats = indexer.get_stats()
            else:
                indexer_stats = {}
            
            # Get Redis metadata
            metadata = repo_data.get('metadata', {})
            
            return {
                "repo_name": repo_name,
                "repo_url": repo_url,
                "cached_in_redis": True,
                "total_files": indexer_stats.get('total_files', 0),
                "total_lines": indexer_stats.get('total_lines', 0),
                "estimated_tokens": metadata.get('estimated_tokens', 'unknown'),
                "stored_at": metadata.get('stored_at', 'unknown'),
                "user_tier": metadata.get('user_tier', 'unknown'),
                "indexer_available": indexer is not None
            }
            
        except Exception as e:
            logger.error(f"Error getting repository stats for {repo_url}: {e}")
            return {"error": str(e)}
    
    def _get_from_redis_fast(self, repo_name: str) -> Optional[Dict[str, Any]]:
        """
        Fast Redis lookup with minimal overhead.
        
        Args:
            repo_name: Repository name
            
        Returns:
            Repository data or None
        """
        with MonitoredOperation("redis_get_repository_data", {"repo_name": repo_name}):
            try:
                if not COSMOS_IMPORTS_AVAILABLE:
                    logger.warning("Cosmos imports not available, skipping Redis lookup")
                    return None
                
                # Initialize Redis cache if needed
                if not self.redis_cache:
                    try:
                        self.redis_cache = SmartRedisCache()
                        logger.info("Redis cache initialized successfully")
                    except Exception as e:
                        logger.warning(f"Failed to initialize Redis cache: {e}")
                        return None
                
                # Get repository data from Redis
                if hasattr(self.redis_cache, 'get_repository_data_cached'):
                    return self.redis_cache.get_repository_data_cached(repo_name)
                elif hasattr(self.redis_cache, 'get_repository_data'):
                    return self.redis_cache.get_repository_data(repo_name)
                else:
                    # Direct Redis fallback
                    return self._get_from_redis_direct(repo_name)
                    
            except Exception as e:
                logger.warning(f"Fast Redis lookup failed for {repo_name}: {e}")
                return None
    
    def _get_from_redis_direct(self, repo_name: str) -> Optional[Dict[str, Any]]:
        """
        Direct Redis access as fallback.
        
        Args:
            repo_name: Repository name
            
        Returns:
            Repository data or None
        """
        try:
            import redis
            import json
            
            # Get Redis connection details from environment
            redis_url = os.getenv('REDIS_URL')
            if not redis_url:
                logger.warning("No REDIS_URL available for direct access")
                return None
            
            # Connect to Redis
            r = redis.from_url(redis_url)
            
            # Try to get repository data
            repo_key = f"repo:{repo_name}"
            repo_data_str = r.get(repo_key)
            
            if repo_data_str:
                repo_data = json.loads(repo_data_str)
                logger.info(f"Retrieved {repo_name} via direct Redis access")
                return repo_data
            else:
                logger.warning(f"Repository {repo_name} not found in Redis via direct access")
                return None
                
        except Exception as e:
            logger.warning(f"Direct Redis access failed for {repo_name}: {e}")
            return None
    
    def _fetch_and_cache_repository(self, repo_url: str, repo_name: str) -> bool:
        """
        Fetch repository using gitingest and cache in Redis with user's GitHub token.
        
        Args:
            repo_url: Repository URL
            repo_name: Repository name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Fetching repository {repo_name} using gitingest")
            
            if not COSMOS_IMPORTS_AVAILABLE:
                logger.warning("Cosmos imports not available, cannot fetch repository")
                return False
            
            # Get GitHub token from KeyManager if user is authenticated
            github_token = None
            if self.user_login:
                try:
                    # Try get_github_token method first
                    github_token = key_manager.get_github_token(self.user_login)
                    if github_token:
                        logger.info(f"Retrieved GitHub token from KeyManager for user: {self.user_login}")
                    else:
                        # Try alternative method
                        github_token = key_manager.get_key(self.user_login, 'github_token')
                        if github_token:
                            logger.info(f"Retrieved GitHub token from KeyManager (alternative method) for user: {self.user_login}")
                        else:
                            logger.info(f"No GitHub token found in KeyManager for user: {self.user_login}")
                except Exception as e:
                    logger.warning(f"Failed to retrieve GitHub token from KeyManager: {e}")
            
            # Fallback to environment variable if no user token available
            if not github_token:
                env_token = os.getenv('GITHUB_TOKEN')
                if env_token and env_token.strip() and not env_token.startswith('your_github') and len(env_token.strip()) > 10:
                    github_token = env_token
                    logger.info("Using GitHub token from environment variable as fallback")
                else:
                    logger.info("No valid GitHub token available - using public API limits")
            
            # CRITICAL: Check repository size before gitingest to prevent Redis memory issues
            try:
                from integrations.cosmos.v1.cosmos.repo_fetch import check_repository_size_for_chat
                
                size_allowed, size_message, repo_size_kb = check_repository_size_for_chat(
                    repo_url, github_token, max_size_mb=150
                )
                
                if not size_allowed:
                    logger.error(f"Repository size check failed for {repo_url}: {size_message}")
                    return False
                
                logger.info(f"Repository size check passed for {repo_url}: {size_message}")
                
            except Exception as e:
                logger.error(f"Repository size check failed for {repo_url}: {e}")
                # Don't proceed if we can't verify repository size
                return False
            
            # Set GitHub token in environment for gitingest
            original_token = os.environ.get("GITHUB_TOKEN")
            if github_token:
                os.environ["GITHUB_TOKEN"] = github_token
                logger.info("Using KeyManager GitHub token for repository fetch")
            elif original_token:
                logger.info("Using existing environment GitHub token")
            else:
                logger.info("No GitHub token available, proceeding without authentication")
            
            try:
                # Use the existing fetch_and_store_repo function
                success = fetch_and_store_repo(repo_url)
                
                if success:
                    logger.info(f"Successfully fetched and cached {repo_name}")
                    
                    # Create virtual codebase mapping
                    self._ensure_virtual_mapping(repo_name)
                    
                    return True
                else:
                    logger.error(f"Failed to fetch and cache {repo_name}")
                    return False
                    
            finally:
                # Restore original token or remove if we set it
                if github_token:
                    if original_token:
                        os.environ["GITHUB_TOKEN"] = original_token
                    else:
                        os.environ.pop("GITHUB_TOKEN", None)
                
        except Exception as e:
            logger.error(f"Error fetching and caching {repo_name}: {e}")
            return False
    
    def _ensure_virtual_mapping(self, repo_name: str) -> bool:
        """
        Ensure virtual codebase mapping exists for the repository.
        
        Args:
            repo_name: Repository name
            
        Returns:
            True if mapping is available, False otherwise
        """
        try:
            indexer = self._get_content_indexer(repo_name)
            if indexer and indexer.ensure_index():
                logger.info(f"Virtual mapping ensured for {repo_name}")
                return True
            else:
                logger.warning(f"Could not ensure virtual mapping for {repo_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error ensuring virtual mapping for {repo_name}: {e}")
            return False
    
    def _get_content_indexer(self, repo_name: str) -> Optional[ContentIndexer]:
        """
        Get content indexer for repository with caching.
        
        Args:
            repo_name: Repository name
            
        Returns:
            ContentIndexer instance or None
        """
        try:
            if not COSMOS_IMPORTS_AVAILABLE:
                logger.warning("Cosmos imports not available, cannot create content indexer")
                return None
                
            # Check cache first
            if repo_name in self._indexer_cache:
                return self._indexer_cache[repo_name]
            
            # Create new indexer
            indexer = ContentIndexer(self.storage_dir, repo_name)
            
            # Cache it for future use
            self._indexer_cache[repo_name] = indexer
            
            return indexer
            
        except Exception as e:
            logger.error(f"Error creating content indexer for {repo_name}: {e}")
            return None
    
    def _normalize_file_path(self, file_path: str) -> str:
        """
        Normalize file path for consistent lookup.
        
        Args:
            file_path: Original file path
            
        Returns:
            Normalized file path
        """
        # Remove leading slashes and normalize separators
        normalized = file_path.lstrip('/\\').replace('\\', '/')
        
        # Handle common variations
        if normalized.startswith('./'):
            normalized = normalized[2:]
        
        return normalized
    
    def _get_possible_file_paths(self, target_path: str, available_files: List[str]) -> List[str]:
        """
        Get possible file path variations for lookup.
        
        Args:
            target_path: Target file path
            available_files: List of available files in repository
            
        Returns:
            List of possible path variations to try
        """
        possible_paths = []
        
        # Add the exact path
        possible_paths.append(target_path)
        
        # Add case-insensitive matches
        target_lower = target_path.lower()
        for file_path in available_files:
            if file_path.lower() == target_lower and file_path not in possible_paths:
                possible_paths.append(file_path)
        
        # Add partial matches (filename only)
        target_filename = os.path.basename(target_path).lower()
        for file_path in available_files:
            if os.path.basename(file_path).lower() == target_filename and file_path not in possible_paths:
                possible_paths.append(file_path)
        
        # Add common variations
        variations = [
            target_path.lower(),
            target_path.upper(),
            target_path.replace('-', '_'),
            target_path.replace('_', '-'),
        ]
        
        for variation in variations:
            if variation not in possible_paths:
                for file_path in available_files:
                    if file_path.lower() == variation.lower() and file_path not in possible_paths:
                        possible_paths.append(file_path)
        
        return possible_paths
    
    def clear_cache(self, repo_url: Optional[str] = None) -> bool:
        """
        Clear cache for specific repository or all repositories.
        
        Args:
            repo_url: Repository URL to clear, or None to clear all
            
        Returns:
            True if successful
        """
        try:
            if repo_url:
                repo_name = _get_repo_name_from_url(repo_url)
                
                # Clear Redis cache
                self.redis_cache.smart_invalidate(repo_name)
                
                # Clear indexer cache
                if repo_name in self._indexer_cache:
                    del self._indexer_cache[repo_name]
                
                logger.info(f"Cleared cache for {repo_name}")
            else:
                # Clear all indexer cache
                self._indexer_cache.clear()
                logger.info("Cleared all indexer cache")
            
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the service.
        
        Returns:
            Health check results
        """
        try:
            redis_healthy = False
            if self.redis_cache:
                try:
                    redis_healthy = self.redis_cache.health_check(force=True)
                except Exception as e:
                    logger.warning(f"Redis health check failed: {e}")
                    redis_healthy = False
            
            storage_accessible = os.path.exists(self.storage_dir) and os.access(self.storage_dir, os.W_OK)
            
            return {
                "service": "OptimizedRepoService",
                "redis_healthy": redis_healthy,
                "storage_accessible": storage_accessible,
                "storage_dir": self.storage_dir,
                "indexer_cache_size": len(self._indexer_cache),
                "cosmos_imports_available": COSMOS_IMPORTS_AVAILABLE,
                "overall_healthy": storage_accessible  # At minimum, storage should be accessible
            }
            
        except Exception as e:
            return {
                "service": "OptimizedRepoService",
                "error": str(e),
                "overall_healthy": False
            }


# Global service instances per user
_service_instances: Dict[str, OptimizedRepoService] = {}


def get_optimized_repo_service(user_login: Optional[str] = None) -> OptimizedRepoService:
    """
    Get the optimized repository service instance for a user.
    
    Args:
        user_login: Username for GitHub token retrieval
        
    Returns:
        OptimizedRepoService instance
    """
    global _service_instances
    
    # Use 'anonymous' as key for unauthenticated users
    service_key = user_login or 'anonymous'
    
    if service_key not in _service_instances:
        _service_instances[service_key] = OptimizedRepoService(user_login)
    
    return _service_instances[service_key]


# Convenience functions for easy integration
def get_repository_data_optimized(repo_url: str, user_login: Optional[str] = None, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Get repository data using optimized service."""
    service = get_optimized_repo_service(user_login)
    return service.get_repository_data(repo_url, force_refresh)


def get_file_content_optimized(repo_url: str, file_path: str, user_login: Optional[str] = None) -> Optional[str]:
    """Get file content using optimized service."""
    service = get_optimized_repo_service(user_login)
    return service.get_file_content(repo_url, file_path)


def list_repository_files_optimized(repo_url: str, user_login: Optional[str] = None) -> List[str]:
    """List repository files using optimized service."""
    service = get_optimized_repo_service(user_login)
    return service.list_repository_files(repo_url)


def search_files_optimized(repo_url: str, pattern: str, user_login: Optional[str] = None) -> List[str]:
    """Search files using optimized service."""
    service = get_optimized_repo_service(user_login)
    return service.search_files(repo_url, pattern)