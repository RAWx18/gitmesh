"""
Tier-based access control service for web chat integration.

This service integrates the existing tier management system with web chat functionality,
providing repository size validation, model access restrictions, and rate limiting.
"""

import os
import logging
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import structlog
import redis
import json

# Import existing tier management components
try:
    from integrations.cosmos.v1.cosmos.tier_manager import TierManager, TierValidationError, get_tier_manager
    from integrations.cosmos.v1.cosmos.tier_access_control import TierAccessController as BaseTierAccessController
    TIER_SYSTEM_AVAILABLE = True
except ImportError:
    TIER_SYSTEM_AVAILABLE = False
    TierManager = None
    TierValidationError = Exception
    BaseTierAccessController = object

# Import existing rate limiting
from utils.auth_utils import rate_limit_manager
from models.api.auth_models import User
from services.repository_token_service import get_repository_token_service
from config.tier_config import get_tier_config_manager, TierConfiguration

logger = structlog.get_logger(__name__)


class TierLevel(Enum):
    """Supported tier levels for web chat."""
    PERSONAL = "personal"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class TierLimits:
    """Tier-specific limits for web chat functionality."""
    max_repository_size_mb: int = None  # For backward compatibility, but will represent tokens
    max_repository_tokens: int = None  # New field for token-based limits
    max_requests_per_month: int = None  # Monthly request limit
    max_requests_per_hour: int = None  # Hourly request limit (derived from monthly)
    max_context_files: int = 10
    allowed_models: List[str] = None
    max_session_duration_hours: int = 2
    max_concurrent_sessions: int = 1
    
    def __post_init__(self):
        """Initialize derived fields after object creation."""
        # Set token limit from MB field for backward compatibility
        if self.max_repository_tokens is None:
            self.max_repository_tokens = self.max_repository_size_mb
        
        # Set default values for None fields
        if self.allowed_models is None:
            self.allowed_models = ["gpt-4o-mini"]
        
        # Calculate hourly limit from monthly if not set
        if self.max_requests_per_hour is None and self.max_requests_per_month is not None:
            # Approximate: monthly / 30 days / 24 hours
            self.max_requests_per_hour = max(1, self.max_requests_per_month // (30 * 24))


@dataclass
class AccessValidationResult:
    """Result of tier access validation."""
    allowed: bool
    message: str
    tier: str
    limits: Optional[TierLimits] = None
    usage: Optional[Dict[str, Any]] = None
    retry_after: Optional[int] = None


class WebTierAccessController:
    """
    Web-specific tier access controller that integrates with existing tier management.
    
    Provides repository size validation, model access restrictions, and rate limiting
    specifically designed for web chat functionality.
    """
    
    # Default tier limits for web chat (easily configurable)
    # Note: Repository size is in tokens (from gitingest), requests are converted from monthly to hourly
    DEFAULT_TIER_LIMITS = {
        TierLevel.PERSONAL.value: TierLimits(
            max_repository_size_mb=1000000,  # 1M tokens (personal plan)
            max_repository_tokens=1000000,
            max_requests_per_month=500,
            max_requests_per_hour=1,  # Derived from monthly
            max_context_files=10,
            allowed_models=["gpt-4o-mini", "claude-3-haiku"],
            max_session_duration_hours=2,
            max_concurrent_sessions=1
        ),
        TierLevel.PRO.value: TierLimits(
            max_repository_size_mb=10000000,  # 10M tokens (pro plan)
            max_repository_tokens=10000000,
            max_requests_per_month=2000,
            max_requests_per_hour=3,  # Derived from monthly
            max_context_files=50,
            allowed_models=["gpt-4o-mini", "gpt-4o", "claude-3-haiku", "claude-3-sonnet"],
            max_session_duration_hours=8,
            max_concurrent_sessions=3
        ),
        TierLevel.ENTERPRISE.value: TierLimits(
            max_repository_size_mb=-1,  # Custom/Unlimited (configurable per customer)
            max_repository_tokens=-1,
            max_requests_per_month=3000,
            max_requests_per_hour=-1,  # Unlimited
            max_context_files=200,
            allowed_models=["*"],  # All models
            max_session_duration_hours=24,
            max_concurrent_sessions=10
        )
    }
    
    def __init__(self, tier_manager: Optional[TierManager] = None):
        """
        Initialize WebTierAccessController.
        
        Args:
            tier_manager: Optional TierManager instance. If None, uses global instance.
        """
        self.logger = structlog.get_logger(__name__)
        
        # Initialize tier manager if available
        if TIER_SYSTEM_AVAILABLE and tier_manager is None:
            try:
                self.tier_manager = get_tier_manager()
                self.base_controller = BaseTierAccessController(self.tier_manager)
            except Exception as e:
                self.logger.warning(f"Failed to initialize tier manager: {e}")
                self.tier_manager = None
                self.base_controller = None
        else:
            self.tier_manager = tier_manager
            self.base_controller = BaseTierAccessController(tier_manager) if tier_manager else None
        
        # Initialize tier configuration manager
        self.tier_config_manager = get_tier_config_manager()
        
        # Load tier limits from configuration
        self.tier_limits = self._load_tier_limits_from_config()
        
        # Track active sessions for concurrent session limits
        self.active_sessions: Dict[str, List[Dict[str, Any]]] = {}
        
        # Initialize Redis connection for gitingest data
        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
        except Exception as e:
            self.logger.warning(f"Failed to initialize Redis client: {e}")
            self.redis_client = None
    
    def _load_tier_limits_from_config(self) -> Dict[str, TierLimits]:
        """Load tier limits from the new tier configuration system."""
        limits = {}
        
        for tier_name, tier_config in self.tier_config_manager.get_all_tiers().items():
            limits[tier_name] = TierLimits(
                max_repository_size_mb=tier_config.max_repository_tokens,  # For backward compatibility
                max_repository_tokens=tier_config.max_repository_tokens,
                max_requests_per_month=tier_config.max_requests_per_month,
                max_requests_per_hour=tier_config.max_requests_per_hour,
                max_context_files=tier_config.max_context_files,
                allowed_models=tier_config.allowed_models,
                max_session_duration_hours=tier_config.max_session_duration_hours,
                max_concurrent_sessions=tier_config.max_concurrent_sessions
            )
        
        return limits
    
    def _load_tier_limits_legacy(self) -> Dict[str, TierLimits]:
        """Load tier limits from environment variables or use defaults."""
        limits = {}
        
        for tier_name, default_limits in self.DEFAULT_TIER_LIMITS.items():
            # Try to load from environment
            env_prefix = f"TIER_{tier_name.upper()}_"
            
            limits[tier_name] = TierLimits(
                max_repository_tokens=int(os.getenv(
                    f"{env_prefix}MAX_REPO_SIZE_TOKENS", 
                    default_limits.max_repository_tokens
                )),
                max_requests_per_hour=int(os.getenv(
                    f"{env_prefix}MAX_REQUESTS_PER_HOUR", 
                    default_limits.max_requests_per_hour
                )),
                max_context_files=int(os.getenv(
                    f"{env_prefix}MAX_CONTEXT_FILES", 
                    default_limits.max_context_files
                )),
                allowed_models=os.getenv(
                    f"{env_prefix}ALLOWED_MODELS", 
                    ",".join(default_limits.allowed_models)
                ).split(","),
                max_session_duration_hours=int(os.getenv(
                    f"{env_prefix}MAX_SESSION_DURATION_HOURS", 
                    default_limits.max_session_duration_hours
                )),
                max_concurrent_sessions=int(os.getenv(
                    f"{env_prefix}MAX_CONCURRENT_SESSIONS", 
                    default_limits.max_concurrent_sessions
                ))
            )
        
        return limits
    
    def validate_repository_access(
        self, 
        user: User, 
        repository_url: str, 
        repository_size_tokens: int,
        branch: str = "main"
    ) -> AccessValidationResult:
        """
        Validate repository access based on user tier and repository token count.
        
        Args:
            user: Authenticated user
            repository_url: URL of the repository
            repository_size_tokens: Repository size in tokens (from gitingest summary)
            branch: Repository branch
            
        Returns:
            AccessValidationResult with validation details
        """
        try:
            # Get user tier
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return AccessValidationResult(
                    allowed=False,
                    message=f"Invalid tier: {user_tier}",
                    tier=user_tier
                )
            
            # Check repository token limit (our new system takes precedence)
            if tier_limits.max_repository_tokens != -1 and repository_size_tokens > tier_limits.max_repository_tokens:
                return AccessValidationResult(
                    allowed=False,
                    message=(
                        f"Repository size ({repository_size_tokens:,} tokens) exceeds your "
                        f"{user_tier} tier limit ({tier_limits.max_repository_tokens:,} tokens). "
                        f"Please upgrade your plan to access larger repositories."
                    ),
                    tier=user_tier,
                    limits=tier_limits
                )
            
            # If our new system allows it (unlimited or within limits), grant access
            # We skip the base controller validation for unlimited tiers or when our limits are more permissive
            if tier_limits.max_repository_tokens == -1:
                # Unlimited access for this tier
                return AccessValidationResult(
                    allowed=True,
                    message=f"Access granted for {user_tier} tier (unlimited repository size)",
                    tier=user_tier,
                    limits=tier_limits
                )
            
            # Use base tier controller if available for additional validation (only for limited tiers)
            if self.base_controller and TIER_SYSTEM_AVAILABLE:
                try:
                    # Map new tier names to old tier names for base controller compatibility
                    legacy_tier_map = {
                        "personal": "free",
                        "pro": "pro", 
                        "enterprise": "enterprise"
                    }
                    legacy_tier = legacy_tier_map.get(user_tier, user_tier)
                    
                    # Use the actual token count from gitingest
                    is_allowed, message, details = self.base_controller.validate_repository_access(
                        repository_url=repository_url,
                        estimated_tokens=repository_size_tokens,
                        user_tier=legacy_tier,
                        user_id=str(user.id)
                    )
                    
                    # Only deny if base controller denies AND our system also has limits
                    if not is_allowed and tier_limits.max_repository_tokens != -1:
                        return AccessValidationResult(
                            allowed=False,
                            message=message,
                            tier=user_tier,
                            limits=tier_limits,
                            usage=details
                        )
                except Exception as e:
                    self.logger.warning(f"Base tier controller validation failed: {e}")
            
            # All validations passed
            return AccessValidationResult(
                allowed=True,
                message=f"Access granted for {user_tier} tier",
                tier=user_tier,
                limits=tier_limits
            )
            
        except Exception as e:
            self.logger.error(f"Repository access validation failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Access validation failed due to system error",
                tier="unknown"
            )
    
    def validate_repository_access_from_url(
        self, 
        user: User, 
        repository_url: str,
        branch: str = "main",
        fallback_on_missing: bool = True
    ) -> AccessValidationResult:
        """
        Validate repository access by fetching token count from Redis (gitingest data).
        
        This is the main method that should be used for repository validation as it
        automatically fetches the token count from the gitingest summary stored in Redis.
        
        Args:
            user: Authenticated user
            repository_url: URL of the repository
            branch: Repository branch
            fallback_on_missing: Whether to use fallback estimation if Redis data is missing
            
        Returns:
            AccessValidationResult with validation details
        """
        try:
            # Get token count from Redis (gitingest summary)
            if fallback_on_missing:
                repository_size_tokens = self.token_service.get_repository_token_count_with_fallback(
                    repository_url, branch
                )
            else:
                repository_size_tokens = self.token_service.get_repository_token_count(
                    repository_url, branch
                )
                
                if repository_size_tokens is None:
                    return AccessValidationResult(
                        allowed=False,
                        message="Repository size information not available. Please try again later.",
                        tier=self._get_user_tier(user)
                    )
            
            # Use the main validation method with the fetched token count
            return self.validate_repository_access(
                user=user,
                repository_url=repository_url,
                repository_size_tokens=repository_size_tokens,
                branch=branch
            )
            
        except Exception as e:
            self.logger.error(f"Repository access validation from URL failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Repository access validation failed due to system error",
                tier="unknown"
            )
    
    def validate_model_access(self, user: User, model_name: str) -> AccessValidationResult:
        """
        Validate model access based on user tier.
        
        Args:
            user: Authenticated user
            model_name: Name of the AI model
            
        Returns:
            AccessValidationResult with validation details
        """
        try:
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return AccessValidationResult(
                    allowed=False,
                    message=f"Invalid tier: {user_tier}",
                    tier=user_tier
                )
            
            # Check if model is allowed for this tier
            allowed_models = tier_limits.allowed_models
            
            # Enterprise tier has access to all models
            if "*" in allowed_models:
                return AccessValidationResult(
                    allowed=True,
                    message=f"Model access granted for {user_tier} tier",
                    tier=user_tier,
                    limits=tier_limits
                )
            
            # Check specific model access
            if model_name not in allowed_models:
                return AccessValidationResult(
                    allowed=False,
                    message=(
                        f"Model '{model_name}' is not available for your {user_tier} tier. "
                        f"Available models: {', '.join(allowed_models)}. "
                        f"Please upgrade your plan for access to more models."
                    ),
                    tier=user_tier,
                    limits=tier_limits
                )
            
            return AccessValidationResult(
                allowed=True,
                message=f"Model access granted for {user_tier} tier",
                tier=user_tier,
                limits=tier_limits
            )
            
        except Exception as e:
            self.logger.error(f"Model access validation failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Model access validation failed due to system error",
                tier="unknown"
            )
    
    def check_rate_limits(self, user: User) -> AccessValidationResult:
        """
        Check rate limits for user based on their tier.
        
        Args:
            user: Authenticated user
            
        Returns:
            AccessValidationResult with rate limit details
        """
        try:
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return AccessValidationResult(
                    allowed=False,
                    message=f"Invalid tier: {user_tier}",
                    tier=user_tier
                )
            
            # Enterprise tier has unlimited requests
            if tier_limits.max_requests_per_hour == -1:
                return AccessValidationResult(
                    allowed=True,
                    message="Unlimited requests for enterprise tier",
                    tier=user_tier,
                    limits=tier_limits
                )
            
            # Check rate limits using existing rate limit manager
            user_identifier = f"chat_user_{user.id}"
            is_rate_limited = rate_limit_manager.is_rate_limited(
                identifier=user_identifier,
                max_requests=tier_limits.max_requests_per_hour,
                window_minutes=60
            )
            
            if is_rate_limited:
                # Get rate limit status for retry information
                status = rate_limit_manager.get_rate_limit_status(
                    identifier=user_identifier,
                    max_requests=tier_limits.max_requests_per_hour,
                    window_minutes=60
                )
                
                return AccessValidationResult(
                    allowed=False,
                    message=(
                        f"Rate limit exceeded for {user_tier} tier. "
                        f"You have used {status['used']} of {status['limit']} requests. "
                        f"Please wait {status['window_minutes']} minutes or upgrade your plan."
                    ),
                    tier=user_tier,
                    limits=tier_limits,
                    usage=status,
                    retry_after=status['window_minutes'] * 60  # Convert to seconds
                )
            
            return AccessValidationResult(
                allowed=True,
                message=f"Rate limit check passed for {user_tier} tier",
                tier=user_tier,
                limits=tier_limits
            )
            
        except Exception as e:
            self.logger.error(f"Rate limit check failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Rate limit check failed due to system error",
                tier="unknown"
            )
    
    def validate_context_files(self, user: User, file_count: int) -> AccessValidationResult:
        """
        Validate context file count based on user tier.
        
        Args:
            user: Authenticated user
            file_count: Number of files in context
            
        Returns:
            AccessValidationResult with validation details
        """
        try:
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return AccessValidationResult(
                    allowed=False,
                    message=f"Invalid tier: {user_tier}",
                    tier=user_tier
                )
            
            if file_count > tier_limits.max_context_files:
                return AccessValidationResult(
                    allowed=False,
                    message=(
                        f"Context file count ({file_count}) exceeds your "
                        f"{user_tier} tier limit ({tier_limits.max_context_files} files). "
                        f"Please remove some files or upgrade your plan."
                    ),
                    tier=user_tier,
                    limits=tier_limits
                )
            
            return AccessValidationResult(
                allowed=True,
                message=f"Context file validation passed for {user_tier} tier",
                tier=user_tier,
                limits=tier_limits
            )
            
        except Exception as e:
            self.logger.error(f"Context file validation failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Context file validation failed due to system error",
                tier="unknown"
            )
    
    def validate_session_limits(self, user: User, session_id: str) -> AccessValidationResult:
        """
        Validate concurrent session limits for user.
        
        Args:
            user: Authenticated user
            session_id: Current session ID
            
        Returns:
            AccessValidationResult with validation details
        """
        try:
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return AccessValidationResult(
                    allowed=False,
                    message=f"Invalid tier: {user_tier}",
                    tier=user_tier
                )
            
            user_id = str(user.id)
            
            # Clean up expired sessions
            self._cleanup_expired_sessions(user_id, tier_limits.max_session_duration_hours)
            
            # Get current active sessions
            active_sessions = self.active_sessions.get(user_id, [])
            
            # Check if current session already exists
            existing_session = next((s for s in active_sessions if s["session_id"] == session_id), None)
            
            if not existing_session:
                # Check concurrent session limit
                if len(active_sessions) >= tier_limits.max_concurrent_sessions:
                    return AccessValidationResult(
                        allowed=False,
                        message=(
                            f"Concurrent session limit exceeded for {user_tier} tier. "
                            f"You have {len(active_sessions)} active sessions "
                            f"(limit: {tier_limits.max_concurrent_sessions}). "
                            f"Please close some sessions or upgrade your plan."
                        ),
                        tier=user_tier,
                        limits=tier_limits
                    )
                
                # Add new session
                if user_id not in self.active_sessions:
                    self.active_sessions[user_id] = []
                
                self.active_sessions[user_id].append({
                    "session_id": session_id,
                    "created_at": datetime.now(),
                    "last_activity": datetime.now()
                })
            else:
                # Update last activity for existing session
                existing_session["last_activity"] = datetime.now()
            
            return AccessValidationResult(
                allowed=True,
                message=f"Session validation passed for {user_tier} tier",
                tier=user_tier,
                limits=tier_limits
            )
            
        except Exception as e:
            self.logger.error(f"Session validation failed: {e}")
            return AccessValidationResult(
                allowed=False,
                message="Session validation failed due to system error",
                tier="unknown"
            )
    
    def cleanup_user_session(self, user: User, session_id: str) -> None:
        """
        Clean up a specific user session.
        
        Args:
            user: Authenticated user
            session_id: Session ID to clean up
        """
        try:
            user_id = str(user.id)
            if user_id in self.active_sessions:
                self.active_sessions[user_id] = [
                    s for s in self.active_sessions[user_id] 
                    if s["session_id"] != session_id
                ]
                
                # Remove user entry if no sessions left
                if not self.active_sessions[user_id]:
                    del self.active_sessions[user_id]
                    
        except Exception as e:
            self.logger.error(f"Session cleanup failed: {e}")
    
    def get_tier_limits(self, user: User) -> Optional[TierLimits]:
        """
        Get tier limits for user.
        
        Args:
            user: Authenticated user
            
        Returns:
            TierLimits for the user's tier or None if invalid
        """
        try:
            user_tier = self._get_user_tier(user)
            return self.tier_limits.get(user_tier)
        except Exception as e:
            self.logger.error(f"Failed to get tier limits: {e}")
            return None
    
    def get_usage_summary(self, user: User) -> Dict[str, Any]:
        """
        Get usage summary for user.
        
        Args:
            user: Authenticated user
            
        Returns:
            Dictionary with usage information
        """
        try:
            user_tier = self._get_user_tier(user)
            tier_limits = self.tier_limits.get(user_tier)
            
            if not tier_limits:
                return {"error": f"Invalid tier: {user_tier}"}
            
            # Get rate limit status
            user_identifier = f"chat_user_{user.id}"
            rate_status = rate_limit_manager.get_rate_limit_status(
                identifier=user_identifier,
                max_requests=tier_limits.max_requests_per_hour if tier_limits.max_requests_per_hour != -1 else 1000,
                window_minutes=60
            )
            
            # Get active sessions
            user_id = str(user.id)
            active_sessions = self.active_sessions.get(user_id, [])
            
            return {
                "tier": user_tier,
                "limits": {
                    "max_repository_size_mb": tier_limits.max_repository_size_mb,
                    "max_requests_per_hour": tier_limits.max_requests_per_hour,
                    "max_context_files": tier_limits.max_context_files,
                    "allowed_models": tier_limits.allowed_models,
                    "max_session_duration_hours": tier_limits.max_session_duration_hours,
                    "max_concurrent_sessions": tier_limits.max_concurrent_sessions
                },
                "usage": {
                    "requests_used": rate_status.get("used", 0),
                    "requests_remaining": rate_status.get("remaining", 0),
                    "active_sessions": len(active_sessions),
                    "rate_limit_reset": rate_status.get("reset_date")
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get usage summary: {e}")
            return {"error": "Failed to get usage summary"}
    
    def _get_user_tier(self, user: User) -> str:
        """
        Get user tier from user object or environment.
        
        Args:
            user: Authenticated user
            
        Returns:
            User tier string
        """
        # Try to get tier from user object
        if hasattr(user, 'tier') and user.tier:
            return user.tier.lower().strip()
        
        # Try to get from user metadata
        if hasattr(user, 'metadata') and user.metadata:
            tier = user.metadata.get('tier') or user.metadata.get('subscription_tier')
            if tier:
                return tier.lower().strip()
        
        # Default to personal tier for demo users
        if user.login == 'demo-user':
            return TierLevel.PERSONAL.value
        
        # Try environment variables as fallback
        tier = os.getenv("USER_TIER", "").strip().lower()
        if tier:
            return tier
        
        # Default to personal tier
        return TierLevel.PERSONAL.value
    
    def _cleanup_expired_sessions(self, user_id: str, max_duration_hours: int) -> None:
        """
        Clean up expired sessions for a user.
        
        Args:
            user_id: User ID
            max_duration_hours: Maximum session duration in hours
        """
        try:
            if user_id not in self.active_sessions:
                return
            
            cutoff_time = datetime.now() - timedelta(hours=max_duration_hours)
            
            # Filter out expired sessions
            self.active_sessions[user_id] = [
                session for session in self.active_sessions[user_id]
                if session["last_activity"] > cutoff_time
            ]
            
            # Remove user entry if no sessions left
            if not self.active_sessions[user_id]:
                del self.active_sessions[user_id]
                
        except Exception as e:
            self.logger.error(f"Session cleanup failed for user {user_id}: {e}")


# Global instance for easy access
_web_tier_access_controller: Optional[WebTierAccessController] = None


def get_web_tier_access_controller() -> WebTierAccessController:
    """
    Get or create global WebTierAccessController instance.
    
    Returns:
        WebTierAccessController instance
    """
    global _web_tier_access_controller
    
    if _web_tier_access_controller is None:
        _web_tier_access_controller = WebTierAccessController()
    
    return _web_tier_access_controller


def reset_web_tier_access_controller() -> None:
    """Reset global WebTierAccessController instance (mainly for testing)."""
    global _web_tier_access_controller
    _web_tier_access_controller = None