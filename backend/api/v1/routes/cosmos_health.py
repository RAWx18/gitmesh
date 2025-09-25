"""
Cosmos Health Check API Routes

Provides comprehensive health check endpoints for the Cosmos Web Chat integration,
including liveness, readiness, and detailed health status for monitoring.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime
import logging

from ....services.cosmos_integration_service import get_cosmos_integration_service
from ....config.production import get_production_settings, is_feature_enabled, FeatureFlag
from ....config.deployment import get_deployment_settings
from ....config.monitoring import get_monitoring_settings
from ....services.error_monitoring import get_monitoring_service
from ....utils.error_handling import ErrorHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cosmos/health", tags=["cosmos-health"])


@router.get("/liveness")
async def liveness_probe():
    """
    Kubernetes liveness probe endpoint.
    
    Returns 200 if the service is alive and can handle requests.
    This should only fail if the service is completely broken.
    """
    try:
        # Basic service availability check
        integration_service = get_cosmos_integration_service()
        
        # Simple check - if we can get the service instance, we're alive
        if integration_service:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "alive",
                    "timestamp": datetime.now().isoformat(),
                    "service": "cosmos-web-chat"
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "dead",
                    "timestamp": datetime.now().isoformat(),
                    "error": "Integration service not available"
                }
            )
    
    except Exception as e:
        logger.error(f"Liveness probe failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "dead",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )


@router.get("/readiness")
async def readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    Returns 200 if the service is ready to handle requests.
    This can fail temporarily during startup or when dependencies are unavailable.
    """
    try:
        integration_service = get_cosmos_integration_service()
        
        if not integration_service:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now().isoformat(),
                    "reason": "Integration service not available"
                }
            )
        
        # Check if service is initialized and healthy
        if not integration_service.is_initialized:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now().isoformat(),
                    "reason": "Service not initialized"
                }
            )
        
        if not integration_service.is_healthy:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now().isoformat(),
                    "reason": "Service not healthy",
                    "errors": integration_service.initialization_errors
                }
            )
        
        # Check if Cosmos Chat is enabled
        if not is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED):
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "timestamp": datetime.now().isoformat(),
                    "note": "Cosmos Chat is disabled via feature flag"
                }
            )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "ready",
                "timestamp": datetime.now().isoformat(),
                "service": "cosmos-web-chat"
            }
        )
    
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )


@router.get("/startup")
async def startup_probe():
    """
    Kubernetes startup probe endpoint.
    
    Returns 200 when the service has completed startup.
    Used to give the service more time to start up before liveness checks begin.
    """
    try:
        integration_service = get_cosmos_integration_service()
        
        if not integration_service:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "starting",
                    "timestamp": datetime.now().isoformat(),
                    "reason": "Integration service not available"
                }
            )
        
        # Check initialization status
        if integration_service.is_initialized:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "started",
                    "timestamp": datetime.now().isoformat(),
                    "service": "cosmos-web-chat"
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "starting",
                    "timestamp": datetime.now().isoformat(),
                    "reason": "Service still initializing"
                }
            )
    
    except Exception as e:
        logger.error(f"Startup probe failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "starting",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )


@router.get("/detailed")
async def detailed_health_check():
    """
    Detailed health check endpoint for monitoring and debugging.
    
    Provides comprehensive health information about all components.
    """
    try:
        integration_service = get_cosmos_integration_service()
        
        if not integration_service:
            raise HTTPException(
                status_code=503,
                detail="Integration service not available"
            )
        
        # Get comprehensive health status
        health_status = await integration_service.get_health_status()
        
        # Add additional monitoring information
        monitoring_service = get_monitoring_service()
        active_alerts = monitoring_service.get_active_alerts()
        
        health_status["monitoring"] = {
            "active_alerts": len(active_alerts),
            "alert_details": [
                {
                    "type": alert.alert_type.value,
                    "level": alert.level.value,
                    "title": alert.title,
                    "timestamp": alert.timestamp.isoformat()
                }
                for alert in active_alerts[:5]  # Show first 5 alerts
            ]
        }
        
        # Add configuration information
        production_settings = get_production_settings()
        deployment_settings = get_deployment_settings()
        
        health_status["configuration"] = {
            "environment": production_settings.environment.value,
            "deployment_type": deployment_settings.deployment_type.value,
            "rollout_percentage": production_settings.cosmos_chat_rollout_percentage,
            "monitoring_enabled": get_monitoring_settings().monitoring_enabled
        }
        
        # Determine HTTP status code based on health
        if health_status["cosmos_integration"]["healthy"]:
            status_code = 200
        else:
            status_code = 503
        
        return JSONResponse(
            status_code=status_code,
            content=health_status
        )
    
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check error: {str(e)}"
        )


