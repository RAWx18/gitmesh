"""
Core settings configuration for the RAG system.
Handles environment variables, validation, and service configuration.
"""

import os
import yaml
from typing import Optional, List, Dict, Any
from pydantic import Field, validator
from pydantic_settings import BaseSettings
import structlog

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    """Main application settings with environment variable support."""

    # ========================
    # KEY MANAGER CONFIGURATION
    # ========================
    vault_addr: str = Field(default="http://127.0.0.1:8200", env="VAULT_ADDR")
    vault_token: Optional[str] = Field(default=None, env="VAULT_TOKEN")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db_field: int = Field(default=0, env="REDIS_DB")
    redis_username: str = Field(default="default", env="REDIS_USERNAME")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_ssl: bool = Field(default=False, env="REDIS_SSL")
    
    # Security
    secret_key: str = Field(default="your-super-secret-key-change-in-production-minimum-32-chars", env="SECRET_KEY")
    jwt_secret: str = Field(default="your-jwt-secret-key-change-in-production-minimum-32-chars", env="JWT_SECRET")
    
    # GitHub Integration
    github_client_id: Optional[str] = Field(default=None, env="GITHUB_CLIENT_ID")
    github_client_secret: Optional[str] = Field(default=None, env="GITHUB_CLIENT_SECRET")
    github_callback_url: Optional[str] = Field(default=None, env="GITHUB_CALLBACK_URL")
    github_webhook_secret: Optional[str] = Field(default=None, env="GITHUB_WEBHOOK_SECRET")
    
    # Allowed origins for CORS and security
    allowed_origins: Optional[str] = Field(default=None, env="ALLOWED_ORIGINS")
    
    # Observability
    trace_file: str = Field(default="./traces.jsonl", env="TRACE_FILE")
    
    # ========================
    # YAML CONFIGURATION
    # ========================
    _yaml_config: Optional[Dict[str, Any]] = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_yaml_config()
    
    def _load_yaml_config(self):
        """Load configuration from YAML file."""
        try:
            yaml_path = os.path.join(os.path.dirname(__file__), "features.yaml")
            with open(yaml_path, 'r', encoding='utf-8') as f:
                self._yaml_config = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load YAML config: {e}")
            self._yaml_config = {}
    
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
    
    # ========================
    # APPLICATION SETTINGS (from YAML)
    # ========================
    @property
    def app_name(self) -> str:
        return self.get_yaml_config("app.name", "GitMesh RAG System")
    
    @property
    def debug(self) -> bool:
        return self.get_yaml_config("app.debug", False)
    
    @property
    def environment(self) -> str:
        return self.get_yaml_config("app.environment", "development")
    
    @property
    def api_prefix(self) -> str:
        return self.get_yaml_config("app.api_prefix", "/api/v1")
    
    @property
    def cors_origins(self) -> List[str]:
        return self.get_yaml_config("app.cors_origins", ["*"])
    
    # ========================
    # EMBEDDING CONFIGURATION (from YAML)
    # ========================
    @property
    def default_embedding_provider(self) -> str:
        return self.get_yaml_config("embeddings.default_provider", "sentence_transformers")
    
    @property
    def default_embedding_model(self) -> str:
        return self.get_yaml_config("embeddings.default_model", "all-MiniLM-L6-v2")
    
    @property
    def sentence_transformers_device(self) -> str:
        return self.get_yaml_config("embeddings.sentence_transformers.device", "cpu")
    
    @property
    def sentence_transformers_batch_size(self) -> int:
        return self.get_yaml_config("embeddings.sentence_transformers.batch_size", 32)
    
    @property
    def jina_base_url(self) -> str:
        return self.get_yaml_config("embeddings.jina.base_url", "https://api.jina.ai/v1")
    
    # ========================
    # VECTOR DATABASE CONFIGURATION (from YAML)
    # ========================
    @property
    def qdrant_collection_name(self) -> str:
        return self.get_yaml_config("vectorstore.qdrant.collection_name", "beetle_documents")
    
    @property
    def max_retrieval_results(self) -> int:
        return self.get_yaml_config("vectorstore.qdrant.max_retrieval_results", 5)
    
    # ========================
    # RAG SETTINGS (from YAML)
    # ========================
    @property
    def max_chunk_size(self) -> int:
        return self.get_yaml_config("rag.max_chunk_size", 1000)
    
    @property
    def chunk_overlap(self) -> int:
        return self.get_yaml_config("rag.chunk_overlap", 200)
    
    @property
    def max_context_length(self) -> int:
        return self.get_yaml_config("rag.max_context_length", 4000)
    
    @property
    def max_sources(self) -> int:
        return self.get_yaml_config("rag.max_sources", 5)
    
    @property
    def include_citations(self) -> bool:
        return self.get_yaml_config("rag.include_citations", True)
    
    @property
    def include_confidence(self) -> bool:
        return self.get_yaml_config("rag.include_confidence", True)
    
    # ========================
    # AI PIPELINE SETTINGS (from YAML)
    # ========================
    @property
    def ai_pipeline_config(self) -> Dict[str, Any]:
        return self.get_yaml_config("ai_pipeline", {})
    
    # ========================
    # CACHE CONFIGURATION (from YAML)
    # ========================
    @property
    def redis_db(self) -> int:
        return self.get_yaml_config("cache.redis_db", self.redis_db_field)
    
    # ========================
    # RATE LIMITING (from YAML)
    # ========================
    @property
    def rate_limit_requests(self) -> int:
        return self.get_yaml_config("rate_limiting.requests", 100)
    
    @property
    def rate_limit_window(self) -> int:
        return self.get_yaml_config("rate_limiting.window", 3600)
    
    # ========================
    # LOGGING (from YAML)
    # ========================
    @property
    def log_level(self) -> str:
        return self.get_yaml_config("logging.level", "INFO")
    
    @property
    def log_format(self) -> str:
        return self.get_yaml_config("logging.format", "json")
    
    # ========================
    # SECURITY (from YAML)
    # ========================
    @property
    def algorithm(self) -> str:
        return self.get_yaml_config("security.algorithm", "HS256")
    
    @property
    def access_token_expire_minutes(self) -> int:
        return self.get_yaml_config("security.access_token_expire_minutes", 30)
    
    # ========================
    # GITHUB INTEGRATION (Environment Variables)
    # ========================
    @property
    def GITHUB_CLIENT_ID(self) -> Optional[str]:
        return self.github_client_id
    
    @property
    def GITHUB_CLIENT_SECRET(self) -> Optional[str]:
        return self.github_client_secret
    
    @property
    def GITHUB_CALLBACK_URL(self) -> Optional[str]:
        return self.github_callback_url
    
    @property
    def GITHUB_WEBHOOK_SECRET(self) -> Optional[str]:
        return self.github_webhook_secret
    
    @property
    def JWT_SECRET(self) -> str:
        return self.jwt_secret
    
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        if self.allowed_origins:
            return [origin.strip() for origin in self.allowed_origins.split(',')]
        return ["*"]
    
    @property
    def ENVIRONMENT(self) -> str:
        return self.environment
  
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


# Convenience functions for feature flags
def is_agent_enabled(agent_name: str) -> bool:
    """Check if an agent is enabled."""
    return settings.is_agent_enabled(agent_name)


def is_provider_enabled(provider_name: str) -> bool:
    """Check if a provider is enabled."""
    return settings.is_provider_enabled(provider_name)


def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled."""
    return settings.is_feature_enabled(feature_name)