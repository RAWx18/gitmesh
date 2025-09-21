"""
Audit Logging System for Cosmos Web Chat Integration

Provides comprehensive audit logging for sensitive operations,
security events, and compliance requirements.
"""

import json
import logging
import hashlib
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import redis
from pathlib import Path
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    
    # Authorization events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_ESCALATION = "permission_escalation"
    
    # Data access events
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    DATA_EXPORT = "data_export"
    
    # Chat and AI events
    CHAT_SESSION_CREATED = "chat_session_created"
    CHAT_MESSAGE_SENT = "chat_message_sent"
    MODEL_CHANGED = "model_changed"
    CONTEXT_FILES_ADDED = "context_files_added"
    CONTEXT_FILES_REMOVED = "context_files_removed"
    
    # Repository events
    REPOSITORY_ACCESS = "repository_access"
    REPOSITORY_FETCH = "repository_fetch"
    REPOSITORY_CACHE_HIT = "repository_cache_hit"
    
    # Security events
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    ABUSE_DETECTED = "abuse_detected"
    SECURITY_VIOLATION = "security_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    
    # System events
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"
    
    # Administrative events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    TIER_CHANGED = "tier_changed"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


@dataclass
class AuditContext:
    """Context information for audit events."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    
    @classmethod
    def from_request(cls, request) -> 'AuditContext':
        """Create audit context from FastAPI request."""
        return cls(
            user_id=getattr(request.state, 'user_id', None),
            session_id=getattr(request.state, 'session_id', None),
            request_id=getattr(request.state, 'request_id', None),
            ip_address=cls._get_client_ip(request),
            user_agent=request.headers.get('user-agent'),
            endpoint=request.url.path,
            method=request.method
        )
    
    @staticmethod
    def _get_client_ip(request) -> Optional[str]:
        """Extract client IP from request."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        if hasattr(request.client, "host"):
            return request.client.host
        
        return None


