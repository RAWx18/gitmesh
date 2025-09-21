"""
Security Monitoring API Routes

Provides endpoints for monitoring security events, rate limits,
abuse patterns, and audit logs.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse
import structlog

from models.api.auth_models import User
from .dependencies import get_current_user
from utils.rate_limiting import rate_limiter, abuse_detector, RateLimitType
from utils.audit_logging import audit_logger, AuditEventType, AuditSeverity
from utils.error_handling import error_handler
from config.security_config import security_config

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/security", tags=["security-monitoring"])


@router.get("/status")
async def get_security_status():
    """
    Get overall security system status.
    
    Returns:
        Security system status and health information
    """
    try:
        # Get rate limiter statistics
        rate_limit_stats = {}
        if hasattr(rate_limiter, 'error_counts'):
            rate_limit_stats = rate_limiter.error_counts
        
        # Get error handler statistics
        error_stats = error_handler.get_error_statistics()
        
        # Get audit statistics
        audit_stats = audit_logger.get_event_statistics(days=1)
        
        status_info = {
            "security_level": security_config.security_level.value,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "rate_limiting": {
                    "enabled": security_config.rate_limiting_enabled,
                    "status": "healthy",
                    "statistics": rate_limit_stats
                },
                "abuse_detection": {
                    "enabled": security_config.abuse_detection_enabled,
                    "status": "healthy"
                },
                "input_validation": {
                    "enabled": security_config.input_sanitization_enabled,
                    "level": security_config.validation_level.value,
                    "status": "healthy"
                },
                "audit_logging": {
                    "enabled": security_config.audit_logging_enabled,
                    "status": "healthy",
                    "events_today": audit_stats.get("total_events", 0)
                },
                "error_handling": {
                    "status": "healthy",
                    "statistics": error_stats
                }
            },
            "security_metrics": {
                "total_errors_today": audit_stats.get("security_events", 0),
                "error_rate": error_stats.get("error_rate_percentage", 0),
                "active_requests": error_stats.get("active_requests", 0)
            }
        }
        
        return {
            "success": True,
            "status": status_info
        }
        
    except Exception as e:
        logger.error(f"Error getting security status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get security status"
        )


@router.get("/rate-limits/{identifier}")
async def get_rate_limit_status(
    identifier: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Get rate limit status for an identifier.
    
    Args:
        identifier: Rate limit identifier (user ID, IP, etc.)
        
    Returns:
        Current rate limit status for all limit types
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Only allow users to check their own rate limits or admins to check any
    user_identifier = f"user:{current_user.id}"
    if identifier != user_identifier and not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Get user tier
        user_tier = getattr(current_user, 'tier', 'free')
        
        # Check all rate limit types
        limit_types = [
            RateLimitType.REQUESTS_PER_MINUTE,
            RateLimitType.REQUESTS_PER_HOUR,
            RateLimitType.REQUESTS_PER_DAY,
            RateLimitType.MESSAGES_PER_MINUTE,
            RateLimitType.MESSAGES_PER_HOUR,
            RateLimitType.CONTEXT_FILES_PER_HOUR,
            RateLimitType.REPOSITORY_FETCHES_PER_DAY,
            RateLimitType.MODEL_SWITCHES_PER_HOUR
        ]
        
        rate_limit_status = {}
        for limit_type in limit_types:
            status_info = rate_limiter.check_rate_limit(
                identifier, limit_type, user_tier, increment=False
            )
            
            rate_limit_status[limit_type.value] = {
                "max_requests": status_info.max_requests,
                "current_count": status_info.current_count,
                "remaining": status_info.remaining,
                "reset_time": status_info.reset_time.isoformat(),
                "is_limited": status_info.is_limited,
                "retry_after": status_info.retry_after
            }
        
        return {
            "success": True,
            "identifier": identifier,
            "user_tier": user_tier,
            "rate_limits": rate_limit_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rate limit status"
        )


@router.get("/abuse-patterns")
async def get_abuse_patterns(
    current_user: Optional[User] = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=30),
    severity_min: int = Query(default=1, ge=1, le=10)
):
    """
    Get detected abuse patterns.
    
    Args:
        days: Number of days to look back
        severity_min: Minimum severity level to include
        
    Returns:
        List of detected abuse patterns
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # This would typically query Redis or database for abuse patterns
        # For now, return a placeholder response
        patterns = {
            "total_patterns": 0,
            "patterns_by_type": {},
            "patterns_by_severity": {},
            "recent_patterns": [],
            "blocked_identifiers": 0,
            "analysis_period": {
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
                "end_date": datetime.now().isoformat(),
                "days": days
            }
        }
        
        return {
            "success": True,
            "abuse_patterns": patterns
        }
        
    except Exception as e:
        logger.error(f"Error getting abuse patterns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get abuse patterns"
        )


