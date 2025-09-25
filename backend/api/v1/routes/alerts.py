"""
Alerts API Routes

Provides endpoints for managing alerts, alert rules, and alert statistics.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

try:
    # Try relative imports first (when used as module)
    from ....services.alerting_service import get_alerting_service, AlertSeverity, AlertStatus
    from ....models.api.auth_models import User
    from ....api.v1.routes.dependencies import get_current_user
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.alerting_service import get_alerting_service, AlertSeverity, AlertStatus
    from models.api.auth_models import User
    from api.v1.routes.dependencies import get_current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/")
async def get_alerts(
    active_only: bool = Query(False, description="Return only active alerts"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history to include"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get alerts with optional filtering.
    """
    try:
        alerting_service = get_alerting_service()
        
        if active_only:
            alerts = alerting_service.get_active_alerts()
        else:
            alerts = alerting_service.get_alert_history(hours=hours)
        
        # Filter by severity if specified
        if severity:
            try:
                severity_enum = AlertSeverity(severity.lower())
                alerts = [alert for alert in alerts if alert.severity == severity_enum]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid severity: {severity}. Valid values: info, warning, critical, emergency"
                )
        
        # Convert to dict format
        alert_data = [alert.to_dict() for alert in alerts]
        
        return {
            "alerts": alert_data,
            "total_count": len(alert_data),
            "active_count": len(alerting_service.get_active_alerts()),
            "filters": {
                "active_only": active_only,
                "severity": severity,
                "hours": hours
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active")
async def get_active_alerts(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all active alerts.
    """
    try:
        alerting_service = get_alerting_service()
        active_alerts = alerting_service.get_active_alerts()
        
        return {
            "alerts": [alert.to_dict() for alert in active_alerts],
            "count": len(active_alerts),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_alert_statistics(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get alert statistics and metrics.
    """
    try:
        alerting_service = get_alerting_service()
        stats = alerting_service.get_alert_statistics()
        
        return {
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting alert statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get a specific alert by ID.
    """
    try:
        alerting_service = get_alerting_service()
        
        # Check active alerts first
        if alert_id in alerting_service.active_alerts:
            alert = alerting_service.active_alerts[alert_id]
            return {
                "alert": alert.to_dict(),
                "timestamp": datetime.now().isoformat()
            }
        
        # Check alert history
        for alert in alerting_service.alert_history:
            if alert.alert_id == alert_id:
                return {
                    "alert": alert.to_dict(),
                    "timestamp": datetime.now().isoformat()
                }
        
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    note: Optional[str] = Body(None, description="Acknowledgment note"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Acknowledge an alert.
    """
    try:
        alerting_service = get_alerting_service()
        
        # Get user identifier
        user_id = getattr(current_user, 'username', getattr(current_user, 'email', 'unknown'))
        
        success = await alerting_service.acknowledge_alert(alert_id, user_id, note)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found or cannot be acknowledged"
            )
        
        return {
            "message": "Alert acknowledged successfully",
            "alert_id": alert_id,
            "acknowledged_by": user_id,
            "acknowledged_at": datetime.now().isoformat(),
            "note": note
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_note: Optional[str] = Body(None, description="Resolution note"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Resolve an alert.
    """
    try:
        alerting_service = get_alerting_service()
        
        success = await alerting_service.resolve_alert(alert_id, resolution_note)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found or cannot be resolved"
            )
        
        return {
            "message": "Alert resolved successfully",
            "alert_id": alert_id,
            "resolved_at": datetime.now().isoformat(),
            "resolution_note": resolution_note
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules/")
async def get_alert_rules(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all alert rules.
    """
    try:
        # Check if user has admin privileges
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to view alert rules"
            )
        
        alerting_service = get_alerting_service()
        
        rules_data = []
        for rule in alerting_service.alert_rules:
            rule_dict = {
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity.value,
                "channels": [channel.value for channel in rule.channels],
                "cooldown_minutes": rule.cooldown_minutes,
                "max_alerts_per_hour": rule.max_alerts_per_hour,
                "auto_resolve_minutes": rule.auto_resolve_minutes,
                "tags": rule.tags,
                "last_triggered": rule.last_triggered.isoformat() if rule.last_triggered else None,
                "alerts_this_hour": rule.alerts_this_hour
            }
            rules_data.append(rule_dict)
        
        return {
            "rules": rules_data,
            "count": len(rules_data),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/")
async def get_alert_dashboard(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get alert dashboard data with summary statistics and recent alerts.
    """
    try:
        alerting_service = get_alerting_service()
        
        # Get statistics
        stats = alerting_service.get_alert_statistics()
        
        # Get recent active alerts
        active_alerts = alerting_service.get_active_alerts()
        
        # Get recent alert history (last 24 hours)
        recent_alerts = alerting_service.get_alert_history(hours=24)
        
        # Group alerts by severity
        severity_counts = {
            "info": 0,
            "warning": 0,
            "critical": 0,
            "emergency": 0
        }
        
        for alert in active_alerts:
            severity_counts[alert.severity.value] += 1
        
        # Get top alert rules by frequency
        rule_frequency = {}
        for alert in recent_alerts:
            rule_frequency[alert.rule_name] = rule_frequency.get(alert.rule_name, 0) + 1
        
        top_rules = sorted(rule_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "summary": {
                "total_active": len(active_alerts),
                "total_24h": stats["total_24h"],
                "total_7d": stats["total_7d"],
                "acknowledgment_rate": stats["acknowledgment_rate"],
                "avg_resolution_time_minutes": stats["avg_resolution_time_minutes"]
            },
            "severity_breakdown": severity_counts,
            "recent_alerts": [alert.to_dict() for alert in active_alerts[:10]],  # Last 10 active
            "top_alert_rules": [{"rule": rule, "count": count} for rule, count in top_rules],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting alert dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_alert_system(
    alert_type: str = Body(..., description="Type of test alert to generate"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Test the alert system by generating a test alert.
    """
    try:
        # Check if user has admin privileges
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to test alert system"
            )
        
        # Only allow in development/testing environments
        from ....config.settings import get_settings
        settings = get_settings()
        if getattr(settings, 'environment', 'development') not in ['development', 'testing']:
            raise HTTPException(
                status_code=403,
                detail="Alert testing only available in development/testing environments"
            )
        
        alerting_service = get_alerting_service()
        
        # Create test metrics that will trigger the specified alert type
        test_metrics = {}
        
        if alert_type == "high_response_time":
            test_metrics = {
                "response_times": {
                    "p95_1h_ms": 6000,
                    "avg_1h_ms": 4000
                }
            }
        elif alert_type == "critical_response_time":
            test_metrics = {
                "response_times": {
                    "p95_1h_ms": 12000
                }
            }
        elif alert_type == "high_memory_usage":
            test_metrics = {
                "memory": {
                    "avg_1h_percent": 85
                }
            }
        elif alert_type == "redis_connectivity":
            test_metrics = {
                "health_checks": {
                    "redis": {
                        "status": "critical"
                    }
                }
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown alert type: {alert_type}"
            )
        
        # Find the matching rule and trigger it manually
        rule = next((r for r in alerting_service.alert_rules if r.name == alert_type), None)
        if not rule:
            raise HTTPException(
                status_code=400,
                detail=f"No alert rule found for type: {alert_type}"
            )
        
        # Temporarily bypass cooldown for testing
        original_last_triggered = rule.last_triggered
        rule.last_triggered = None
        
        try:
            if rule.condition(test_metrics):
                await alerting_service._trigger_alert(rule, test_metrics)
                
                return {
                    "message": f"Test alert triggered successfully: {alert_type}",
                    "alert_type": alert_type,
                    "test_metrics": test_metrics,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "message": f"Test alert condition not met for: {alert_type}",
                    "alert_type": alert_type,
                    "test_metrics": test_metrics,
                    "timestamp": datetime.now().isoformat()
                }
        finally:
            # Restore original state
            rule.last_triggered = original_last_triggered
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing alert system: {e}")
        raise HTTPException(status_code=500, detail=str(e))