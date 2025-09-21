"""
System Health and Error Monitoring API Routes

Provides endpoints for monitoring system health, error statistics,
and alert management for the Cosmos Web Chat system.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

# Import models and services
try:
    from ...services.error_monitoring import get_monitoring_service, Alert, AlertLevel, AlertType
    from ...services.graceful_degradation import get_graceful_degradation_service
    from ...utils.cosmos_error_handler import get_cosmos_error_handler
    from ...utils.error_handling import get_settings
    from ...models.api.auth_models import User
    from ...api.v1.routes.dependencies import get_current_user
except ImportError:
    from services.error_monitoring import get_monitoring_service, Alert, AlertLevel, AlertType
    from services.graceful_degradation import get_graceful_degradation_service
    from utils.cosmos_error_handler import get_cosmos_error_handler
    from utils.error_handling import get_settings
    from models.api.auth_models import User
    from api.v1.routes.dependencies import get_current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/system", tags=["system-health"])

# Initialize services
settings = get_settings()


@router.get("/health")
async def get_system_health():
    """
    Get comprehensive system health status.
    
    Returns overall system health, service status, and degradation information.
    """
    try:
        degradation_service = get_graceful_degradation_service()
        health_data = await degradation_service.get_system_health()
        
        # Add additional health information
        health_data["api_status"] = "healthy"
        health_data["version"] = "2.0.0"
        health_data["environment"] = getattr(settings, 'environment', 'development')
        
        return JSONResponse(
            content=health_data,
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return JSONResponse(
            content={
                "overall_status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get("/health/services")
async def get_service_health():
    """
    Get detailed health status for individual services.
    
    Returns health status for Redis, AI models, repository manager, etc.
    """
    try:
        degradation_service = get_graceful_degradation_service()
        
        # Check individual services
        services = ["redis", "cosmos_ai", "repository_manager", "external_apis"]
        service_health = {}
        
        for service_name in services:
            try:
                health = await degradation_service.check_service_health(service_name)
                service_health[service_name] = {
                    "status": health.status.value,
                    "last_check": health.last_check.isoformat(),
                    "response_time": health.response_time,
                    "error_message": health.error_message,
                    "degradation_level": health.degradation_level.value
                }
            except Exception as e:
                service_health[service_name] = {
                    "status": "error",
                    "error": str(e),
                    "last_check": datetime.now().isoformat()
                }
        
        return JSONResponse(
            content={
                "services": service_health,
                "timestamp": datetime.now().isoformat()
            },
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error getting service health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving service health: {str(e)}"
        )


@router.get("/health/features")
async def get_available_features():
    """
    Get list of currently available and unavailable features.
    
    Returns feature availability based on current system health.
    """
    try:
        degradation_service = get_graceful_degradation_service()
        features = degradation_service.get_available_features()
        
        return JSONResponse(
            content=features,
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error getting available features: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving feature availability: {str(e)}"
        )


@router.get("/errors/statistics")
async def get_error_statistics(
    days: int = Query(7, ge=1, le=30, description="Number of days to include in statistics"),
    current_user: User = Depends(get_current_user)
):
    """
    Get error statistics and metrics.
    
    Requires authentication. Returns error counts, rates, and patterns.
    """
    try:
        # Check if user has admin privileges (simplified check)
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to access error statistics"
            )
        
        error_handler = get_cosmos_error_handler()
        stats = error_handler.get_error_statistics(days=days)
        
        # Add chat-specific statistics
        chat_stats = error_handler.get_chat_error_statistics()
        stats["chat_specific"] = chat_stats.get("chat_errors", {})
        
        return JSONResponse(
            content=stats,
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting error statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving error statistics: {str(e)}"
        )


@router.get("/alerts")
async def get_alerts(
    active_only: bool = Query(False, description="Return only active (unresolved) alerts"),
    hours: int = Query(24, ge=1, le=168, description="Hours of alert history to include"),
    current_user: User = Depends(get_current_user)
):
    """
    Get system alerts.
    
    Requires authentication. Returns active alerts and alert history.
    """
    try:
        # Check if user has admin privileges
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to access alerts"
            )
        
        monitoring_service = get_monitoring_service()
        
        if active_only:
            alerts = monitoring_service.get_active_alerts()
        else:
            alerts = monitoring_service.get_alert_history(hours=hours)
        
        # Convert alerts to dict format
        alert_data = []
        for alert in alerts:
            alert_dict = {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "level": alert.level.value,
                "title": alert.title,
                "description": alert.description,
                "timestamp": alert.timestamp.isoformat(),
                "details": alert.details,
                "resolved": alert.resolved
            }
            
            if alert.resolved_at:
                alert_dict["resolved_at"] = alert.resolved_at.isoformat()
            
            alert_data.append(alert_dict)
        
        return JSONResponse(
            content={
                "alerts": alert_data,
                "total_count": len(alert_data),
                "active_count": len(monitoring_service.get_active_alerts()),
                "query_params": {
                    "active_only": active_only,
                    "hours": hours
                },
                "timestamp": datetime.now().isoformat()
            },
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving alerts: {str(e)}"
        )


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_note: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Resolve an active alert.
    
    Requires admin authentication. Marks an alert as resolved.
    """
    try:
        # Check if user has admin privileges
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to resolve alerts"
            )
        
        monitoring_service = get_monitoring_service()
        await monitoring_service.resolve_alert(alert_id, resolution_note)
        
        return JSONResponse(
            content={
                "message": "Alert resolved successfully",
                "alert_id": alert_id,
                "resolved_by": current_user.username if hasattr(current_user, 'username') else 'admin',
                "resolved_at": datetime.now().isoformat(),
                "resolution_note": resolution_note
            },
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resolving alert: {str(e)}"
        )


