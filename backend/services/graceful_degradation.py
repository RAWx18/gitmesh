"""
Graceful Degradation Service

Provides fallback mechanisms and graceful degradation when services are unavailable.
Ensures the system continues to function with reduced capabilities rather than failing completely.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import redis
import json

try:
    from ..utils.error_handling import (
        ErrorHandler, SystemError, NetworkError, StorageError, ExternalAPIError,
        ErrorContext, handle_cosmos_error
    )
    from ..config.settings import get_settings
except ImportError:
    from utils.error_handling import (
        ErrorHandler, SystemError, NetworkError, StorageError, ExternalAPIError,
        ErrorContext, handle_cosmos_error
    )
    from config.settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Service status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DegradationLevel(str, Enum):
    """Degradation level enumeration."""
    NONE = "none"
    MINIMAL = "minimal"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass
class ServiceHealth:
    """Service health information."""
    service_name: str
    status: ServiceStatus
    last_check: datetime
    response_time: Optional[float] = None
    error_rate: Optional[float] = None
    error_message: Optional[str] = None
    degradation_level: DegradationLevel = DegradationLevel.NONE
    
    def __post_init__(self):
        if self.last_check is None:
            self.last_check = datetime.now()


@dataclass
class FallbackResponse:
    """Fallback response when services are unavailable."""
    content: str
    is_fallback: bool = True
    degradation_level: DegradationLevel = DegradationLevel.MINIMAL
    available_features: List[str] = None
    unavailable_features: List[str] = None
    recovery_suggestions: List[str] = None
    
    def __post_init__(self):
        if self.available_features is None:
            self.available_features = []
        if self.unavailable_features is None:
            self.unavailable_features = []
        if self.recovery_suggestions is None:
            self.recovery_suggestions = []


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for service calls.
    
    Prevents cascading failures by temporarily disabling calls to failing services.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type that triggers circuit opening
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute a function call through the circuit breaker.
        
        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result or raises exception
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise SystemError(
                    message="Service temporarily unavailable due to repeated failures",
                    service=func.__name__
                )
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        return (datetime.now() - self.last_failure_time).total_seconds() > self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        self.state = "closed"
    
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class GracefulDegradationService:
    """
    Graceful Degradation Service
    
    Monitors service health and provides fallback mechanisms when services are unavailable.
    Implements circuit breaker patterns and graceful degradation strategies.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the graceful degradation service."""
        self.settings = get_settings()
        self.redis_client = redis_client
        self.error_handler = ErrorHandler(redis_client)
        
        # Service health tracking
        self.service_health: Dict[str, ServiceHealth] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Degradation configuration
        self.degradation_config = {
            "redis": {
                "fallback_enabled": True,
                "fallback_message": "Using temporary storage. Some features may be limited.",
                "degradation_level": DegradationLevel.MINIMAL
            },
            "cosmos_ai": {
                "fallback_enabled": True,
                "fallback_message": "AI service temporarily unavailable. Using cached responses.",
                "degradation_level": DegradationLevel.MODERATE
            },
            "repository_manager": {
                "fallback_enabled": True,
                "fallback_message": "Repository access limited. Using cached data.",
                "degradation_level": DegradationLevel.MODERATE
            },
            "external_apis": {
                "fallback_enabled": True,
                "fallback_message": "External services unavailable. Some features disabled.",
                "degradation_level": DegradationLevel.SEVERE
            }
        }
        
        # Initialize circuit breakers
        self._initialize_circuit_breakers()
        
        # Fallback responses
        self.fallback_responses = {
            "chat_unavailable": FallbackResponse(
                content="I apologize, but the AI chat service is temporarily unavailable. Please try again in a few moments.",
                degradation_level=DegradationLevel.SEVERE,
                unavailable_features=["AI chat", "Code assistance", "Repository analysis"],
                recovery_suggestions=[
                    "Try refreshing the page",
                    "Check your internet connection",
                    "Contact support if the issue persists"
                ]
            ),
            "repository_unavailable": FallbackResponse(
                content="Repository access is currently limited. You can still chat, but repository-specific features may not work.",
                degradation_level=DegradationLevel.MODERATE,
                available_features=["Basic chat", "Model selection"],
                unavailable_features=["Repository browsing", "File context", "Code analysis"],
                recovery_suggestions=[
                    "Try again in a few moments",
                    "Verify repository URL is correct",
                    "Check repository permissions"
                ]
            ),
            "storage_unavailable": FallbackResponse(
                content="Data storage is temporarily unavailable. Your session may not be saved.",
                degradation_level=DegradationLevel.MINIMAL,
                available_features=["Chat (temporary)", "AI responses"],
                unavailable_features=["Session persistence", "Chat history", "Context saving"],
                recovery_suggestions=[
                    "Your current session will work but may not be saved",
                    "Try refreshing if you experience issues"
                ]
            )
        }
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers for different services."""
        self.circuit_breakers = {
            "redis": CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=30,
                expected_exception=redis.RedisError
            ),
            "cosmos_ai": CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                expected_exception=Exception
            ),
            "repository_manager": CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=45,
                expected_exception=Exception
            ),
            "external_apis": CircuitBreaker(
                failure_threshold=2,
                recovery_timeout=120,
                expected_exception=(ConnectionError, TimeoutError)
            )
        }
    
    async def check_service_health(self, service_name: str) -> ServiceHealth:
        """
        Check the health of a specific service.
        
        Args:
            service_name: Name of the service to check
            
        Returns:
            ServiceHealth object with current status
        """
        try:
            start_time = datetime.now()
            
            if service_name == "redis":
                health = await self._check_redis_health()
            elif service_name == "cosmos_ai":
                health = await self._check_cosmos_ai_health()
            elif service_name == "repository_manager":
                health = await self._check_repository_manager_health()
            elif service_name == "external_apis":
                health = await self._check_external_apis_health()
            else:
                health = ServiceHealth(
                    service_name=service_name,
                    status=ServiceStatus.UNKNOWN,
                    last_check=datetime.now(),
                    error_message="Unknown service"
                )
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()
            health.response_time = response_time
            
            # Update service health cache
            self.service_health[service_name] = health
            
            logger.debug(f"Service health check: {service_name} = {health.status.value}")
            return health
            
        except Exception as e:
            logger.error(f"Error checking service health for {service_name}: {e}")
            
            health = ServiceHealth(
                service_name=service_name,
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message=str(e),
                degradation_level=DegradationLevel.SEVERE
            )
            
            self.service_health[service_name] = health
            return health
    
    async def _check_redis_health(self) -> ServiceHealth:
        """Check Redis service health."""
        if not self.redis_client:
            return ServiceHealth(
                service_name="redis",
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message="Redis client not configured",
                degradation_level=DegradationLevel.MINIMAL
            )
        
        try:
            # Simple ping test
            await asyncio.wait_for(
                asyncio.to_thread(self.redis_client.ping),
                timeout=5.0
            )
            
            return ServiceHealth(
                service_name="redis",
                status=ServiceStatus.HEALTHY,
                last_check=datetime.now()
            )
            
        except asyncio.TimeoutError:
            return ServiceHealth(
                service_name="redis",
                status=ServiceStatus.DEGRADED,
                last_check=datetime.now(),
                error_message="Redis response timeout",
                degradation_level=DegradationLevel.MINIMAL
            )
        except Exception as e:
            return ServiceHealth(
                service_name="redis",
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message=str(e),
                degradation_level=DegradationLevel.MINIMAL
            )
    
    async def _check_cosmos_ai_health(self) -> ServiceHealth:
        """Check Cosmos AI service health."""
        try:
            # This would be a simple test call to the AI service
            # For now, we'll simulate the check
            await asyncio.sleep(0.1)  # Simulate network call
            
            return ServiceHealth(
                service_name="cosmos_ai",
                status=ServiceStatus.HEALTHY,
                last_check=datetime.now()
            )
            
        except Exception as e:
            return ServiceHealth(
                service_name="cosmos_ai",
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message=str(e),
                degradation_level=DegradationLevel.MODERATE
            )
    
    async def _check_repository_manager_health(self) -> ServiceHealth:
        """Check repository manager service health."""
        try:
            # This would test repository access
            # For now, we'll simulate the check
            await asyncio.sleep(0.1)  # Simulate network call
            
            return ServiceHealth(
                service_name="repository_manager",
                status=ServiceStatus.HEALTHY,
                last_check=datetime.now()
            )
            
        except Exception as e:
            return ServiceHealth(
                service_name="repository_manager",
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message=str(e),
                degradation_level=DegradationLevel.MODERATE
            )
    
    async def _check_external_apis_health(self) -> ServiceHealth:
        """Check external APIs health."""
        try:
            # This would test external API connectivity
            # For now, we'll simulate the check
            await asyncio.sleep(0.1)  # Simulate network call
            
            return ServiceHealth(
                service_name="external_apis",
                status=ServiceStatus.HEALTHY,
                last_check=datetime.now()
            )
            
        except Exception as e:
            return ServiceHealth(
                service_name="external_apis",
                status=ServiceStatus.UNAVAILABLE,
                last_check=datetime.now(),
                error_message=str(e),
                degradation_level=DegradationLevel.SEVERE
            )
    
    async def execute_with_fallback(
        self,
        service_name: str,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with fallback handling.
        
        Args:
            service_name: Name of the service being called
            primary_func: Primary function to execute
            fallback_func: Optional fallback function
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result or fallback response
        """
        try:
            # Get circuit breaker for this service
            circuit_breaker = self.circuit_breakers.get(service_name)
            
            if circuit_breaker:
                # Execute through circuit breaker
                result = await circuit_breaker.call(primary_func, *args, **kwargs)
            else:
                # Execute directly
                result = await primary_func(*args, **kwargs) if asyncio.iscoroutinefunction(primary_func) else primary_func(*args, **kwargs)
            
            # Update service health on success
            if service_name in self.service_health:
                self.service_health[service_name].status = ServiceStatus.HEALTHY
                self.service_health[service_name].last_check = datetime.now()
            
            return result
            
        except Exception as e:
            logger.warning(f"Primary function failed for {service_name}: {e}")
            
            # Update service health on failure
            if service_name in self.service_health:
                self.service_health[service_name].status = ServiceStatus.UNAVAILABLE
                self.service_health[service_name].last_check = datetime.now()
                self.service_health[service_name].error_message = str(e)
            
            # Try fallback function
            if fallback_func:
                try:
                    logger.info(f"Executing fallback for {service_name}")
                    result = await fallback_func(*args, **kwargs) if asyncio.iscoroutinefunction(fallback_func) else fallback_func(*args, **kwargs)
                    return result
                except Exception as fallback_error:
                    logger.error(f"Fallback function also failed for {service_name}: {fallback_error}")
            
            # Return degraded response
            return self._get_degraded_response(service_name, e)
    
    def _get_degraded_response(self, service_name: str, error: Exception) -> FallbackResponse:
        """
        Get a degraded response for a failed service.
        
        Args:
            service_name: Name of the failed service
            error: The error that occurred
            
        Returns:
            FallbackResponse with appropriate degradation
        """
        # Map service names to fallback responses
        fallback_map = {
            "cosmos_ai": "chat_unavailable",
            "repository_manager": "repository_unavailable",
            "redis": "storage_unavailable"
        }
        
        fallback_key = fallback_map.get(service_name, "chat_unavailable")
        fallback_response = self.fallback_responses.get(fallback_key)
        
        if fallback_response:
            # Add error context
            fallback_response.recovery_suggestions.append(f"Error: {str(error)[:100]}")
            return fallback_response
        
        # Default fallback
        return FallbackResponse(
            content=f"Service {service_name} is temporarily unavailable. Please try again later.",
            degradation_level=DegradationLevel.MODERATE,
            recovery_suggestions=[
                "Try again in a few moments",
                "Contact support if the issue persists"
            ]
        )
    
    async def get_system_health(self) -> Dict[str, Any]:
        """
        Get overall system health status.
        
        Returns:
            Dictionary with system health information
        """
        try:
            # Check all services
            services = ["redis", "cosmos_ai", "repository_manager", "external_apis"]
            health_checks = []
            
            for service in services:
                health_checks.append(self.check_service_health(service))
            
            # Wait for all health checks
            health_results = await asyncio.gather(*health_checks, return_exceptions=True)
            
            # Analyze results
            healthy_services = 0
            degraded_services = 0
            unavailable_services = 0
            
            service_details = {}
            
            for i, result in enumerate(health_results):
                service_name = services[i]
                
                if isinstance(result, Exception):
                    service_details[service_name] = {
                        "status": ServiceStatus.UNAVAILABLE.value,
                        "error": str(result)
                    }
                    unavailable_services += 1
                else:
                    service_details[service_name] = {
                        "status": result.status.value,
                        "response_time": result.response_time,
                        "degradation_level": result.degradation_level.value,
                        "last_check": result.last_check.isoformat()
                    }
                    
                    if result.error_message:
                        service_details[service_name]["error"] = result.error_message
                    
                    if result.status == ServiceStatus.HEALTHY:
                        healthy_services += 1
                    elif result.status == ServiceStatus.DEGRADED:
                        degraded_services += 1
                    else:
                        unavailable_services += 1
            
            # Determine overall system status
            total_services = len(services)
            if unavailable_services == 0 and degraded_services == 0:
                overall_status = ServiceStatus.HEALTHY
                degradation_level = DegradationLevel.NONE
            elif unavailable_services == 0:
                overall_status = ServiceStatus.DEGRADED
                degradation_level = DegradationLevel.MINIMAL
            elif unavailable_services < total_services / 2:
                overall_status = ServiceStatus.DEGRADED
                degradation_level = DegradationLevel.MODERATE
            else:
                overall_status = ServiceStatus.UNAVAILABLE
                degradation_level = DegradationLevel.SEVERE
            
            return {
                "overall_status": overall_status.value,
                "degradation_level": degradation_level.value,
                "healthy_services": healthy_services,
                "degraded_services": degraded_services,
                "unavailable_services": unavailable_services,
                "total_services": total_services,
                "services": service_details,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                "overall_status": ServiceStatus.UNKNOWN.value,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_available_features(self) -> Dict[str, Any]:
        """
        Get list of currently available features based on service health.
        
        Returns:
            Dictionary with available and unavailable features
        """
        available_features = []
        unavailable_features = []
        degraded_features = []
        
        # Check each service and its associated features
        for service_name, health in self.service_health.items():
            if service_name == "redis":
                if health.status == ServiceStatus.HEALTHY:
                    available_features.extend(["Session persistence", "Chat history", "Context saving"])
                elif health.status == ServiceStatus.DEGRADED:
                    degraded_features.extend(["Session persistence", "Chat history"])
                    available_features.append("Context saving")
                else:
                    unavailable_features.extend(["Session persistence", "Chat history", "Context saving"])
            
            elif service_name == "cosmos_ai":
                if health.status == ServiceStatus.HEALTHY:
                    available_features.extend(["AI chat", "Code assistance", "Model selection"])
                elif health.status == ServiceStatus.DEGRADED:
                    degraded_features.extend(["AI chat", "Code assistance"])
                    available_features.append("Model selection")
                else:
                    unavailable_features.extend(["AI chat", "Code assistance", "Model selection"])
            
            elif service_name == "repository_manager":
                if health.status == ServiceStatus.HEALTHY:
                    available_features.extend(["Repository browsing", "File context", "Code analysis"])
                elif health.status == ServiceStatus.DEGRADED:
                    degraded_features.extend(["Repository browsing", "Code analysis"])
                    available_features.append("File context")
                else:
                    unavailable_features.extend(["Repository browsing", "File context", "Code analysis"])
        
        return {
            "available_features": list(set(available_features)),
            "degraded_features": list(set(degraded_features)),
            "unavailable_features": list(set(unavailable_features)),
            "timestamp": datetime.now().isoformat()
        }
    
    async def start_health_monitoring(self, interval: int = 60):
        """
        Start periodic health monitoring.
        
        Args:
            interval: Health check interval in seconds
        """
        logger.info(f"Starting health monitoring with {interval}s interval")
        
        while True:
            try:
                await self.get_system_health()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
                await asyncio.sleep(interval)


# Global graceful degradation service instance
graceful_degradation_service = None


def get_graceful_degradation_service(redis_client: Optional[redis.Redis] = None) -> GracefulDegradationService:
    """Get or create the global graceful degradation service instance."""
    global graceful_degradation_service
    
    if graceful_degradation_service is None:
        graceful_degradation_service = GracefulDegradationService(redis_client)
    
    return graceful_degradation_service