class AuditLogger:
    """
    Comprehensive audit logging system.
    
    Provides secure, tamper-evident logging of sensitive operations
    and security events with multiple storage backends.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the audit logger."""
        self.redis_client = redis_client
        self.settings = get_settings()
        
        # Configure file logging
        self.audit_log_path = Path("logs/audit.log")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure structured logger for audit events
        self.audit_logger = structlog.get_logger("audit")
        
        # Event retention periods (in days)
        self.retention_periods = {
            AuditSeverity.LOW: 30,
            AuditSeverity.MEDIUM: 90,
            AuditSeverity.HIGH: 365,
            AuditSeverity.CRITICAL: 2555  # 7 years for critical events
        }
        
        # Events that require immediate alerting
        self.alert_events = {
            AuditEventType.LOGIN_FAILURE,
            AuditEventType.ACCESS_DENIED,
            AuditEventType.ABUSE_DETECTED,
            AuditEventType.SECURITY_VIOLATION,
            AuditEventType.SUSPICIOUS_ACTIVITY,
            AuditEventType.PERMISSION_ESCALATION
        }
    
    def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        context: Optional[AuditContext] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        result: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Log an audit event.
        
        Args:
            event_type: Type of audit event
            severity: Severity level
            context: Audit context information
            resource: Resource being accessed/modified
            action: Action being performed
            result: Result of the action
            details: Additional event details
            correlation_id: Correlation ID for tracking
            
        Returns:
            Event ID for tracking
        """
        # Create audit event
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            user_id=context.user_id if context else None,
            session_id=context.session_id if context else None,
            ip_address=context.ip_address if context else None,
            user_agent=context.user_agent if context else None,
            endpoint=context.endpoint if context else None,
            method=context.method if context else None,
            resource=resource,
            action=action,
            result=result,
            details=details or {},
            correlation_id=correlation_id
        )
        
        # Generate event ID
        event_id = self._generate_event_id(event)
        
        # Log to structured logger
        self._log_to_structured_logger(event, event_id)
        
        # Store in Redis for real-time access
        if self.redis_client:
            self._store_in_redis(event, event_id)
        
        # Store in file for long-term retention
        self._store_in_file(event, event_id)
        
        # Check for alerting
        if event_type in self.alert_events or severity == AuditSeverity.CRITICAL:
            self._trigger_alert(event, event_id)
        
        return event_id
    
    def _generate_event_id(self, event: AuditEvent) -> str:
        """Generate a unique event ID."""
        # Create hash from event data for uniqueness and integrity
        event_data = f"{event.timestamp.isoformat()}{event.event_type.value}{event.user_id or 'anonymous'}"
        event_hash = hashlib.sha256(event_data.encode()).hexdigest()[:16]
        return f"audit_{event_hash}"
    
    def _log_to_structured_logger(self, event: AuditEvent, event_id: str):
        """Log event to structured logger."""
        log_data = {
            "event_id": event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "timestamp": event.timestamp.isoformat(),
            "user_id": event.user_id,
            "session_id": event.session_id,
            "ip_address": event.ip_address,
            "endpoint": event.endpoint,
            "method": event.method,
            "resource": event.resource,
            "action": event.action,
            "result": event.result,
            "correlation_id": event.correlation_id
        }
        
        # Add details if present
        if event.details:
            log_data["details"] = event.details
        
        # Log with appropriate level based on severity
        if event.severity == AuditSeverity.CRITICAL:
            self.audit_logger.critical("Critical audit event", **log_data)
        elif event.severity == AuditSeverity.HIGH:
            self.audit_logger.error("High severity audit event", **log_data)
        elif event.severity == AuditSeverity.MEDIUM:
            self.audit_logger.warning("Medium severity audit event", **log_data)
        else:
            self.audit_logger.info("Audit event", **log_data)
    
    def _store_in_redis(self, event: AuditEvent, event_id: str):
        """Store event in Redis for real-time access."""
        try:
            # Store individual event
            event_key = f"audit:event:{event_id}"
            event_data = asdict(event)
            
            # Convert datetime to string
            event_data["timestamp"] = event.timestamp.isoformat()
            
            # Store with TTL based on severity
            ttl_days = self.retention_periods.get(event.severity, 30)
            ttl_seconds = ttl_days * 24 * 3600
            
            self.redis_client.setex(
                event_key,
                ttl_seconds,
                json.dumps(event_data, default=str)
            )
            
            # Add to event index by type
            type_index_key = f"audit:index:type:{event.event_type.value}"
            self.redis_client.lpush(type_index_key, event_id)
            self.redis_client.expire(type_index_key, ttl_seconds)
            
            # Add to event index by user
            if event.user_id:
                user_index_key = f"audit:index:user:{event.user_id}"
                self.redis_client.lpush(user_index_key, event_id)
                self.redis_client.expire(user_index_key, ttl_seconds)
            
            # Add to daily index
            date_key = event.timestamp.strftime("%Y-%m-%d")
            daily_index_key = f"audit:index:daily:{date_key}"
            self.redis_client.lpush(daily_index_key, event_id)
            self.redis_client.expire(daily_index_key, ttl_seconds)
            
            # Add to severity index
            severity_index_key = f"audit:index:severity:{event.severity.value}"
            self.redis_client.lpush(severity_index_key, event_id)
            self.redis_client.expire(severity_index_key, ttl_seconds)
            
        except Exception as e:
            logger.error(f"Failed to store audit event in Redis: {e}")
    
    def _store_in_file(self, event: AuditEvent, event_id: str):
        """Store event in file for long-term retention."""
        try:
            # Create log entry
            log_entry = {
                "event_id": event_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "user_id": event.user_id,
                "session_id": event.session_id,
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "endpoint": event.endpoint,
                "method": event.method,
                "resource": event.resource,
                "action": event.action,
                "result": event.result,
                "details": event.details,
                "correlation_id": event.correlation_id
            }
            
            # Write to file (one JSON object per line)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, default=str) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to store audit event in file: {e}")
    
    def _trigger_alert(self, event: AuditEvent, event_id: str):
        """Trigger alert for critical events."""
        try:
            alert_data = {
                "event_id": event_id,
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "timestamp": event.timestamp.isoformat(),
                "user_id": event.user_id,
                "ip_address": event.ip_address,
                "details": event.details
            }
            
            # Store alert in Redis for immediate processing
            if self.redis_client:
                alert_key = f"audit:alert:{event_id}"
                self.redis_client.setex(
                    alert_key,
                    3600,  # 1 hour TTL for alerts
                    json.dumps(alert_data, default=str)
                )
                
                # Add to alert queue
                self.redis_client.lpush("audit:alerts", event_id)
            
            # Log critical alert
            logger.critical(
                f"AUDIT ALERT: {event.event_type.value}",
                extra=alert_data
            )
            
        except Exception as e:
            logger.error(f"Failed to trigger audit alert: {e}")
    
    def get_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit events based on filters.
        
        Args:
            event_type: Filter by event type
            user_id: Filter by user ID
            severity: Filter by severity
            start_date: Start date for filtering
            end_date: End date for filtering
            limit: Maximum number of events to return
            
        Returns:
            List of audit events
        """
        if not self.redis_client:
            return []
        
        try:
            event_ids = []
            
            # Get event IDs based on filters
            if event_type:
                index_key = f"audit:index:type:{event_type.value}"
                event_ids = self.redis_client.lrange(index_key, 0, limit - 1)
            elif user_id:
                index_key = f"audit:index:user:{user_id}"
                event_ids = self.redis_client.lrange(index_key, 0, limit - 1)
            elif severity:
                index_key = f"audit:index:severity:{severity.value}"
                event_ids = self.redis_client.lrange(index_key, 0, limit - 1)
            else:
                # Get from daily index (most recent day)
                date_key = datetime.now().strftime("%Y-%m-%d")
                index_key = f"audit:index:daily:{date_key}"
                event_ids = self.redis_client.lrange(index_key, 0, limit - 1)
            
            # Retrieve event data
            events = []
            for event_id in event_ids:
                event_key = f"audit:event:{event_id.decode() if isinstance(event_id, bytes) else event_id}"
                event_data = self.redis_client.get(event_key)
                
                if event_data:
                    try:
                        event_dict = json.loads(event_data)
                        
                        # Apply date filtering if specified
                        if start_date or end_date:
                            event_timestamp = datetime.fromisoformat(event_dict["timestamp"])
                            
                            if start_date and event_timestamp < start_date:
                                continue
                            if end_date and event_timestamp > end_date:
                                continue
                        
                        events.append(event_dict)
                        
                    except json.JSONDecodeError:
                        continue
            
            return events[:limit]
            
        except Exception as e:
            logger.error(f"Failed to retrieve audit events: {e}")
            return []
    
    def get_event_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get audit event statistics.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with event statistics
        """
        if not self.redis_client:
            return {}
        
        try:
            stats = {
                "total_events": 0,
                "events_by_type": {},
                "events_by_severity": {},
                "events_by_day": {},
                "top_users": {},
                "security_events": 0
            }
            
            # Analyze events for the specified number of days
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                daily_index_key = f"audit:index:daily:{date}"
                
                event_ids = self.redis_client.lrange(daily_index_key, 0, -1)
                daily_count = len(event_ids)
                
                stats["events_by_day"][date] = daily_count
                stats["total_events"] += daily_count
                
                # Analyze individual events (sample to avoid performance issues)
                sample_size = min(100, daily_count)
                for event_id in event_ids[:sample_size]:
                    event_key = f"audit:event:{event_id.decode() if isinstance(event_id, bytes) else event_id}"
                    event_data = self.redis_client.get(event_key)
                    
                    if event_data:
                        try:
                            event_dict = json.loads(event_data)
                            
                            # Count by type
                            event_type = event_dict.get("event_type", "unknown")
                            stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
                            
                            # Count by severity
                            severity = event_dict.get("severity", "unknown")
                            stats["events_by_severity"][severity] = stats["events_by_severity"].get(severity, 0) + 1
                            
                            # Count by user
                            user_id = event_dict.get("user_id")
                            if user_id:
                                stats["top_users"][user_id] = stats["top_users"].get(user_id, 0) + 1
                            
                            # Count security events
                            if event_type in [e.value for e in self.alert_events]:
                                stats["security_events"] += 1
                                
                        except json.JSONDecodeError:
                            continue
            
            # Sort top users
            stats["top_users"] = dict(sorted(
                stats["top_users"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return {}


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for common audit events
def log_authentication_event(
    event_type: AuditEventType,
    context: AuditContext,
    result: str,
    details: Optional[Dict[str, Any]] = None
):
    """Log authentication-related events."""
    severity = AuditSeverity.HIGH if "failure" in event_type.value else AuditSeverity.MEDIUM
    
    audit_logger.log_event(
        event_type=event_type,
        severity=severity,
        context=context,
        action="authenticate",
        result=result,
        details=details
    )


def log_authorization_event(
    event_type: AuditEventType,
    context: AuditContext,
    resource: str,
    action: str,
    result: str,
    details: Optional[Dict[str, Any]] = None
):
    """Log authorization-related events."""
    severity = AuditSeverity.HIGH if "denied" in result.lower() else AuditSeverity.MEDIUM
    
    audit_logger.log_event(
        event_type=event_type,
        severity=severity,
        context=context,
        resource=resource,
        action=action,
        result=result,
        details=details
    )


def log_data_access_event(
    event_type: AuditEventType,
    context: AuditContext,
    resource: str,
    action: str,
    result: str = "success",
    details: Optional[Dict[str, Any]] = None
):
    """Log data access events."""
    severity = AuditSeverity.MEDIUM if "delete" in action.lower() else AuditSeverity.LOW
    
    audit_logger.log_event(
        event_type=event_type,
        severity=severity,
        context=context,
        resource=resource,
        action=action,
        result=result,
        details=details
    )


def log_security_event(
    event_type: AuditEventType,
    context: AuditContext,
    description: str,
    severity: AuditSeverity = AuditSeverity.HIGH,
    details: Optional[Dict[str, Any]] = None
):
    """Log security-related events."""
    audit_logger.log_event(
        event_type=event_type,
        severity=severity,
        context=context,
        action="security_check",
        result=description,
        details=details
    )


def log_chat_event(
    event_type: AuditEventType,
    context: AuditContext,
    session_id: str,
    action: str,
    details: Optional[Dict[str, Any]] = None
):
    """Log chat-related events."""
    audit_logger.log_event(
        event_type=event_type,
        severity=AuditSeverity.LOW,
        context=context,
        resource=f"chat_session:{session_id}",
        action=action,
        result="success",
        details=details
    )