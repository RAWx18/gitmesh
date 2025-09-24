"""
Configuration for the Optimized Repository System

This module provides configuration options for the optimized system,
allowing you to enable/disable features and tune performance settings.
"""

import os
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class OptimizedSystemConfig:
    """Configuration for the optimized repository system."""
    
    # Feature flags
    enabled: bool = True
    use_optimized_middleware: bool = True
    use_virtual_mapping: bool = True
    enable_request_caching: bool = True
    
    # Performance settings
    max_files_in_context: int = 100
    file_cache_size: int = 1000
    request_cache_timeout: int = 300  # seconds
    
    # Redis settings
    redis_connection_timeout: int = 5
    redis_operation_timeout: int = 10
    redis_retry_attempts: int = 3
    
    # GitIngest settings
    gitingest_timeout: int = 60
    gitingest_retry_attempts: int = 3
    
    # Storage settings
    storage_dir: str = "/tmp/repo_storage"
    create_storage_dir: bool = True
    
    # Logging settings
    log_performance_metrics: bool = True
    log_cache_hits: bool = False
    log_file_access: bool = False
    
    # Health check settings
    health_check_interval: int = 30
    health_check_timeout: int = 5


def load_config_from_env() -> OptimizedSystemConfig:
    """
    Load configuration from environment variables.
    
    Returns:
        OptimizedSystemConfig instance
    """
    config = OptimizedSystemConfig()
    
    # Feature flags
    config.enabled = os.getenv("OPTIMIZED_SYSTEM_ENABLED", "true").lower() == "true"
    config.use_optimized_middleware = os.getenv("USE_OPTIMIZED_MIDDLEWARE", "true").lower() == "true"
    config.use_virtual_mapping = os.getenv("USE_VIRTUAL_MAPPING", "true").lower() == "true"
    config.enable_request_caching = os.getenv("ENABLE_REQUEST_CACHING", "true").lower() == "true"
    
    # Performance settings
    config.max_files_in_context = int(os.getenv("MAX_FILES_IN_CONTEXT", "100"))
    config.file_cache_size = int(os.getenv("FILE_CACHE_SIZE", "1000"))
    config.request_cache_timeout = int(os.getenv("REQUEST_CACHE_TIMEOUT", "300"))
    
    # Redis settings
    config.redis_connection_timeout = int(os.getenv("REDIS_CONNECTION_TIMEOUT", "5"))
    config.redis_operation_timeout = int(os.getenv("REDIS_OPERATION_TIMEOUT", "10"))
    config.redis_retry_attempts = int(os.getenv("REDIS_RETRY_ATTEMPTS", "3"))
    
    # GitIngest settings
    config.gitingest_timeout = int(os.getenv("GITINGEST_TIMEOUT", "60"))
    config.gitingest_retry_attempts = int(os.getenv("GITINGEST_RETRY_ATTEMPTS", "3"))
    
    # Storage settings
    config.storage_dir = os.getenv("STORAGE_DIR", "/tmp/repo_storage")
    config.create_storage_dir = os.getenv("CREATE_STORAGE_DIR", "true").lower() == "true"
    
    # Logging settings
    config.log_performance_metrics = os.getenv("LOG_PERFORMANCE_METRICS", "true").lower() == "true"
    config.log_cache_hits = os.getenv("LOG_CACHE_HITS", "false").lower() == "true"
    config.log_file_access = os.getenv("LOG_FILE_ACCESS", "false").lower() == "true"
    
    # Health check settings
    config.health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
    config.health_check_timeout = int(os.getenv("HEALTH_CHECK_TIMEOUT", "5"))
    
    return config


def get_config() -> OptimizedSystemConfig:
    """
    Get the global configuration instance.
    
    Returns:
        OptimizedSystemConfig instance
    """
    global _config_instance
    
    if '_config_instance' not in globals():
        _config_instance = load_config_from_env()
    
    return _config_instance


