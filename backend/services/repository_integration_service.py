"""
Repository Integration Service with GitIngest

Enhanced repository integration that builds on existing GitIngest implementation
with additional features for caching, validation, branch/commit info, and tier-based limits.
"""

import os
import time
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from urllib.parse import urlparse
import structlog

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..config.key_manager import key_manager
    from ..config.tier_config import get_tier_config_manager, TierConfiguration
    from ..integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
    from ..integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
    from ..services.redis_repo_manager import RedisRepoManager
    from ..services.repository_token_service import RepositoryTokenService
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from config.key_manager import key_manager
    from config.tier_config import get_tier_config_manager, TierConfiguration
    from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
    from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
    from services.redis_repo_manager import RedisRepoManager
    from services.repository_token_service import RepositoryTokenService

# Configure logging
logger = structlog.get_logger(__name__)


@dataclass
class RepositoryInfo:
    """Repository information with metadata."""
    url: str
    name: str
    owner: str
    repo: str
    branch: str
    default_branch: str
    size_tokens: int
    file_count: int
    languages: List[str]
    last_updated: datetime
    cached_at: datetime
    cache_expires_at: datetime
    is_private: bool
    access_tier_required: str
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    commit_date: Optional[datetime] = None


@dataclass
class BranchInfo:
    """Branch information."""
    name: str
    commit_sha: str
    commit_message: str
    commit_author: str
    commit_date: datetime
    is_default: bool


@dataclass
class RepositoryValidationResult:
    """Repository validation result."""
    is_valid: bool
    is_accessible: bool
    tier_allowed: bool
    size_within_limits: bool
    error_message: Optional[str] = None
    required_tier: Optional[str] = None
    actual_size: Optional[int] = None
    size_limit: Optional[int] = None


