"""
Repository Selection Automation for Cosmos Integration
Handles automatic repository selection from current context with fallback logic
"""
import re
import redis
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import structlog
import os

logger = structlog.get_logger(__name__)

@dataclass
class RepositoryInfo:
    """Information about a repository option"""
    url: str
    name: str
    owner: str
    cached: bool = False
    last_updated: Optional[str] = None
    size_estimate: Optional[int] = None

class RepositorySelector:
    """
    Handles automatic repository selection from current context.
    
    This class provides intelligent repository selection based on:
    1. Current repository context from GitMesh
    2. Available repositories in Redis cache
    3. Fallback logic when context is unclear
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize the repository selector.
        
        Args:
            redis_client: Optional Redis client for cache access
        """
        self.redis_client = redis_client or self._get_redis_client()
        self.cached_repositories = []
        self._refresh_cached_repositories()
        
        logger.info("RepositorySelector initialized", 
                   cached_repos_count=len(self.cached_repositories))
    
    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client from environment configuration"""
        try:
            redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_CLOUD_URL")
            if redis_url:
                return redis.from_url(redis_url, decode_responses=True)
            else:
                logger.warning("No Redis URL configured for repository cache access")
                return None
        except Exception as e:
            logger.error("Failed to create Redis client", error=str(e))
            return None
    
    def _refresh_cached_repositories(self):
        """Refresh the list of cached repositories from Redis"""
        if not self.redis_client:
            logger.warning("No Redis client available for repository cache refresh")
            return
        
        try:
            # Look for repository cache keys
            repo_keys = self.redis_client.keys("repo:*:summary")
            self.cached_repositories = []
            
            for key in repo_keys:
                # Extract owner/repo from key format: repo:owner/repo:summary
                match = re.match(r"repo:([^:]+/[^:]+):summary", key)
                if match:
                    owner_repo = match.group(1)
                    owner, repo_name = owner_repo.split('/', 1)
                    
                    # Check if repository has content cached
                    content_key = f"repo:{owner_repo}:content"
                    has_content = self.redis_client.exists(content_key)
                    
                    # Get last updated info if available
                    metadata_key = f"repo:{owner_repo}:metadata"
                    last_updated = None
                    size_estimate = None
                    
                    try:
                        metadata = self.redis_client.get(metadata_key)
                        if metadata:
                            metadata_dict = json.loads(metadata)
                            last_updated = metadata_dict.get("last_updated")
                            size_estimate = metadata_dict.get("size_estimate")
                    except:
                        pass
                    
                    repo_info = RepositoryInfo(
                        url=f"https://github.com/{owner_repo}",
                        name=repo_name,
                        owner=owner,
                        cached=bool(has_content),
                        last_updated=last_updated,
                        size_estimate=size_estimate
                    )
                    
                    self.cached_repositories.append(repo_info)
            
            logger.info("Refreshed cached repositories", 
                       count=len(self.cached_repositories),
                       cached_with_content=sum(1 for r in self.cached_repositories if r.cached))
            
        except Exception as e:
            logger.error("Failed to refresh cached repositories", error=str(e))
            self.cached_repositories = []
    
    def select_repository_automatically(self, 
                                      context: Dict[str, Any] = None,
                                      available_options: List[str] = None) -> Tuple[str, str]:
        """
        Automatically select a repository based on context and available options.
        
        Args:
            context: Current context including repository_url, project_id, etc.
            available_options: List of available repository options from Cosmos
            
        Returns:
            Tuple of (selection_response, reasoning)
        """
        # Strategy 1: Use repository from current context
        if context and context.get("repository_url"):
            current_repo_url = context["repository_url"]
            
            # If we have available options, try to match
            if available_options:
                selection, reasoning = self._match_repository_in_options(
                    current_repo_url, available_options)
                if selection:
                    return selection, reasoning
            
            # If no options provided or no match, validate repository availability
            if self._validate_repository_availability(current_repo_url):
                return current_repo_url, f"Using repository from current context: {current_repo_url}"
        
        # Strategy 2: Use first cached repository with content
        cached_with_content = [r for r in self.cached_repositories if r.cached]
        if cached_with_content:
            selected_repo = cached_with_content[0]
            
            # If we have options, try to find this repo in the list
            if available_options:
                selection, reasoning = self._match_repository_in_options(
                    selected_repo.url, available_options)
                if selection:
                    return selection, reasoning
            
            return selected_repo.url, f"Using first cached repository: {selected_repo.url}"
        
        # Strategy 3: Use any cached repository
        if self.cached_repositories:
            selected_repo = self.cached_repositories[0]
            
            if available_options:
                selection, reasoning = self._match_repository_in_options(
                    selected_repo.url, available_options)
                if selection:
                    return selection, reasoning
            
            return selected_repo.url, f"Using first available cached repository: {selected_repo.url}"
        
        # Strategy 4: Default fallback
        if available_options:
            return "1", "No context available, selecting first option"
        
        # Final fallback - use GitMesh repository
        fallback_url = "https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh"
        return fallback_url, f"Using fallback repository: {fallback_url}"
    
    def _match_repository_in_options(self, target_url: str, options: List[str]) -> Tuple[Optional[str], str]:
        """
        Try to match a target repository URL in the available options.
        
        Args:
            target_url: The repository URL to find
            options: List of available options
            
        Returns:
            Tuple of (selection_number, reasoning) or (None, reason_for_no_match)
        """
        # Extract owner/repo from target URL
        target_owner_repo = self._extract_owner_repo(target_url)
        if not target_owner_repo:
            return None, f"Could not extract owner/repo from URL: {target_url}"
        
        # Try to match in options
        for i, option in enumerate(options):
            option_owner_repo = self._extract_owner_repo(option)
            if option_owner_repo and option_owner_repo == target_owner_repo:
                selection = str(i + 1)
                return selection, f"Found matching repository at option {selection}: {option}"
            
            # Also try partial matching
            if target_owner_repo in option or option in target_url:
                selection = str(i + 1)
                return selection, f"Found partial match at option {selection}: {option}"
        
        return None, f"Repository {target_url} not found in available options"
    
    def _extract_owner_repo(self, url: str) -> Optional[str]:
        """
        Extract owner/repo from a GitHub URL or string.
        
        Args:
            url: GitHub URL or repository string
            
        Returns:
            owner/repo string or None if not found
        """
        # Handle GitHub URLs
        github_match = re.search(r"github\.com[/:]([^/]+/[^/\s]+)", url)
        if github_match:
            return github_match.group(1).rstrip('.git')
        
        # Handle owner/repo format directly
        owner_repo_match = re.match(r"^([^/\s]+/[^/\s]+)$", url.strip())
        if owner_repo_match:
            return owner_repo_match.group(1)
        
        return None
    
    def _validate_repository_availability(self, repository_url: str) -> bool:
        """
        Validate that a repository is available in cache.
        
        Args:
            repository_url: Repository URL to validate
            
        Returns:
            True if repository is available in cache
        """
        if not self.redis_client:
            logger.warning("No Redis client available for repository validation")
            return False
        
        owner_repo = self._extract_owner_repo(repository_url)
        if not owner_repo:
            return False
        
        try:
            # Check if repository has any cached data
            summary_key = f"repo:{owner_repo}:summary"
            content_key = f"repo:{owner_repo}:content"
            
            has_summary = self.redis_client.exists(summary_key)
            has_content = self.redis_client.exists(content_key)
            
            is_available = has_summary or has_content
            
            logger.info("Repository availability check",
                       repository=repository_url,
                       owner_repo=owner_repo,
                       has_summary=bool(has_summary),
                       has_content=bool(has_content),
                       available=is_available)
            
            return is_available
            
        except Exception as e:
            logger.error("Failed to validate repository availability", 
                        repository=repository_url, error=str(e))
            return False
    
    def handle_repository_selection_failure(self, 
                                          error: Exception, 
                                          context: Dict[str, Any] = None) -> Tuple[str, str]:
        """
        Handle repository selection failures with fallback logic.
        
        Args:
            error: The error that occurred during selection
            context: Current context for fallback selection
            
        Returns:
            Tuple of (fallback_selection, reasoning)
        """
        logger.warning("Repository selection failed, using fallback", error=str(error))
        
        # Try to refresh cached repositories in case of stale data
        try:
            self._refresh_cached_repositories()
        except:
            pass
        
        # Use any available cached repository
        if self.cached_repositories:
            fallback_repo = self.cached_repositories[0]
            return fallback_repo.url, f"Fallback to first cached repository after error: {fallback_repo.url}"
        
        # Final fallback
        fallback_url = "https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh"
        return fallback_url, f"Final fallback repository after error: {fallback_url}"
    
    def get_cached_repositories(self) -> List[RepositoryInfo]:
        """
        Get list of cached repositories.
        
        Returns:
            List of RepositoryInfo objects
        """
        return self.cached_repositories.copy()
    
    def get_repository_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about cached repositories.
        
        Returns:
            Dictionary with repository statistics
        """
        total_repos = len(self.cached_repositories)
        cached_with_content = sum(1 for r in self.cached_repositories if r.cached)
        
        owners = set(r.owner for r in self.cached_repositories)
        
        return {
            "total_cached_repositories": total_repos,
            "repositories_with_content": cached_with_content,
            "unique_owners": len(owners),
            "cache_coverage": cached_with_content / total_repos if total_repos > 0 else 0.0
        }
    
    def refresh_cache(self):
        """Manually refresh the cached repositories list"""
        self._refresh_cached_repositories()
        logger.info("Repository cache manually refreshed")