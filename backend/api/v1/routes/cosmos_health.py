"""
Cosmos Health Check API Routes

Comprehensive health check endpoints for Cosmos web chat integration
and production monitoring.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any, Optional
import logging
from datetime import datetime
import asyncio

from backend.config.production import get_production_settings, is_feature_enabled, FeatureFlag
from backend.config.monitoring import get_monitoring_settings
from backend.config.deployment import get_deployment_settings
from backend.services.cosmos_integration_service import get_integration_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/cosmos/health", tags=["cosmos-health"])


@router.get("/")
async def cosmos_health_overview():
    """
    Get overall Cosmos integration health status.
    
    This endpoint provides a quick overview of the Cosmos chat integration
    health and feature status.
    """
    try:
        # Check if Cosmos is enabled
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            return {
                "status": "disabled",
                "message": "Cosmos chat is disabled by feature flag",
                "timestamp": datetime.now().isoformat(),
                "features_enabled": False
            }
        
        # Get integration service
        try:
            integration_service = await get_integration_service()
            health_status = await integration_service.get_health_status()
            
            overall_healthy = health_status.get("overall", False)
            
            return {
                "status": "healthy" if overall_healthy else "unhealthy",
                "message": "Cosmos integration is operational" if overall_healthy else "Some Cosmos services are unhealthy",
                "timestamp": datetime.now().isoformat(),
                "features_enabled": True,
                "services": health_status,
                "initialization_time": integration_service.initialization_time.isoformat() if integration_service.initialization_time else None
            }
            
        except Exception as e:
            logger.error(f"Error getting integration service health: {e}")
            return {
                "status": "error",
                "message": f"Failed to get Cosmos integration status: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "features_enabled": True
            }
        
    except Exception as e:
        logger.error(f"Error in Cosmos health overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/detailed")
async def cosmos_detailed_health():
    """
    Get detailed health information for all Cosmos components.
    
    This endpoint provides comprehensive health information including
    service status, metrics, and configuration details.
    """
    try:
        production_settings = get_production_settings()
        monitoring_settings = get_monitoring_settings()
        deployment_settings = get_deployment_settings()
        
        health_info = {
            "timestamp": datetime.now().isoformat(),
            "environment": production_settings.environment.value,
            "deployment_type": deployment_settings.deployment_type.value,
            "feature_flags": production_settings.get_feature_status(),
            "configuration": {
                "rollout_percentage": production_settings.cosmos_chat_rollout_percentage,
                "monitoring_enabled": monitoring_settings.monitoring_enabled,
                "performance_config": production_settings.get_performance_config(),
                "security_config": production_settings.get_security_config()
            }
        }
        
        # Get integration service status if available
        if is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            try:
                integration_service = await get_integration_service()
                
                # Get comprehensive system metrics
                system_metrics = await integration_service.get_system_metrics()
                health_info["system_metrics"] = system_metrics
                
                # Get individual service health
                health_status = await integration_service.get_health_status()
                health_info["service_health"] = health_status
                
                # Overall status
                health_info["overall_status"] = "healthy" if health_status.get("overall", False) else "unhealthy"
                
            except Exception as e:
                logger.error(f"Error getting detailed integration status: {e}")
                health_info["integration_error"] = str(e)
                health_info["overall_status"] = "error"
        else:
            health_info["overall_status"] = "disabled"
            health_info["message"] = "Cosmos chat is disabled by feature flag"
        
        return health_info
        
    except Exception as e:
        logger.error(f"Error in detailed health check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detailed health check failed: {str(e)}"
        )


@router.get("/services/{service_name}")
async def cosmos_service_health(service_name: str):
    """
    Get health status for a specific Cosmos service.
    
    Args:
        service_name: Name of the service to check
    """
    try:
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cosmos chat is disabled"
            )
        
        integration_service = await get_integration_service()
        health_status = await integration_service.get_health_status()
        
        if service_name not in health_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service_name}' not found"
            )
        
        service_healthy = health_status[service_name]
        
        return {
            "service": service_name,
            "status": "healthy" if service_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "details": {
                "available": service_healthy,
                "last_check": datetime.now().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking service health for {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service health check failed: {str(e)}"
        )


@router.get("/metrics")
async def cosmos_metrics():
    """
    Get Cosmos integration metrics for monitoring.
    
    This endpoint provides metrics data for external monitoring systems.
    """
    try:
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            return {
                "status": "disabled",
                "metrics": {},
                "timestamp": datetime.now().isoformat()
            }
        
        integration_service = await get_integration_service()
        system_metrics = await integration_service.get_system_metrics()
        
        # Format metrics for monitoring systems
        formatted_metrics = {
            "cosmos_chat_enabled": 1 if is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED) else 0,
            "cosmos_services_healthy": 1 if system_metrics.get("health_status", {}).get("overall", False) else 0,
            "cosmos_uptime_seconds": system_metrics.get("uptime_seconds", 0),
            "timestamp": datetime.now().isoformat()
        }
        
        # Add service-specific metrics
        if "performance" in system_metrics:
            performance_metrics = system_metrics["performance"]
            formatted_metrics.update({
                "cosmos_active_sessions": performance_metrics.get("active_sessions", 0),
                "cosmos_total_requests": performance_metrics.get("total_requests", 0),
                "cosmos_avg_response_time": performance_metrics.get("avg_response_time_ms", 0)
            })
        
        if "analytics" in system_metrics:
            analytics_metrics = system_metrics["analytics"]
            formatted_metrics.update({
                "cosmos_total_messages": analytics_metrics.get("total_messages", 0),
                "cosmos_unique_users": analytics_metrics.get("unique_users", 0),
                "cosmos_conversion_rate": analytics_metrics.get("conversion_rate", 0)
            })
        
        return {
            "status": "active",
            "metrics": formatted_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting Cosmos metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics collection failed: {str(e)}"
        )


@router.post("/test-connection")
async def test_cosmos_connection():
    """
    Test Cosmos integration connectivity.
    
    This endpoint performs a comprehensive connectivity test
    of all Cosmos integration components.
    """
    try:
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cosmos chat is disabled"
            )
        
        test_results = {}
        start_time = datetime.now()
        
        # Test integration service
        try:
            integration_service = await get_integration_service()
            test_results["integration_service"] = {
                "status": "success",
                "initialized": integration_service.is_initialized,
                "initialization_time": integration_service.initialization_time.isoformat() if integration_service.initialization_time else None
            }
        except Exception as e:
            test_results["integration_service"] = {
                "status": "failed",
                "error": str(e)
            }
        
        # Test Redis connectivity
        try:
            from backend.services.redis_repo_manager import RedisRepoManager
            test_repo_manager = RedisRepoManager(
                repo_url="https://github.com/test/test",
                branch="main",
                user_tier="free",
                username="test_user"
            )
            redis_healthy = await test_repo_manager.health_check()
            test_results["redis_connectivity"] = {
                "status": "success" if redis_healthy else "failed",
                "healthy": redis_healthy
            }
        except Exception as e:
            test_results["redis_connectivity"] = {
                "status": "failed",
                "error": str(e)
            }
        
        # Test AI model availability
        try:
            from backend.services.cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            available_models = cosmos_service.get_available_models()
            test_results["ai_models"] = {
                "status": "success",
                "available_models": len(available_models),
                "models": [model.name for model in available_models[:3]]  # First 3 models
            }
        except Exception as e:
            test_results["ai_models"] = {
                "status": "failed",
                "error": str(e)
            }
        
        # Calculate test duration
        test_duration = (datetime.now() - start_time).total_seconds() * 1000
        
        # Determine overall test result
        all_tests_passed = all(
            result.get("status") == "success" 
            for result in test_results.values()
        )
        
        return {
            "overall_status": "success" if all_tests_passed else "partial_failure",
            "test_duration_ms": int(test_duration),
            "timestamp": datetime.now().isoformat(),
            "test_results": test_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in connection test: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.get("/readiness")
async def cosmos_readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    This endpoint is designed for Kubernetes readiness probes
    and returns a simple status indicating if Cosmos is ready to serve traffic.
    """
    try:
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            return {"status": "ready", "reason": "disabled"}
        
        integration_service = await get_integration_service()
        
        if not integration_service.is_initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cosmos integration not initialized"
            )
        
        # Quick health check
        health_status = await integration_service.get_health_status()
        core_services_healthy = health_status.get("cosmos_service", False) and health_status.get("redis_connectivity", False)
        
        if not core_services_healthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Core services not healthy"
            )
        
        return {
            "status": "ready",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in readiness probe: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Readiness check failed: {str(e)}"
        )


@router.get("/liveness")
async def cosmos_liveness_probe():
    """
    Kubernetes liveness probe endpoint.
    
    This endpoint is designed for Kubernetes liveness probes
    and returns a simple status indicating if the Cosmos service is alive.
    """
    try:
        # Simple liveness check - just verify the service can respond
        return {
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
            "cosmos_enabled": is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED)
        }
        
    except Exception as e:
        logger.error(f"Error in liveness probe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Liveness check failed: {str(e)}"
        )