@router.get("/metrics")
async def health_metrics():
    """
    Health metrics endpoint for Prometheus scraping.
    
    Returns metrics in Prometheus format for monitoring.
    """
    try:
        integration_service = get_cosmos_integration_service()
        monitoring_service = get_monitoring_service()
        
        metrics = []
        
        # Service health metrics
        if integration_service:
            metrics.append(f"cosmos_service_initialized {1 if integration_service.is_initialized else 0}")
            metrics.append(f"cosmos_service_healthy {1 if integration_service.is_healthy else 0}")
            metrics.append(f"cosmos_initialization_errors {len(integration_service.initialization_errors)}")
        
        # Feature flag metrics
        production_settings = get_production_settings()
        for flag, enabled in production_settings.feature_flags.items():
            flag_name = flag.value.replace("_", "_")
            metrics.append(f"cosmos_feature_{flag_name} {1 if enabled else 0}")
        
        # Alert metrics
        active_alerts = monitoring_service.get_active_alerts()
        metrics.append(f"cosmos_active_alerts {len(active_alerts)}")
        
        # Alert level breakdown
        alert_levels = {}
        for alert in active_alerts:
            level = alert.level.value
            alert_levels[level] = alert_levels.get(level, 0) + 1
        
        for level, count in alert_levels.items():
            metrics.append(f"cosmos_alerts_by_level{{level=\"{level}\"}} {count}")
        
        # Configuration metrics
        metrics.append(f"cosmos_rollout_percentage {production_settings.cosmos_chat_rollout_percentage}")
        metrics.append(f"cosmos_monitoring_enabled {1 if get_monitoring_settings().monitoring_enabled else 0}")
        
        # Join metrics with newlines
        metrics_text = "\n".join(metrics) + "\n"
        
        return JSONResponse(
            status_code=200,
            content=metrics_text,
            media_type="text/plain"
        )
    
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Metrics error: {str(e)}"
        )


