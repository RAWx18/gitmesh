"""
Simplified unified configuration that actually works.
"""

import os
from typing import Optional, List, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
import structlog

logger = structlog.get_logger(__name__)


class Config(BaseSettings):
    """Unified configuration class."""
    
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Database
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    supabase_url: Optional[str] = Field(default=None, env="SUPABASE_URL")  # Fallback
    db_pool_size: int = Field(default=10, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, env="DB_MAX_OVERFLOW")
    db_echo: bool = Field(default=False, env="DB_ECHO")
    
    # Redis
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_username: str = Field(default="default", env="REDIS_USERNAME")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_ssl: bool = Field(default=False, env="REDIS_SSL")
    
    # Security
    secret_key: str = Field(default="dev-secret-key-change-in-production-32chars", env="SECRET_KEY")
    jwt_secret: str = Field(default="dev-jwt-secret-key-change-in-production-32chars", env="JWT_SECRET")
    jwt_expires_in: str = Field(default="7d", env="JWT_EXPIRES_IN")
    
    # Server
    server_host: str = Field(default="0.0.0.0", env="SERVER_HOST")
    server_port: int = Field(default=8000, env="SERVER_PORT")
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://localhost:8000",
        env="ALLOWED_ORIGINS"
    )
    
    # GitHub
    github_client_id: Optional[str] = Field(default=None, env="GITHUB_CLIENT_ID")
    github_client_secret: Optional[str] = Field(default=None, env="GITHUB_CLIENT_SECRET")
    github_callback_url: Optional[str] = Field(default=None, env="GITHUB_CALLBACK_URL")
    
    # AI
    ai_provider: str = Field(default="gemini", env="AI_PROVIDER")
    gemini_api_key: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    ai_default_model: str = Field(default="gemini-2.0-flash", env="AI_DEFAULT_MODEL")
    
    # Vault
    vault_enabled: bool = Field(default=False, env="VAULT_ENABLED")
    vault_addr: str = Field(default="http://127.0.0.1:8200", env="VAULT_ADDR")
    vault_token: Optional[str] = Field(default=None, env="VAULT_TOKEN")
    
    # Tiers
    tier_plan: str = Field(default="pro", env="TIER_PLAN")
    tier_free_limit: int = Field(default=50000, env="TIER_FREE_LIMIT")
    tier_pro_limit: int = Field(default=500000, env="TIER_PRO_LIMIT")
    tier_enterprise_limit: int = Field(default=2000000, env="TIER_ENTERPRISE_LIMIT")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    debug_mode: bool = Field(default=False, env="DEBUG_MODE")
    
    model_config = {
        "env_file": "backend/.env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    def __init__(self, **kwargs):
        # Find the correct .env file path
        env_paths = [
            ".env",
            "backend/.env",
            os.path.join(os.path.dirname(__file__), "../.env"),
        ]
        
        env_file = None
        for path in env_paths:
            if os.path.exists(path):
                env_file = path
                break
        
        if env_file:
            self.model_config["env_file"] = env_file
        
        super().__init__(**kwargs)
        
        # Load YAML config
        self._yaml_config = self._load_yaml_config()
    
    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load YAML configuration file."""
        try:
            yaml_path = os.path.join(os.path.dirname(__file__), "features.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                logger.info("Loaded YAML configuration", path=yaml_path)
                return config or {}
            else:
                logger.warning("YAML config file not found", path=yaml_path)
                return {}
        except Exception as e:
            logger.error("Failed to load YAML config", error=str(e))
            return {}
    
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
    
    def get_database_url(self) -> str:
        """Get database URL with fallback."""
        if self.database_url:
            return self.database_url
        
        if self.supabase_url:
            logger.warning("Using legacy SUPABASE_URL, please migrate to DATABASE_URL")
            return self.supabase_url
        
        raise ValueError("No database URL configured")
    
    def get_redis_url(self) -> str:
        """Get Redis URL."""
        if self.redis_url:
            return self.redis_url
        
        # Build from components
        if self.redis_password:
            return f"redis://{self.redis_username}:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    def get_ai_api_key(self) -> Optional[str]:
        """Get AI API key based on provider."""
        provider = self.ai_provider.lower()
        if provider == "gemini":
            return self.gemini_api_key
        elif provider == "openai":
            return self.openai_api_key
        return None
    
    def get_cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        origins = [origin.strip() for origin in self.allowed_origins.split(',')]
        
        # Add YAML-configured origins
        yaml_origins = self.get_yaml_config("app.cors_origins", [])
        for origin in yaml_origins:
            if origin not in origins:
                origins.append(origin)
        
        return origins if origins else ["*"]
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled."""
        return self.get_yaml_config(f"features.{feature_name}", False)
    
    def is_agent_enabled(self, agent_name: str) -> bool:
        """Check if an agent is enabled."""
        return self.get_yaml_config(f"agents.{agent_name}", False)
    
    def is_provider_enabled(self, provider_name: str) -> bool:
        """Check if a provider is enabled."""
        return self.get_yaml_config(f"providers.{provider_name}", False)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
        logger.info("Configuration loaded", environment=_config.environment)
    return _config


def reload_config() -> Config:
    """Reload configuration (useful for testing)."""
    global _config
    _config = None
    return get_config()


# Backward compatibility
def get_settings() -> Config:
    """Backward compatibility alias."""
    return get_config()


if __name__ == "__main__":
    # Test configuration loading
    config = get_config()
    print("Configuration loaded successfully!")
    print(f"Environment: {config.environment}")
    print(f"Database configured: {bool(config.database_url or config.supabase_url)}")
    print(f"Redis configured: {bool(config.redis_url)}")
    print(f"AI provider: {config.ai_provider}")
    print(f"Secret key length: {len(config.secret_key)}")
    
    try:
        db_url = config.get_database_url()
        print(f"Database URL: {db_url[:20]}...")
    except ValueError as e:
        print(f"Database URL error: {e}")
    
    print(f"Redis URL: {config.get_redis_url()}")
    print(f"CORS origins: {len(config.get_cors_origins())} configured")