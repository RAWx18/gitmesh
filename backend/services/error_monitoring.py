"""
Error Monitoring and Alerting Service

Provides comprehensive error monitoring, alerting, and analytics
for the Cosmos Web Chat system. Integrates with the error handling
system to provide real-time monitoring and proactive alerting.
"""

import logging
import asyncio
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import redis

import sys
import os

# Add the backend directory to the path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from ..utils.error_handling import ErrorHandler, ErrorCategory, ErrorSeverity
    from ..utils.cosmos_error_handler import CosmosErrorHandler, ChatErrorType
    from .graceful_degradation import get_graceful_degradation_service, ServiceStatus
    from ..config.settings import get_settings
except ImportError:
    try:
        from utils.error_handling import ErrorHandler, ErrorCategory, ErrorSeverity
        from utils.cosmos_error_handler import CosmosErrorHandler, ChatErrorType
        from services.graceful_degradation import get_graceful_degradation_service, ServiceStatus
        from config.settings import get_settings
    except ImportError:
        from error_handling import ErrorHandler, ErrorCategory, ErrorSeverity
        from cosmos_error_handler import CosmosErrorHandler, ChatErrorType
        from graceful_degradation import get_graceful_degradation_service, ServiceStatus
        from settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of alerts."""
    ERROR_RATE_HIGH = "error_rate_high"
    SERVICE_DOWN = "service_down"
    REPEATED_ERRORS = "repeated_errors"
    SYSTEM_DEGRADED = "system_degraded"
    CHAT_FAILURES = "chat_failures"
    MODEL_UNAVAILABLE = "model_unavailable"
    REPOSITORY_ACCESS_ISSUES = "repository_access_issues"


@dataclass
class Alert:
    """Alert information."""
    alert_id: str
    alert_type: AlertType
    level: AlertLevel
    title: str
    description: str
    timestamp: datetime
    details: Dict[str, Any]
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ErrorMetrics:
    """Error metrics for monitoring."""
    total_errors: int
    error_rate: float
    errors_by_category: Dict[str, int]
    errors_by_severity: Dict[str, int]
    top_error_types: List[tuple]
    time_period: str
    timestamp: datetime
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class SystemHealthMetrics:
    """System health metrics."""
    overall_health: str
    service_health: Dict[str, str]
    degradation_level: str
    active_alerts: int
    resolved_alerts: int
    uptime_percentage: float
    timestamp: datetime
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ErrorMonitoringService:
    """
    Error Monitoring and Alerting Service
    
    Monitors error patterns, system health, and generates alerts
    for proactive issue resolution.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the error monitoring service."""
        self.settings = get_settings()
        self.redis_client = redis_client
        self.error_handler = ErrorHandler(redis_client)
        self.cosmos_error_handler = CosmosErrorHandler(redis_client)
        self.degradation_service = get_graceful_degradation_service(redis_client)
        
        # Monitoring configuration
        self.monitoring_config = {
            "error_rate_threshold": 0.05,  # 5% error rate threshold
            "critical_error_threshold": 10,  # 10 critical errors in time window
            "service_check_interval": 60,  # 60 seconds
            "alert_cooldown": 300,  # 5 minutes cooldown between similar alerts
            "metrics_retention_days": 30
        }
        
        # Alert handlers
        self.alert_handlers: List[Callable] = []
        
        # Active alerts tracking
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        
        # Metrics cache
        self.metrics_cache: Dict[str, Any] = {}
        self.last_metrics_update = datetime.now()
        
        # Initialize monitoring
        self._initialize_monitoring()
    
    def _initialize_monitoring(self):
        """Initialize monitoring components."""
        try:
            # Set up default alert handlers
            self.add_alert_handler(self._log_alert)
            
            # Initialize metrics
            self._update_metrics_cache()
            
            logger.info("Error monitoring service initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing monitoring service: {e}")
    
    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add an alert handler function."""
        self.alert_handlers.append(handler)
    
    async def start_monitoring(self):
        """Start the monitoring loop."""
        logger.info("Starting error monitoring loop")
        
        while True:
            try:
                await self._monitoring_cycle()
                await asyncio.sleep(self.monitoring_config["service_check_interval"])
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _monitoring_cycle(self):
        """Execute one monitoring cycle."""
        try:
            # Update metrics
            self._update_metrics_cache()
            
            # Check error rates
            await self._check_error_rates()
            
            # Check system health
            await self._check_system_health()
            
            # Check for repeated errors
            await self._check_repeated_errors()
            
            # Check chat-specific issues
            await self._check_chat_issues()
            
            # Clean up old alerts
            self._cleanup_old_alerts()
            
            # Store metrics
            await self._store_metrics()
            
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}")
    
    def _update_metrics_cache(self):
        """Update the metrics cache."""
        try:
            # Get error statistics
            error_stats = self.error_handler.get_error_statistics()
            chat_stats = self.cosmos_error_handler.get_chat_error_statistics()
            
            # Calculate error rate
            total_requests = error_stats.get("total_errors", 0) + 1000  # Assume some baseline
            error_rate = error_stats.get("total_errors", 0) / total_requests
            
            # Create metrics object
            metrics = ErrorMetrics(
                total_errors=error_stats.get("total_errors", 0),
                error_rate=error_rate,
                errors_by_category=error_stats.get("errors_by_category", {}),
                errors_by_severity={},  # Would be calculated from detailed error data
                top_error_types=error_stats.get("top_errors", []),
                time_period="24h",
                timestamp=datetime.now()
            )
            
            self.metrics_cache["error_metrics"] = metrics
            self.last_metrics_update = datetime.now()
            
        except Exception as e:
            logger.error(f"Error updating metrics cache: {e}")
    
    async def _check_error_rates(self):
        """Check if error rates exceed thresholds."""
        try:
            metrics = self.metrics_cache.get("error_metrics")
            if not metrics:
                return
            
            # Check overall error rate
            if metrics.error_rate > self.monitoring_config["error_rate_threshold"]:
                await self._create_alert(
                    alert_type=AlertType.ERROR_RATE_HIGH,
                    level=AlertLevel.WARNING,
                    title="High Error Rate Detected",
                    description=f"Error rate is {metrics.error_rate:.2%}, above threshold of {self.monitoring_config['error_rate_threshold']:.2%}",
                    details={
                        "current_rate": metrics.error_rate,
                        "threshold": self.monitoring_config["error_rate_threshold"],
                        "total_errors": metrics.total_errors
                    }
                )
            
            # Check critical errors
            critical_errors = sum(
                count for error_type, count in metrics.top_error_types
                if "critical" in error_type.lower() or "system" in error_type.lower()
            )
            
            if critical_errors > self.monitoring_config["critical_error_threshold"]:
                await self._create_alert(
                    alert_type=AlertType.REPEATED_ERRORS,
                    level=AlertLevel.CRITICAL,
                    title="High Critical Error Count",
                    description=f"Detected {critical_errors} critical errors, above threshold of {self.monitoring_config['critical_error_threshold']}",
                    details={
                        "critical_error_count": critical_errors,
                        "threshold": self.monitoring_config["critical_error_threshold"]
                    }
                )
            
        except Exception as e:
            logger.error(f"Error checking error rates: {e}")
    
    async def _check_system_health(self):
        """Check overall system health."""
        try:
            health = await self.degradation_service.get_system_health()
            
            # Check if system is degraded
            if health.get("overall_status") == ServiceStatus.DEGRADED.value:
                await self._create_alert(
                    alert_type=AlertType.SYSTEM_DEGRADED,
                    level=AlertLevel.WARNING,
                    title="System Performance Degraded",
                    description=f"System is running in degraded mode: {health.get('degradation_level', 'unknown')}",
                    details=health
                )
            
            # Check if critical services are down
            services = health.get("services", {})
            for service_name, service_info in services.items():
                if service_info.get("status") == ServiceStatus.UNAVAILABLE.value:
                    await self._create_alert(
                        alert_type=AlertType.SERVICE_DOWN,
                        level=AlertLevel.ERROR,
                        title=f"Service Unavailable: {service_name}",
                        description=f"Critical service {service_name} is unavailable",
                        details={
                            "service": service_name,
                            "service_info": service_info
                        }
                    )
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
    
    async def _check_repeated_errors(self):
        """Check for patterns of repeated errors."""
        try:
            metrics = self.metrics_cache.get("error_metrics")
            if not metrics:
                return
            
            # Look for error types that are occurring frequently
            for error_type, count in metrics.top_error_types[:5]:  # Top 5 errors
                if count > 20:  # More than 20 occurrences
                    await self._create_alert(
                        alert_type=AlertType.REPEATED_ERRORS,
                        level=AlertLevel.WARNING,
                        title=f"Repeated Error Pattern: {error_type}",
                        description=f"Error type '{error_type}' has occurred {count} times",
                        details={
                            "error_type": error_type,
                            "occurrence_count": count
                        }
                    )
            
        except Exception as e:
            logger.error(f"Error checking repeated errors: {e}")
    
    async def _check_chat_issues(self):
        """Check for chat-specific issues."""
        try:
            chat_stats = self.cosmos_error_handler.get_chat_error_statistics()
            
            # Check for high chat failure rate
            chat_errors = chat_stats.get("chat_errors", {})
            total_chat_errors = sum(chat_errors.values())
            
            if total_chat_errors > 50:  # More than 50 chat errors
                await self._create_alert(
                    alert_type=AlertType.CHAT_FAILURES,
                    level=AlertLevel.ERROR,
                    title="High Chat Error Rate",
                    description=f"Detected {total_chat_errors} chat-related errors",
                    details=chat_errors
                )
            
            # Check for model availability issues
            model_errors = chat_errors.get("model_errors", 0)
            if model_errors > 10:
                await self._create_alert(
                    alert_type=AlertType.MODEL_UNAVAILABLE,
                    level=AlertLevel.WARNING,
                    title="AI Model Availability Issues",
                    description=f"Detected {model_errors} AI model errors",
                    details={"model_error_count": model_errors}
                )
            
            # Check for repository access issues
            repo_errors = chat_errors.get("repository_errors", 0)
            if repo_errors > 15:
                await self._create_alert(
                    alert_type=AlertType.REPOSITORY_ACCESS_ISSUES,
                    level=AlertLevel.WARNING,
                    title="Repository Access Issues",
                    description=f"Detected {repo_errors} repository access errors",
                    details={"repository_error_count": repo_errors}
                )
            
        except Exception as e:
            logger.error(f"Error checking chat issues: {e}")
    
    async def _create_alert(
        self,
        alert_type: AlertType,
        level: AlertLevel,
        title: str,
        description: str,
        details: Dict[str, Any]
    ):
        """Create and process a new alert."""
        try:
            # Check if similar alert exists and is in cooldown
            alert_key = f"{alert_type.value}:{title}"
            
            if alert_key in self.active_alerts:
                last_alert = self.active_alerts[alert_key]
                cooldown_period = timedelta(seconds=self.monitoring_config["alert_cooldown"])
                
                if datetime.now() - last_alert.timestamp < cooldown_period:
                    return  # Skip alert due to cooldown
            
            # Create new alert
            alert = Alert(
                alert_id=f"{alert_type.value}_{int(datetime.now().timestamp())}",
                alert_type=alert_type,
                level=level,
                title=title,
                description=description,
                details=details,
                timestamp=datetime.now()
            )
            
            # Store alert
            self.active_alerts[alert_key] = alert
            self.alert_history.append(alert)
            
            # Process alert through handlers
            for handler in self.alert_handlers:
                try:
                    await handler(alert) if asyncio.iscoroutinefunction(handler) else handler(alert)
                except Exception as e:
                    logger.error(f"Error in alert handler: {e}")
            
            # Store alert in Redis for persistence
            if self.redis_client:
                await self._store_alert(alert)
            
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
    
    async def _store_alert(self, alert: Alert):
        """Store alert in Redis."""
        try:
            alert_data = asdict(alert)
            alert_data["timestamp"] = alert.timestamp.isoformat()
            if alert.resolved_at:
                alert_data["resolved_at"] = alert.resolved_at.isoformat()
            
            # Store individual alert
            alert_key = f"cosmos:alert:{alert.alert_id}"
            await asyncio.to_thread(
                self.redis_client.setex,
                alert_key,
                86400 * 7,  # 7 days
                json.dumps(alert_data, default=str)
            )
            
            # Add to alert index
            alert_index_key = f"cosmos:alerts:{datetime.now().strftime('%Y-%m-%d')}"
            await asyncio.to_thread(
                self.redis_client.lpush,
                alert_index_key,
                alert.alert_id
            )
            await asyncio.to_thread(
                self.redis_client.expire,
                alert_index_key,
                86400 * 30  # 30 days
            )
            
        except Exception as e:
            logger.error(f"Error storing alert in Redis: {e}")
    
    async def _store_metrics(self):
        """Store current metrics in Redis."""
        try:
            if not self.redis_client:
                return
            
            metrics = self.metrics_cache.get("error_metrics")
            if not metrics:
                return
            
            metrics_data = asdict(metrics)
            metrics_data["timestamp"] = metrics.timestamp.isoformat()
            
            # Store metrics
            metrics_key = f"cosmos:metrics:{datetime.now().strftime('%Y-%m-%d-%H')}"
            await asyncio.to_thread(
                self.redis_client.setex,
                metrics_key,
                86400 * self.monitoring_config["metrics_retention_days"],
                json.dumps(metrics_data, default=str)
            )
            
        except Exception as e:
            logger.error(f"Error storing metrics: {e}")
    
    def _cleanup_old_alerts(self):
        """Clean up old resolved alerts."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            # Remove old alerts from active alerts
            to_remove = []
            for key, alert in self.active_alerts.items():
                if alert.resolved and alert.resolved_at and alert.resolved_at < cutoff_time:
                    to_remove.append(key)
            
            for key in to_remove:
                del self.active_alerts[key]
            
            # Limit alert history size
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-500:]  # Keep last 500
            
        except Exception as e:
            logger.error(f"Error cleaning up old alerts: {e}")
    
    async def _log_alert(self, alert: Alert):
        """Default alert handler that logs alerts."""
        log_level = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical
        }.get(alert.level, logger.info)
        
        log_level(
            f"ALERT [{alert.level.value.upper()}] {alert.title}: {alert.description}",
            extra={
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "details": alert.details
            }
        )
    
    async def resolve_alert(self, alert_id: str, resolution_note: Optional[str] = None):
        """Resolve an active alert."""
        try:
            # Find and resolve alert
            for key, alert in self.active_alerts.items():
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    alert.resolved_at = datetime.now()
                    
                    if resolution_note:
                        alert.details["resolution_note"] = resolution_note
                    
                    logger.info(f"Alert resolved: {alert.title} ({alert_id})")
                    
                    # Update in Redis
                    if self.redis_client:
                        await self._store_alert(alert)
                    
                    break
            
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get list of active (unresolved) alerts."""
        return [alert for alert in self.active_alerts.values() if not alert.resolved]
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if alert.timestamp >= cutoff_time
        ]
    
    def get_system_health_metrics(self) -> SystemHealthMetrics:
        """Get current system health metrics."""
        try:
            active_alerts = len(self.get_active_alerts())
            resolved_alerts = len([a for a in self.alert_history if a.resolved])
            
            # Calculate uptime percentage (simplified)
            uptime_percentage = max(0, 100 - (active_alerts * 5))  # Rough calculation
            
            return SystemHealthMetrics(
                overall_health="healthy" if active_alerts == 0 else "degraded",
                service_health={},  # Would be populated from degradation service
                degradation_level="none" if active_alerts == 0 else "minimal",
                active_alerts=active_alerts,
                resolved_alerts=resolved_alerts,
                uptime_percentage=uptime_percentage,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error getting system health metrics: {e}")
            return SystemHealthMetrics(
                overall_health="unknown",
                service_health={},
                degradation_level="unknown",
                active_alerts=0,
                resolved_alerts=0,
                uptime_percentage=0,
                timestamp=datetime.now()
            )


# Global monitoring service instance
monitoring_service = None


def get_monitoring_service(redis_client: Optional[redis.Redis] = None) -> ErrorMonitoringService:
    """Get or create the global monitoring service instance."""
    global monitoring_service
    
    if monitoring_service is None:
        monitoring_service = ErrorMonitoringService(redis_client)
    
    return monitoring_service