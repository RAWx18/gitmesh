"""
Simplified Optimized Repository Service

A simplified version that focuses on the core optimization without complex dependencies.
This version can be used as a fallback if the full optimized system has import issues.
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class SimpleOptimizedRepoService:
    """
    Simplified optimized repository service with basic caching and KeyManager integration.
    """
    
    def __init__(self, user_login: Optional[str] = None):
        """
        Initialize the simplified optimized repository service.
        
        Args:
            user_login: Username for GitHub token retrieval from KeyManager
        """
        self.user_login = user_login
        self._cache = {}  # Simple in-memory cache
        
        logger.info(f"SimpleOptimizedRepoService initialized for user: {user_login or 'anonymous'}")
    
    def get_github_token(self) -> Optional[str]:
        """Get GitHub token from KeyManager if available."""
        if not self.user_login:
            # Fallback to environment variable if no user
            env_token = os.getenv('GITHUB_TOKEN')
            if env_token and env_token.strip() and not env_token.startswith('your_github') and len(env_token.strip()) > 10:
                logger.info("Using GitHub token from environment variable (no user login)")
                return env_token
            return None
        
        try:
            from config.key_manager import key_manager
            
            # Try get_github_token method first
            token = key_manager.get_github_token(self.user_login)
            if token:
                logger.info(f"Retrieved GitHub token from KeyManager for user: {self.user_login}")
                return token
            
            # Try alternative method
            token = key_manager.get_key(self.user_login, 'github_token')
            if token:
                logger.info(f"Retrieved GitHub token from KeyManager (alternative method) for user: {self.user_login}")
                return token
            
            logger.info(f"No GitHub token found in KeyManager for user: {self.user_login}")
            
        except Exception as e:
            logger.warning(f"Failed to retrieve GitHub token from KeyManager: {e}")
        
        # Fallback to environment variable
        env_token = os.getenv('GITHUB_TOKEN')
        if env_token and env_token.strip() and not env_token.startswith('your_github') and len(env_token.strip()) > 10:
            logger.info("Using GitHub token from environment variable as fallback")
            return env_token
        
        logger.info("No valid GitHub token available")
        return None
    
    def get_repository_data(self, repo_url: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get repository data with simple caching.
        
        Args:
            repo_url: Repository URL
            force_refresh: Force refresh from source
            
        Returns:
            Repository data dictionary or None if failed
        """
        cache_key = f"repo_data:{repo_url}"
        
        # Check cache first
        if not force_refresh and cache_key in self._cache:
            logger.info(f"Repository data found in cache for {repo_url}")
            return self._cache[cache_key]
        
        # Try to fetch from Redis first
        try:
            redis_data = self._get_from_redis(repo_url)
            if redis_data:
                self._cache[cache_key] = redis_data
                return redis_data
        except Exception as e:
            logger.warning(f"Redis fetch failed: {e}")
        
        # Fallback to gitingest
        try:
            gitingest_data = self._fetch_with_gitingest(repo_url)
            if gitingest_data:
                self._cache[cache_key] = gitingest_data
                return gitingest_data
        except Exception as e:
            logger.error(f"GitIngest fetch failed: {e}")
        
        return None
    
    def get_file_content(self, repo_url: str, file_path: str) -> Optional[str]:
        """
        Get file content from repository.
        
        Args:
            repo_url: Repository URL
            file_path: Path to the file
            
        Returns:
            File content or None if not found
        """
        cache_key = f"file_content:{repo_url}:{file_path}"
        
        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get repository data
        repo_data = self.get_repository_data(repo_url)
        if not repo_data or 'content' not in repo_data:
            return None
        
        # Extract file from content.md
        try:
            content = self._extract_file_from_content_md(file_path, repo_data['content'])
            if content:
                self._cache[cache_key] = content
            return content
        except Exception as e:
            logger.error(f"Error extracting file {file_path}: {e}")
            return None
    
    def list_repository_files(self, repo_url: str) -> List[str]:
        """
        List all files in the repository.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            List of file paths
        """
        repo_data = self.get_repository_data(repo_url)
        if not repo_data or 'tree' not in repo_data:
            return []
        
        try:
            return self._parse_tree_for_files(repo_data['tree'])
        except Exception as e:
            logger.error(f"Error parsing tree for {repo_url}: {e}")
            return []
    
    def _get_from_redis(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """Try to get repository data from Redis."""
        try:
            # Import Redis cache if available
            from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
            
            redis_cache = SmartRedisCache()
            repo_name = self._get_repo_name_from_url(repo_url)
            
            return redis_cache.get_repository_data_cached(repo_name)
            
        except ImportError:
            logger.info("Redis cache not available, skipping Redis lookup")
            return None
        except Exception as e:
            logger.warning(f"Redis lookup failed: {e}")
            return None
    
    def _fetch_with_gitingest(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """Fetch repository using gitingest."""
        try:
            # Set GitHub token if available
            github_token = self.get_github_token()
            original_token = os.environ.get("GITHUB_TOKEN")
            
            if github_token:
                os.environ["GITHUB_TOKEN"] = github_token
                logger.info("Using KeyManager GitHub token for gitingest")
            
            # CRITICAL: Check repository size before gitingest to prevent Redis memory issues
            try:
                from integrations.cosmos.v1.cosmos.repo_fetch import check_repository_size_for_chat
                
                size_allowed, size_message, repo_size_kb = check_repository_size_for_chat(
                    repo_url, github_token, max_size_mb=150
                )
                
                if not size_allowed:
                    logger.error(f"Repository size check failed for {repo_url}: {size_message}")
                    return None
                
                logger.info(f"Repository size check passed for {repo_url}: {size_message}")
                
            except Exception as e:
                logger.error(f"Repository size check failed for {repo_url}: {e}")
                # Don't proceed if we can't verify repository size
                return None
            
            try:
                from gitingest import ingest
                
                # Fetch repository with analytics folder exclusion
                summary, tree, content = ingest(repo_url, exclude_patterns=[
                    'analytics/*',
                    '*/analytics/*',
                    '.analytics/*',
                    '*/.analytics/*',
                    'analytics/**',
                    '**/analytics/**'
                ])
                
                # Log analytics folder detection and filter content
                def _filter_analytics_folders(content_str: str, tree_str: str) -> tuple:
                    """Filter out analytics folders from content and tree data."""
                    if not content_str or not tree_str:
                        return content_str, tree_str
                    
                    # Log analytics folder detection
                    analytics_patterns = ['analytics/', '/analytics/', 'analytics\\', '\\analytics\\']
                    has_analytics = any(pattern in content_str.lower() or pattern in tree_str.lower() 
                                      for pattern in analytics_patterns)
                    
                    if has_analytics:
                        logger.info(f"Analytics folder detected in repository - filtering from cache storage")
                        print(f"Analytics folder found - excluding from cache")
                        
                        # Filter content - remove sections related to analytics folders
                        filtered_content_lines = []
                        for line in content_str.split('\n'):
                            line_lower = line.lower()
                            if not any(pattern.strip('/\\') in line_lower for pattern in analytics_patterns):
                                filtered_content_lines.append(line)
                        
                        # Filter tree - remove analytics folder entries
                        filtered_tree_lines = []
                        for line in tree_str.split('\n'):
                            line_lower = line.lower()
                            if not any(pattern.strip('/\\') in line_lower for pattern in analytics_patterns):
                                filtered_tree_lines.append(line)
                        
                        return '\n'.join(filtered_content_lines), '\n'.join(filtered_tree_lines)
                    
                    return content_str, tree_str
                
                # Apply analytics folder filtering
                filtered_content, filtered_tree = _filter_analytics_folders(content, tree)
                
                return {
                    'content': filtered_content,
                    'tree': filtered_tree,
                    'summary': summary,
                    'metadata': {
                        'fetched_at': time.time(),
                        'repo_url': repo_url
                    }
                }
                
            finally:
                # Restore original token
                if github_token:
                    if original_token:
                        os.environ["GITHUB_TOKEN"] = original_token
                    else:
                        os.environ.pop("GITHUB_TOKEN", None)
            
        except ImportError:
            logger.error("GitIngest not available")
            return None
        except Exception as e:
            logger.error(f"GitIngest fetch failed: {e}")
            return None
    
    def _extract_file_from_content_md(self, file_path: str, content_md: str) -> Optional[str]:
        """Extract file content from content.md string."""
        try:
            lines = content_md.split('\n')
            
            # Look for file boundary
            file_start = None
            for i, line in enumerate(lines):
                if f"FILE: {file_path}" in line:
                    file_start = i + 2  # Skip the FILE: line and boundary
                    break
            
            if file_start is None:
                return None
            
            # Find end of file
            file_content = []
            for i in range(file_start, len(lines)):
                line = lines[i]
                if line.strip() == "=" * 48:  # End boundary
                    break
                file_content.append(line)
            
            return '\n'.join(file_content)
            
        except Exception as e:
            logger.error(f"Error extracting file {file_path}: {e}")
            return None
    
    def _parse_tree_for_files(self, tree_content: str) -> List[str]:
        """Parse tree.txt content to get list of files."""
        try:
            files = []
            for line in tree_content.split('\n'):
                line = line.strip()
                if line and not line.startswith('├') and not line.startswith('└') and not line.startswith('│'):
                    # Simple heuristic: if it contains a dot, it's likely a file
                    if '.' in line and not line.endswith('/'):
                        files.append(line)
            return files
        except Exception as e:
            logger.error(f"Error parsing tree: {e}")
            return []
    
    def _get_repo_name_from_url(self, repo_url: str) -> str:
        """Extract repository name from URL."""
        from urllib.parse import urlparse
        
        path = urlparse(repo_url).path
        path_parts = [part for part in path.strip('/').split('/') if part]
        
        if len(path_parts) >= 2:
            repo_name = path_parts[1].replace('.git', '')
            return f"{path_parts[0]}/{repo_name}"
        
        return "unknown/repo"
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        return {
            "service": "SimpleOptimizedRepoService",
            "user_login": self.user_login,
            "cache_size": len(self._cache),
            "overall_healthy": True
        }
    
    def clear_cache(self):
        """Clear the cache."""
        self._cache.clear()
        logger.info("Cache cleared")


# Global service instances
_simple_service_instances: Dict[str, SimpleOptimizedRepoService] = {}


def get_simple_optimized_repo_service(user_login: Optional[str] = None) -> SimpleOptimizedRepoService:
    """
    Get the simple optimized repository service instance for a user.
    
    Args:
        user_login: Username for GitHub token retrieval
        
    Returns:
        SimpleOptimizedRepoService instance
    """
    global _simple_service_instances
    
    service_key = user_login or 'anonymous'
    
    if service_key not in _simple_service_instances:
        _simple_service_instances[service_key] = SimpleOptimizedRepoService(user_login)
    
    return _simple_service_instances[service_key]