@router.get("/metrics")
async def get_system_metrics(
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive system metrics.
    
    Requires authentication. Returns performance and health metrics.
    """
    try:
        # Check if user has admin privileges
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to access system metrics"
            )
        
        monitoring_service = get_monitoring_service()
        degradation_service = get_graceful_degradation_service()
        
        # Get various metrics
        health_metrics = monitoring_service.get_system_health_metrics()
        system_health = await degradation_service.get_system_health()
        error_stats = get_cosmos_error_handler().get_error_statistics()
        
        metrics = {
            "system_health": {
                "overall_health": health_metrics.overall_health,
                "active_alerts": health_metrics.active_alerts,
                "resolved_alerts": health_metrics.resolved_alerts,
                "uptime_percentage": health_metrics.uptime_percentage
            },
            "service_status": system_health.get("services", {}),
            "error_metrics": {
                "total_errors": error_stats.get("total_errors", 0),
                "errors_by_category": error_stats.get("errors_by_category", {}),
                "top_errors": error_stats.get("top_errors", [])[:10]  # Top 10
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(
            content=metrics,
            status_code=status.HTTP_200_OK
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving system metrics: {str(e)}"
        )


@router.get("/status")
async def get_system_status():
    """
    Get basic system status (public endpoint).
    
    Returns basic system status without sensitive information.
    No authentication required.
    """
    try:
        degradation_service = get_graceful_degradation_service()
        health = await degradation_service.get_system_health()
        
        # Return basic status information
        status_info = {
            "status": health.get("overall_status", "unknown"),
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "services_healthy": health.get("healthy_services", 0),
            "services_total": health.get("total_services", 0)
        }
        
        # Add degradation notice if system is degraded
        if health.get("overall_status") == "degraded":
            status_info["notice"] = "Some features may be limited due to system maintenance"
        elif health.get("overall_status") == "unavailable":
            status_info["notice"] = "System is temporarily unavailable"
        
        return JSONResponse(
            content=status_info,
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": "Unable to determine system status",
                "timestamp": datetime.now().isoformat()
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@router.post("/test-error")
async def test_error_handling(
    error_type: str = Query("validation", description="Type of error to simulate"),
    current_user: User = Depends(get_current_user)
):
    """
    Test error handling system (development/testing only).
    
    Simulates different types of errors to test the error handling system.
    """
    try:
        # Check if user has admin privileges and system is in development mode
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required for error testing"
            )
        
        # Only allow in development environment
        if getattr(settings, 'environment', 'development') != 'development':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Error testing only available in development environment"
            )
        
        # Simulate different error types
        if error_type == "validation":
            raise ValueError("Test validation error")
        elif error_type == "authentication":
            raise HTTPException(status_code=401, detail="Test authentication error")
        elif error_type == "authorization":
            raise HTTPException(status_code=403, detail="Test authorization error")
        elif error_type == "system":
            raise RuntimeError("Test system error")
        elif error_type == "network":
            raise ConnectionError("Test network error")
        else:
            raise Exception(f"Test generic error: {error_type}")
        
    except HTTPException:
        raise
    except Exception as e:
        # This will be caught by the error middleware and processed
        logger.info(f"Test error generated: {e}")
        raise e


# Health check endpoint for load balancers
@router.get("/ping")
async def ping():
    """
    Simple ping endpoint for health checks.
    
    Returns a simple response to indicate the service is running.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "service": "cosmos-web-chat"
        },
        status_code=status.HTTP_200_OK
    )