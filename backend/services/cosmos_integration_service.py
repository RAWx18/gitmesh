"""
Cosmos Integration Service

This service orchestrates the integration of all Cosmos web chat components
and manages the production deployment lifecycle.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

from backend.config.production import (
    ProductionSettings, 
    FeatureFlag, 
    get_production_settings,
    is_feature_enabled,
    should_enable_for_user
)
from backend.config.monitoring import (
    MonitoringSettings,
    get_monitoring_settings,
    is_monitoring_enabled
)
from backend.config.deployment import (
    DeploymentSettings,
    get_deployment_settings,
    is_production_deployment
)

# Import all Cosmos services
from backend.services.cosmos_web_service import CosmosWebService
from backend.services.cosmos_web_wrapper import CosmosWebWrapper
from backend.services.redis_repo_manager import RedisRepoManager
from backend.services.response_processor import ResponseProcessor
from backend.services.tier_access_service import TierAccessService
from backend.services.session_persistence_service import SessionPersistenceService
from backend.services.performance_optimization_service import PerformanceOptimizationService
from backend.services.chat_analytics_service import ChatAnalyticsService
from backend.services.error_monitoring import ErrorMonitoringService

logger = structlog.get_logger(__name__)


class CosmosIntegrationService:
    """
    Main integration service that orchestrates all Cosmos web chat components.
    
    This service handles:
    - Feature flag management
    - Service initialization and lifecycle
    - Production deployment coordination
    - Monitoring and health checks
    - Graceful degradation
    """
    
    def __init__(self):
        self.production_settings = get_production_settings()
        self.monitoring_settings = get_monitoring_settings()
        self.deployment_settings = get_deployment_settings()
        
        # Service instances
        self.cosmos_service: Optional[CosmosWebService] = None
        self.response_processor: Optional[ResponseProcessor] = None
        self.tier_access_service: Optional[TierAccessService] = None
        self.session_service: Optional[SessionPersistenceService] = None
        self.performance_service: Optional[PerformanceOptimizationService] = None
        self.analytics_service: Optional[ChatAnalyticsService] = None
        self.error_monitoring: Optional[ErrorMonitoringService] = None
        
        # Integration state
        self.is_initialized = False
        self.initialization_time: Optional[datetime] = None
        self.health_status: Dict[str, Any] = {}
        
        logger.info("Cosmos Integration Service created", 
                   environment=self.production_settings.environment.value)
    
    async def initialize(self) -> bool:
        """
        Initialize all Cosmos integration components.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("Initializing Cosmos Integration Service...")
            start_time = datetime.now()
            
            # Initialize cosmos configuration first
            try:
                from backend.integrations.cosmos.v1.cosmos.config import initialize_configuration
                initialize_configuration()
                logger.info("Cosmos configuration initialized successfully")
            except Exception as e:
                logger.warning(f"Cosmos configuration initialization failed: {e}")
                logger.info("Continuing with basic chat functionality without advanced Cosmos features")
                # Return False to indicate cosmos-specific features are not available
                return False
            
            # Check if Cosmos chat is enabled
            if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
                logger.info("Cosmos chat is disabled by feature flag")
                return False
            
            # Initialize core services
            await self._initialize_core_services()
            
            # Initialize optional services based on feature flags
            await self._initialize_optional_services()
            
            # Initialize monitoring if enabled
            if is_monitoring_enabled():
                await self._initialize_monitoring()
            
            # Perform health checks
            health_ok = await self._perform_initial_health_checks()
            
            if health_ok:
                self.is_initialized = True
                self.initialization_time = datetime.now()
                
                initialization_duration = (self.initialization_time - start_time).total_seconds()
                logger.info("Cosmos Integration Service initialized successfully",
                           duration_seconds=initialization_duration)
                
                # Start background tasks
                await self._start_background_tasks()
                
                return True
            else:
                logger.error("Cosmos Integration Service initialization failed health checks")
                return False
                
        except Exception as e:
            logger.error("Failed to initialize Cosmos Integration Service", error=str(e))
            return False
    
    async def _initialize_core_services(self):
        """Initialize core required services."""
        logger.info("Initializing core services...")
        
        # Initialize Cosmos Web Service
        self.cosmos_service = CosmosWebService()
        await self.cosmos_service.initialize()
        
        # Initialize Response Processor
        self.response_processor = ResponseProcessor()
        
        # Initialize Tier Access Service
        if is_feature_enabled(FeatureFlag.TIER_ACCESS_CONTROL):
            self.tier_access_service = TierAccessService()
            await self.tier_access_service.initialize()
        
        logger.info("Core services initialized")
    
    async def _initialize_optional_services(self):
        """Initialize optional services based on feature flags."""
        logger.info("Initializing optional services...")
        
        # Session Persistence
        if is_feature_enabled(FeatureFlag.SESSION_PERSISTENCE):
            self.session_service = SessionPersistenceService()
            await self.session_service.initialize()
        
        # Performance Optimization
        if is_feature_enabled(FeatureFlag.PERFORMANCE_MONITORING):
            self.performance_service = PerformanceOptimizationService()
            await self.performance_service.initialize()
        
        # Analytics
        if is_feature_enabled(FeatureFlag.ANALYTICS_TRACKING):
            self.analytics_service = ChatAnalyticsService()
            await self.analytics_service.initialize()
        
        logger.info("Optional services initialized")
    
    async def _initialize_monitoring(self):
        """Initialize monitoring and error tracking."""
        logger.info("Initializing monitoring services...")
        
        self.error_monitoring = ErrorMonitoringService()
        await self.error_monitoring.initialize()
        
        logger.info("Monitoring services initialized")
    
    async def _perform_initial_health_checks(self) -> bool:
        """Perform initial health checks on all services."""
        logger.info("Performing initial health checks...")
        
        health_results = {}
        
        # Check core services
        if self.cosmos_service:
            health_results["cosmos_service"] = await self.cosmos_service.health_check()
        
        if self.tier_access_service:
            health_results["tier_access_service"] = await self.tier_access_service.health_check()
        
        # Check optional services
        if self.session_service:
            health_results["session_service"] = await self.session_service.health_check()
        
        if self.performance_service:
            health_results["performance_service"] = await self.performance_service.health_check()
        
        if self.analytics_service:
            health_results["analytics_service"] = await self.analytics_service.health_check()
        
        # Check Redis connectivity
        try:
            # Test Redis connection through a simple repo manager
            test_repo_manager = RedisRepoManager(
                repo_url="https://github.com/test/test",
                branch="main",
                user_tier="free",
                username="test_user"
            )
            health_results["redis_connectivity"] = await test_repo_manager.health_check()
        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
            health_results["redis_connectivity"] = False
        
        self.health_status = health_results
        
        # All core services must be healthy
        core_services_healthy = all([
            health_results.get("cosmos_service", False),
            health_results.get("redis_connectivity", False)
        ])
        
        if not core_services_healthy:
            logger.error("Core services health check failed", health_status=health_results)
            return False
        
        logger.info("Initial health checks passed", health_status=health_results)
        return True
    
    async def _start_background_tasks(self):
        """Start background monitoring and maintenance tasks."""
        logger.info("Starting background tasks...")
        
        # Start health monitoring
        asyncio.create_task(self._health_monitoring_loop())
        
        # Start performance monitoring if enabled
        if self.performance_service:
            asyncio.create_task(self._performance_monitoring_loop())
        
        # Start analytics collection if enabled
        if self.analytics_service:
            asyncio.create_task(self._analytics_collection_loop())
        
        logger.info("Background tasks started")
    
    async def _health_monitoring_loop(self):
        """Background task for continuous health monitoring."""
        while self.is_initialized:
            try:
                await asyncio.sleep(self.monitoring_settings.health_check_interval)
                
                # Perform health checks
                health_status = await self.get_health_status()
                
                # Log any unhealthy services
                unhealthy_services = [
                    service for service, status in health_status.items()
                    if not status
                ]
                
                if unhealthy_services:
                    logger.warning("Unhealthy services detected", 
                                 unhealthy_services=unhealthy_services)
                
                # Update health status
                self.health_status = health_status
                
            except Exception as e:
                logger.error("Error in health monitoring loop", error=str(e))
    
    async def _performance_monitoring_loop(self):
        """Background task for performance monitoring."""
        while self.is_initialized and self.performance_service:
            try:
                await asyncio.sleep(self.monitoring_settings.metrics_collection_interval)
                
                # Collect performance metrics
                await self.performance_service.collect_metrics()
                
            except Exception as e:
                logger.error("Error in performance monitoring loop", error=str(e))
    
    async def _analytics_collection_loop(self):
        """Background task for analytics collection."""
        while self.is_initialized and self.analytics_service:
            try:
                await asyncio.sleep(300)  # Collect analytics every 5 minutes
                
                # Collect analytics data
                await self.analytics_service.collect_session_metrics()
                
            except Exception as e:
                logger.error("Error in analytics collection loop", error=str(e))
    
    async def get_health_status(self) -> Dict[str, bool]:
        """Get current health status of all services."""
        health_status = {}
        
        try:
            # Check core services
            if self.cosmos_service:
                health_status["cosmos_service"] = await self.cosmos_service.health_check()
            
            if self.tier_access_service:
                health_status["tier_access_service"] = await self.tier_access_service.health_check()
            
            # Check optional services
            if self.session_service:
                health_status["session_service"] = await self.session_service.health_check()
            
            if self.performance_service:
                health_status["performance_service"] = await self.performance_service.health_check()
            
            if self.analytics_service:
                health_status["analytics_service"] = await self.analytics_service.health_check()
            
            # Overall system health
            health_status["overall"] = all(health_status.values())
            
        except Exception as e:
            logger.error("Error getting health status", error=str(e))
            health_status["overall"] = False
        
        return health_status
    
    def is_enabled_for_user(self, user_id: str) -> bool:
        """Check if Cosmos chat is enabled for a specific user."""
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            return False
        
        return should_enable_for_user(user_id)
    
    def get_feature_status(self) -> Dict[str, Any]:
        """Get current feature flag status."""
        return {
            "cosmos_chat_enabled": is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED),
            "tier_access_control": is_feature_enabled(FeatureFlag.TIER_ACCESS_CONTROL),
            "session_persistence": is_feature_enabled(FeatureFlag.SESSION_PERSISTENCE),
            "performance_monitoring": is_feature_enabled(FeatureFlag.PERFORMANCE_MONITORING),
            "analytics_tracking": is_feature_enabled(FeatureFlag.ANALYTICS_TRACKING),
            "rollout_percentage": self.production_settings.cosmos_chat_rollout_percentage,
            "environment": self.production_settings.environment.value,
            "deployment_type": self.deployment_settings.deployment_type.value
        }
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics."""
        metrics = {
            "initialization_time": self.initialization_time.isoformat() if self.initialization_time else None,
            "uptime_seconds": (datetime.now() - self.initialization_time).total_seconds() if self.initialization_time else 0,
            "health_status": self.health_status,
            "feature_status": self.get_feature_status()
        }
        
        # Add service-specific metrics
        if self.performance_service:
            metrics["performance"] = await self.performance_service.get_metrics()
        
        if self.analytics_service:
            metrics["analytics"] = await self.analytics_service.get_summary_metrics()
        
        return metrics
    
    async def shutdown(self):
        """Gracefully shutdown all services."""
        logger.info("Shutting down Cosmos Integration Service...")
        
        try:
            # Stop background tasks
            self.is_initialized = False
            
            # Shutdown services in reverse order
            if self.analytics_service:
                await self.analytics_service.shutdown()
            
            if self.performance_service:
                await self.performance_service.shutdown()
            
            if self.session_service:
                await self.session_service.shutdown()
            
            if self.tier_access_service:
                await self.tier_access_service.shutdown()
            
            if self.cosmos_service:
                await self.cosmos_service.shutdown()
            
            if self.error_monitoring:
                await self.error_monitoring.shutdown()
            
            logger.info("Cosmos Integration Service shutdown complete")
            
        except Exception as e:
            logger.error("Error during shutdown", error=str(e))


# Global integration service instance
_integration_service: Optional[CosmosIntegrationService] = None


async def get_integration_service() -> CosmosIntegrationService:
    """Get or create the global integration service instance."""
    global _integration_service
    
    if _integration_service is None:
        _integration_service = CosmosIntegrationService()
        await _integration_service.initialize()
    
    return _integration_service


async def initialize_cosmos_integration() -> bool:
    """Initialize the Cosmos integration service."""
    service = await get_integration_service()
    return service.is_initialized


async def shutdown_cosmos_integration():
    """Shutdown the Cosmos integration service."""
    global _integration_service
    
    if _integration_service:
        await _integration_service.shutdown()
        _integration_service = None