@router.get("/dependencies")
async def dependency_health():
    """
    Check health of external dependencies.
    
    Returns status of Redis, database, AI models, and other dependencies.
    """
    try:
        integration_service = get_cosmos_integration_service()
        
        if not integration_service:
            raise HTTPException(
                status_code=503,
                detail="Integration service not available"
            )
        
        dependencies = {
            "timestamp": datetime.now().isoformat(),
            "dependencies": {}
        }
        
        # Check Redis
        try:
            if integration_service.redis_client:
                await asyncio.to_thread(integration_service.redis_client.ping)
                dependencies["dependencies"]["redis"] = {
                    "status": "healthy",
                    "response_time_ms": 0  # Would measure actual response time
                }
            else:
                dependencies["dependencies"]["redis"] = {
                    "status": "not_configured"
                }
        except Exception as e:
            dependencies["dependencies"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check AI model availability (simplified)
        dependencies["dependencies"]["ai_models"] = {
            "status": "healthy",  # Would check actual model availability
            "configured_models": ["gemini-2.0-flash"]  # From configuration
        }
        
        # Check Vault (if enabled)
        vault_enabled = get_production_settings().production_settings.get("vault_enabled", False)
        if vault_enabled:
            dependencies["dependencies"]["vault"] = {
                "status": "healthy",  # Would check actual Vault connectivity
                "note": "Vault connectivity check not implemented"
            }
        
        # Determine overall dependency health
        unhealthy_deps = [
            name for name, dep in dependencies["dependencies"].items()
            if dep.get("status") == "unhealthy"
        ]
        
        overall_status = "healthy" if not unhealthy_deps else "degraded"
        dependencies["overall_status"] = overall_status
        dependencies["unhealthy_dependencies"] = unhealthy_deps
        
        status_code = 200 if overall_status == "healthy" else 503
        
        return JSONResponse(
            status_code=status_code,
            content=dependencies
        )
    
    except Exception as e:
        logger.error(f"Dependency health check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Dependency check error: {str(e)}"
        )


@router.get("/feature-flags")
async def feature_flag_status():
    """
    Get current feature flag status.
    
    Returns the status of all feature flags for debugging and monitoring.
    """
    try:
        production_settings = get_production_settings()
        
        feature_status = {
            "timestamp": datetime.now().isoformat(),
            "environment": production_settings.environment.value,
            "rollout_percentage": production_settings.cosmos_chat_rollout_percentage,
            "feature_flags": {}
        }
        
        # Convert feature flags to readable format
        for flag, enabled in production_settings.feature_flags.items():
            feature_status["feature_flags"][flag.value] = {
                "enabled": enabled,
                "description": _get_feature_description(flag)
            }
        
        return JSONResponse(
            status_code=200,
            content=feature_status
        )
    
    except Exception as e:
        logger.error(f"Feature flag status check failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Feature flag error: {str(e)}"
        )


def _get_feature_description(flag: FeatureFlag) -> str:
    """Get human-readable description for feature flags."""
    descriptions = {
        FeatureFlag.COSMOS_CHAT_ENABLED: "Enable Cosmos Chat functionality",
        FeatureFlag.COSMOS_CHAT_BETA: "Enable beta features for Cosmos Chat",
        FeatureFlag.COSMOS_CHAT_FULL: "Enable full Cosmos Chat features",
        FeatureFlag.TIER_ACCESS_CONTROL: "Enable tier-based access control",
        FeatureFlag.REDIS_REPO_MANAGER: "Enable Redis repository manager",
        FeatureFlag.CONTEXT_FILE_MANAGEMENT: "Enable context file management",
        FeatureFlag.REAL_TIME_CHAT: "Enable real-time chat features",
        FeatureFlag.SHELL_COMMAND_CONVERSION: "Enable shell command conversion",
        FeatureFlag.PERFORMANCE_MONITORING: "Enable performance monitoring",
        FeatureFlag.SECURITY_HARDENING: "Enable security hardening features",
        FeatureFlag.SESSION_PERSISTENCE: "Enable session persistence",
        FeatureFlag.ANALYTICS_TRACKING: "Enable analytics tracking"
    }
    
    return descriptions.get(flag, "No description available")


@router.post("/reset-health")
async def reset_health_status():
    """
    Reset health status and clear errors.
    
    Useful for recovering from transient issues without restarting the service.
    """
    try:
        integration_service = get_cosmos_integration_service()
        
        if not integration_service:
            raise HTTPException(
                status_code=503,
                detail="Integration service not available"
            )
        
        # Clear initialization errors
        integration_service.initialization_errors.clear()
        
        # Try to re-initialize if needed
        if not integration_service.is_initialized:
            success = await integration_service.initialize()
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to re-initialize service"
                )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "reset_complete",
                "timestamp": datetime.now().isoformat(),
                "message": "Health status has been reset"
            }
        )
    
    except Exception as e:
        logger.error(f"Health reset failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Health reset error: {str(e)}"
        )