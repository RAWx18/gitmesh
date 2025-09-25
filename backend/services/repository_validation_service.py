"""
Repository Validation Service

Provides repository validation functionality for chat and other services.
Includes size checks, access validation, and rate limit handling.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

try:
    # Try relative imports first (when used as module)
    from ..config.key_manager import key_manager
    from ..integrations.cosmos.v1.cosmos.repo_fetch import check_repository_size_for_chat, GitHubAPIError, RepositorySizeError
    from ..services.github_token_service import github_token_service, AuthStatus
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.key_manager import key_manager
    from integrations.cosmos.v1.cosmos.repo_fetch import check_repository_size_for_chat, GitHubAPIError, RepositorySizeError
    from services.github_token_service import github_token_service, AuthStatus

logger = logging.getLogger(__name__)


@dataclass
class RepositoryValidationResult:
    """Result of repository validation."""
    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    size_mb: Optional[float] = None
    size_kb: Optional[int] = None
    should_block_chat: bool = False
    user_message: Optional[str] = None


class RepositoryValidationService:
    """Service for validating repositories before processing."""
    
    def __init__(self):
        self.key_manager = key_manager
        self.max_size_mb = 150  # Default 150MB limit
        self._blocked_repos_cache = {}  # Cache for blocked repositories to avoid repeated API calls
        self._session_validation_cache = {}  # Cache for session-based validation to avoid repeated checks
    
    async def validate_repository_for_chat(self, repo_url: str, user_id: Optional[str] = None) -> RepositoryValidationResult:
        """
        Validate repository for chat functionality using enhanced GitHub token service.
        
        Args:
            repo_url: GitHub repository URL
            user_id: User ID for token retrieval
            
        Returns:
            RepositoryValidationResult with validation details
        """
        try:
            # Check if repository is already known to be blocked (cache for 1 hour)
            import time
            cache_key = repo_url.lower()
            current_time = time.time()
            
            if cache_key in self._blocked_repos_cache:
                cached_result, cache_time = self._blocked_repos_cache[cache_key]
                # Cache for 1 hour (3600 seconds)
                if current_time - cache_time < 3600:
                    logger.info(f"Repository {repo_url} found in blocked cache, returning cached result")
                    return cached_result
                else:
                    # Cache expired, remove it
                    del self._blocked_repos_cache[cache_key]
            
            # Get GitHub token using the enhanced token service
            github_token = None
            token_source = "none"
            
            if user_id:
                try:
                    # Use the enhanced GitHub token service
                    token_obj = await github_token_service.get_best_available_token(user_id)
                    if token_obj:
                        github_token = token_obj.token
                        token_source = token_obj.source
                        logger.info(f"Using GitHub token from {token_source} for user {user_id}")
                    else:
                        logger.info(f"No GitHub token available for user {user_id}")
                except Exception as e:
                    logger.error(f"Error retrieving GitHub token for user {user_id}: {e}")
            
            # Final fallback to environment variable if no token from service
            if not github_token:
                env_token = os.getenv('GITHUB_TOKEN')
                if env_token and env_token.strip() and not env_token.startswith('your_github') and len(env_token.strip()) > 10:
                    github_token = env_token
                    token_source = "environment_fallback"
                    logger.info("Using GitHub token from environment variable as final fallback")
                else:
                    logger.warning("No valid GitHub token available - using public API limits")
            
            # Check repository size
            try:
                size_allowed, size_message, repo_size_kb = check_repository_size_for_chat(
                    repo_url, github_token, self.max_size_mb
                )
                
                size_mb = repo_size_kb / 1024 if repo_size_kb else None
                
                if not size_allowed:
                    # Repository is too large or has access issues
                    if "exceeds the maximum allowed size" in size_message:
                        result = RepositoryValidationResult(
                            is_valid=False,
                            error_type="repository_too_large",
                            error_message=size_message,
                            size_mb=size_mb,
                            size_kb=repo_size_kb,
                            should_block_chat=True,
                            user_message=f"🚫 **Repository Too Large**\n\n{size_message}\n\nPlease try with a smaller repository (under {self.max_size_mb}MB) or upgrade your plan for larger repository support."
                        )
                        # Cache the blocked result
                        self._blocked_repos_cache[cache_key] = (result, current_time)
                        return result
                    elif "rate limit" in size_message.lower():
                        # Provide different messages based on token source
                        if token_source == "user":
                            user_message = "🚫 **GitHub API Rate Limit Exceeded**\n\nYour GitHub token has reached its rate limit. Please:\n\n1. Wait for the rate limit to reset (usually within an hour)\n2. Try again later\n3. Contact support if this persists\n\nYour authenticated token provides higher rate limits, but they can still be exceeded with heavy usage."
                        elif token_source in ["environment", "environment_fallback"]:
                            user_message = "🚫 **GitHub API Rate Limit Exceeded**\n\nThe system's GitHub token has reached its rate limit. Please:\n\n1. Wait a few minutes and try again\n2. Add your personal GitHub token in settings for higher rate limits\n3. Try with a different repository\n\nPersonal tokens provide much higher rate limits than shared system tokens."
                        else:
                            user_message = "🚫 **GitHub API Rate Limit Exceeded**\n\nWe cannot verify the repository size due to GitHub API rate limits. Please:\n\n1. Add a GitHub token in your settings for higher rate limits\n2. Wait a few minutes and try again\n3. Try with a different repository\n\nAuthenticated users get much higher rate limits (5000 vs 60 requests per hour)."
                        
                        result = RepositoryValidationResult(
                            is_valid=False,
                            error_type="github_rate_limit",
                            error_message=f"{size_message} (using {token_source} token)",
                            should_block_chat=True,
                            user_message=user_message
                        )
                        # Cache rate limit errors for shorter time (15 minutes)
                        self._blocked_repos_cache[cache_key] = (result, current_time - 2700)  # Cache for 15 minutes
                        return result
                    elif "not found" in size_message.lower():
                        return RepositoryValidationResult(
                            is_valid=False,
                            error_type="repository_not_found",
                            error_message=size_message,
                            should_block_chat=True,
                            user_message="🚫 **Repository Not Found**\n\nThe repository could not be found or is not accessible. Please check:\n\n1. The repository URL is correct\n2. The repository is public, or you have access to it\n3. Add a GitHub token in your settings if it's a private repository"
                        )
                    else:
                        return RepositoryValidationResult(
                            is_valid=False,
                            error_type="repository_access_denied",
                            error_message=size_message,
                            should_block_chat=True,
                            user_message="🚫 **Repository Access Denied**\n\nCannot access the repository. This may be because:\n\n1. The repository is private and requires authentication\n2. You don't have permission to access it\n3. Add a GitHub token in your settings for private repositories"
                        )
                
                # Repository size check passed
                return RepositoryValidationResult(
                    is_valid=True,
                    size_mb=size_mb,
                    size_kb=repo_size_kb,
                    should_block_chat=False,
                    user_message=None
                )
                
            except GitHubAPIError as e:
                logger.error(f"GitHub API error during repository validation: {e}")
                return RepositoryValidationResult(
                    is_valid=False,
                    error_type="github_api_error",
                    error_message=str(e),
                    should_block_chat=True,
                    user_message="🚫 **GitHub API Error**\n\nWe encountered an error while checking the repository. This could be due to:\n\n1. GitHub API rate limits\n2. Network connectivity issues\n3. Repository access restrictions\n\nPlease try again in a few minutes or add a GitHub token in your settings for better reliability."
                )
            
            except RepositorySizeError as e:
                logger.error(f"Repository size error: {e}")
                return RepositoryValidationResult(
                    is_valid=False,
                    error_type="repository_size_error",
                    error_message=str(e),
                    should_block_chat=True,
                    user_message=f"🚫 **Repository Too Large**\n\n{str(e)}\n\nPlease try with a smaller repository (under {self.max_size_mb}MB) or upgrade your plan for larger repository support."
                )
            
            except Exception as e:
                logger.error(f"Unexpected error during repository validation: {e}")
                return RepositoryValidationResult(
                    is_valid=False,
                    error_type="validation_error",
                    error_message=str(e),
                    should_block_chat=True,
                    user_message="🚫 **Repository Validation Error**\n\nWe encountered an unexpected error while validating the repository. Please try again or contact support if the issue persists."
                )
        
        except Exception as e:
            logger.error(f"Critical error in repository validation: {e}")
            return RepositoryValidationResult(
                is_valid=False,
                error_type="critical_error",
                error_message=str(e),
                should_block_chat=True,
                user_message="🚫 **System Error**\n\nA critical error occurred during repository validation. Please try again or contact support."
            )
    
    def set_max_size_mb(self, max_size_mb: int):
        """Set the maximum repository size in MB."""
        self.max_size_mb = max_size_mb
        logger.info(f"Repository size limit set to {max_size_mb}MB")
    
    def clear_blocked_cache(self, repo_url: Optional[str] = None):
        """Clear the blocked repositories cache."""
        if repo_url:
            cache_key = repo_url.lower()
            if cache_key in self._blocked_repos_cache:
                del self._blocked_repos_cache[cache_key]
                logger.info(f"Cleared cache for repository: {repo_url}")
        else:
            self._blocked_repos_cache.clear()
            logger.info("Cleared all blocked repositories cache")
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get current cache status for monitoring."""
        import time
        current_time = time.time()
        active_entries = 0
        expired_entries = 0
        
        for cache_key, (result, cache_time) in self._blocked_repos_cache.items():
            if current_time - cache_time < 3600:
                active_entries += 1
            else:
                expired_entries += 1
        
        return {
            "total_entries": len(self._blocked_repos_cache),
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "max_size_mb": self.max_size_mb
        }


# Global instance
repository_validation_service = RepositoryValidationService()