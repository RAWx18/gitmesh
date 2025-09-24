"""
Optimized Redis Repository Manager

This is a drop-in replacement for RedisRepoManager that uses the optimized
repository service as a backend, providing the same interface but with
much better performance.
"""

import logging
from typing import Dict, Any, Optional, List
from .optimized_repo_service import get_optimized_repo_service
from .redis_repo_manager import RedisRepoManager

logger = logging.getLogger(__name__)


class OptimizedRedisRepoManager(RedisRepoManager):
    """
    Optimized version of RedisRepoManager that uses the fast repository service.
    
    This class maintains the same interface as RedisRepoManager but uses
    the optimized service for much faster repository data access.
    """
    
    def __init__(self, repo_url: str, branch: str = "main", username: str = "default"):
        """
        Initialize optimized repository manager.
        
        Args:
            repo_url: Repository URL
            branch: Repository branch
            username: Username for context and GitHub token retrieval
        """
        # Initialize parent class but don't use its slow methods
        super().__init__(repo_url, branch, username)
        
        # Use our optimized service with user login for GitHub token access
        self.optimized_service = get_optimized_repo_service(username)
        
        # Cache repository context for this session
        self._repo_context = None
        self._file_cache = {}
        
        logger.info(f"OptimizedRedisRepoManager initialized for {repo_url} with user: {username}")
    
    def get_repository_data(self) -> Optional[Dict[str, Any]]:
        """
        Get repository data using optimized service.
        
        Returns:
            Repository data dictionary or None
        """
        try:
            if self._repo_context is None:
                self._repo_context = self.optimized_service.get_repository_data(self.repo_url)
            
            return self._repo_context
            
        except Exception as e:
            logger.error(f"Error getting repository data: {e}")
            return None
    
    def get_file_content(self, file_path: str) -> Optional[str]:
        """
        Get file content using optimized virtual codebase mapping.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content or None if not found
        """
        try:
            # Check cache first
            if file_path in self._file_cache:
                return self._file_cache[file_path]
            
            # Get content using optimized service
            content = self.optimized_service.get_file_content(self.repo_url, file_path)
            
            # Cache the result
            if content is not None:
                self._file_cache[file_path] = content
            
            return content
            
        except Exception as e:
            logger.error(f"Error getting file content for {file_path}: {e}")
            return None
    
    def list_files(self) -> List[str]:
        """
        List all files in the repository.
        
        Returns:
            List of file paths
        """
        try:
            return self.optimized_service.list_repository_files(self.repo_url)
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    def search_files(self, pattern: str) -> List[str]:
        """
        Search for files matching a pattern.
        
        Args:
            pattern: Search pattern
            
        Returns:
            List of matching file paths
        """
        try:
            return self.optimized_service.search_files(self.repo_url, pattern)
        except Exception as e:
            logger.error(f"Error searching files with pattern {pattern}: {e}")
            return []
    
    def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in the repository.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file exists
        """
        try:
            content = self.get_file_content(file_path)
            return content is not None
        except Exception as e:
            logger.error(f"Error checking file existence for {file_path}: {e}")
            return False
    
    def get_repository_stats(self) -> Dict[str, Any]:
        """
        Get repository statistics.
        
        Returns:
            Dictionary with repository statistics
        """
        try:
            return self.optimized_service.get_repository_stats(self.repo_url)
        except Exception as e:
            logger.error(f"Error getting repository stats: {e}")
            return {}
    
    def clear_cache(self):
        """Clear the local cache."""
        self._repo_context = None
        self._file_cache.clear()
        logger.info(f"Cleared cache for {self.repo_url}")
    
    def health_check(self) -> bool:
        """
        Perform health check.
        
        Returns:
            True if healthy
        """
        try:
            health = self.optimized_service.health_check()
            return health.get("overall_healthy", False)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    # Override parent methods that might be slow
    def extract_file_from_content_md(self, file_path: str, content_md: str) -> Optional[str]:
        """
        Override parent method to use optimized file extraction.
        
        Args:
            file_path: Path to the file
            content_md: Content.md string (ignored, we use optimized service)
            
        Returns:
            File content or None
        """
        # Use our optimized method instead of parsing content_md
        return self.get_file_content(file_path)
    
    def get_repository_content_from_redis(self) -> Optional[str]:
        """
        Override parent method to use optimized repository data access.
        
        Returns:
            Repository content or None
        """
        try:
            repo_data = self.get_repository_data()
            if repo_data:
                return repo_data.get('content')
            return None
        except Exception as e:
            logger.error(f"Error getting repository content: {e}")
            return None
    
    def get_repository_tree_from_redis(self) -> Optional[str]:
        """
        Override parent method to use optimized repository data access.
        
        Returns:
            Repository tree or None
        """
        try:
            repo_data = self.get_repository_data()
            if repo_data:
                return repo_data.get('tree')
            return None
        except Exception as e:
            logger.error(f"Error getting repository tree: {e}")
            return None
    
    def get_repository_summary_from_redis(self) -> Optional[str]:
        """
        Override parent method to use optimized repository data access.
        
        Returns:
            Repository summary or None
        """
        try:
            repo_data = self.get_repository_data()
            if repo_data:
                return repo_data.get('summary')
            return None
        except Exception as e:
            logger.error(f"Error getting repository summary: {e}")
            return None
    
    def get_repository_info(self) -> Dict[str, Any]:
        """
        Get repository information including file count.
        
        Returns:
            Dictionary with repository information
        """
        try:
            # Get file list using optimized service
            files = self.list_files()
            
            # Get repository stats
            stats = self.get_repository_stats()
            
            return {
                'file_count': len(files),
                'total_files': len(files),
                'files': files[:100],  # Limit to first 100 files for performance
                'repo_name': stats.get('repo_name', 'unknown'),
                'repo_url': self.repo_url,
                'branch': self.branch,
                'username': self.username,
                'cached_in_redis': stats.get('cached_in_redis', False),
                'estimated_tokens': stats.get('estimated_tokens', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return {
                'file_count': 0,
                'total_files': 0,
                'files': [],
                'repo_name': 'unknown',
                'repo_url': self.repo_url,
                'branch': self.branch,
                'username': self.username,
                'error': str(e)
            }


def create_optimized_repo_manager(repo_url: str, branch: str = "main", username: str = "default") -> OptimizedRedisRepoManager:
    """
    Create an optimized repository manager instance.
    
    Args:
        repo_url: Repository URL
        branch: Repository branch
        username: Username for context
        
    Returns:
        OptimizedRedisRepoManager instance
    """
    return OptimizedRedisRepoManager(repo_url, branch, username)