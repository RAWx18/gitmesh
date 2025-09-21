"""
Production Configuration for Cosmos Web Chat Integration

This module provides production-specific configuration settings,
feature flags, and environment management for the Cosmos web chat integration.
"""

import os
from typing import Dict, Any, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class DeploymentEnvironment(str, Enum):
    """Deployment environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class FeatureFlag(str, Enum):
    """Feature flags for gradual rollout."""
    COSMOS_CHAT_ENABLED = "cosmos_chat_enabled"
    COSMOS_CHAT_BETA = "cosmos_chat_beta"
    COSMOS_CHAT_FULL = "cosmos_chat_full"
    TIER_ACCESS_CONTROL = "tier_access_control"
    REDIS_REPO_MANAGER = "redis_repo_manager"
    CONTEXT_FILE_MANAGEMENT = "context_file_management"
    REAL_TIME_CHAT = "real_time_chat"
    SHELL_COMMAND_CONVERSION = "shell_command_conversion"
    PERFORMANCE_MONITORING = "performance_monitoring"
    SECURITY_HARDENING = "security_hardening"
    SESSION_PERSISTENCE = "session_persistence"
    ANALYTICS_TRACKING = "analytics_tracking"


class ProductionSettings(BaseSettings):
    """Production-specific settings."""
    
    # Environment
    environment: DeploymentEnvironment = Field(
        default=DeploymentEnvironment.DEVELOPMENT,
        env="DEPLOYMENT_ENVIRONMENT"
    )
    
    # Feature flags
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    
    # Cosmos Chat Configuration
    cosmos_chat_enabled: bool = Field(default=False, env="COSMOS_CHAT_ENABLED")
    cosmos_chat_beta_users: List[str] = Field(default_factory=list, env="COSMOS_CHAT_BETA_USERS")
    cosmos_chat_rollout_percentage: int = Field(default=0, env="COSMOS_CHAT_ROLLOUT_PERCENTAGE")
    
    # Performance Settings
    max_concurrent_sessions: int = Field(default=100, env="MAX_CONCURRENT_SESSIONS")
    session_timeout_minutes: int = Field(default=30, env="SESSION_TIMEOUT_MINUTES")
    max_context_files_per_session: int = Field(default=50, env="MAX_CONTEXT_FILES_PER_SESSION")
    max_message_length: int = Field(default=10000, env="MAX_MESSAGE_LENGTH")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, env="RATE_LIMIT_PER_HOUR")
    rate_limit_per_day: int = Field(default=10000, env="RATE_LIMIT_PER_DAY")
    
    # Monitoring and Alerting
    monitoring_enabled: bool = Field(default=True, env="MONITORING_ENABLED")
    alerting_enabled: bool = Field(default=True, env="ALERTING_ENABLED")
    metrics_collection_interval: int = Field(default=60, env="METRICS_COLLECTION_INTERVAL")
    
    # Security
    security_hardening_enabled: bool = Field(default=True, env="SECURITY_HARDENING_ENABLED")
    input_validation_strict: bool = Field(default=True, env="INPUT_VALIDATION_STRICT")
    audit_logging_enabled: bool = Field(default=True, env="AUDIT_LOGGING_ENABLED")
    
    # Redis Configuration
    redis_connection_pool_size: int = Field(default=20, env="REDIS_CONNECTION_POOL_SIZE")
    redis_connection_timeout: int = Field(default=5, env="REDIS_CONNECTION_TIMEOUT")
    redis_retry_attempts: int = Field(default=3, env="REDIS_RETRY_ATTEMPTS")
    
    # AI Model Configuration
    default_ai_model: str = Field(default="gemini-2.0-flash", env="DEFAULT_AI_MODEL")
    ai_model_timeout: int = Field(default=30, env="AI_MODEL_TIMEOUT")
    ai_model_retry_attempts: int = Field(default=2, env="AI_MODEL_RETRY_ATTEMPTS")
    
    # Tier Limits
    free_tier_daily_limit: int = Field(default=50, env="FREE_TIER_DAILY_LIMIT")
    pro_tier_daily_limit: int = Field(default=500, env="PRO_TIER_DAILY_LIMIT")
    enterprise_tier_daily_limit: int = Field(default=10000, env="ENTERPRISE_TIER_DAILY_LIMIT")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._initialize_feature_flags()
    
    def _initialize_feature_flags(self):
        """Initialize feature flags based on environment and configuration."""
        # Default feature flags based on environment
        if self.environment == DeploymentEnvironment.DEVELOPMENT:
            self.feature_flags = {
                FeatureFlag.COSMOS_CHAT_ENABLED: True,
                FeatureFlag.COSMOS_CHAT_BETA: True,
                FeatureFlag.COSMOS_CHAT_FULL: True,
                FeatureFlag.TIER_ACCESS_CONTROL: True,
                FeatureFlag.REDIS_REPO_MANAGER: True,
                FeatureFlag.CONTEXT_FILE_MANAGEMENT: True,
                FeatureFlag.REAL_TIME_CHAT: True,
                FeatureFlag.SHELL_COMMAND_CONVERSION: True,
                FeatureFlag.PERFORMANCE_MONITORING: True,
                FeatureFlag.SECURITY_HARDENING: False,  # Less strict in dev
                FeatureFlag.SESSION_PERSISTENCE: True,
                FeatureFlag.ANALYTICS_TRACKING: False,  # No tracking in dev
            }
        elif self.environment == DeploymentEnvironment.STAGING:
            self.feature_flags = {
                FeatureFlag.COSMOS_CHAT_ENABLED: True,
                FeatureFlag.COSMOS_CHAT_BETA: True,
                FeatureFlag.COSMOS_CHAT_FULL: False,  # Beta only in staging
                FeatureFlag.TIER_ACCESS_CONTROL: True,
                FeatureFlag.REDIS_REPO_MANAGER: True,
                FeatureFlag.CONTEXT_FILE_MANAGEMENT: True,
                FeatureFlag.REAL_TIME_CHAT: True,
                FeatureFlag.SHELL_COMMAND_CONVERSION: True,
                FeatureFlag.PERFORMANCE_MONITORING: True,
                FeatureFlag.SECURITY_HARDENING: True,
                FeatureFlag.SESSION_PERSISTENCE: True,
                FeatureFlag.ANALYTICS_TRACKING: True,
            }
        else:  # PRODUCTION
            self.feature_flags = {
                FeatureFlag.COSMOS_CHAT_ENABLED: self.cosmos_chat_enabled,
                FeatureFlag.COSMOS_CHAT_BETA: False,  # No beta in production
                FeatureFlag.COSMOS_CHAT_FULL: self.cosmos_chat_enabled,
                FeatureFlag.TIER_ACCESS_CONTROL: True,
                FeatureFlag.REDIS_REPO_MANAGER: True,
                FeatureFlag.CONTEXT_FILE_MANAGEMENT: True,
                FeatureFlag.REAL_TIME_CHAT: True,
                FeatureFlag.SHELL_COMMAND_CONVERSION: True,
                FeatureFlag.PERFORMANCE_MONITORING: True,
                FeatureFlag.SECURITY_HARDENING: True,
                FeatureFlag.SESSION_PERSISTENCE: True,
                FeatureFlag.ANALYTICS_TRACKING: True,
            }
        
        # Override with environment variables
        for flag in FeatureFlag:
            env_var = f"FEATURE_{flag.value.upper()}"
            env_value = os.getenv(env_var)
            if env_value is not None:
                self.feature_flags[flag] = env_value.lower() in ('true', '1', 'yes', 'on')
    
    def is_feature_enabled(self, feature: FeatureFlag) -> bool:
        """Check if a feature flag is enabled."""
        return self.feature_flags.get(feature, False)
    
    def enable_feature(self, feature: FeatureFlag) -> None:
        """Enable a feature flag."""
        self.feature_flags[feature] = True
        logger.info(f"Feature enabled: {feature.value}")
    
    def disable_feature(self, feature: FeatureFlag) -> None:
        """Disable a feature flag."""
        self.feature_flags[feature] = False
        logger.info(f"Feature disabled: {feature.value}")
    
    def get_rollout_config(self) -> Dict[str, Any]:
        """Get rollout configuration for gradual deployment."""
        return {
            "cosmos_chat_enabled": self.cosmos_chat_enabled,
            "rollout_percentage": self.cosmos_chat_rollout_percentage,
            "beta_users": self.cosmos_chat_beta_users,
            "environment": self.environment.value,
            "feature_flags": self.feature_flags
        }
    
    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance-related configuration."""
        return {
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "session_timeout_minutes": self.session_timeout_minutes,
            "max_context_files_per_session": self.max_context_files_per_session,
            "max_message_length": self.max_message_length,
            "redis_connection_pool_size": self.redis_connection_pool_size,
            "redis_connection_timeout": self.redis_connection_timeout,
            "ai_model_timeout": self.ai_model_timeout
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security-related configuration."""
        return {
            "security_hardening_enabled": self.security_hardening_enabled,
            "input_validation_strict": self.input_validation_strict,
            "audit_logging_enabled": self.audit_logging_enabled,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "rate_limit_per_day": self.rate_limit_per_day
        }
    
    def get_tier_limits(self) -> Dict[str, int]:
        """Get tier-based usage limits."""
        return {
            "free": self.free_tier_daily_limit,
            "pro": self.pro_tier_daily_limit,
            "enterprise": self.enterprise_tier_daily_limit
        }
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


# Global production settings instance
production_settings = ProductionSettings()


def get_production_settings() -> ProductionSettings:
    """Get the global production settings instance."""
    return production_settings


def is_feature_enabled(feature: FeatureFlag) -> bool:
    """Check if a feature flag is enabled."""
    return production_settings.is_feature_enabled(feature)


def get_rollout_percentage() -> int:
    """Get the current rollout percentage for Cosmos chat."""
    return production_settings.cosmos_chat_rollout_percentage


def is_user_in_beta(user_id: str) -> bool:
    """Check if a user is in the beta program."""
    return user_id in production_settings.cosmos_chat_beta_users


def should_enable_for_user(user_id: str) -> bool:
    """Determine if Cosmos chat should be enabled for a specific user."""
    # Always enable for beta users
    if is_user_in_beta(user_id):
        return True
    
    # Check rollout percentage
    if production_settings.cosmos_chat_rollout_percentage >= 100:
        return True
    
    # Use hash-based rollout for consistent user experience
    import hashlib
    user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
    rollout_threshold = (production_settings.cosmos_chat_rollout_percentage / 100) * (2**128)
    
    return user_hash < rollout_threshold