class RepositoryIntegrationService:
    """
    Enhanced Repository Integration Service with GitIngest
    
    Provides comprehensive repository integration with caching, validation,
    branch/commit information, and tier-based access control.
    """
    
    def __init__(self):
        """Initialize the repository integration service."""
        self.settings = get_settings()
        self.key_manager = key_manager
        self.redis_cache = SmartRedisCache()
        self.token_service = RepositoryTokenService()
        self.tier_manager = get_tier_config_manager()
        
        # Cache settings
        self.cache_ttl_hours = 24  # Repository info cache TTL
        self.branch_cache_ttl_hours = 6  # Branch info cache TTL
        
        logger.info("Initialized RepositoryIntegrationService")
    
    def fetch_repository(
        self, 
        repo_url: str, 
        branch: str = "main", 
        user_tier: str = "personal",
        username: Optional[str] = None,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Fetch repository using GitIngest with enhanced validation and caching.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            user_tier: User tier for access control
            username: Username for token retrieval
            force_refresh: Force refresh even if cached
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            logger.info(f"Fetching repository: {repo_url} (branch: {branch}, tier: {user_tier})")
            
            # Parse repository information
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return False, "Invalid repository URL format"
            
            # Check if repository is already cached and valid
            if not force_refresh:
                cached_info = self.get_repository_info(repo_url, branch)
                if cached_info and not self._is_cache_expired(cached_info):
                    logger.info(f"Repository {repo_name} found in cache and still valid")
                    return True, None
            
            # Validate tier access before fetching
            validation_result = self.validate_repository_access(
                repo_url, user_tier, username, branch
            )
            
            if not validation_result.tier_allowed:
                error_msg = f"Repository access denied for tier '{user_tier}': {validation_result.error_message}"
                logger.warning(error_msg)
                return False, error_msg
            
            # Create RedisRepoManager for the fetch operation
            repo_manager = RedisRepoManager(
                repo_url=repo_url,
                branch=branch,
                user_tier=user_tier,
                username=username
            )
            
            # Perform the fetch
            success = repo_manager.fetch_repository_with_auth(repo_url)
            
            if success:
                # Update repository metadata cache
                self._update_repository_cache(repo_url, branch, user_tier)
                logger.info(f"Successfully fetched and cached repository: {repo_name}")
                return True, None
            else:
                error_msg = f"Failed to fetch repository: {repo_name}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error fetching repository {repo_url}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def get_repository_info(
        self, 
        repo_url: str, 
        branch: str = "main"
    ) -> Optional[RepositoryInfo]:
        """
        Get comprehensive repository information.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            RepositoryInfo object or None if not found
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return None
            
            # Try to get from cache first
            cache_key = f"repo_info:{repo_name}:{branch}"
            cached_data = self.redis_cache.get(cache_key)
            
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    # Convert datetime strings back to datetime objects
                    for field in ['last_updated', 'cached_at', 'cache_expires_at', 'commit_date']:
                        if data.get(field):
                            data[field] = datetime.fromisoformat(data[field])
                    
                    return RepositoryInfo(**data)
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse cached repository info: {e}")
            
            # Get from Redis repository data
            repo_manager = RedisRepoManager(repo_url, branch)
            repo_data = repo_manager.get_repository_info()
            
            if not repo_data:
                return None
            
            # Get token count
            token_count = self.token_service.get_repository_token_count_with_fallback(
                repo_url, branch
            )
            
            # Get file list for language detection
            files = repo_manager.list_files()
            languages = self._detect_repository_languages(files)
            
            # Create repository info
            now = datetime.now()
            repo_info = RepositoryInfo(
                url=repo_url,
                name=repo_name,
                owner=repo_data.get('owner', ''),
                repo=repo_data.get('repo', ''),
                branch=branch,
                default_branch=branch,  # TODO: Get actual default branch
                size_tokens=token_count,
                file_count=repo_data.get('file_count', 0),
                languages=languages,
                last_updated=now,
                cached_at=now,
                cache_expires_at=now + timedelta(hours=self.cache_ttl_hours),
                is_private=self._is_likely_private_repo(repo_url),
                access_tier_required=self._determine_required_tier(token_count)
            )
            
            # Cache the result
            self._cache_repository_info(repo_info)
            
            return repo_info
            
        except Exception as e:
            logger.error(f"Error getting repository info for {repo_url}: {e}")
            return None
    
    def get_branch_info(
        self, 
        repo_url: str, 
        branch: str = "main"
    ) -> Optional[BranchInfo]:
        """
        Get branch information including commit details.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            BranchInfo object or None if not found
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return None
            
            # Try to get from cache first
            cache_key = f"branch_info:{repo_name}:{branch}"
            cached_data = self.redis_cache.get(cache_key)
            
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    if data.get('commit_date'):
                        data['commit_date'] = datetime.fromisoformat(data['commit_date'])
                    return BranchInfo(**data)
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse cached branch info: {e}")
            
            # For now, create basic branch info from repository data
            # In a full implementation, this would query GitHub API for actual branch info
            repo_manager = RedisRepoManager(repo_url, branch)
            repo_data = repo_manager.get_repository_info()
            
            if not repo_data:
                return None
            
            # Create basic branch info (would be enhanced with actual GitHub API calls)
            branch_info = BranchInfo(
                name=branch,
                commit_sha="unknown",  # Would get from GitHub API
                commit_message="Latest commit",  # Would get from GitHub API
                commit_author="unknown",  # Would get from GitHub API
                commit_date=datetime.now(),  # Would get from GitHub API
                is_default=(branch in ["main", "master"])
            )
            
            # Cache the result
            cache_data = asdict(branch_info)
            cache_data['commit_date'] = cache_data['commit_date'].isoformat()
            
            self.redis_cache.setex(
                cache_key,
                int(timedelta(hours=self.branch_cache_ttl_hours).total_seconds()),
                json.dumps(cache_data)
            )
            
            return branch_info
            
        except Exception as e:
            logger.error(f"Error getting branch info for {repo_url}:{branch}: {e}")
            return None
    
    def validate_repository_access(
        self,
        repo_url: str,
        user_tier: str,
        username: Optional[str] = None,
        branch: str = "main"
    ) -> RepositoryValidationResult:
        """
        Validate repository access based on tier limits and repository size.
        
        Args:
            repo_url: Repository URL
            user_tier: User tier
            username: Username for token retrieval
            branch: Branch name
            
        Returns:
            RepositoryValidationResult object
        """
        try:
            # Get tier configuration
            tier_config = self.tier_manager.get_tier_config(user_tier)
            if not tier_config:
                return RepositoryValidationResult(
                    is_valid=False,
                    is_accessible=False,
                    tier_allowed=False,
                    size_within_limits=False,
                    error_message=f"Invalid tier: {user_tier}"
                )
            
            # Check if repository URL is valid
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return RepositoryValidationResult(
                    is_valid=False,
                    is_accessible=False,
                    tier_allowed=False,
                    size_within_limits=False,
                    error_message="Invalid repository URL format"
                )
            
            # Get repository size
            token_count = self.token_service.get_repository_token_count_with_fallback(
                repo_url, branch
            )
            
            # Check size limits
            size_limit = tier_config.max_repository_tokens
            size_within_limits = (size_limit == -1) or (token_count <= size_limit)
            
            # Determine required tier for this repository
            required_tier = self._determine_required_tier(token_count)
            tier_allowed = self._is_tier_sufficient(user_tier, required_tier)
            
            # Check if repository is accessible (for private repos)
            is_accessible = True
            if self._is_likely_private_repo(repo_url) and username:
                # Check if user has GitHub token for private repo access
                token = self.key_manager.get_github_token(username)
                is_accessible = token is not None
            
            # Determine overall validity
            is_valid = size_within_limits and tier_allowed and is_accessible
            
            # Create error message if not valid
            error_message = None
            if not is_valid:
                if not size_within_limits:
                    error_message = f"Repository size ({token_count:,} tokens) exceeds tier limit ({size_limit:,} tokens)"
                elif not tier_allowed:
                    error_message = f"Repository requires '{required_tier}' tier or higher, but user has '{user_tier}' tier"
                elif not is_accessible:
                    error_message = "Repository appears to be private but no GitHub token available"
            
            return RepositoryValidationResult(
                is_valid=is_valid,
                is_accessible=is_accessible,
                tier_allowed=tier_allowed,
                size_within_limits=size_within_limits,
                error_message=error_message,
                required_tier=required_tier,
                actual_size=token_count,
                size_limit=size_limit if size_limit != -1 else None
            )
            
        except Exception as e:
            logger.error(f"Error validating repository access: {e}")
            return RepositoryValidationResult(
                is_valid=False,
                is_accessible=False,
                tier_allowed=False,
                size_within_limits=False,
                error_message=f"Validation error: {str(e)}"
            )
    
    def list_cached_repositories(self, user_tier: Optional[str] = None) -> List[RepositoryInfo]:
        """
        List all cached repositories, optionally filtered by tier access.
        
        Args:
            user_tier: Optional tier filter
            
        Returns:
            List of RepositoryInfo objects
        """
        try:
            # Get all repository info cache keys
            pattern = "repo_info:*"
            keys = self.redis_cache.keys(pattern)
            
            repositories = []
            for key in keys:
                try:
                    cached_data = self.redis_cache.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        # Convert datetime strings back to datetime objects
                        for field in ['last_updated', 'cached_at', 'cache_expires_at', 'commit_date']:
                            if data.get(field):
                                data[field] = datetime.fromisoformat(data[field])
                        
                        repo_info = RepositoryInfo(**data)
                        
                        # Filter by tier if specified
                        if user_tier:
                            if self._is_tier_sufficient(user_tier, repo_info.access_tier_required):
                                repositories.append(repo_info)
                        else:
                            repositories.append(repo_info)
                            
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse cached repository info from key {key}: {e}")
                    continue
            
            # Sort by last updated (most recent first)
            repositories.sort(key=lambda r: r.last_updated, reverse=True)
            
            return repositories
            
        except Exception as e:
            logger.error(f"Error listing cached repositories: {e}")
            return []
    
    def clear_repository_cache(self, repo_url: str, branch: str = "main") -> bool:
        """
        Clear cache for a specific repository.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            True if cache was cleared successfully
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return False
            
            # Clear repository info cache
            repo_info_key = f"repo_info:{repo_name}:{branch}"
            self.redis_cache.delete(repo_info_key)
            
            # Clear branch info cache
            branch_info_key = f"branch_info:{repo_name}:{branch}"
            self.redis_cache.delete(branch_info_key)
            
            # Clear RedisRepoManager caches
            repo_manager = RedisRepoManager(repo_url, branch)
            repo_manager._clear_caches()
            
            logger.info(f"Cleared cache for repository: {repo_name}:{branch}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing repository cache: {e}")
            return False
    
    def get_repository_size_info(self, repo_url: str, branch: str = "main") -> Dict[str, Any]:
        """
        Get detailed repository size information.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            Dictionary with size information
        """
        try:
            repo_name = self._extract_repo_name(repo_url)
            if not repo_name:
                return {}
            
            # Get token count
            token_count = self.token_service.get_repository_token_count_with_fallback(
                repo_url, branch
            )
            
            # Get file information
            repo_manager = RedisRepoManager(repo_url, branch)
            files = repo_manager.list_files()
            
            # Calculate size breakdown by language
            language_breakdown = {}
            total_file_size = 0
            
            for file_path in files:
                metadata = repo_manager.get_file_metadata(file_path)
                if metadata:
                    lang = metadata.language
                    if lang not in language_breakdown:
                        language_breakdown[lang] = {'files': 0, 'size': 0}
                    
                    language_breakdown[lang]['files'] += 1
                    language_breakdown[lang]['size'] += metadata.size
                    total_file_size += metadata.size
            
            # Determine tier requirements
            required_tier = self._determine_required_tier(token_count)
            
            return {
                'repository': repo_name,
                'branch': branch,
                'token_count': token_count,
                'file_count': len(files),
                'total_file_size_bytes': total_file_size,
                'language_breakdown': language_breakdown,
                'required_tier': required_tier,
                'tier_limits': {
                    'personal': self.tier_manager.get_tier_config('personal').max_repository_tokens,
                    'pro': self.tier_manager.get_tier_config('pro').max_repository_tokens,
                    'enterprise': self.tier_manager.get_tier_config('enterprise').max_repository_tokens
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting repository size info: {e}")
            return {}
    
    # Private helper methods
    
    def _extract_repo_name(self, repo_url: str) -> Optional[str]:
        """Extract repository name from URL."""
        try:
            # Handle SSH URLs like git@github.com:owner/repo.git
            if repo_url.startswith('git@'):
                if ':' in repo_url:
                    path_part = repo_url.split(':', 1)[1]
                    path_parts = [part for part in path_part.strip('/').split('/') if part]
                else:
                    return None
            else:
                # Handle HTTPS URLs
                path = urlparse(repo_url).path
                path_parts = [part for part in path.strip('/').split('/') if part]
            
            if len(path_parts) < 2:
                return None
            
            # Create full repo identifier with owner for uniqueness
            repo_name = path_parts[1].replace('.git', '')
            full_repo_name = f"{path_parts[0]}/{repo_name}"
            return full_repo_name
            
        except Exception:
            return None
    
    def _is_cache_expired(self, repo_info: RepositoryInfo) -> bool:
        """Check if repository cache is expired."""
        return datetime.now() > repo_info.cache_expires_at
    
    def _update_repository_cache(self, repo_url: str, branch: str, user_tier: str) -> None:
        """Update repository cache after successful fetch."""
        try:
            # This would be called after a successful fetch to update metadata
            repo_info = self.get_repository_info(repo_url, branch)
            if repo_info:
                self._cache_repository_info(repo_info)
        except Exception as e:
            logger.warning(f"Failed to update repository cache: {e}")
    
    def _cache_repository_info(self, repo_info: RepositoryInfo) -> None:
        """Cache repository information."""
        try:
            cache_key = f"repo_info:{repo_info.name}:{repo_info.branch}"
            
            # Convert to dict and handle datetime serialization
            data = asdict(repo_info)
            for field in ['last_updated', 'cached_at', 'cache_expires_at', 'commit_date']:
                if data.get(field):
                    data[field] = data[field].isoformat()
            
            # Cache with TTL
            ttl_seconds = int(timedelta(hours=self.cache_ttl_hours).total_seconds())
            self.redis_cache.setex(cache_key, ttl_seconds, json.dumps(data))
            
        except Exception as e:
            logger.warning(f"Failed to cache repository info: {e}")
    
    def _detect_repository_languages(self, files: List[str]) -> List[str]:
        """Detect programming languages in repository."""
        language_counts = {}
        
        for file_path in files:
            # Simple language detection based on file extension
            _, ext = os.path.splitext(file_path.lower())
            
            language_map = {
                '.py': 'Python',
                '.js': 'JavaScript',
                '.ts': 'TypeScript',
                '.java': 'Java',
                '.cpp': 'C++',
                '.c': 'C',
                '.go': 'Go',
                '.rs': 'Rust',
                '.rb': 'Ruby',
                '.php': 'PHP',
                '.cs': 'C#',
                '.swift': 'Swift',
                '.kt': 'Kotlin',
                '.scala': 'Scala',
                '.r': 'R',
                '.m': 'MATLAB',
                '.sh': 'Shell',
                '.html': 'HTML',
                '.css': 'CSS',
                '.scss': 'SCSS',
                '.json': 'JSON',
                '.yaml': 'YAML',
                '.yml': 'YAML',
                '.xml': 'XML',
                '.sql': 'SQL'
            }
            
            language = language_map.get(ext)
            if language:
                language_counts[language] = language_counts.get(language, 0) + 1
        
        # Return languages sorted by frequency
        return sorted(language_counts.keys(), key=lambda x: language_counts[x], reverse=True)
    
    def _is_likely_private_repo(self, repo_url: str) -> bool:
        """Determine if repository is likely private (simplified check)."""
        # In a full implementation, this would make an API call to check
        # For now, assume all repos might be private
        return True
    
    def _determine_required_tier(self, token_count: int) -> str:
        """Determine minimum tier required for repository size."""
        personal_limit = self.tier_manager.get_tier_config('personal').max_repository_tokens
        pro_limit = self.tier_manager.get_tier_config('pro').max_repository_tokens
        
        if token_count <= personal_limit:
            return 'personal'
        elif pro_limit == -1 or token_count <= pro_limit:
            return 'pro'
        else:
            return 'enterprise'
    
    def _is_tier_sufficient(self, user_tier: str, required_tier: str) -> bool:
        """Check if user tier is sufficient for required tier."""
        tier_hierarchy = ['personal', 'pro', 'enterprise']
        
        try:
            user_level = tier_hierarchy.index(user_tier)
            required_level = tier_hierarchy.index(required_tier)
            return user_level >= required_level
        except ValueError:
            return False


# Global instance for easy access
_repository_integration_service: Optional[RepositoryIntegrationService] = None


def get_repository_integration_service() -> RepositoryIntegrationService:
    """
    Get or create global RepositoryIntegrationService instance.
    
    Returns:
        RepositoryIntegrationService instance
    """
    global _repository_integration_service
    
    if _repository_integration_service is None:
        _repository_integration_service = RepositoryIntegrationService()
    
    return _repository_integration_service


def reset_repository_integration_service() -> None:
    """Reset global RepositoryIntegrationService instance (mainly for testing)."""
    global _repository_integration_service
    _repository_integration_service = None