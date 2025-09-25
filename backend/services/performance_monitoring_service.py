"""
Performance Monitoring Service

Implements comprehensive performance metrics collection, health checks, and alerting
for the Cosmos optimization system.
"""

import asyncio
import time
import psutil
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum
import redis
import json

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..services.smart_redis_repo_manager import SmartRedisRepoManager
    from ..services.intelligent_vfs import IntelligentVFS
    from ..services.optimized_cosmos_wrapper import OptimizedCosmosWrapper
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from services.smart_redis_repo_manager import SmartRedisRepoManager
    from services.intelligent_vfs import IntelligentVFS
    from services.optimized_cosmos_wrapper import OptimizedCosmosWrapper

# Configure logging
logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of performance metrics."""
    RESPONSE_TIME = "response_time"
    MEMORY_USAGE = "memory_usage"
    REDIS_OPERATION = "redis_operation"
    FILE_ACCESS = "file_access"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class MetricPoint:
    """Individual metric data point."""
    timestamp: datetime
    value: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'metric_type': self.metric_type.value,
            'labels': self.labels
        }


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    component: str
    status: HealthStatus
    message: str
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'component': self.component,
            'status': self.status.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details
        }


@dataclass
class PerformanceAlert:
    """Performance alert definition."""
    name: str
    condition: Callable[[List[MetricPoint]], bool]
    message: str
    severity: str = "warning"
    cooldown_minutes: int = 5
    last_triggered: Optional[datetime] = None
    
    def should_trigger(self, metrics: List[MetricPoint]) -> bool:
        """Check if alert should trigger."""
        if self.last_triggered:
            cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
            if datetime.now() < cooldown_end:
                return False
        
        return self.condition(metrics)
    
    def trigger(self) -> None:
        """Mark alert as triggered."""
        self.last_triggered = datetime.now()


class MetricsCollector:
    """Collects and stores performance metrics."""
    
    def __init__(self, max_points_per_metric: int = 1000):
        """Initialize metrics collector."""
        self.max_points_per_metric = max_points_per_metric
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self._lock = asyncio.Lock()
    
    async def record_metric(
        self, 
        name: str, 
        value: float, 
        metric_type: MetricType,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a metric point."""
        async with self._lock:
            point = MetricPoint(
                timestamp=datetime.now(),
                value=value,
                metric_type=metric_type,
                labels=labels or {}
            )
            self._metrics[name].append(point)
    
    async def get_metrics(
        self, 
        name: str, 
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[MetricPoint]:
        """Get metrics for a given name."""
        async with self._lock:
            points = list(self._metrics.get(name, []))
            
            if since:
                points = [p for p in points if p.timestamp >= since]
            
            if limit:
                points = points[-limit:]
            
            return points
    
    async def get_all_metric_names(self) -> List[str]:
        """Get all metric names."""
        async with self._lock:
            return list(self._metrics.keys())
    
    async def calculate_average(
        self, 
        name: str, 
        since: Optional[datetime] = None
    ) -> Optional[float]:
        """Calculate average value for a metric."""
        points = await self.get_metrics(name, since)
        if not points:
            return None
        
        return sum(p.value for p in points) / len(points)
    
    async def calculate_percentile(
        self, 
        name: str, 
        percentile: float,
        since: Optional[datetime] = None
    ) -> Optional[float]:
        """Calculate percentile for a metric."""
        points = await self.get_metrics(name, since)
        if not points:
            return None
        
        values = sorted([p.value for p in points])
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]


class ResponseTimeTracker:
    """Tracks response times for chat operations."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize response time tracker."""
        self.metrics_collector = metrics_collector
        self._active_requests: Dict[str, float] = {}
    
    def start_request(self, request_id: str) -> None:
        """Start tracking a request."""
        self._active_requests[request_id] = time.time()
    
    async def end_request(
        self, 
        request_id: str, 
        labels: Optional[Dict[str, str]] = None
    ) -> Optional[float]:
        """End tracking a request and record metrics."""
        if request_id not in self._active_requests:
            return None
        
        start_time = self._active_requests.pop(request_id)
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        await self.metrics_collector.record_metric(
            "chat_response_time_ms",
            response_time,
            MetricType.RESPONSE_TIME,
            labels
        )
        
        return response_time
    
    async def get_average_response_time(
        self, 
        since: Optional[datetime] = None
    ) -> Optional[float]:
        """Get average response time."""
        return await self.metrics_collector.calculate_average(
            "chat_response_time_ms", 
            since
        )


