"""
Repository token count service for tier validation.

This service fetches repository token counts from Redis where gitingest stores
the repository summary data, and provides it to the tier access control system.
"""

import json
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import structlog

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = structlog.get_logger(__name__)


class RepositoryTokenService:
    """
    Service to fetch repository token counts from Redis (gitingest data).
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize the repository token service.
        
        Args:
            redis_client: Optional Redis client. If None, creates a new one.
        """
        self.logger = structlog.get_logger(__name__)
        
        if redis_client:
            self.redis_client = redis_client
        elif REDIS_AVAILABLE:
            try:
                # Try to connect to Redis with default settings
                self.redis_client = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True
                )
                # Test connection
                self.redis_client.ping()
                self.logger.info("Connected to Redis for repository token service")
            except Exception as e:
                self.logger.warning(f"Failed to connect to Redis: {e}")
                self.redis_client = None
        else:
            self.logger.warning("Redis not available - repository token service disabled")
            self.redis_client = None
    
    def get_repository_token_count(
        self, 
        repository_url: str, 
        branch: str = "main"
    ) -> Optional[int]:
        """
        Get repository token count from Redis (gitingest summary).
        
        Args:
            repository_url: Repository URL (e.g., https://github.com/owner/repo)
            branch: Repository branch
            
        Returns:
            Token count if found, None otherwise
        """
        if not self.redis_client:
            self.logger.warning("Redis client not available for token count lookup")
            return None
        
        try:
            # Parse repository URL to get owner/repo
            repo_key = self._get_repository_key(repository_url, branch)
            if not repo_key:
                return None
            
            # Try different possible Redis key formats that gitingest might use
            possible_keys = [
                f"gitingest:summary:{repo_key}",
                f"gitingest:{repo_key}:summary",
                f"repo:summary:{repo_key}",
                f"summary:{repo_key}",
                repo_key
            ]
            
            for key in possible_keys:
                try:
                    # Try to get the summary data
                    summary_data = self.redis_client.get(key)
                    if summary_data:
                        # Parse JSON data
                        data = json.loads(summary_data)
                        
                        # Look for token count in various possible fields
                        token_count = self._extract_token_count(data)
                        if token_count is not None:
                            self.logger.info(
                                f"Found token count for {repository_url}:{branch} = {token_count:,} tokens"
                            )
                            return token_count
                        
                except (json.JSONDecodeError, TypeError) as e:
                    self.logger.debug(f"Failed to parse data from key {key}: {e}")
                    continue
                except Exception as e:
                    self.logger.debug(f"Error accessing key {key}: {e}")
                    continue
            
            self.logger.info(f"No token count found for {repository_url}:{branch}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting repository token count: {e}")
            return None
    
    def _get_repository_key(self, repository_url: str, branch: str) -> Optional[str]:
        """
        Extract repository key from URL for Redis lookup.
        
        Args:
            repository_url: Repository URL
            branch: Repository branch
            
        Returns:
            Repository key string or None if invalid URL
        """
        try:
            # Parse GitHub URL
            parsed = urlparse(repository_url)
            
            if parsed.netloc == "github.com":
                # Extract owner/repo from path
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    owner = path_parts[0]
                    repo = path_parts[1]
                    
                    # Remove .git suffix if present
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    
                    # Create repository key
                    repo_key = f"{owner}/{repo}:{branch}"
                    return repo_key
            
            # For non-GitHub URLs, try to extract a meaningful key
            if parsed.path:
                path_clean = parsed.path.strip("/").replace("/", "_")
                return f"{parsed.netloc}_{path_clean}:{branch}"
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing repository URL {repository_url}: {e}")
            return None
    
    def _extract_token_count(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Extract token count from gitingest summary data.
        
        Args:
            data: Parsed JSON data from Redis
            
        Returns:
            Token count if found, None otherwise
        """
        # Try different possible field names for token count
        token_fields = [
            "token_count",
            "tokens",
            "total_tokens",
            "estimated_tokens",
            "size_tokens",
            "content_tokens"
        ]
        
        for field in token_fields:
            if field in data:
                try:
                    token_count = int(data[field])
                    if token_count > 0:
                        return token_count
                except (ValueError, TypeError):
                    continue
        
        # Try nested structures
        if "summary" in data and isinstance(data["summary"], dict):
            for field in token_fields:
                if field in data["summary"]:
                    try:
                        token_count = int(data["summary"][field])
                        if token_count > 0:
                            return token_count
                    except (ValueError, TypeError):
                        continue
        
        # Try stats section
        if "stats" in data and isinstance(data["stats"], dict):
            for field in token_fields:
                if field in data["stats"]:
                    try:
                        token_count = int(data["stats"][field])
                        if token_count > 0:
                            return token_count
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    def estimate_token_count_fallback(self, repository_url: str) -> int:
        """
        Provide a fallback token count estimation when Redis data is not available.
        
        This is a conservative estimate to prevent blocking access when gitingest
        data is not available.
        
        Args:
            repository_url: Repository URL
            
        Returns:
            Estimated token count (conservative)
        """
        # Conservative fallback - assume medium-sized repository
        # This allows access while being conservative about resource usage
        fallback_tokens = 500000  # 500K tokens - reasonable for most repos
        
        self.logger.info(
            f"Using fallback token estimate for {repository_url}: {fallback_tokens:,} tokens"
        )
        
        return fallback_tokens
    
    def get_repository_token_count_with_fallback(
        self, 
        repository_url: str, 
        branch: str = "main"
    ) -> int:
        """
        Get repository token count with fallback estimation.
        
        Args:
            repository_url: Repository URL
            branch: Repository branch
            
        Returns:
            Token count (from Redis or fallback estimate)
        """
        # Try to get actual token count from Redis
        token_count = self.get_repository_token_count(repository_url, branch)
        
        if token_count is not None:
            return token_count
        
        # Use fallback estimation
        return self.estimate_token_count_fallback(repository_url)


# Global instance for easy access
_repository_token_service: Optional[RepositoryTokenService] = None


def get_repository_token_service() -> RepositoryTokenService:
    """
    Get or create global RepositoryTokenService instance.
    
    Returns:
        RepositoryTokenService instance
    """
    global _repository_token_service
    
    if _repository_token_service is None:
        _repository_token_service = RepositoryTokenService()
    
    return _repository_token_service


def reset_repository_token_service() -> None:
    """Reset global RepositoryTokenService instance (mainly for testing)."""
    global _repository_token_service
    _repository_token_service = None