def reload_config() -> OptimizedSystemConfig:
    """
    Reload configuration from environment variables.
    
    Returns:
        New OptimizedSystemConfig instance
    """
    global _config_instance
    _config_instance = load_config_from_env()
    return _config_instance


def is_optimized_system_enabled() -> bool:
    """
    Check if the optimized system is enabled.
    
    Returns:
        True if enabled, False otherwise
    """
    config = get_config()
    return config.enabled


def get_performance_config() -> Dict[str, Any]:
    """
    Get performance-related configuration.
    
    Returns:
        Dictionary with performance settings
    """
    config = get_config()
    
    return {
        "max_files_in_context": config.max_files_in_context,
        "file_cache_size": config.file_cache_size,
        "request_cache_timeout": config.request_cache_timeout,
        "redis_operation_timeout": config.redis_operation_timeout,
        "gitingest_timeout": config.gitingest_timeout
    }


def get_feature_flags() -> Dict[str, bool]:
    """
    Get feature flag configuration.
    
    Returns:
        Dictionary with feature flags
    """
    config = get_config()
    
    return {
        "enabled": config.enabled,
        "use_optimized_middleware": config.use_optimized_middleware,
        "use_virtual_mapping": config.use_virtual_mapping,
        "enable_request_caching": config.enable_request_caching,
        "log_performance_metrics": config.log_performance_metrics,
        "log_cache_hits": config.log_cache_hits,
        "log_file_access": config.log_file_access
    }


# Example environment configuration
EXAMPLE_ENV_CONFIG = """
# Optimized Repository System Configuration

# Feature flags
OPTIMIZED_SYSTEM_ENABLED=true
USE_OPTIMIZED_MIDDLEWARE=true
USE_VIRTUAL_MAPPING=true
ENABLE_REQUEST_CACHING=true

# Performance settings
MAX_FILES_IN_CONTEXT=100
FILE_CACHE_SIZE=1000
REQUEST_CACHE_TIMEOUT=300

# Redis settings
REDIS_CONNECTION_TIMEOUT=5
REDIS_OPERATION_TIMEOUT=10
REDIS_RETRY_ATTEMPTS=3

# GitIngest settings
GITINGEST_TIMEOUT=60
GITINGEST_RETRY_ATTEMPTS=3

# Storage settings
STORAGE_DIR=/tmp/repo_storage
CREATE_STORAGE_DIR=true

# Logging settings
LOG_PERFORMANCE_METRICS=true
LOG_CACHE_HITS=false
LOG_FILE_ACCESS=false

# Health check settings
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=5
"""


if __name__ == "__main__":
    """Print current configuration."""
    
    print("🔧 Optimized Repository System Configuration")
    print("=" * 50)
    
    config = get_config()
    
    print(f"System Enabled: {config.enabled}")
    print(f"Optimized Middleware: {config.use_optimized_middleware}")
    print(f"Virtual Mapping: {config.use_virtual_mapping}")
    print(f"Request Caching: {config.enable_request_caching}")
    print()
    
    print("Performance Settings:")
    print(f"  Max Files in Context: {config.max_files_in_context}")
    print(f"  File Cache Size: {config.file_cache_size}")
    print(f"  Request Cache Timeout: {config.request_cache_timeout}s")
    print()
    
    print("Redis Settings:")
    print(f"  Connection Timeout: {config.redis_connection_timeout}s")
    print(f"  Operation Timeout: {config.redis_operation_timeout}s")
    print(f"  Retry Attempts: {config.redis_retry_attempts}")
    print()
    
    print("Storage Settings:")
    print(f"  Storage Directory: {config.storage_dir}")
    print(f"  Create Directory: {config.create_storage_dir}")
    print()
    
    print("Logging Settings:")
    print(f"  Performance Metrics: {config.log_performance_metrics}")
    print(f"  Cache Hits: {config.log_cache_hits}")
    print(f"  File Access: {config.log_file_access}")
    
    print("\n📝 Example .env configuration:")
    print(EXAMPLE_ENV_CONFIG)