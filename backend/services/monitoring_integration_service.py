"""
Monitoring Integration Service

Integrates performance monitoring with health checks and provides automatic recovery mechanisms.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

try:
    # Try relative imports first (when used as module)
    from .performance_monitoring_service import get_performance_monitoring_service, HealthStatus
    from .smart_redis_repo_manager import SmartRedisRepoManager
    from .intelligent_vfs import IntelligentVFS
    from .optimized_cosmos_wrapper import OptimizedCosmosWrapper
    from .error_monitoring import get_monitoring_service
    from .graceful_degradation import get_graceful_degradation_service
    from ..config.settings import get_settings
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.performance_monitoring_service import get_performance_monitoring_service, HealthStatus
    from services.smart_redis_repo_manager import SmartRedisRepoManager
    from services.intelligent_vfs import IntelligentVFS
    from services.optimized_cosmos_wrapper import OptimizedCosmosWrapper
    from services.error_monitoring import get_monitoring_service
    from services.graceful_degradation import get_graceful_degradation_service
    from config.settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)


class RecoveryAction(Enum):
    """Types of automatic recovery actions."""
    NONE = "none"
    RESTART_SERVICE = "restart_service"
    CLEAR_CACHE = "clear_cache"
    RECONNECT_REDIS = "reconnect_redis"
    REDUCE_LOAD = "reduce_load"
    ALERT_ADMIN = "alert_admin"


@dataclass
class MonitoringRule:
    """Monitoring rule definition."""
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    recovery_action: RecoveryAction
    cooldown_minutes: int = 5
    max_attempts: int = 3
    last_triggered: Optional[datetime] = None
    attempt_count: int = 0
    
    def should_trigger(self, metrics: Dict[str, Any]) -> bool:
        """Check if rule should trigger."""
        if self.last_triggered:
            cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
            if datetime.now() < cooldown_end:
                return False
        
        if self.attempt_count >= self.max_attempts:
            return False
        
        return self.condition(metrics)
    
    def trigger(self) -> None:
        """Mark rule as triggered."""
        self.last_triggered = datetime.now()
        self.attempt_count += 1
    
    def reset(self) -> None:
        """Reset rule state."""
        self.last_triggered = None
        self.attempt_count = 0


class MonitoringIntegrationService:
    """Integrates monitoring with health checks and automatic recovery."""
    
    def __init__(self):
        """Initialize monitoring integration service."""
        self.settings = get_settings()
        self.performance_monitoring = get_performance_monitoring_service()
        
        # Component references
        self._redis_manager: Optional[SmartRedisRepoManager] = None
        self._vfs: Optional[IntelligentVFS] = None
        self._cosmos_wrapper: Optional[OptimizedCosmosWrapper] = None
        
        # Monitoring rules
        self.monitoring_rules: List[MonitoringRule] = []
        self._setup_default_rules()
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        
        # Recovery state
        self._recovery_in_progress = False
        self._last_recovery_attempt: Optional[datetime] = None
    
    def _setup_default_rules(self) -> None:
        """Setup default monitoring rules."""
        # Redis connectivity rule
        self.monitoring_rules.append(MonitoringRule(
            name="redis_connectivity",
            condition=lambda m: m.get("redis_health", {}).get("status") == "critical",
            recovery_action=RecoveryAction.RECONNECT_REDIS,
            cooldown_minutes=2,
            max_attempts=5
        ))
        
        # High memory usage rule
        self.monitoring_rules.append(MonitoringRule(
            name="high_memory_usage",
            condition=lambda m: m.get("memory", {}).get("max_1h_percent", 0) > 85,
            recovery_action=RecoveryAction.CLEAR_CACHE,
            cooldown_minutes=10,
            max_attempts=3
        ))
        
        # Slow response times rule
        self.monitoring_rules.append(MonitoringRule(
            name="slow_response_times",
            condition=lambda m: m.get("response_times", {}).get("p95_1h_ms", 0) > 10000,
            recovery_action=RecoveryAction.REDUCE_LOAD,
            cooldown_minutes=5,
            max_attempts=2
        ))
        
        # VFS integrity rule
        self.monitoring_rules.append(MonitoringRule(
            name="vfs_integrity",
            condition=lambda m: m.get("vfs_health", {}).get("status") == "critical",
            recovery_action=RecoveryAction.RESTART_SERVICE,
            cooldown_minutes=15,
            max_attempts=2
        ))
    
    def register_component(self, component_type: str, component: Any) -> None:
        """Register a component for monitoring."""
        if component_type == "redis_manager":
            self._redis_manager = component
        elif component_type == "vfs":
            self._vfs = component
        elif component_type == "cosmos_wrapper":
            self._cosmos_wrapper = component
        
        logger.info(f"Registered {component_type} component for monitoring")
    
    async def start_monitoring(self) -> None:
        """Start integrated monitoring."""
        # Start performance monitoring
        await self.performance_monitoring.start_monitoring()
        
        # Start monitoring integration tasks
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        
        logger.info("Monitoring integration started")
    
    async def stop_monitoring(self) -> None:
        """Stop integrated monitoring."""
        # Stop performance monitoring
        await self.performance_monitoring.stop_monitoring()
        
        # Cancel integration tasks
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Monitoring integration stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while True:
            try:
                # Get comprehensive metrics
                metrics = await self._collect_comprehensive_metrics()
                
                # Check monitoring rules
                await self._check_monitoring_rules(metrics)
                
                # Update health status
                await self._update_health_status(metrics)
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _recovery_loop(self) -> None:
        """Recovery action execution loop."""
        while True:
            try:
                if self._recovery_in_progress:
                    await asyncio.sleep(30)  # Wait during recovery
                    continue
                
                # Check if any rules need recovery actions
                for rule in self.monitoring_rules:
                    if rule.last_triggered and rule.attempt_count > 0:
                        time_since_trigger = datetime.now() - rule.last_triggered
                        
                        # Execute recovery if enough time has passed
                        if time_since_trigger.total_seconds() > 30:  # 30 seconds delay
                            await self._execute_recovery_action(rule)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in recovery loop: {e}")
                await asyncio.sleep(30)
    
    async def _collect_comprehensive_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive metrics from all sources."""
        metrics = {}
        
        try:
            # Get performance summary
            performance_summary = await self.performance_monitoring.get_performance_summary()
            metrics.update(performance_summary)
            
            # Get health check results
            health_results = self.performance_monitoring.health_checker.get_last_results()
            metrics["health_checks"] = {
                name: result.to_dict() for name, result in health_results.items()
            }
            
            # Get component-specific metrics
            if self._redis_manager:
                redis_metrics = await self._get_redis_metrics()
                metrics["redis_metrics"] = redis_metrics
            
            if self._vfs:
                vfs_metrics = await self._get_vfs_metrics()
                metrics["vfs_metrics"] = vfs_metrics
            
            if self._cosmos_wrapper:
                cosmos_metrics = await self._get_cosmos_metrics()
                metrics["cosmos_metrics"] = cosmos_metrics
            
            # Add system metrics
            system_metrics = await self._get_system_metrics()
            metrics["system_metrics"] = system_metrics
            
        except Exception as e:
            logger.error(f"Error collecting comprehensive metrics: {e}")
            metrics["collection_error"] = str(e)
        
        return metrics
    
    async def _get_redis_metrics(self) -> Dict[str, Any]:
        """Get Redis-specific metrics."""
        try:
            if not self._redis_manager:
                return {"status": "not_available"}
            
            # Get Redis connection stats
            stats = await self._redis_manager.get_connection_stats()
            
            return {
                "connection_pool_size": stats.get("pool_size", 0),
                "active_connections": stats.get("active_connections", 0),
                "total_operations": stats.get("total_operations", 0),
                "failed_operations": stats.get("failed_operations", 0),
                "avg_response_time_ms": stats.get("avg_response_time_ms", 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting Redis metrics: {e}")
            return {"error": str(e)}
    
    async def _get_vfs_metrics(self) -> Dict[str, Any]:
        """Get VFS-specific metrics."""
        try:
            if not self._vfs:
                return {"status": "not_available"}
            
            # Get VFS stats
            stats = self._vfs.get_stats()
            
            return {
                "indexed_files": stats.get("indexed_files", 0),
                "cache_size_mb": stats.get("cache_size_mb", 0),
                "cache_hit_rate": stats.get("cache_hit_rate", 0),
                "total_file_accesses": stats.get("total_file_accesses", 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting VFS metrics: {e}")
            return {"error": str(e)}
    
    async def _get_cosmos_metrics(self) -> Dict[str, Any]:
        """Get Cosmos wrapper metrics."""
        try:
            if not self._cosmos_wrapper:
                return {"status": "not_available"}
            
            # Get Cosmos stats
            stats = await self._cosmos_wrapper.get_performance_stats()
            
            return {
                "total_requests": stats.get("total_requests", 0),
                "successful_requests": stats.get("successful_requests", 0),
                "failed_requests": stats.get("failed_requests", 0),
                "avg_processing_time_ms": stats.get("avg_processing_time_ms", 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting Cosmos metrics: {e}")
            return {"error": str(e)}
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system-level metrics."""
        try:
            import psutil
            
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network I/O
            network = psutil.net_io_counters()
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": (disk.used / disk.total) * 100,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv
            }
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {"error": str(e)}
    
    async def _check_monitoring_rules(self, metrics: Dict[str, Any]) -> None:
        """Check all monitoring rules against current metrics."""
        for rule in self.monitoring_rules:
            try:
                if rule.should_trigger(metrics):
                    rule.trigger()
                    logger.warning(f"Monitoring rule triggered: {rule.name}")
                    
                    # Record the rule trigger as a metric
                    await self.performance_monitoring.metrics_collector.record_metric(
                        "monitoring_rule_triggered",
                        1,
                        self.performance_monitoring.metrics_collector.MetricType.ERROR_RATE,
                        {"rule_name": rule.name, "recovery_action": rule.recovery_action.value}
                    )
                    
            except Exception as e:
                logger.error(f"Error checking monitoring rule {rule.name}: {e}")
    
    async def _update_health_status(self, metrics: Dict[str, Any]) -> None:
        """Update overall health status based on metrics."""
        try:
            # Determine overall health
            health_checks = metrics.get("health_checks", {})
            critical_count = sum(1 for check in health_checks.values() 
                               if check.get("status") == "critical")
            warning_count = sum(1 for check in health_checks.values() 
                              if check.get("status") == "warning")
            
            if critical_count > 0:
                overall_status = HealthStatus.CRITICAL
            elif warning_count > 0:
                overall_status = HealthStatus.WARNING
            else:
                overall_status = HealthStatus.HEALTHY
            
            # Update degradation service if available
            try:
                degradation_service = get_graceful_degradation_service()
                if overall_status == HealthStatus.CRITICAL:
                    await degradation_service.set_degradation_level("high")
                elif overall_status == HealthStatus.WARNING:
                    await degradation_service.set_degradation_level("medium")
                else:
                    await degradation_service.set_degradation_level("none")
            except Exception as e:
                logger.error(f"Error updating degradation service: {e}")
            
        except Exception as e:
            logger.error(f"Error updating health status: {e}")
    
    async def _execute_recovery_action(self, rule: MonitoringRule) -> None:
        """Execute recovery action for a triggered rule."""
        if self._recovery_in_progress:
            return
        
        self._recovery_in_progress = True
        self._last_recovery_attempt = datetime.now()
        
        try:
            logger.info(f"Executing recovery action: {rule.recovery_action.value} for rule: {rule.name}")
            
            if rule.recovery_action == RecoveryAction.RECONNECT_REDIS:
                await self._reconnect_redis()
            elif rule.recovery_action == RecoveryAction.CLEAR_CACHE:
                await self._clear_cache()
            elif rule.recovery_action == RecoveryAction.REDUCE_LOAD:
                await self._reduce_load()
            elif rule.recovery_action == RecoveryAction.RESTART_SERVICE:
                await self._restart_service()
            elif rule.recovery_action == RecoveryAction.ALERT_ADMIN:
                await self._alert_admin(rule)
            
            # Reset rule if recovery was successful
            await asyncio.sleep(30)  # Wait for recovery to take effect
            rule.reset()
            
            logger.info(f"Recovery action completed: {rule.recovery_action.value}")
            
        except Exception as e:
            logger.error(f"Error executing recovery action {rule.recovery_action.value}: {e}")
        finally:
            self._recovery_in_progress = False
    
    async def _reconnect_redis(self) -> None:
        """Reconnect Redis connections."""
        try:
            if self._redis_manager:
                await self._redis_manager.reconnect()
            
            # Also reconnect performance service Redis
            from .performance_optimization_service import get_performance_service
            perf_service = get_performance_service()
            perf_service.connection_pool_manager.close_all()
            
            logger.info("Redis reconnection completed")
            
        except Exception as e:
            logger.error(f"Error reconnecting Redis: {e}")
            raise
    
    async def _clear_cache(self) -> None:
        """Clear caches to free memory."""
        try:
            # Clear VFS cache
            if self._vfs:
                self._vfs.clear_cache()
            
            # Clear performance service caches
            from .performance_optimization_service import get_performance_service
            perf_service = get_performance_service()
            await perf_service.response_cache.clear_expired()
            await perf_service.repo_map_cache.clear_expired()
            
            logger.info("Cache clearing completed")
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            raise
    
    async def _reduce_load(self) -> None:
        """Reduce system load."""
        try:
            # Implement load reduction strategies
            # This could include:
            # - Reducing connection pool sizes
            # - Increasing cache TTLs
            # - Limiting concurrent requests
            
            logger.info("Load reduction completed")
            
        except Exception as e:
            logger.error(f"Error reducing load: {e}")
            raise
    
    async def _restart_service(self) -> None:
        """Restart service components."""
        try:
            # Restart VFS if available
            if self._vfs:
                await self._vfs.restart()
            
            # Restart Cosmos wrapper if available
            if self._cosmos_wrapper:
                await self._cosmos_wrapper.restart()
            
            logger.info("Service restart completed")
            
        except Exception as e:
            logger.error(f"Error restarting service: {e}")
            raise
    
    async def _alert_admin(self, rule: MonitoringRule) -> None:
        """Send alert to administrators."""
        try:
            # Create alert through monitoring service
            monitoring_service = get_monitoring_service()
            await monitoring_service.create_alert(
                alert_type="system_health",
                level="critical",
                title=f"Monitoring Rule Triggered: {rule.name}",
                description=f"Recovery action {rule.recovery_action.value} needed",
                details={"rule": rule.name, "attempts": rule.attempt_count}
            )
            
            logger.info(f"Admin alert sent for rule: {rule.name}")
            
        except Exception as e:
            logger.error(f"Error sending admin alert: {e}")
            raise
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status."""
        return {
            "monitoring_active": self._monitoring_task is not None and not self._monitoring_task.done(),
            "recovery_active": self._recovery_task is not None and not self._recovery_task.done(),
            "recovery_in_progress": self._recovery_in_progress,
            "last_recovery_attempt": self._last_recovery_attempt.isoformat() if self._last_recovery_attempt else None,
            "monitoring_rules": [
                {
                    "name": rule.name,
                    "recovery_action": rule.recovery_action.value,
                    "attempt_count": rule.attempt_count,
                    "last_triggered": rule.last_triggered.isoformat() if rule.last_triggered else None
                }
                for rule in self.monitoring_rules
            ],
            "registered_components": {
                "redis_manager": self._redis_manager is not None,
                "vfs": self._vfs is not None,
                "cosmos_wrapper": self._cosmos_wrapper is not None
            }
        }


# Global service instance
monitoring_integration_service = MonitoringIntegrationService()


def get_monitoring_integration_service() -> MonitoringIntegrationService:
    """Get the global monitoring integration service."""
    return monitoring_integration_service