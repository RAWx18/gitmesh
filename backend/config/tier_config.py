"""
Tier configuration for easy management of tier limits.

This module provides centralized configuration for tier-based access control,
making it easy to modify limits without changing core code.
"""

import os
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class TierConfiguration:
    """Configuration for a specific tier."""
    name: str
    display_name: str
    max_repository_tokens: int  # Maximum repository size in tokens
    max_requests_per_month: int  # Maximum AI requests per month
    max_requests_per_hour: int  # Maximum AI requests per hour (for burst protection)
    max_context_files: int  # Maximum files in context
    allowed_models: List[str]  # List of allowed AI models
    max_session_duration_hours: int  # Maximum session duration
    max_concurrent_sessions: int  # Maximum concurrent sessions
    
    # Display properties
    description: str = ""
    features: List[str] = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = []


class TierConfigManager:
    """Manager for tier configurations with environment variable support."""
    
    # Default tier configurations (easily modifiable)
    DEFAULT_TIERS = {
        "personal": TierConfiguration(
            name="personal",
            display_name="Personal Plan",
            max_repository_tokens=1_000_000,  # 1M tokens
            max_requests_per_month=500,  # 500 AI requests/month
            max_requests_per_hour=1,  # ~500/(30*24) requests/hour
            max_context_files=10,
            allowed_models=["gpt-4o-mini", "claude-3-haiku"],
            max_session_duration_hours=2,
            max_concurrent_sessions=1,
            description="Perfect for individual developers and small projects",
            features=[
                "Up to 1M tokens per repository",
                "500 AI requests per month",
                "Basic AI models",
                "10 context files"
            ]
        ),
        "pro": TierConfiguration(
            name="pro",
            display_name="Pro Plan",
            max_repository_tokens=10_000_000,  # 10M tokens
            max_requests_per_month=2_000,  # 2000 AI requests/month
            max_requests_per_hour=3,  # ~2000/(30*24) requests/hour
            max_context_files=50,
            allowed_models=[
                "gpt-4o-mini", "gpt-4o", 
                "claude-3-haiku", "claude-3-sonnet"
            ],
            max_session_duration_hours=8,
            max_concurrent_sessions=3,
            description="Ideal for professional developers and medium-sized teams",
            features=[
                "Up to 10M tokens per repository",
                "2,000 AI requests per month",
                "Advanced AI models",
                "50 context files",
                "Extended session duration"
            ]
        ),
        "enterprise": TierConfiguration(
            name="enterprise",
            display_name="Enterprise Plan",
            max_repository_tokens=-1,  # Unlimited (configurable)
            max_requests_per_month=3_000,  # 3000 AI requests/month (configurable)
            max_requests_per_hour=-1,  # Unlimited (configurable)
            max_context_files=200,
            allowed_models=["*"],  # All models
            max_session_duration_hours=24,
            max_concurrent_sessions=10,
            description="For large teams and organizations with custom requirements",
            features=[
                "Custom repository size limits",
                "Custom AI request limits",
                "All AI models available",
                "200 context files",
                "24-hour sessions",
                "Priority support"
            ]
        )
    }
    
    def __init__(self):
        """Initialize tier configuration manager."""
        self.tiers = self._load_tier_configurations()
    
    def _load_tier_configurations(self) -> Dict[str, TierConfiguration]:
        """Load tier configurations with environment variable overrides."""
        tiers = {}
        
        for tier_name, default_config in self.DEFAULT_TIERS.items():
            # Create configuration with environment variable overrides
            env_prefix = f"TIER_{tier_name.upper()}_"
            
            # Load values from environment or use defaults
            max_repo_tokens = self._get_env_int(
                f"{env_prefix}MAX_REPO_TOKENS", 
                default_config.max_repository_tokens
            )
            
            max_requests_month = self._get_env_int(
                f"{env_prefix}MAX_REQUESTS_MONTH", 
                default_config.max_requests_per_month
            )
            
            max_requests_hour = self._get_env_int(
                f"{env_prefix}MAX_REQUESTS_HOUR", 
                default_config.max_requests_per_hour
            )
            
            max_context_files = self._get_env_int(
                f"{env_prefix}MAX_CONTEXT_FILES", 
                default_config.max_context_files
            )
            
            allowed_models = self._get_env_list(
                f"{env_prefix}ALLOWED_MODELS", 
                default_config.allowed_models
            )
            
            max_session_hours = self._get_env_int(
                f"{env_prefix}MAX_SESSION_HOURS", 
                default_config.max_session_duration_hours
            )
            
            max_concurrent = self._get_env_int(
                f"{env_prefix}MAX_CONCURRENT_SESSIONS", 
                default_config.max_concurrent_sessions
            )
            
            # Create tier configuration
            tiers[tier_name] = TierConfiguration(
                name=tier_name,
                display_name=default_config.display_name,
                max_repository_tokens=max_repo_tokens,
                max_requests_per_month=max_requests_month,
                max_requests_per_hour=max_requests_hour,
                max_context_files=max_context_files,
                allowed_models=allowed_models,
                max_session_duration_hours=max_session_hours,
                max_concurrent_sessions=max_concurrent,
                description=default_config.description,
                features=default_config.features
            )
        
        return tiers
    
    def _get_env_int(self, key: str, default: int) -> int:
        """Get integer value from environment variable."""
        try:
            value = os.getenv(key)
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    def _get_env_list(self, key: str, default: List[str]) -> List[str]:
        """Get list value from environment variable (comma-separated)."""
        try:
            value = os.getenv(key)
            if value is not None:
                return [item.strip() for item in value.split(",") if item.strip()]
            return default
        except (ValueError, TypeError):
            return default
    
    def get_tier_config(self, tier_name: str) -> TierConfiguration:
        """Get configuration for a specific tier."""
        return self.tiers.get(tier_name.lower())
    
    def get_all_tiers(self) -> Dict[str, TierConfiguration]:
        """Get all tier configurations."""
        return self.tiers.copy()
    
    def get_tier_names(self) -> List[str]:
        """Get list of available tier names."""
        return list(self.tiers.keys())
    
    def is_valid_tier(self, tier_name: str) -> bool:
        """Check if tier name is valid."""
        return tier_name.lower() in self.tiers
    
    def get_tier_comparison(self) -> Dict[str, Dict[str, any]]:
        """Get tier comparison data for frontend display."""
        comparison = {}
        
        for tier_name, config in self.tiers.items():
            comparison[tier_name] = {
                "display_name": config.display_name,
                "description": config.description,
                "features": config.features,
                "limits": {
                    "repository_tokens": config.max_repository_tokens,
                    "requests_per_month": config.max_requests_per_month,
                    "context_files": config.max_context_files,
                    "models": config.allowed_models,
                    "session_hours": config.max_session_duration_hours,
                    "concurrent_sessions": config.max_concurrent_sessions
                }
            }
        
        return comparison
    
    def update_tier_config(self, tier_name: str, **kwargs) -> bool:
        """Update tier configuration (for runtime modifications)."""
        if tier_name.lower() not in self.tiers:
            return False
        
        config = self.tiers[tier_name.lower()]
        
        # Update allowed fields
        updatable_fields = [
            'max_repository_tokens', 'max_requests_per_month', 'max_requests_per_hour',
            'max_context_files', 'allowed_models', 'max_session_duration_hours',
            'max_concurrent_sessions', 'description', 'features'
        ]
        
        for field, value in kwargs.items():
            if field in updatable_fields and hasattr(config, field):
                setattr(config, field, value)
        
        return True


# Global tier configuration manager
_tier_config_manager = None


def get_tier_config_manager() -> TierConfigManager:
    """Get global tier configuration manager instance."""
    global _tier_config_manager
    if _tier_config_manager is None:
        _tier_config_manager = TierConfigManager()
    return _tier_config_manager


def reset_tier_config_manager():
    """Reset global tier configuration manager (for testing)."""
    global _tier_config_manager
    _tier_config_manager = None


# Convenience functions
def get_tier_config(tier_name: str) -> TierConfiguration:
    """Get configuration for a specific tier."""
    return get_tier_config_manager().get_tier_config(tier_name)


def get_all_tier_configs() -> Dict[str, TierConfiguration]:
    """Get all tier configurations."""
    return get_tier_config_manager().get_all_tiers()


def is_valid_tier(tier_name: str) -> bool:
    """Check if tier name is valid."""
    return get_tier_config_manager().is_valid_tier(tier_name)