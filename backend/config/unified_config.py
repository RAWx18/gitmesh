"""
Unified Configuration Management System

This module provides a centralized configuration system that:
1. Eliminates hardcoded values throughout the codebase
2. Consolidates environment variables and YAML configuration
3. Provides type-safe configuration access
4. Supports environment-specific overrides
5. Validates configuration at startup
"""

import os
import yaml
from typing import Optional, List, Dict, Any, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class Environment(str, Enum):
    """Application environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    url: Optional[str] = Field(default=None, env="DATABASE_URL")
    pool_size: int = Field(default=10, env="DB_POOL_SIZE")
    max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW")
    echo: bool = Field(default=False, env="DB_ECHO")
    
    model_config = {
        "env_prefix": "DB_",
        "extra": "ignore"
    }


class RedisConfig(BaseSettings):
    """Redis configuration."""
    url: Optional[str] = Field(default=None, env="REDIS_URL")
    host: str = Field(default="localhost", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    username: str = Field(default="default", env="REDIS_USERNAME")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    db: int = Field(default=0, env="REDIS_DB")
    ssl: bool = Field(default=False, env="REDIS_SSL")
    ssl_cert_reqs: str = Field(default="none", env="REDIS_SSL_CERT_REQS")
    ssl_ca_certs: Optional[str] = Field(default=None, env="REDIS_SSL_CA_CERTS")
    ssl_certfile: Optional[str] = Field(default=None, env="REDIS_SSL_CERTFILE")
    ssl_keyfile: Optional[str] = Field(default=None, env="REDIS_SSL_KEYFILE")
    ssl_check_hostname: bool = Field(default=False, env="REDIS_SSL_CHECK_HOSTNAME")
    socket_timeout: float = Field(default=5.0, env="REDIS_SOCKET_TIMEOUT")
    connect_timeout: float = Field(default=5.0, env="REDIS_CONNECT_TIMEOUT")
    socket_keepalive: bool = Field(default=True, env="REDIS_SOCKET_KEEPALIVE")
    retry_on_timeout: bool = Field(default=True, env="REDIS_RETRY_ON_TIMEOUT")
    health_check_interval: int = Field(default=30, env="REDIS_HEALTH_CHECK_INTERVAL")
    max_connections: int = Field(default=20, env="REDIS_MAX_CONNECTIONS")
    decode_responses: bool = Field(default=True, env="REDIS_DECODE_RESPONSES")
    encoding: str = Field(default="utf-8", env="REDIS_ENCODING")
    
    model_config = {"extra": "ignore"}
    
    @model_validator(mode='before')
    @classmethod
    def build_redis_url(cls, values):
        """Build Redis URL if not provided."""
        if isinstance(values, dict) and not values.get('url'):
            host = values.get('host', 'localhost')
            port = values.get('port', 6379)
            username = values.get('username', 'default')
            password = values.get('password', '')
            db = values.get('db', 0)
            
            if password:
                values['url'] = f"redis://{username}:{password}@{host}:{port}/{db}"
            else:
                values['url'] = f"redis://{host}:{port}/{db}"
        
        return values


class SecurityConfig(BaseSettings):
    """Security configuration."""
    secret_key: str = Field(default="dev-secret-key-change-in-production-32chars", env="SECRET_KEY")
    jwt_secret: str = Field(default="dev-jwt-secret-key-change-in-production-32chars", env="JWT_SECRET")
    jwt_expires_in: str = Field(default="7d", env="JWT_EXPIRES_IN")
    algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    
    model_config = {"extra": "ignore"}
    
    @field_validator('secret_key', 'jwt_secret')
    @classmethod
    def validate_secret_length(cls, v):
        if len(v) < 32:
            raise ValueError('Secret keys must be at least 32 characters long')
        return v


class GitHubConfig(BaseSettings):
    """GitHub OAuth configuration."""
    client_id: Optional[str] = Field(default=None, env="GITHUB_CLIENT_ID")
    client_secret: Optional[str] = Field(default=None, env="GITHUB_CLIENT_SECRET")
    callback_url: Optional[str] = Field(default=None, env="GITHUB_CALLBACK_URL")
    webhook_secret: Optional[str] = Field(default=None, env="GITHUB_WEBHOOK_SECRET")
    max_retries: int = Field(default=3, env="GITHUB_MAX_RETRIES")
    
    model_config = {"extra": "ignore"}


class AIConfig(BaseSettings):
    """AI/LLM configuration."""
    provider: str = Field(default="gemini", env="AI_PROVIDER")
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    default_model: str = Field(default="gemini-2.0-flash", env="AI_DEFAULT_MODEL")
    temperature: float = Field(default=0.7, env="AI_TEMPERATURE")
    max_tokens: int = Field(default=1000, env="AI_MAX_TOKENS")
    timeout: int = Field(default=30, env="AI_TIMEOUT")
    retry_attempts: int = Field(default=2, env="AI_RETRY_ATTEMPTS")
    
    model_config = {"extra": "ignore"}


class VaultConfig(BaseSettings):
    """HashiCorp Vault configuration."""
    addr: str = Field(default="http://127.0.0.1:8200", env="VAULT_ADDR")
    token: Optional[str] = Field(default=None, env="VAULT_TOKEN")
    mount_point: str = Field(default="secret", env="VAULT_MOUNT_POINT")
    enabled: bool = Field(default=False, env="VAULT_ENABLED")
    
    model_config = {"extra": "ignore"}


class ServerConfig(BaseSettings):
    """Server configuration."""
    host: str = Field(default="0.0.0.0", env="SERVER_HOST")
    port: int = Field(default=8000, env="SERVER_PORT")
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://localhost:8000",
        env="ALLOWED_ORIGINS"
    )
    
    model_config = {"extra": "ignore"}
    
    @property
    def origins_list(self) -> List[str]:
        """Get allowed origins as a list."""
        return [origin.strip() for origin in self.allowed_origins.split(',')]


class TierConfig(BaseSettings):
    """Tier limits configuration."""
    free_limit: int = Field(default=50000, env="TIER_FREE_LIMIT")
    pro_limit: int = Field(default=500000, env="TIER_PRO_LIMIT")
    enterprise_limit: int = Field(default=2000000, env="TIER_ENTERPRISE_LIMIT")
    tier_plan: str = Field(default="pro", env="TIER_PLAN")
    
    model_config = {"extra": "ignore"}


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")
    debug_mode: bool = Field(default=False, env="DEBUG_MODE")
    
    model_config = {"extra": "ignore"}


class UnifiedConfig(BaseSettings):
    """Main unified configuration class."""
    
    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT, env="ENVIRONMENT")
    
    # Sub-configurations will be initialized in __init__
    database: Optional[DatabaseConfig] = None
    redis: Optional[RedisConfig] = None
    security: Optional[SecurityConfig] = None
    github: Optional[GitHubConfig] = None
    ai: Optional[AIConfig] = None
    vault: Optional[VaultConfig] = None
    server: Optional[ServerConfig] = None
    tiers: Optional[TierConfig] = None
    logging: Optional[LoggingConfig] = None
    
    # Feature flags from YAML
    _yaml_config: Optional[Dict[str, Any]] = None
    
    model_config = {
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    def __init__(self, **kwargs):
        # Find the correct .env file path
        env_paths = [
            ".env",  # Current directory
            "backend/.env",  # From project root
            os.path.join(os.path.dirname(__file__), "../.env"),  # Relative to config dir
        ]
        
        env_file = None
        for path in env_paths:
            if os.path.exists(path):
                env_file = path
                break
        
        if env_file:
            self.model_config["env_file"] = env_file
        
        super().__init__(**kwargs)
        
        # Initialize sub-configurations with the same env file
        config_kwargs = {}
        if env_file:
            # For sub-configs, we need to pass the env_file in their model_config
            for config_class in [DatabaseConfig, RedisConfig, SecurityConfig, GitHubConfig, 
                               AIConfig, VaultConfig, ServerConfig, TierConfig, LoggingConfig]:
                if hasattr(config_class, 'model_config'):
                    config_class.model_config["env_file"] = env_file
        
        self.database = DatabaseConfig()
        self.redis = RedisConfig()
        self.security = SecurityConfig()
        self.github = GitHubConfig()
        self.ai = AIConfig()
        self.vault = VaultConfig()
        self.server = ServerConfig()
        self.tiers = TierConfig()
        self.logging = LoggingConfig()
        
        self._load_yaml_config()
        self._validate_environment_config()
    
    def _load_yaml_config(self):
        """Load YAML configuration file."""
        try:
            yaml_path = os.path.join(os.path.dirname(__file__), "features.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    self._yaml_config = yaml.safe_load(f)
                logger.info("Loaded YAML configuration", path=yaml_path)
            else:
                logger.warning("YAML config file not found", path=yaml_path)
                self._yaml_config = {}
        except Exception as e:
            logger.error("Failed to load YAML config", error=str(e))
            self._yaml_config = {}
    
    def _validate_environment_config(self):
        """Validate configuration based on environment."""
        if self.environment == Environment.PRODUCTION:
            self._validate_production_config()
        elif self.environment == Environment.STAGING:
            self._validate_staging_config()
    
    def _validate_production_config(self):
        """Validate production-specific configuration."""
        required_fields = [
            (self.security.secret_key, "SECRET_KEY"),
            (self.security.jwt_secret, "JWT_SECRET"),
            (self.database.url, "DATABASE_URL"),
        ]
        
        missing_fields = []
        for value, field_name in required_fields:
            if not value or value.startswith("your-") or value.startswith("change-"):
                missing_fields.append(field_name)
        
        if missing_fields:
            raise ValueError(f"Production environment requires: {', '.join(missing_fields)}")
        
        # Validate origins don't contain wildcards
        if "*" in self.server.origins_list:
            logger.warning("Wildcard origins detected in production environment")
    
    def _validate_staging_config(self):
        """Validate staging-specific configuration."""
        if not self.database.url:
            raise ValueError("DATABASE_URL is required for staging environment")
    
    def get_yaml_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value from YAML file."""
        if not self._yaml_config:
            return default
        
        keys = key.split('.')
        value = self._yaml_config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        return self.get_yaml_config(f"features.{feature_name}", False)
    
    def is_agent_enabled(self, agent_name: str) -> bool:
        """Check if an agent is enabled."""
        return self.get_yaml_config(f"agents.{agent_name}", False)
    
    def is_provider_enabled(self, provider_name: str) -> bool:
        """Check if a provider is enabled."""
        return self.get_yaml_config(f"providers.{provider_name}", False)
    
    def get_database_url(self) -> str:
        """Get database URL with fallback to SUPABASE_URL."""
        if self.database.url:
            return self.database.url
        
        # Fallback to legacy SUPABASE_URL
        supabase_url = os.getenv("SUPABASE_URL")
        if supabase_url:
            logger.warning("Using legacy SUPABASE_URL, please migrate to DATABASE_URL")
            return supabase_url
        
        raise ValueError("No database URL configured")
    
    def get_redis_url(self) -> str:
        """Get Redis URL."""
        return self.redis.url
    
    def get_ai_api_key(self) -> Optional[str]:
        """Get AI API key based on provider."""
        provider = self.ai.provider.lower()
        if provider == "gemini":
            return self.ai.gemini_api_key
        elif provider == "openai":
            return self.ai.openai_api_key
        elif provider == "anthropic":
            return self.ai.anthropic_api_key
        return None
    
    def get_cors_origins(self) -> List[str]:
        """Get CORS origins with environment-specific defaults."""
        origins = self.server.origins_list
        
        # Add YAML-configured origins
        yaml_origins = self.get_yaml_config("app.cors_origins", [])
        for origin in yaml_origins:
            if origin not in origins:
                origins.append(origin)
        
        # Environment-specific filtering
        if self.environment == Environment.PRODUCTION:
            # Remove localhost origins in production
            origins = [o for o in origins if "localhost" not in o and "127.0.0.1" not in o]
        
        return origins if origins else ["*"]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for debugging)."""
        return {
            "environment": self.environment,
            "database": {
                "url": "***" if self.database.url else None,
                "pool_size": self.database.pool_size,
                "echo": self.database.echo,
            },
            "redis": {
                "host": self.redis.host,
                "port": self.redis.port,
                "db": self.redis.db,
                "ssl": self.redis.ssl,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "frontend_url": self.server.frontend_url,
                "origins_count": len(self.server.origins_list),
            },
            "ai": {
                "provider": self.ai.provider,
                "model": self.ai.default_model,
                "has_api_key": bool(self.get_ai_api_key()),
            },
            "features": {
                "vault_enabled": self.vault.enabled,
                "github_configured": bool(self.github.client_id),
            }
        }


# Global configuration instance
_config: Optional[UnifiedConfig] = None


def get_config() -> UnifiedConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = UnifiedConfig()
        logger.info("Configuration loaded", environment=_config.environment)
    return _config


def reload_config() -> UnifiedConfig:
    """Reload configuration (useful for testing)."""
    global _config
    _config = None
    return get_config()


# Convenience functions for backward compatibility
def get_settings() -> UnifiedConfig:
    """Backward compatibility alias."""
    return get_config()


# Configuration validation
def validate_config() -> bool:
    """Validate the current configuration."""
    try:
        config = get_config()
        logger.info("Configuration validation passed", config_summary=config.to_dict())
        return True
    except Exception as e:
        logger.error("Configuration validation failed", error=str(e))
        return False


if __name__ == "__main__":
    # Test configuration loading
    config = get_config()
    print("Configuration loaded successfully!")
    print(f"Environment: {config.environment}")
    print(f"Database configured: {bool(config.database.url)}")
    print(f"Redis configured: {bool(config.redis.url)}")
    print(f"AI provider: {config.ai.provider}")