"""
Optimized Repository Middleware

This middleware replaces the slow Redis loops with the optimized repository service.
It provides fast repository data access and file content retrieval for chat operations.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from functools import wraps

from services.optimized_repo_service import get_optimized_repo_service

# Configure logger
logger = logging.getLogger(__name__)

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

logger = logging.getLogger(__name__)


class RepoAccessMiddleware:
    """
    Middleware for optimized repository access in chat operations.
    """
    
    def __init__(self, user_login: Optional[str] = None):
        """
        Initialize the repository access middleware.
        
        Args:
            user_login: Username for GitHub token retrieval
        """
        self.user_login = user_login
        self.service = get_optimized_repo_service(user_login)
        self._request_cache = {}  # Cache for single request lifecycle
        
    def get_repository_context(self, repo_url: str, required_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get repository context for chat operations.
        
        Args:
            repo_url: Repository URL
            required_files: List of specific files needed (optional)
            
        Returns:
            Repository context dictionary
        """
        with MonitoredOperation("middleware_get_repository_context", {"repo_url": repo_url}):
            try:
                # Check request cache first
                cache_key = f"repo_context:{repo_url}"
                if cache_key in self._request_cache:
                    logger.debug(f"Using cached repository context for {repo_url}")
                    return self._request_cache[cache_key]
                
                start_time = time.time()
                
                # Get repository data (this will use Redis cache or fetch with gitingest)
                repo_data = self.service.get_repository_data(repo_url)
                if not repo_data:
                    logger.warning(f"Could not get repository data for {repo_url}")
                    return {"error": "Repository not available", "repo_url": repo_url}
                
                # Get repository statistics
                stats = self.service.get_repository_stats(repo_url)
                
                # Get file list
                all_files = self.service.list_repository_files(repo_url)
                
                # Get specific files if requested
                file_contents = {}
                if required_files:
                    for file_path in required_files:
                        content = self.service.get_file_content(repo_url, file_path)
                        if content is not None:
                            file_contents[file_path] = content
                        else:
                            logger.warning(f"Could not get content for {file_path} in {repo_url}")
                
                context = {
                    "repo_url": repo_url,
                    "repo_name": stats.get("repo_name", "unknown"),
                    "total_files": len(all_files),
                    "total_lines": stats.get("total_lines", 0),
                    "estimated_tokens": stats.get("estimated_tokens", "unknown"),
                    "all_files": all_files[:100],  # Limit to first 100 files for performance
                    "file_contents": file_contents,
                    "cached_in_redis": stats.get("cached_in_redis", False),
                    "indexer_available": stats.get("indexer_available", False),
                    "fetch_time_ms": round((time.time() - start_time) * 1000, 2)
                }
                
                # Cache for this request
                self._request_cache[cache_key] = context
                
                logger.info(f"Repository context prepared for {repo_url} in {context['fetch_time_ms']}ms")
                return context
                
            except Exception as e:
                logger.error(f"Error getting repository context for {repo_url}: {e}")
                return {"error": str(e), "repo_url": repo_url}
    
    def get_file_content_fast(self, repo_url: str, file_path: str) -> Optional[str]:
        """
        Get file content with fast lookup using virtual codebase mapping.
        
        Args:
            repo_url: Repository URL
            file_path: File path within repository
            
        Returns:
            File content or None if not found
        """
        with MonitoredOperation("middleware_get_file_content", {"repo_url": repo_url, "file_path": file_path}):
            try:
                # Check request cache first
                cache_key = f"file_content:{repo_url}:{file_path}"
                if cache_key in self._request_cache:
                    return self._request_cache[cache_key]
                
                start_time = time.time()
                
                # Get file content using optimized service
                content = self.service.get_file_content(repo_url, file_path)
                
                # Cache for this request
                if content is not None:
                    self._request_cache[cache_key] = content
                    fetch_time = round((time.time() - start_time) * 1000, 2)
                    logger.info(f"File content retrieved for {file_path} in {fetch_time}ms")
                else:
                    logger.warning(f"File not found: {file_path} in {repo_url}")
                
                return content
                
            except Exception as e:
                logger.error(f"Error getting file content for {file_path} in {repo_url}: {e}")
                return None
    
    def search_repository_files(self, repo_url: str, pattern: str) -> List[str]:
        """
        Search for files in repository matching pattern.
        
        Args:
            repo_url: Repository URL
            pattern: Search pattern
            
        Returns:
            List of matching file paths
        """
        try:
            return self.service.search_files(repo_url, pattern)
        except Exception as e:
            logger.error(f"Error searching files in {repo_url} with pattern {pattern}: {e}")
            return []
    
    def clear_request_cache(self):
        """Clear the request-level cache."""
        self._request_cache.clear()
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on the middleware."""
        try:
            service_health = self.service.health_check()
            return {
                "middleware": "RepoAccessMiddleware",
                "service_health": service_health,
                "request_cache_size": len(self._request_cache),
                "overall_healthy": service_health.get("overall_healthy", False)
            }
        except Exception as e:
            return {
                "middleware": "RepoAccessMiddleware",
                "error": str(e),
                "overall_healthy": False
            }


# Global middleware instances per user
_middleware_instances: Dict[str, RepoAccessMiddleware] = {}


def get_repo_middleware(user_login: Optional[str] = None) -> RepoAccessMiddleware:
    """
    Get the repository access middleware instance for a user.
    
    Args:
        user_login: Username for GitHub token retrieval
        
    Returns:
        RepoAccessMiddleware instance
    """
    global _middleware_instances
    
    # Use 'anonymous' as key for unauthenticated users
    middleware_key = user_login or 'anonymous'
    
    if middleware_key not in _middleware_instances:
        _middleware_instances[middleware_key] = RepoAccessMiddleware(user_login)
    
    return _middleware_instances[middleware_key]


def with_repo_context(required_files: Optional[List[str]] = None):
    """
    Decorator to inject repository context into route handlers.
    
    Args:
        required_files: List of files to preload (optional)
    
    Usage:
        @with_repo_context(['README.md', 'package.json'])
        def my_route(repo_url: str, repo_context: dict):
            # repo_context contains repository data and file contents
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract repo_url from kwargs or args
            repo_url = kwargs.get('repo_url')
            if not repo_url and len(args) > 0:
                # Try to find repo_url in args (assuming it's a common parameter)
                for arg in args:
                    if isinstance(arg, str) and ('github.com' in arg or 'gitlab.com' in arg):
                        repo_url = arg
                        break
            
            if repo_url:
                middleware = get_repo_middleware()
                repo_context = middleware.get_repository_context(repo_url, required_files)
                kwargs['repo_context'] = repo_context
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def clear_middleware_cache():
    """Clear the middleware request cache."""
    middleware = get_repo_middleware()
    middleware.clear_request_cache()


# Convenience functions for direct use
def get_repository_context_fast(repo_url: str, user_login: Optional[str] = None, required_files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Get repository context using middleware."""
    middleware = get_repo_middleware(user_login)
    return middleware.get_repository_context(repo_url, required_files)


def get_file_content_middleware(repo_url: str, file_path: str, user_login: Optional[str] = None) -> Optional[str]:
    """Get file content using middleware."""
    middleware = get_repo_middleware(user_login)
    return middleware.get_file_content_fast(repo_url, file_path)


def search_files_middleware(repo_url: str, pattern: str, user_login: Optional[str] = None) -> List[str]:
    """Search files using middleware."""
    middleware = get_repo_middleware(user_login)
    return middleware.search_repository_files(repo_url, pattern)