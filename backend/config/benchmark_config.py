"""
Configuration for performance benchmarks.

This module defines the performance targets and thresholds for the Cosmos optimization benchmarks.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class BenchmarkThresholds:
    """Performance thresholds for benchmarks."""
    
    # Response time targets (seconds)
    RESPONSE_TIME_TARGET = 3.0
    RESPONSE_TIME_WARNING = 2.5
    
    # Memory usage targets (MB)
    MEMORY_USAGE_TARGET = 500
    MEMORY_USAGE_WARNING = 400
    
    # Redis connection efficiency targets (percentage)
    REDIS_REUSE_TARGET = 0.95
    REDIS_REUSE_WARNING = 0.90
    
    # File access time targets (seconds)
    FILE_ACCESS_TARGET = 0.1  # 100ms
    FILE_ACCESS_WARNING = 0.05  # 50ms


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark execution."""
    
    # Test data sizes
    SMALL_REPO_FILES = 100
    MEDIUM_REPO_FILES = 1000
    LARGE_REPO_FILES = 10000
    
    # Test iterations
    RESPONSE_TIME_ITERATIONS = 5
    MEMORY_TEST_ITERATIONS = 3
    REDIS_OPERATIONS_COUNT = 100
    FILE_ACCESS_ITERATIONS = 10
    
    # Timeout settings (seconds)
    BENCHMARK_TIMEOUT = 300  # 5 minutes
    INDIVIDUAL_TEST_TIMEOUT = 60  # 1 minute
    
    # Memory monitoring
    MEMORY_SAMPLE_INTERVAL = 0.1  # seconds
    MEMORY_MONITORING_DURATION = 30  # seconds
    
    # Redis settings
    REDIS_POOL_SIZE = 10
    REDIS_TIMEOUT = 5
    
    # File system settings
    VFS_CACHE_SIZE = 1000  # files
    VFS_INDEX_CHUNK_SIZE = 1024 * 1024  # 1MB


# Global configuration instances
THRESHOLDS = BenchmarkThresholds()
CONFIG = BenchmarkConfig()


def get_benchmark_targets() -> Dict[str, Any]:
    """Get all benchmark targets as a dictionary."""
    return {
        'response_time': THRESHOLDS.RESPONSE_TIME_TARGET,
        'memory_usage': THRESHOLDS.MEMORY_USAGE_TARGET,
        'redis_reuse_rate': THRESHOLDS.REDIS_REUSE_TARGET,
        'file_access_time': THRESHOLDS.FILE_ACCESS_TARGET
    }


def get_warning_thresholds() -> Dict[str, Any]:
    """Get warning thresholds for performance monitoring."""
    return {
        'response_time': THRESHOLDS.RESPONSE_TIME_WARNING,
        'memory_usage': THRESHOLDS.MEMORY_USAGE_WARNING,
        'redis_reuse_rate': THRESHOLDS.REDIS_REUSE_WARNING,
        'file_access_time': THRESHOLDS.FILE_ACCESS_WARNING
    }


def validate_performance_result(metric_name: str, value: float) -> Dict[str, Any]:
    """
    Validate a performance result against thresholds.
    
    Args:
        metric_name: Name of the metric being validated
        value: The measured value
        
    Returns:
        Dictionary with validation results
    """
    targets = get_benchmark_targets()
    warnings = get_warning_thresholds()
    
    if metric_name not in targets:
        return {'status': 'unknown', 'message': f'Unknown metric: {metric_name}'}
    
    target = targets[metric_name]
    warning = warnings[metric_name]
    
    # For reuse rate, higher is better
    if metric_name == 'redis_reuse_rate':
        if value >= target:
            status = 'pass'
            message = f'Excellent: {value:.2%} >= {target:.2%}'
        elif value >= warning:
            status = 'warning'
            message = f'Warning: {value:.2%} < {target:.2%} but >= {warning:.2%}'
        else:
            status = 'fail'
            message = f'Fail: {value:.2%} < {warning:.2%}'
    
    # For other metrics, lower is better
    else:
        if value <= warning:
            status = 'excellent'
            message = f'Excellent: {value} <= {warning}'
        elif value <= target:
            status = 'pass'
            message = f'Pass: {value} <= {target}'
        else:
            status = 'fail'
            message = f'Fail: {value} > {target}'
    
    return {
        'status': status,
        'message': message,
        'value': value,
        'target': target,
        'warning': warning
    }


# Environment-specific configurations
ENVIRONMENT_CONFIGS = {
    'development': {
        'iterations_multiplier': 0.5,  # Fewer iterations for faster dev testing
        'timeout_multiplier': 0.5,
        'memory_limit_multiplier': 1.5  # More lenient memory limits
    },
    'ci': {
        'iterations_multiplier': 1.0,
        'timeout_multiplier': 2.0,  # More time for CI environments
        'memory_limit_multiplier': 1.2
    },
    'production': {
        'iterations_multiplier': 2.0,  # More thorough testing
        'timeout_multiplier': 1.0,
        'memory_limit_multiplier': 0.8  # Stricter memory limits
    }
}


def get_environment_config(environment: str = 'development') -> Dict[str, float]:
    """Get configuration adjustments for specific environment."""
    return ENVIRONMENT_CONFIGS.get(environment, ENVIRONMENT_CONFIGS['development'])