class MemoryMonitor:
    """Monitors memory usage for large repository processing."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize memory monitor."""
        self.metrics_collector = metrics_collector
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self, interval_seconds: int = 30) -> None:
        """Start continuous memory monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds)
        )
    
    async def stop_monitoring(self) -> None:
        """Stop memory monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitor_loop(self, interval_seconds: int) -> None:
        """Memory monitoring loop."""
        while self._monitoring:
            try:
                # Get current process memory usage
                process = psutil.Process()
                memory_info = process.memory_info()
                
                # Record RSS memory usage in MB
                await self.metrics_collector.record_metric(
                    "memory_usage_mb",
                    memory_info.rss / 1024 / 1024,
                    MetricType.MEMORY_USAGE,
                    {"type": "rss"}
                )
                
                # Record VMS memory usage in MB
                await self.metrics_collector.record_metric(
                    "memory_usage_mb",
                    memory_info.vms / 1024 / 1024,
                    MetricType.MEMORY_USAGE,
                    {"type": "vms"}
                )
                
                # Record memory percentage
                memory_percent = process.memory_percent()
                await self.metrics_collector.record_metric(
                    "memory_usage_percent",
                    memory_percent,
                    MetricType.MEMORY_USAGE,
                    {"type": "percent"}
                )
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory monitoring: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def record_repository_memory_usage(
        self, 
        repo_name: str, 
        operation: str
    ) -> None:
        """Record memory usage for a specific repository operation."""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            await self.metrics_collector.record_metric(
                "repository_memory_usage_mb",
                memory_mb,
                MetricType.MEMORY_USAGE,
                {
                    "repo_name": repo_name,
                    "operation": operation
                }
            )
        except Exception as e:
            logger.error(f"Error recording repository memory usage: {e}")


