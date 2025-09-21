"""
Monitoring and Alerting Configuration for Cosmos Web Chat Integration

This module provides comprehensive monitoring, metrics collection,
and alerting configuration for production deployment.
"""

import os
from typing import Dict, Any, List, Optional
from pydantic import BaseSettings, Field
from enum import Enum
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)


class MetricType(str, Enum):
    """Types of metrics to collect."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MonitoringSettings(BaseSettings):
    """Monitoring and alerting configuration."""
    
    # General Monitoring
    monitoring_enabled: bool = Field(default=True, env="MONITORING_ENABLED")
    metrics_collection_interval: int = Field(default=60, env="METRICS_COLLECTION_INTERVAL")
    metrics_retention_days: int = Field(default=30, env="METRICS_RETENTION_DAYS")
    
    # Health Check Configuration
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    health_check_timeout: int = Field(default=10, env="HEALTH_CHECK_TIMEOUT")
    
    # Performance Monitoring
    performance_monitoring_enabled: bool = Field(default=True, env="PERFORMANCE_MONITORING_ENABLED")
    slow_query_threshold_ms: int = Field(default=1000, env="SLOW_QUERY_THRESHOLD_MS")
    memory_usage_threshold_percent: int = Field(default=80, env="MEMORY_USAGE_THRESHOLD_PERCENT")
    cpu_usage_threshold_percent: int = Field(default=80, env="CPU_USAGE_THRESHOLD_PERCENT")
    
    # Error Monitoring
    error_rate_threshold_percent: float = Field(default=5.0, env="ERROR_RATE_THRESHOLD_PERCENT")
    error_count_threshold: int = Field(default=10, env="ERROR_COUNT_THRESHOLD")
    
    # Chat-Specific Monitoring
    chat_response_time_threshold_ms: int = Field(default=5000, env="CHAT_RESPONSE_TIME_THRESHOLD_MS")
    chat_session_timeout_threshold_minutes: int = Field(default=30, env="CHAT_SESSION_TIMEOUT_THRESHOLD_MINUTES")
    max_concurrent_sessions_threshold: int = Field(default=100, env="MAX_CONCURRENT_SESSIONS_THRESHOLD")
    
    # Redis Monitoring
    redis_connection_threshold: int = Field(default=80, env="REDIS_CONNECTION_THRESHOLD")
    redis_memory_threshold_percent: int = Field(default=80, env="REDIS_MEMORY_THRESHOLD_PERCENT")
    redis_latency_threshold_ms: int = Field(default=100, env="REDIS_LATENCY_THRESHOLD_MS")
    
    # AI Model Monitoring
    ai_model_response_time_threshold_ms: int = Field(default=10000, env="AI_MODEL_RESPONSE_TIME_THRESHOLD_MS")
    ai_model_error_rate_threshold_percent: float = Field(default=10.0, env="AI_MODEL_ERROR_RATE_THRESHOLD_PERCENT")
    ai_model_token_usage_threshold: int = Field(default=1000000, env="AI_MODEL_TOKEN_USAGE_THRESHOLD")
    
    # Alerting Configuration
    alerting_enabled: bool = Field(default=True, env="ALERTING_ENABLED")
    alert_webhook_url: Optional[str] = Field(default=None, env="ALERT_WEBHOOK_URL")
    alert_email_recipients: List[str] = Field(default_factory=list, env="ALERT_EMAIL_RECIPIENTS")
    alert_cooldown_minutes: int = Field(default=15, env="ALERT_COOLDOWN_MINUTES")
    
    def get_metrics_config(self) -> Dict[str, Any]:
        """Get metrics collection configuration."""
        return {
            "enabled": self.monitoring_enabled,
            "collection_interval": self.metrics_collection_interval,
            "retention_days": self.metrics_retention_days,
            "metrics": {
                # System Metrics
                "system.cpu_usage": {
                    "type": MetricType.GAUGE,
                    "threshold": self.cpu_usage_threshold_percent,
                    "unit": "percent"
                },
                "system.memory_usage": {
                    "type": MetricType.GAUGE,
                    "threshold": self.memory_usage_threshold_percent,
                    "unit": "percent"
                },
                
                # Application Metrics
                "app.request_count": {
                    "type": MetricType.COUNTER,
                    "labels": ["method", "endpoint", "status_code"]
                },
                "app.request_duration": {
                    "type": MetricType.HISTOGRAM,
                    "threshold": self.slow_query_threshold_ms,
                    "unit": "milliseconds"
                },
                "app.error_rate": {
                    "type": MetricType.GAUGE,
                    "threshold": self.error_rate_threshold_percent,
                    "unit": "percent"
                },
                
                # Chat Metrics
                "chat.active_sessions": {
                    "type": MetricType.GAUGE,
                    "threshold": self.max_concurrent_sessions_threshold
                },
                "chat.message_count": {
                    "type": MetricType.COUNTER,
                    "labels": ["session_id", "user_tier"]
                },
                "chat.response_time": {
                    "type": MetricType.HISTOGRAM,
                    "threshold": self.chat_response_time_threshold_ms,
                    "unit": "milliseconds"
                },
                "chat.context_files_count": {
                    "type": MetricType.GAUGE,
                    "labels": ["session_id"]
                },
                "chat.conversion_rate": {
                    "type": MetricType.GAUGE,
                    "unit": "percent"
                },
                
                # Redis Metrics
                "redis.connections_active": {
                    "type": MetricType.GAUGE,
                    "threshold": self.redis_connection_threshold
                },
                "redis.memory_usage": {
                    "type": MetricType.GAUGE,
                    "threshold": self.redis_memory_threshold_percent,
                    "unit": "percent"
                },
                "redis.latency": {
                    "type": MetricType.HISTOGRAM,
                    "threshold": self.redis_latency_threshold_ms,
                    "unit": "milliseconds"
                },
                "redis.cache_hit_rate": {
                    "type": MetricType.GAUGE,
                    "unit": "percent"
                },
                
                # AI Model Metrics
                "ai.model_requests": {
                    "type": MetricType.COUNTER,
                    "labels": ["model", "user_tier"]
                },
                "ai.model_response_time": {
                    "type": MetricType.HISTOGRAM,
                    "threshold": self.ai_model_response_time_threshold_ms,
                    "unit": "milliseconds"
                },
                "ai.model_error_rate": {
                    "type": MetricType.GAUGE,
                    "threshold": self.ai_model_error_rate_threshold_percent,
                    "unit": "percent"
                },
                "ai.token_usage": {
                    "type": MetricType.COUNTER,
                    "threshold": self.ai_model_token_usage_threshold,
                    "labels": ["model", "user_tier"]
                },
                
                # Security Metrics
                "security.failed_auth_attempts": {
                    "type": MetricType.COUNTER,
                    "labels": ["user_id", "ip_address"]
                },
                "security.rate_limit_violations": {
                    "type": MetricType.COUNTER,
                    "labels": ["user_id", "endpoint"]
                },
                "security.suspicious_activity": {
                    "type": MetricType.COUNTER,
                    "labels": ["type", "severity"]
                }
            }
        }
    
    def get_alert_rules(self) -> List[Dict[str, Any]]:
        """Get alerting rules configuration."""
        return [
            {
                "name": "high_error_rate",
                "condition": f"error_rate > {self.error_rate_threshold_percent}",
                "severity": AlertSeverity.HIGH,
                "message": "Error rate is above threshold",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "high_cpu_usage",
                "condition": f"cpu_usage > {self.cpu_usage_threshold_percent}",
                "severity": AlertSeverity.MEDIUM,
                "message": "CPU usage is above threshold",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "high_memory_usage",
                "condition": f"memory_usage > {self.memory_usage_threshold_percent}",
                "severity": AlertSeverity.MEDIUM,
                "message": "Memory usage is above threshold",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "slow_chat_responses",
                "condition": f"chat_response_time > {self.chat_response_time_threshold_ms}",
                "severity": AlertSeverity.MEDIUM,
                "message": "Chat response times are slow",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "too_many_concurrent_sessions",
                "condition": f"active_sessions > {self.max_concurrent_sessions_threshold}",
                "severity": AlertSeverity.HIGH,
                "message": "Too many concurrent chat sessions",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "redis_connection_issues",
                "condition": f"redis_connections_active > {self.redis_connection_threshold}",
                "severity": AlertSeverity.HIGH,
                "message": "Redis connection pool is nearly exhausted",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "ai_model_errors",
                "condition": f"ai_model_error_rate > {self.ai_model_error_rate_threshold_percent}",
                "severity": AlertSeverity.HIGH,
                "message": "AI model error rate is high",
                "cooldown_minutes": self.alert_cooldown_minutes
            },
            {
                "name": "security_threats",
                "condition": "failed_auth_attempts > 10 OR rate_limit_violations > 5",
                "severity": AlertSeverity.CRITICAL,
                "message": "Potential security threat detected",
                "cooldown_minutes": 5  # Shorter cooldown for security alerts
            }
        ]
    
    def get_health_checks(self) -> List[Dict[str, Any]]:
        """Get health check configuration."""
        return [
            {
                "name": "database_connection",
                "endpoint": "/api/v1/health/database",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "critical": True
            },
            {
                "name": "redis_connection",
                "endpoint": "/api/v1/health/redis",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "critical": True
            },
            {
                "name": "ai_model_availability",
                "endpoint": "/api/v1/health/ai-models",
                "timeout": self.health_check_timeout * 2,  # AI models may be slower
                "interval": self.health_check_interval * 2,
                "critical": False
            },
            {
                "name": "cosmos_chat_service",
                "endpoint": "/api/v1/cosmos/chat/health",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "critical": False
            },
            {
                "name": "session_persistence",
                "endpoint": "/api/v1/health/sessions",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "critical": False
            }
        ]
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """Get monitoring dashboard configuration."""
        return {
            "title": "Cosmos Web Chat Integration - Production Monitoring",
            "refresh_interval": self.metrics_collection_interval,
            "panels": [
                {
                    "title": "System Overview",
                    "metrics": ["system.cpu_usage", "system.memory_usage", "app.request_count"],
                    "type": "graph"
                },
                {
                    "title": "Chat Performance",
                    "metrics": ["chat.active_sessions", "chat.response_time", "chat.message_count"],
                    "type": "graph"
                },
                {
                    "title": "AI Model Performance",
                    "metrics": ["ai.model_response_time", "ai.model_error_rate", "ai.token_usage"],
                    "type": "graph"
                },
                {
                    "title": "Redis Performance",
                    "metrics": ["redis.connections_active", "redis.memory_usage", "redis.cache_hit_rate"],
                    "type": "graph"
                },
                {
                    "title": "Error Rates",
                    "metrics": ["app.error_rate", "ai.model_error_rate"],
                    "type": "graph"
                },
                {
                    "title": "Security Metrics",
                    "metrics": ["security.failed_auth_attempts", "security.rate_limit_violations"],
                    "type": "table"
                }
            ]
        }


# Global monitoring settings instance
monitoring_settings = MonitoringSettings()


def get_monitoring_settings() -> MonitoringSettings:
    """Get the global monitoring settings instance."""
    return monitoring_settings


def is_monitoring_enabled() -> bool:
    """Check if monitoring is enabled."""
    return monitoring_settings.monitoring_enabled


def get_metrics_config() -> Dict[str, Any]:
    """Get metrics configuration."""
    return monitoring_settings.get_metrics_config()


def get_alert_rules() -> List[Dict[str, Any]]:
    """Get alert rules."""
    return monitoring_settings.get_alert_rules()


def get_health_checks() -> List[Dict[str, Any]]:
    """Get health check configuration."""
    return monitoring_settings.get_health_checks()