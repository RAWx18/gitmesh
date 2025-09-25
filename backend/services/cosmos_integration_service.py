"""
Cosmos Integration Service - Final Production Integration

This service integrates all Cosmos Web Chat components into the main application,
providing a unified interface for production deployment with feature flags,
monitoring, and graceful degradation.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import redis
from contextlib import asynccontextmanager

from ..config.production import get_production_settings, FeatureFlag, is_feature_enabled
from ..config.deployment import get_deployment_settings
from ..config.monitoring import get_monitoring_settings
from ..services.cosmos_web_service import CosmosWebService
from ..services.enhanced_session_service import EnhancedSessionService
from ..services.tier_access_service import TierAccessService
from ..services.cache_management_service import CacheManagementService
from ..services.navigation_cache_manager import NavigationCacheManager
from ..services.error_monitoring import get_monitoring_service
from ..services.graceful_degradation import get_graceful_degradation_service
from ..services.chat_analytics_service import ChatAnalyticsService
from ..services.cosmos_compatibility_layer import get_compatibility_layer, CosmosCompatibilityLayer
from ..utils.audit_logging import AuditLogger
from ..utils.error_handling import ErrorHandler

logger = logging.getLogger(__name__)


class CosmosIntegrationService:
    """
    Main integration service that coordinates all Cosmos Web Chat components
    for production deployment with feature flags and monitoring.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the integration service."""
        self.redis_client = redis_client
        self.production_settings = get_production_settings()
        self.deployment_settings = get_deployment_settings()
        self.monitoring_settings = get_monitoring_settings()
        
        # Core services
        self.cosmos_web_service: Optional[CosmosWebService] = None
        self.session_service: Optional[EnhancedSessionService] = None
        self.tier_access_service: Optional[TierAccessService] = None
        self.cache_management_service: Optional[CacheManagementService] = None
        self.navigation_cache_manager: Optional[NavigationCacheManager] = None
        self.analytics_service: Optional[ChatAnalyticsService] = None
        
        # Compatibility layer for backward compatibility and migration
        self.compatibility_layer: Optional[CosmosCompatibilityLayer] = None
        
        # Monitoring and error handling
        self.monitoring_service = get_monitoring_service(redis_client)
        self.degradation_service = get_graceful_degradation_service(redis_client)
        self.error_handler = ErrorHandler(redis_client)
        self.audit_logger = AuditLogger(redis_client)
        
        # Service status
        self.is_initialized = False
        self.is_healthy = False
        self.initialization_errors: List[str] = []
        
        # Feature flag cache
        self._feature_cache: Dict[str, bool] = {}
        self._last_feature_update = datetime.now()
    
    async def initialize(self) -> bool:
        """Initialize all services and components."""
        try:
            logger.info("Initializing Cosmos Integration Service...")
            
            # Check if Cosmos Chat is enabled
            if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
                logger.info("Cosmos Chat is disabled via feature flag")
                return True
            
            # Initialize core services
            await self._initialize_core_services()
            
            # Initialize monitoring
            await self._initialize_monitoring()
            
            # Start background tasks
            await self._start_background_tasks()
            
            # Perform health checks
            await self._perform_initial_health_checks()
            
            self.is_initialized = True
            self.is_healthy = True
            
            logger.info("Cosmos Integration Service initialized successfully")
            
            # Log initialization metrics
            await self.audit_logger.log_system_event(
                event_type="cosmos_integration_initialized",
                details={
                    "environment": self.production_settings.environment.value,
                    "deployment_type": self.deployment_settings.deployment_type.value,
                    "enabled_features": [
                        flag.value for flag, enabled in self.production_settings.feature_flags.items()
                        if enabled
                    ]
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos Integration Service: {e}")
            self.initialization_errors.append(str(e))
            self.is_healthy = False
            
            # Log initialization failure
            await self.audit_logger.log_system_event(
                event_type="cosmos_integration_failed",
                details={"error": str(e)},
                severity="error"
            )
            
            return False
    
    async def _initialize_core_services(self):
        """Initialize core Cosmos services with optimized components."""
        try:
            # Initialize session service
            if is_feature_enabled(FeatureFlag.SESSION_PERSISTENCE):
                self.session_service = EnhancedSessionService(self.redis_client)
                await self.session_service.initialize()
                logger.info("Session service initialized")
            
            # Initialize tier access service
            if is_feature_enabled(FeatureFlag.TIER_ACCESS_CONTROL):
                self.tier_access_service = TierAccessService(self.redis_client)
                await self.tier_access_service.initialize()
                logger.info("Tier access service initialized")
            
            # Initialize cache management with optimized Redis manager
            if is_feature_enabled(FeatureFlag.REDIS_REPO_MANAGER):
                self.cache_management_service = CacheManagementService(self.redis_client)
                self.navigation_cache_manager = NavigationCacheManager(self.redis_client)
                logger.info("Cache management services initialized")
            
            # Initialize analytics service
            if is_feature_enabled(FeatureFlag.ANALYTICS_TRACKING):
                self.analytics_service = ChatAnalyticsService(self.redis_client)
                await self.analytics_service.initialize()
                logger.info("Analytics service initialized")
            
            # Initialize main Cosmos web service with Redis client
            self.cosmos_web_service = CosmosWebService(redis_client=self.redis_client)
            
            # Configure optimized wrapper usage based on feature flags
            if is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION):
                self.cosmos_web_service.enable_optimized_wrapper(True)
                logger.info("OptimizedCosmosWrapper enabled")
            else:
                self.cosmos_web_service.enable_optimized_wrapper(False)
                logger.info("OptimizedCosmosWrapper disabled, using legacy mode")
            
            # Enable legacy fallback for graceful degradation
            self.cosmos_web_service.enable_legacy_fallback(True)
            
            # Initialize compatibility layer
            self.compatibility_layer = get_compatibility_layer(
                self.cosmos_web_service,
                self,  # Pass self as integration service
                self.redis_client
            )
            
            logger.info("Cosmos web service initialized with optimized components and compatibility layer")
            
        except Exception as e:
            logger.error(f"Error initializing core services: {e}")
            raise
    
    async def _initialize_monitoring(self):
        """Initialize monitoring and alerting."""
        try:
            if not is_feature_enabled(FeatureFlag.PERFORMANCE_MONITORING):
                return
            
            # Set up custom alert handlers
            self.monitoring_service.add_alert_handler(self._handle_cosmos_alert)
            
            # Initialize degradation service with Cosmos-specific services
            await self.degradation_service.register_service(
                "cosmos_chat",
                self._check_cosmos_health,
                critical=True
            )
            
            logger.info("Monitoring initialized")
            
        except Exception as e:
            logger.error(f"Error initializing monitoring: {e}")
            raise
    
    async def _start_background_tasks(self):
        """Start background monitoring and maintenance tasks."""
        try:
            # Start monitoring loop
            if is_feature_enabled(FeatureFlag.PERFORMANCE_MONITORING):
                asyncio.create_task(self.monitoring_service.start_monitoring())
            
            # Start cache cleanup tasks
            if self.cache_management_service:
                asyncio.create_task(self._cache_cleanup_loop())
            
            # Start analytics aggregation
            if self.analytics_service:
                asyncio.create_task(self._analytics_aggregation_loop())
            
            logger.info("Background tasks started")
            
        except Exception as e:
            logger.error(f"Error starting background tasks: {e}")
            raise
    
    async def _perform_initial_health_checks(self):
        """Perform initial health checks on all services."""
        try:
            health_results = {}
            
            # Check Redis connectivity
            if self.redis_client:
                try:
                    await asyncio.to_thread(self.redis_client.ping)
                    health_results["redis"] = "healthy"
                except Exception as e:
                    health_results["redis"] = f"unhealthy: {e}"
            
            # Check core services
            if self.cosmos_web_service:
                health_results["cosmos_web"] = await self.cosmos_web_service.health_check()
            
            if self.session_service:
                health_results["sessions"] = await self.session_service.health_check()
            
            if self.tier_access_service:
                health_results["tier_access"] = await self.tier_access_service.health_check()
            
            # Log health check results
            logger.info(f"Initial health check results: {health_results}")
            
            # Check if any critical services are unhealthy
            critical_services = ["redis", "cosmos_web"]
            for service in critical_services:
                if service in health_results and "unhealthy" in str(health_results[service]):
                    raise Exception(f"Critical service {service} is unhealthy: {health_results[service]}")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise
    
    async def _handle_cosmos_alert(self, alert):
        """Handle Cosmos-specific alerts."""
        try:
            # Log alert
            logger.warning(f"Cosmos Alert: {alert.title} - {alert.description}")
            
            # Take automated actions based on alert type
            if alert.alert_type.value == "chat_failures":
                # Enable graceful degradation for chat service
                await self.degradation_service.set_service_degraded(
                    "cosmos_chat",
                    "High chat failure rate detected"
                )
            
            elif alert.alert_type.value == "redis_connection_issues":
                # Clear cache and reduce Redis load
                if self.cache_management_service:
                    await self.cache_management_service.emergency_cleanup()
            
            # Log alert handling
            await self.audit_logger.log_system_event(
                event_type="cosmos_alert_handled",
                details={
                    "alert_type": alert.alert_type.value,
                    "alert_level": alert.level.value,
                    "alert_title": alert.title
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling Cosmos alert: {e}")
    
    async def _check_cosmos_health(self) -> Dict[str, Any]:
        """Check health of Cosmos services including optimized components."""
        try:
            health = {
                "status": "healthy",
                "services": {},
                "optimization": {},
                "timestamp": datetime.now().isoformat()
            }
            
            # Check core services
            if self.cosmos_web_service:
                service_health = await self.cosmos_web_service.health_check()
                health["services"]["cosmos_web"] = service_health
                
                # Check optimization status
                service_status = self.cosmos_web_service.get_service_status()
                health["optimization"] = {
                    "optimized_wrapper_enabled": service_status.get("optimized_wrapper_enabled", False),
                    "legacy_fallback_enabled": service_status.get("legacy_fallback_enabled", False),
                    "active_wrappers": service_status.get("active_wrappers", 0),
                    "redis_connected": service_status.get("redis_connected", False)
                }
            
            if self.session_service:
                health["services"]["sessions"] = await self.session_service.health_check()
            
            if self.cache_management_service:
                health["services"]["cache"] = await self.cache_management_service.health_check()
            
            # Check if SmartRedisRepoManager is working
            try:
                from ..services.smart_redis_repo_manager import SmartRedisRepoManager
                test_manager = SmartRedisRepoManager(self.redis_client, "test://repo")
                health["services"]["smart_redis_manager"] = "available"
            except Exception as e:
                health["services"]["smart_redis_manager"] = f"unavailable: {e}"
            
            # Check if IntelligentVFS is working
            try:
                from ..services.intelligent_vfs import IntelligentVFS
                health["services"]["intelligent_vfs"] = "available"
            except Exception as e:
                health["services"]["intelligent_vfs"] = f"unavailable: {e}"
            
            # Determine overall status
            unhealthy_services = [
                name for name, status in health["services"].items()
                if isinstance(status, str) and "unhealthy" in status
            ]
            
            if unhealthy_services:
                health["status"] = "degraded" if len(unhealthy_services) < len(health["services"]) / 2 else "unhealthy"
                health["unhealthy_services"] = unhealthy_services
            
            return health
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _cache_cleanup_loop(self):
        """Background cache cleanup loop."""
        while True:
            try:
                if self.cache_management_service:
                    await self.cache_management_service.cleanup_expired_caches()
                
                # Sleep for 1 hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in cache cleanup loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _analytics_aggregation_loop(self):
        """Background analytics aggregation loop."""
        while True:
            try:
                if self.analytics_service:
                    await self.analytics_service.aggregate_hourly_metrics()
                
                # Sleep for 1 hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in analytics aggregation loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    # Public API methods
    
    async def create_chat_session(self, user_id: str, repository_context: Dict[str, Any]) -> Optional[str]:
        """Create a new chat session using compatibility layer."""
        try:
            if not self.is_healthy or not self.compatibility_layer:
                return None
            
            # Check feature flags
            if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
                return None
            
            # Check user tier access
            if self.tier_access_service:
                if not await self.tier_access_service.check_user_access(user_id, "chat_session"):
                    return None
            
            # Extract repository info from context
            repository_url = repository_context.get("repository_url")
            branch = repository_context.get("branch", "main")
            title = repository_context.get("title", "New Chat")
            model = repository_context.get("model", "gemini")
            
            # Create session through compatibility layer
            session_id = await self.compatibility_layer.create_session(
                user_id=user_id,
                title=title,
                repository_url=repository_url,
                branch=branch,
                model=model
            )
            
            # Track analytics
            if self.analytics_service:
                await self.analytics_service.track_session_created(user_id, session_id)
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error creating chat session: {e}")
            await self.error_handler.handle_error(e, {"user_id": user_id})
            return None
    
    async def send_message(
        self, 
        session_id: str, 
        user_id: str, 
        message: str,
        context: Dict[str, Any] = None,
        selected_files: List[str] = None,
        model_name: str = None
    ) -> Optional[Dict[str, Any]]:
        """Send a message in a chat session using optimized processing."""
        try:
            if not self.is_healthy or not self.cosmos_web_service:
                return None
            
            # Check rate limits
            if self.tier_access_service:
                if not await self.tier_access_service.check_rate_limit(user_id):
                    return {"error": "Rate limit exceeded"}
            
            # Use compatibility layer for message processing
            response = await self.compatibility_layer.send_message(
                session_id=session_id,
                user_id=user_id,
                message=message,
                context=context,
                selected_files=selected_files,
                model_name=model_name
            )
            
            # Track analytics
            if self.analytics_service:
                await self.analytics_service.track_message_sent(user_id, session_id, len(message))
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            await self.error_handler.handle_error(e, {"session_id": session_id, "user_id": user_id})
            return {"error": "Internal server error"}
    
    async def get_session_context(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get session context and file information using compatibility layer."""
        try:
            if not self.is_healthy or not self.compatibility_layer:
                return None
            
            # Get session data
            session_data = await self.compatibility_layer.get_session(session_id)
            if not session_data:
                return None
            
            # Get context files
            context_files = await self.compatibility_layer.get_context_files(session_id)
            
            return {
                "session": session_data,
                "context_files": context_files,
                "optimization_status": session_data.get("optimization_status", {}),
                "available_models": self.compatibility_layer.get_available_models()
            }
            
        except Exception as e:
            logger.error(f"Error getting session context: {e}")
            await self.error_handler.handle_error(e, {"session_id": session_id, "user_id": user_id})
            return None
    
    async def cleanup_user_session(self, user_id: str, session_id: Optional[str] = None):
        """Clean up user session data when leaving the contribution page."""
        try:
            # Clean up navigation cache
            if self.navigation_cache_manager:
                await self.navigation_cache_manager.on_leave_contribution_page(user_id)
            
            # Clean up session if specified
            if session_id and self.session_service:
                await self.session_service.cleanup_session(session_id)
            
            # Clean up wrapper instances for this user/session
            if self.cosmos_web_service and session_id:
                await self.cosmos_web_service.cleanup_expired_wrappers()
            
            # Track analytics
            if self.analytics_service:
                await self.analytics_service.track_session_ended(user_id, session_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up user session: {e}")
    
    async def enable_cosmos_optimization(self, enable: bool = True):
        """Enable or disable Cosmos optimization features."""
        try:
            if self.cosmos_web_service:
                self.cosmos_web_service.enable_optimized_wrapper(enable)
                logger.info(f"Cosmos optimization {'enabled' if enable else 'disabled'}")
                
                # Log the change
                await self.audit_logger.log_system_event(
                    event_type="cosmos_optimization_toggled",
                    details={"enabled": enable},
                    severity="info"
                )
            
        except Exception as e:
            logger.error(f"Error toggling Cosmos optimization: {e}")
    
    async def get_optimization_metrics(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Get performance metrics from optimized wrapper."""
        try:
            if not self.cosmos_web_service:
                return None
            
            return await self.cosmos_web_service.get_wrapper_performance_metrics(user_id, session_id)
            
        except Exception as e:
            logger.error(f"Error getting optimization metrics: {e}")
            return None
    
    async def migrate_session_to_optimized(self, session_id: str) -> bool:
        """Migrate a session to use optimized wrapper."""
        try:
            if not self.cosmos_web_service:
                return False
            
            success = await self.cosmos_web_service.migrate_session_to_optimized(session_id)
            
            if success:
                await self.audit_logger.log_system_event(
                    event_type="session_migrated_to_optimized",
                    details={"session_id": session_id},
                    severity="info"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error migrating session to optimized: {e}")
            return False
    
    # Migration and compatibility management methods
    
    async def get_compatibility_report(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get compatibility assessment report for migration planning."""
        try:
            if not self.compatibility_layer:
                return {"error": "Compatibility layer not available"}
            
            return await self.compatibility_layer.get_compatibility_report(user_id)
            
        except Exception as e:
            logger.error(f"Error getting compatibility report: {e}")
            return {"error": str(e)}
    
    async def migrate_user_sessions(self, user_id: str, force: bool = False) -> Dict[str, Any]:
        """Migrate all sessions for a user to optimized processing."""
        try:
            if not self.compatibility_layer:
                return {"error": "Compatibility layer not available"}
            
            # Get user sessions
            sessions = await self.compatibility_layer.get_user_sessions(user_id)
            
            migration_results = []
            for session in sessions:
                if session.get("optimization_status", {}).get("can_optimize", False):
                    result = await self.compatibility_layer.migrate_session_to_optimized(
                        session["id"], force
                    )
                    migration_results.append(result)
            
            successful = len([r for r in migration_results if r.get("success", False)])
            failed = len([r for r in migration_results if not r.get("success", False)])
            
            return {
                "user_id": user_id,
                "total_sessions": len(sessions),
                "migration_attempted": len(migration_results),
                "successful": successful,
                "failed": failed,
                "results": migration_results
            }
            
        except Exception as e:
            logger.error(f"Error migrating user sessions: {e}")
            return {"error": str(e)}
    
    async def rollback_user_sessions(self, user_id: str) -> Dict[str, Any]:
        """Rollback all optimized sessions for a user."""
        try:
            if not self.compatibility_layer:
                return {"error": "Compatibility layer not available"}
            
            # Get user sessions
            sessions = await self.compatibility_layer.get_user_sessions(user_id)
            
            rollback_results = []
            for session in sessions:
                if session.get("optimization_status", {}).get("migrated", False):
                    result = await self.compatibility_layer.rollback_session(session["id"])
                    rollback_results.append(result)
            
            successful = len([r for r in rollback_results if r.get("success", False)])
            failed = len([r for r in rollback_results if not r.get("success", False)])
            
            return {
                "user_id": user_id,
                "rollback_attempted": len(rollback_results),
                "successful": successful,
                "failed": failed,
                "results": rollback_results
            }
            
        except Exception as e:
            logger.error(f"Error rolling back user sessions: {e}")
            return {"error": str(e)}
    
    async def get_migration_statistics(self) -> Dict[str, Any]:
        """Get overall migration statistics."""
        try:
            if not self.compatibility_layer:
                return {"error": "Compatibility layer not available"}
            
            return await self.compatibility_layer.get_migration_statistics()
            
        except Exception as e:
            logger.error(f"Error getting migration statistics: {e}")
            return {"error": str(e)}
    
    def configure_migration_behavior(
        self,
        auto_migrate_sessions: bool = True,
        fallback_on_error: bool = True
    ):
        """Configure migration and compatibility behavior."""
        try:
            if self.compatibility_layer:
                self.compatibility_layer.configure_compatibility(
                    auto_migrate_sessions=auto_migrate_sessions,
                    fallback_on_error=fallback_on_error
                )
                
                logger.info(f"Migration behavior configured: auto_migrate={auto_migrate_sessions}, fallback={fallback_on_error}")
            
        except Exception as e:
            logger.error(f"Error configuring migration behavior: {e}")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        try:
            return {
                "cosmos_integration": {
                    "initialized": self.is_initialized,
                    "healthy": self.is_healthy,
                    "initialization_errors": self.initialization_errors
                },
                "feature_flags": self.production_settings.feature_flags,
                "services": await self._check_cosmos_health(),
                "compatibility_layer": await self.compatibility_layer.health_check() if self.compatibility_layer else None,
                "deployment": {
                    "environment": self.production_settings.environment.value,
                    "type": self.deployment_settings.deployment_type.value
                },
                "monitoring": {
                    "enabled": self.monitoring_settings.monitoring_enabled,
                    "active_alerts": len(self.monitoring_service.get_active_alerts())
                }
            }
            
        except Exception as e:
            return {
                "cosmos_integration": {
                    "initialized": False,
                    "healthy": False,
                    "error": str(e)
                }
            }
    
    async def shutdown(self):
        """Gracefully shutdown the integration service."""
        try:
            logger.info("Shutting down Cosmos Integration Service...")
            
            # Stop background tasks (they will exit on next iteration)
            
            # Clean up services
            if self.cosmos_web_service:
                await self.cosmos_web_service.shutdown()
            
            if self.session_service:
                await self.session_service.shutdown()
            
            if self.cache_management_service:
                await self.cache_management_service.shutdown()
            
            # Log shutdown
            await self.audit_logger.log_system_event(
                event_type="cosmos_integration_shutdown",
                details={"timestamp": datetime.now().isoformat()}
            )
            
            logger.info("Cosmos Integration Service shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Global integration service instance
integration_service: Optional[CosmosIntegrationService] = None


def get_cosmos_integration_service(redis_client: Optional[redis.Redis] = None) -> CosmosIntegrationService:
    """Get or create the global integration service instance."""
    global integration_service
    
    if integration_service is None:
        integration_service = CosmosIntegrationService(redis_client)
    
    return integration_service


@asynccontextmanager
async def cosmos_integration_context(redis_client: Optional[redis.Redis] = None):
    """Context manager for Cosmos integration service lifecycle."""
    service = get_cosmos_integration_service(redis_client)
    
    try:
        # Initialize service
        await service.initialize()
        yield service
    finally:
        # Shutdown service
        await service.shutdown()