class RedisMetricsTracker:
    """Tracks Redis operation performance metrics."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize Redis metrics tracker."""
        self.metrics_collector = metrics_collector
    
    async def track_operation(
        self, 
        operation: str, 
        duration_ms: float,
        success: bool = True,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track a Redis operation."""
        operation_labels = {
            "operation": operation,
            "success": str(success).lower(),
            **(labels or {})
        }
        
        # Record operation duration
        await self.metrics_collector.record_metric(
            "redis_operation_duration_ms",
            duration_ms,
            MetricType.REDIS_OPERATION,
            operation_labels
        )
        
        # Record operation count
        await self.metrics_collector.record_metric(
            "redis_operation_count",
            1,
            MetricType.REDIS_OPERATION,
            operation_labels
        )
    
    async def get_operation_stats(
        self, 
        operation: str,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get statistics for a Redis operation."""
        # Get all operation metrics
        duration_points = await self.metrics_collector.get_metrics(
            "redis_operation_duration_ms", 
            since
        )
        
        # Filter by operation
        operation_durations = [
            p.value for p in duration_points 
            if p.labels.get("operation") == operation
        ]
        
        if not operation_durations:
            return {"operation": operation, "count": 0}
        
        return {
            "operation": operation,
            "count": len(operation_durations),
            "avg_duration_ms": sum(operation_durations) / len(operation_durations),
            "min_duration_ms": min(operation_durations),
            "max_duration_ms": max(operation_durations),
            "p95_duration_ms": sorted(operation_durations)[int(len(operation_durations) * 0.95)]
        }


class FileAccessTracker:
    """Tracks file access time measurements and optimization."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize file access tracker."""
        self.metrics_collector = metrics_collector
    
    async def track_file_access(
        self, 
        file_path: str, 
        access_time_ms: float,
        cache_hit: bool = False,
        file_size_bytes: Optional[int] = None
    ) -> None:
        """Track file access performance."""
        labels = {
            "cache_hit": str(cache_hit).lower(),
            "file_extension": file_path.split('.')[-1] if '.' in file_path else "none"
        }
        
        if file_size_bytes is not None:
            labels["size_category"] = self._categorize_file_size(file_size_bytes)
        
        await self.metrics_collector.record_metric(
            "file_access_time_ms",
            access_time_ms,
            MetricType.FILE_ACCESS,
            labels
        )
        
        # Track cache hit rate
        await self.metrics_collector.record_metric(
            "file_cache_hit_rate",
            1.0 if cache_hit else 0.0,
            MetricType.FILE_ACCESS,
            {"file_path": file_path}
        )
    
    def _categorize_file_size(self, size_bytes: int) -> str:
        """Categorize file size for metrics."""
        if size_bytes < 1024:  # < 1KB
            return "small"
        elif size_bytes < 1024 * 1024:  # < 1MB
            return "medium"
        elif size_bytes < 10 * 1024 * 1024:  # < 10MB
            return "large"
        else:
            return "very_large"
    
    async def get_cache_hit_rate(
        self, 
        since: Optional[datetime] = None
    ) -> Optional[float]:
        """Get overall cache hit rate."""
        return await self.metrics_collector.calculate_average(
            "file_cache_hit_rate", 
            since
        )


class HealthChecker:
    """Performs health checks on system components."""
    
    def __init__(self):
        """Initialize health checker."""
        self._health_checks: Dict[str, Callable] = {}
        self._last_results: Dict[str, HealthCheckResult] = {}
    
    def register_health_check(
        self, 
        component: str, 
        check_func: Callable[[], HealthCheckResult]
    ) -> None:
        """Register a health check function."""
        self._health_checks[component] = check_func
    
    async def run_health_check(self, component: str) -> HealthCheckResult:
        """Run health check for a specific component."""
        if component not in self._health_checks:
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNKNOWN,
                message=f"No health check registered for {component}",
                timestamp=datetime.now()
            )
        
        try:
            check_func = self._health_checks[component]
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            
            self._last_results[component] = result
            return result
            
        except Exception as e:
            result = HealthCheckResult(
                component=component,
                status=HealthStatus.CRITICAL,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
            self._last_results[component] = result
            return result
    
    async def run_all_health_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all registered health checks."""
        results = {}
        
        for component in self._health_checks:
            results[component] = await self.run_health_check(component)
        
        return results
    
    def get_last_results(self) -> Dict[str, HealthCheckResult]:
        """Get last health check results."""
        return self._last_results.copy()


class PerformanceMonitoringService:
    """Main performance monitoring service."""
    
    def __init__(self):
        """Initialize performance monitoring service."""
        self.settings = get_settings()
        
        # Initialize components
        self.metrics_collector = MetricsCollector()
        self.response_time_tracker = ResponseTimeTracker(self.metrics_collector)
        self.memory_monitor = MemoryMonitor(self.metrics_collector)
        self.redis_metrics_tracker = RedisMetricsTracker(self.metrics_collector)
        self.file_access_tracker = FileAccessTracker(self.metrics_collector)
        self.health_checker = HealthChecker()
        
        # Performance alerts
        self.alerts: List[PerformanceAlert] = []
        self._setup_default_alerts()
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._alert_task: Optional[asyncio.Task] = None
        
        # Register default health checks
        self._register_default_health_checks()
    
    def _setup_default_alerts(self) -> None:
        """Setup default performance alerts."""
        # Response time alert
        self.alerts.append(PerformanceAlert(
            name="high_response_time",
            condition=lambda metrics: any(m.value > 5000 for m in metrics[-10:]),  # > 5 seconds
            message="Chat response time exceeded 5 seconds",
            severity="warning",
            cooldown_minutes=5
        ))
        
        # Memory usage alert
        self.alerts.append(PerformanceAlert(
            name="high_memory_usage",
            condition=lambda metrics: any(m.value > 80 for m in metrics[-5:]),  # > 80%
            message="Memory usage exceeded 80%",
            severity="critical",
            cooldown_minutes=10
        ))
        
        # Redis operation alert
        self.alerts.append(PerformanceAlert(
            name="slow_redis_operations",
            condition=lambda metrics: any(m.value > 1000 for m in metrics[-20:]),  # > 1 second
            message="Redis operations are taking longer than 1 second",
            severity="warning",
            cooldown_minutes=5
        ))
    
    def _register_default_health_checks(self) -> None:
        """Register default health checks."""
        self.health_checker.register_health_check("redis", self._check_redis_health)
        self.health_checker.register_health_check("memory", self._check_memory_health)
        self.health_checker.register_health_check("system", self._check_system_health)
    
    async def _check_redis_health(self) -> HealthCheckResult:
        """Check Redis connectivity and performance."""
        try:
            # Try to get a Redis client and perform a simple operation
            from .performance_optimization_service import get_performance_service
            perf_service = get_performance_service()
            client = perf_service.get_redis_client()
            
            start_time = time.time()
            client.ping()
            ping_time = (time.time() - start_time) * 1000
            
            if ping_time > 100:  # > 100ms
                return HealthCheckResult(
                    component="redis",
                    status=HealthStatus.WARNING,
                    message=f"Redis ping time is high: {ping_time:.2f}ms",
                    timestamp=datetime.now(),
                    details={"ping_time_ms": ping_time}
                )
            
            return HealthCheckResult(
                component="redis",
                status=HealthStatus.HEALTHY,
                message=f"Redis is healthy (ping: {ping_time:.2f}ms)",
                timestamp=datetime.now(),
                details={"ping_time_ms": ping_time}
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="redis",
                status=HealthStatus.CRITICAL,
                message=f"Redis connection failed: {str(e)}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
    
    async def _check_memory_health(self) -> HealthCheckResult:
        """Check system memory health."""
        try:
            process = psutil.Process()
            memory_percent = process.memory_percent()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_percent > 90:
                status = HealthStatus.CRITICAL
                message = f"Critical memory usage: {memory_percent:.1f}% ({memory_mb:.1f}MB)"
            elif memory_percent > 75:
                status = HealthStatus.WARNING
                message = f"High memory usage: {memory_percent:.1f}% ({memory_mb:.1f}MB)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory_percent:.1f}% ({memory_mb:.1f}MB)"
            
            return HealthCheckResult(
                component="memory",
                status=status,
                message=message,
                timestamp=datetime.now(),
                details={
                    "memory_percent": memory_percent,
                    "memory_mb": memory_mb
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="memory",
                status=HealthStatus.CRITICAL,
                message=f"Memory check failed: {str(e)}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
    
    async def _check_system_health(self) -> HealthCheckResult:
        """Check overall system health."""
        try:
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Check disk usage
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            
            issues = []
            if cpu_percent > 90:
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")
            if disk_percent > 90:
                issues.append(f"High disk usage: {disk_percent:.1f}%")
            
            if issues:
                status = HealthStatus.WARNING if len(issues) == 1 else HealthStatus.CRITICAL
                message = "; ".join(issues)
            else:
                status = HealthStatus.HEALTHY
                message = f"System healthy (CPU: {cpu_percent:.1f}%, Disk: {disk_percent:.1f}%)"
            
            return HealthCheckResult(
                component="system",
                status=status,
                message=message,
                timestamp=datetime.now(),
                details={
                    "cpu_percent": cpu_percent,
                    "disk_percent": disk_percent
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="system",
                status=HealthStatus.CRITICAL,
                message=f"System check failed: {str(e)}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
    
    async def start_monitoring(self) -> None:
        """Start performance monitoring."""
        # Start memory monitoring
        await self.memory_monitor.start_monitoring(interval_seconds=30)
        
        # Start background monitoring task
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Start alert checking task
        self._alert_task = asyncio.create_task(self._alert_loop())
        
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        # Stop memory monitoring
        await self.memory_monitor.stop_monitoring()
        
        # Cancel background tasks
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._alert_task:
            self._alert_task.cancel()
            try:
                await self._alert_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Performance monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while True:
            try:
                # Run health checks every 5 minutes
                await self.health_checker.run_all_health_checks()
                
                # Record throughput metrics
                await self._record_throughput_metrics()
                
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _alert_loop(self) -> None:
        """Background alert checking loop."""
        while True:
            try:
                await self._check_alerts()
                await asyncio.sleep(60)  # Check alerts every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert loop: {e}")
                await asyncio.sleep(60)
    
    async def _record_throughput_metrics(self) -> None:
        """Record throughput metrics."""
        try:
            # Get recent response time metrics to calculate throughput
            recent_responses = await self.metrics_collector.get_metrics(
                "chat_response_time_ms",
                since=datetime.now() - timedelta(minutes=5)
            )
            
            throughput = len(recent_responses) / 5.0  # requests per minute
            
            await self.metrics_collector.record_metric(
                "throughput_rpm",
                throughput,
                MetricType.THROUGHPUT
            )
            
        except Exception as e:
            logger.error(f"Error recording throughput metrics: {e}")
    
    async def _check_alerts(self) -> None:
        """Check all performance alerts."""
        for alert in self.alerts:
            try:
                # Get recent metrics for the alert
                if alert.name == "high_response_time":
                    metrics = await self.metrics_collector.get_metrics(
                        "chat_response_time_ms",
                        since=datetime.now() - timedelta(minutes=10)
                    )
                elif alert.name == "high_memory_usage":
                    metrics = await self.metrics_collector.get_metrics(
                        "memory_usage_percent",
                        since=datetime.now() - timedelta(minutes=5)
                    )
                elif alert.name == "slow_redis_operations":
                    metrics = await self.metrics_collector.get_metrics(
                        "redis_operation_duration_ms",
                        since=datetime.now() - timedelta(minutes=10)
                    )
                else:
                    continue
                
                if alert.should_trigger(metrics):
                    alert.trigger()
                    await self._handle_alert(alert, metrics)
                    
            except Exception as e:
                logger.error(f"Error checking alert {alert.name}: {e}")
    
    async def _handle_alert(self, alert: PerformanceAlert, metrics: List[MetricPoint]) -> None:
        """Handle triggered alert."""
        logger.warning(f"Performance alert triggered: {alert.name} - {alert.message}")
        
        # Record alert as a metric
        await self.metrics_collector.record_metric(
            "performance_alerts",
            1,
            MetricType.ERROR_RATE,
            {
                "alert_name": alert.name,
                "severity": alert.severity
            }
        )
        
        # Here you could integrate with external alerting systems
        # like Slack, email, PagerDuty, etc.
    
    # Public API methods
    
    async def record_chat_response_time(
        self, 
        request_id: str, 
        response_time_ms: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record chat response time."""
        await self.metrics_collector.record_metric(
            "chat_response_time_ms",
            response_time_ms,
            MetricType.RESPONSE_TIME,
            labels
        )
    
    async def record_redis_operation(
        self, 
        operation: str, 
        duration_ms: float,
        success: bool = True
    ) -> None:
        """Record Redis operation metrics."""
        await self.redis_metrics_tracker.track_operation(
            operation, 
            duration_ms, 
            success
        )
    
    async def record_file_access(
        self, 
        file_path: str, 
        access_time_ms: float,
        cache_hit: bool = False,
        file_size_bytes: Optional[int] = None
    ) -> None:
        """Record file access metrics."""
        await self.file_access_tracker.track_file_access(
            file_path, 
            access_time_ms, 
            cache_hit, 
            file_size_bytes
        )
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)
        
        # Response time metrics
        avg_response_time_1h = await self.metrics_collector.calculate_average(
            "chat_response_time_ms", last_hour
        )
        p95_response_time_1h = await self.metrics_collector.calculate_percentile(
            "chat_response_time_ms", 95, last_hour
        )
        
        # Memory metrics
        avg_memory_1h = await self.metrics_collector.calculate_average(
            "memory_usage_percent", last_hour
        )
        max_memory_1h = await self.metrics_collector.calculate_percentile(
            "memory_usage_percent", 100, last_hour
        )
        
        # Cache hit rate
        cache_hit_rate = await self.file_access_tracker.get_cache_hit_rate(last_hour)
        
        # Health status
        health_results = self.health_checker.get_last_results()
        
        return {
            "response_times": {
                "avg_1h_ms": avg_response_time_1h,
                "p95_1h_ms": p95_response_time_1h
            },
            "memory": {
                "avg_1h_percent": avg_memory_1h,
                "max_1h_percent": max_memory_1h
            },
            "cache": {
                "hit_rate_1h": cache_hit_rate
            },
            "health": {
                component: result.to_dict() 
                for component, result in health_results.items()
            },
            "timestamp": now.isoformat()
        }


# Global service instance
performance_monitoring_service = PerformanceMonitoringService()


def get_performance_monitoring_service() -> PerformanceMonitoringService:
    """Get the global performance monitoring service."""
    return performance_monitoring_service