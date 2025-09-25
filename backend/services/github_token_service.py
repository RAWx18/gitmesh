"""
Enhanced GitHub Token Service

Provides centralized GitHub token management with proper KeyManager integration,
token validation, refresh logic, and comprehensive error handling.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import requests
import time

try:
    from ..config.key_manager import key_manager
except ImportError:
    from config.key_manager import key_manager

logger = logging.getLogger(__name__)


class AuthStatus(Enum):
    """Authentication status enumeration."""
    AUTHENTICATED = "authenticated"
    NO_TOKEN = "no_token"
    INVALID_TOKEN = "invalid_token"
    EXPIRED_TOKEN = "expired_token"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    FALLBACK_TOKEN = "fallback_token"
    KEYMANAGER_ERROR = "keymanager_error"


@dataclass
class GitHubToken:
    """GitHub token data structure."""
    token: str
    user_id: str
    expires_at: Optional[datetime] = None
    scopes: List[str] = None
    is_valid: bool = True
    last_validated: datetime = None
    source: str = "user"  # "user", "environment", "fallback"
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []
        if self.last_validated is None:
            self.last_validated = datetime.now()


@dataclass
class TokenValidationResult:
    """Result of token validation."""
    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None
    scopes: List[str] = None
    user_login: Optional[str] = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = []


@dataclass
class UserContext:
    """User authentication context."""
    user_id: str
    github_token: Optional[GitHubToken] = None
    auth_status: AuthStatus = AuthStatus.NO_TOKEN
    permissions: List[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


class GitHubTokenService:
    """Enhanced GitHub token service with KeyManager integration."""
    
    def __init__(self):
        self.key_manager = key_manager
        self._token_cache = {}  # In-memory cache for validated tokens
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._validation_cache = {}  # Cache for token validation results
        
    async def get_user_token(self, user_id: str) -> Optional[GitHubToken]:
        """
        Get GitHub token for a user with proper error handling.
        
        Args:
            user_id: User ID to get token for
            
        Returns:
            GitHubToken if available, None otherwise
        """
        if not user_id:
            logger.warning("No user_id provided for token retrieval")
            return None
            
        # Check cache first
        cache_key = f"token:{user_id}"
        if cache_key in self._token_cache:
            cached_token, cache_time = self._token_cache[cache_key]
            if time.time() - cache_time < self._cache_ttl:
                logger.info(f"Using cached GitHub token for user {user_id}")
                return cached_token
            else:
                # Cache expired, remove it
                del self._token_cache[cache_key]
        
        try:
            # Try to get GitHub token from KeyManager
            logger.info(f"Attempting to retrieve GitHub token for user {user_id}")
            
            # First try the dedicated get_github_token method
            token_value = self.key_manager.get_github_token(user_id)
            
            if not token_value:
                # Try alternative method
                logger.info(f"No token from get_github_token, trying get_key for user {user_id}")
                token_value = self.key_manager.get_key(user_id, 'github_token')
            
            if token_value and token_value.strip():
                logger.info(f"Successfully retrieved GitHub token from KeyManager for user {user_id}")
                
                # Create GitHubToken object
                github_token = GitHubToken(
                    token=token_value,
                    user_id=user_id,
                    source="user",
                    last_validated=datetime.now()
                )
                
                # Cache the token
                self._token_cache[cache_key] = (github_token, time.time())
                
                return github_token
            else:
                logger.info(f"No GitHub token found in KeyManager for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving GitHub token for user {user_id}: {e}")
            return None
    
    async def validate_token(self, token: str) -> TokenValidationResult:
        """
        Validate a GitHub token by making an API call.
        
        Args:
            token: GitHub token to validate
            
        Returns:
            TokenValidationResult with validation details
        """
        if not token or not token.strip():
            return TokenValidationResult(
                is_valid=False,
                error_type="empty_token",
                error_message="Token is empty or None"
            )
        
        # Check validation cache
        token_hash = hash(token)
        cache_key = f"validation:{token_hash}"
        if cache_key in self._validation_cache:
            cached_result, cache_time = self._validation_cache[cache_key]
            if time.time() - cache_time < 60:  # Cache validation for 1 minute
                return cached_result
        
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'GitHubTokenService/1.0'
            }
            
            # Make a simple API call to validate the token
            response = requests.get(
                'https://api.github.com/user',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user_data = response.json()
                
                # Get rate limit info
                rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
                rate_limit_reset = None
                if 'X-RateLimit-Reset' in response.headers:
                    reset_timestamp = int(response.headers['X-RateLimit-Reset'])
                    rate_limit_reset = datetime.fromtimestamp(reset_timestamp)
                
                # Get token scopes
                scopes = response.headers.get('X-OAuth-Scopes', '').split(', ') if response.headers.get('X-OAuth-Scopes') else []
                
                result = TokenValidationResult(
                    is_valid=True,
                    rate_limit_remaining=rate_limit_remaining,
                    rate_limit_reset=rate_limit_reset,
                    scopes=scopes,
                    user_login=user_data.get('login')
                )
                
                # Cache the result
                self._validation_cache[cache_key] = (result, time.time())
                
                logger.info(f"Token validation successful for user {user_data.get('login')}, rate limit: {rate_limit_remaining}")
                return result
                
            elif response.status_code == 401:
                result = TokenValidationResult(
                    is_valid=False,
                    error_type="invalid_token",
                    error_message="Token is invalid or expired"
                )
                self._validation_cache[cache_key] = (result, time.time())
                return result
                
            elif response.status_code == 403:
                # Check if it's a rate limit issue
                if 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                    rate_limit_reset = None
                    if 'X-RateLimit-Reset' in response.headers:
                        reset_timestamp = int(response.headers['X-RateLimit-Reset'])
                        rate_limit_reset = datetime.fromtimestamp(reset_timestamp)
                    
                    result = TokenValidationResult(
                        is_valid=False,
                        error_type="rate_limit_exceeded",
                        error_message="GitHub API rate limit exceeded",
                        rate_limit_remaining=0,
                        rate_limit_reset=rate_limit_reset
                    )
                else:
                    result = TokenValidationResult(
                        is_valid=False,
                        error_type="insufficient_permissions",
                        error_message="Token has insufficient permissions"
                    )
                
                self._validation_cache[cache_key] = (result, time.time())
                return result
                
            else:
                result = TokenValidationResult(
                    is_valid=False,
                    error_type="api_error",
                    error_message=f"GitHub API returned status {response.status_code}"
                )
                return result
                
        except requests.exceptions.Timeout:
            return TokenValidationResult(
                is_valid=False,
                error_type="timeout",
                error_message="GitHub API request timed out"
            )
        except requests.exceptions.RequestException as e:
            return TokenValidationResult(
                is_valid=False,
                error_type="network_error",
                error_message=f"Network error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error validating token: {e}")
            return TokenValidationResult(
                is_valid=False,
                error_type="validation_error",
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def get_fallback_token(self) -> Optional[str]:
        """
        Get fallback GitHub token from environment variables.
        
        Returns:
            Environment GitHub token if available and valid
        """
        env_token = os.getenv('GITHUB_TOKEN')
        if env_token and env_token.strip() and not env_token.startswith('your_github') and len(env_token.strip()) > 10:
            logger.info("Using GitHub token from environment variable as fallback")
            return env_token.strip()
        else:
            logger.info("No valid fallback GitHub token available in environment")
            return None
    
    async def get_token_status(self, user_id: str) -> AuthStatus:
        """
        Get authentication status for a user.
        
        Args:
            user_id: User ID to check status for
            
        Returns:
            AuthStatus indicating the user's authentication state
        """
        try:
            # Try to get user token
            user_token = await self.get_user_token(user_id)
            
            if user_token:
                # Validate the token
                validation_result = await self.validate_token(user_token.token)
                
                if validation_result.is_valid:
                    return AuthStatus.AUTHENTICATED
                elif validation_result.error_type == "invalid_token":
                    return AuthStatus.INVALID_TOKEN
                elif validation_result.error_type == "rate_limit_exceeded":
                    return AuthStatus.AUTHENTICATED  # Token is valid, just rate limited
                elif validation_result.error_type == "insufficient_permissions":
                    return AuthStatus.INSUFFICIENT_PERMISSIONS
                else:
                    return AuthStatus.INVALID_TOKEN
            else:
                # Check if fallback token is available
                fallback_token = self.get_fallback_token()
                if fallback_token:
                    return AuthStatus.FALLBACK_TOKEN
                else:
                    return AuthStatus.NO_TOKEN
                    
        except Exception as e:
            logger.error(f"Error getting token status for user {user_id}: {e}")
            return AuthStatus.KEYMANAGER_ERROR
    
    async def get_user_context(self, user_id: str) -> UserContext:
        """
        Get complete user authentication context.
        
        Args:
            user_id: User ID to get context for
            
        Returns:
            UserContext with authentication details
        """
        try:
            # Get user token
            user_token = await self.get_user_token(user_id)
            auth_status = await self.get_token_status(user_id)
            
            # Determine permissions based on token and status
            permissions = []
            if user_token and auth_status == AuthStatus.AUTHENTICATED:
                # Validate token to get scopes
                validation_result = await self.validate_token(user_token.token)
                if validation_result.is_valid:
                    permissions = validation_result.scopes
            
            return UserContext(
                user_id=user_id,
                github_token=user_token,
                auth_status=auth_status,
                permissions=permissions
            )
            
        except Exception as e:
            logger.error(f"Error getting user context for {user_id}: {e}")
            return UserContext(
                user_id=user_id,
                auth_status=AuthStatus.KEYMANAGER_ERROR
            )
    
    async def get_best_available_token(self, user_id: str) -> Optional[GitHubToken]:
        """
        Get the best available token for a user (user token first, then fallback).
        
        Args:
            user_id: User ID to get token for
            
        Returns:
            Best available GitHubToken or None
        """
        # Try user token first
        user_token = await self.get_user_token(user_id)
        if user_token:
            # Validate the token
            validation_result = await self.validate_token(user_token.token)
            if validation_result.is_valid:
                logger.info(f"Using user's GitHub token for {user_id}")
                return user_token
            else:
                logger.warning(f"User token invalid for {user_id}: {validation_result.error_message}")
        
        # Fall back to environment token
        fallback_token = self.get_fallback_token()
        if fallback_token:
            logger.info(f"Using fallback GitHub token for {user_id}")
            return GitHubToken(
                token=fallback_token,
                user_id=user_id,
                source="environment",
                last_validated=datetime.now()
            )
        
        logger.warning(f"No GitHub token available for {user_id}")
        return None
    
    def clear_cache(self, user_id: Optional[str] = None):
        """
        Clear token cache for a specific user or all users.
        
        Args:
            user_id: User ID to clear cache for, or None to clear all
        """
        if user_id:
            cache_key = f"token:{user_id}"
            if cache_key in self._token_cache:
                del self._token_cache[cache_key]
                logger.info(f"Cleared token cache for user {user_id}")
        else:
            self._token_cache.clear()
            self._validation_cache.clear()
            logger.info("Cleared all token caches")


# Global instance
github_token_service = GitHubTokenService()