@router.get("/audit-events")
async def get_audit_events(
    current_user: Optional[User] = Depends(get_current_user),
    event_type: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Get audit events.
    
    Args:
        event_type: Filter by event type
        severity: Filter by severity level
        start_date: Start date for filtering
        end_date: End date for filtering
        limit: Maximum number of events to return
        
    Returns:
        List of audit events
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Convert string parameters to enums if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event type: {event_type}"
                )
        
        severity_enum = None
        if severity:
            try:
                severity_enum = AuditSeverity(severity)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid severity: {severity}"
                )
        
        # Get events from audit logger
        events = audit_logger.get_events(
            event_type=event_type_enum,
            user_id=None,  # Admin can see all users
            severity=severity_enum,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return {
            "success": True,
            "events": events,
            "total_events": len(events),
            "filters": {
                "event_type": event_type,
                "severity": severity,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "limit": limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit events"
        )


@router.get("/audit-statistics")
async def get_audit_statistics(
    current_user: Optional[User] = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=30)
):
    """
    Get audit event statistics.
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Audit event statistics and trends
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = audit_logger.get_event_statistics(days=days)
        
        return {
            "success": True,
            "statistics": stats,
            "analysis_period": {
                "days": days,
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
                "end_date": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting audit statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit statistics"
        )


@router.get("/error-statistics")
async def get_error_statistics(
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Get error handling statistics.
    
    Returns:
        Error statistics and trends
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = error_handler.get_error_statistics()
        
        return {
            "success": True,
            "error_statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting error statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get error statistics"
        )


@router.post("/block-identifier")
async def block_identifier(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Block an identifier due to abuse.
    
    Request body:
        - identifier: Identifier to block
        - reason: Reason for blocking
        - duration_hours: Block duration in hours
        - severity: Severity level (1-10)
        
    Returns:
        Block confirmation
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        identifier = request.get("identifier")
        reason = request.get("reason")
        duration_hours = request.get("duration_hours", 1)
        severity = request.get("severity", 5)
        
        if not identifier or not reason:
            raise HTTPException(
                status_code=400,
                detail="identifier and reason are required"
            )
        
        # Validate parameters
        if duration_hours < 0 or duration_hours > 168:  # Max 1 week
            raise HTTPException(
                status_code=400,
                detail="duration_hours must be between 0 and 168"
            )
        
        if severity < 1 or severity > 10:
            raise HTTPException(
                status_code=400,
                detail="severity must be between 1 and 10"
            )
        
        # Block the identifier
        duration_seconds = int(duration_hours * 3600)
        abuse_detector.block_identifier(
            identifier=identifier,
            reason=reason,
            duration_seconds=duration_seconds,
            severity=severity
        )
        
        # Log the administrative action
        from utils.audit_logging import log_security_event, AuditContext
        
        context = AuditContext(
            user_id=str(current_user.id),
            ip_address="admin_action"
        )
        
        log_security_event(
            AuditEventType.SECURITY_VIOLATION,
            context,
            f"Identifier blocked by admin: {identifier}",
            AuditSeverity.HIGH,
            {
                "blocked_identifier": identifier,
                "reason": reason,
                "duration_hours": duration_hours,
                "severity": severity,
                "admin_user": current_user.login
            }
        )
        
        return {
            "success": True,
            "message": f"Identifier {identifier} blocked successfully",
            "block_details": {
                "identifier": identifier,
                "reason": reason,
                "duration_hours": duration_hours,
                "severity": severity,
                "expires_at": (datetime.now() + timedelta(seconds=duration_seconds)).isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error blocking identifier: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to block identifier"
        )


@router.delete("/block-identifier/{identifier}")
async def unblock_identifier(
    identifier: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Unblock an identifier.
    
    Args:
        identifier: Identifier to unblock
        
    Returns:
        Unblock confirmation
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Check if identifier is currently blocked
        is_blocked, block_reason = abuse_detector.is_identifier_blocked(identifier)
        
        if not is_blocked:
            return {
                "success": True,
                "message": f"Identifier {identifier} is not currently blocked"
            }
        
        # Unblock by removing from Redis (if Redis is available)
        if abuse_detector.redis_client:
            block_key = f"blocked:{identifier}"
            abuse_detector.redis_client.delete(block_key)
        
        # Log the administrative action
        from utils.audit_logging import log_security_event, AuditContext
        
        context = AuditContext(
            user_id=str(current_user.id),
            ip_address="admin_action"
        )
        
        log_security_event(
            AuditEventType.SECURITY_VIOLATION,
            context,
            f"Identifier unblocked by admin: {identifier}",
            AuditSeverity.MEDIUM,
            {
                "unblocked_identifier": identifier,
                "previous_reason": block_reason,
                "admin_user": current_user.login
            }
        )
        
        return {
            "success": True,
            "message": f"Identifier {identifier} unblocked successfully",
            "previous_block_reason": block_reason
        }
        
    except Exception as e:
        logger.error(f"Error unblocking identifier: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unblock identifier"
        )


@router.get("/configuration")
async def get_security_configuration(
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Get current security configuration.
    
    Returns:
        Security configuration details
    """
    if not current_user or not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        config_info = {
            "security_level": security_config.security_level.value,
            "validation_level": security_config.validation_level.value,
            "features": {
                "input_sanitization": security_config.input_sanitization_enabled,
                "output_sanitization": security_config.output_sanitization_enabled,
                "rate_limiting": security_config.rate_limiting_enabled,
                "abuse_detection": security_config.abuse_detection_enabled,
                "auto_blocking": security_config.auto_blocking_enabled,
                "cors": security_config.cors_enabled,
                "security_headers": security_config.security_headers_enabled,
                "hsts": security_config.hsts_enabled,
                "csp": security_config.csp_enabled,
                "audit_logging": security_config.audit_logging_enabled
            },
            "limits": {
                "max_file_size_mb": security_config.max_file_size_mb,
                "max_request_size_mb": security_config.max_request_size_mb,
                "max_json_payload_mb": security_config.max_json_payload_mb,
                "session_timeout_minutes": security_config.session_timeout_minutes,
                "audit_retention_days": security_config.audit_retention_days
            },
            "cors_settings": {
                "allowed_origins": security_config.allowed_origins,
                "allow_credentials": security_config.allow_credentials
            },
            "allowed_file_types": security_config.allowed_file_types
        }
        
        return {
            "success": True,
            "configuration": config_info,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting security configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get security configuration"
        )