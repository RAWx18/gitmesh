"""
Chat Analytics Service for Cosmos Web Chat Integration
Provides comprehensive monitoring and analytics functionality.
"""

import json
import uuid
import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import asdict
from collections import defaultdict, Counter

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..config.key_manager import key_manager
    from ..services.performance_optimization_service import get_performance_service, cached_response
    from ..models.api.chat_analytics_models import (
        SessionMetrics, UserEngagementMetrics, ModelUsageMetrics, ErrorMetrics,
        PerformanceMetrics, SystemHealthMetrics, Alert, AlertRule, AlertSeverity,
        AnalyticsSummary, ConversionAnalytics, RealtimeMetrics, MetricType
    )
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from config.key_manager import key_manager
    from services.performance_optimization_service import get_performance_service, cached_response
    from models.api.chat_analytics_models import (
        SessionMetrics, UserEngagementMetrics, ModelUsageMetrics, ErrorMetrics,
        PerformanceMetrics, SystemHealthMetrics, Alert, AlertRule, AlertSeverity,
        AnalyticsSummary, ConversionAnalytics, RealtimeMetrics, MetricType
    )

logger = structlog.get_logger(__name__)


class ChatAnalyticsService:
    """
    Comprehensive analytics service for Cosmos Web Chat.
    
    Provides monitoring, metrics collection, error tracking, and alerting
    functionality for the chat system.
    """
    
    def __init__(self):
        """Initialize the analytics service."""
        self.settings = get_settings()
        self.performance_service = get_performance_service()
        self.redis_client = self.performance_service.get_redis_client("chat_analytics")
        
        # Key prefixes for different metric types
        self.session_metrics_prefix = "analytics:session:"
        self.user_metrics_prefix = "analytics:user:"
        self.model_metrics_prefix = "analytics:model:"
        self.error_metrics_prefix = "analytics:error:"
        self.performance_metrics_prefix = "analytics:performance:"
        self.alert_prefix = "analytics:alert:"
        self.alert_rules_prefix = "analytics:alert_rules:"
        self.conversion_metrics_prefix = "analytics:conversion:"
        
        # Metric retention periods (in seconds)
        self.session_retention = 30 * 24 * 3600  # 30 days
        self.user_retention = 90 * 24 * 3600     # 90 days
        self.model_retention = 90 * 24 * 3600    # 90 days
        self.error_retention = 30 * 24 * 3600    # 30 days
        self.performance_retention = 7 * 24 * 3600  # 7 days
        self.alert_retention = 30 * 24 * 3600    # 30 days
        
        # Model cost estimates (USD per 1K tokens)
        self.model_costs = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "deepseek-coder": {"input": 0.00014, "output": 0.00028},
        }
        
        # Initialize alert rules
        self._initialize_default_alert_rules()
    
    async def track_session_metrics(
        self,
        session_id: str,
        user_id: str,
        model_used: str,
        repository_url: Optional[str] = None,
        branch: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Track session-level metrics.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            model_used: AI model being used
            repository_url: Repository URL if applicable
            branch: Branch name if applicable
            **kwargs: Additional session data
        """
        try:
            # Get existing session data or create new
            session_key = f"{self.session_metrics_prefix}{session_id}"
            existing_data = self.redis_client.hgetall(session_key)
            
            if existing_data:
                # Update existing session
                session_data = {
                    "last_activity": datetime.now().isoformat(),
                    "message_count": int(existing_data.get("message_count", 0)) + kwargs.get("message_increment", 0),
                    "context_files_count": kwargs.get("context_files_count", existing_data.get("context_files_count", 0)),
                    "context_files_size": kwargs.get("context_files_size", existing_data.get("context_files_size", 0)),
                    "conversion_operations": int(existing_data.get("conversion_operations", 0)) + kwargs.get("conversion_increment", 0),
                    "error_count": int(existing_data.get("error_count", 0)) + kwargs.get("error_increment", 0),
                    "is_active": kwargs.get("is_active", True)
                }
                
                # Calculate duration
                created_at = datetime.fromisoformat(existing_data["created_at"])
                duration = (datetime.now() - created_at).total_seconds()
                session_data["duration_seconds"] = int(duration)
            else:
                # Create new session metrics
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat(),
                    "last_activity": datetime.now().isoformat(),
                    "duration_seconds": 0,
                    "message_count": kwargs.get("message_count", 0),
                    "user_messages": kwargs.get("user_messages", 0),
                    "assistant_messages": kwargs.get("assistant_messages", 0),
                    "context_files_count": kwargs.get("context_files_count", 0),
                    "context_files_size": kwargs.get("context_files_size", 0),
                    "repository_url": repository_url or "",
                    "branch": branch or "",
                    "model_used": model_used,
                    "conversion_operations": kwargs.get("conversion_operations", 0),
                    "error_count": kwargs.get("error_count", 0),
                    "is_active": kwargs.get("is_active", True)
                }
            
            # Store session metrics
            pipe = self.redis_client.pipeline()
            pipe.hset(session_key, mapping=session_data)
            pipe.expire(session_key, self.session_retention)
            
            # Add to daily session index
            date_key = f"analytics:sessions:daily:{datetime.now().strftime('%Y-%m-%d')}"
            pipe.sadd(date_key, session_id)
            pipe.expire(date_key, self.session_retention)
            
            pipe.execute()
            
            logger.debug("Session metrics tracked", session_id=session_id, user_id=user_id)
            
        except Exception as e:
            logger.error("Error tracking session metrics", error=str(e), session_id=session_id)
    
    async def track_user_engagement(
        self,
        user_id: str,
        session_id: str,
        activity_type: str,
        **kwargs
    ) -> None:
        """
        Track user engagement metrics.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            activity_type: Type of activity (message, file_add, etc.)
            **kwargs: Additional activity data
        """
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            user_key = f"{self.user_metrics_prefix}{user_id}:{date_str}"
            
            # Get existing user metrics for today
            existing_data = self.redis_client.hgetall(user_key)
            
            if existing_data:
                # Update existing metrics
                user_data = {
                    "total_sessions": len(set(existing_data.get("session_ids", "").split(",") + [session_id])),
                    "total_messages": int(existing_data.get("total_messages", 0)) + (1 if activity_type == "message" else 0),
                    "context_files_added": int(existing_data.get("context_files_added", 0)) + kwargs.get("files_added", 0),
                    "conversion_operations": int(existing_data.get("conversion_operations", 0)) + kwargs.get("conversions", 0),
                    "last_activity": datetime.now().isoformat(),
                    "session_ids": ",".join(set(existing_data.get("session_ids", "").split(",") + [session_id]))
                }
                
                # Update models used
                models_used = set(existing_data.get("models_used", "").split(","))
                if kwargs.get("model"):
                    models_used.add(kwargs["model"])
                user_data["models_used"] = ",".join(filter(None, models_used))
                
                # Update repositories used
                repos_used = set(existing_data.get("repositories_used", "").split(","))
                if kwargs.get("repository_url"):
                    repos_used.add(kwargs["repository_url"])
                user_data["repositories_used"] = ",".join(filter(None, repos_used))
                
            else:
                # Create new user metrics
                user_data = {
                    "user_id": user_id,
                    "date": date_str,
                    "total_sessions": 1,
                    "total_messages": 1 if activity_type == "message" else 0,
                    "context_files_added": kwargs.get("files_added", 0),
                    "conversion_operations": kwargs.get("conversions", 0),
                    "last_activity": datetime.now().isoformat(),
                    "session_ids": session_id,
                    "models_used": kwargs.get("model", ""),
                    "repositories_used": kwargs.get("repository_url", "")
                }
            
            # Store user metrics
            pipe = self.redis_client.pipeline()
            pipe.hset(user_key, mapping=user_data)
            pipe.expire(user_key, self.user_retention)
            
            # Add to daily user index
            daily_users_key = f"analytics:users:daily:{date_str}"
            pipe.sadd(daily_users_key, user_id)
            pipe.expire(daily_users_key, self.user_retention)
            
            pipe.execute()
            
            logger.debug("User engagement tracked", user_id=user_id, activity_type=activity_type)
            
        except Exception as e:
            logger.error("Error tracking user engagement", error=str(e), user_id=user_id)
    
    async def track_model_usage(
        self,
        model_name: str,
        canonical_name: str,
        provider: str,
        session_id: str,
        user_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_time: float = 0.0,
        success: bool = True
    ) -> None:
        """
        Track AI model usage and cost metrics.
        
        Args:
            model_name: Model alias name
            canonical_name: Canonical model name
            provider: Model provider
            session_id: Session identifier
            user_id: User identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            response_time: Response time in seconds
            success: Whether the request was successful
        """
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            model_key = f"{self.model_metrics_prefix}{model_name}:{date_str}"
            
            # Calculate estimated cost
            cost_config = self.model_costs.get(canonical_name, {"input": 0.001, "output": 0.002})
            estimated_cost = (
                (input_tokens / 1000) * cost_config["input"] +
                (output_tokens / 1000) * cost_config["output"]
            )
            
            # Get existing model metrics for today
            existing_data = self.redis_client.hgetall(model_key)
            
            if existing_data:
                # Update existing metrics
                total_requests = int(existing_data.get("request_count", 0)) + 1
                total_tokens = int(existing_data.get("total_tokens", 0)) + input_tokens + output_tokens
                total_input_tokens = int(existing_data.get("input_tokens", 0)) + input_tokens
                total_output_tokens = int(existing_data.get("output_tokens", 0)) + output_tokens
                total_cost = float(existing_data.get("estimated_cost", 0)) + estimated_cost
                total_response_time = float(existing_data.get("total_response_time", 0)) + response_time
                error_count = int(existing_data.get("error_count", 0)) + (0 if success else 1)
                
                # Update unique users and sessions
                unique_users = set(existing_data.get("unique_user_ids", "").split(","))
                unique_users.add(user_id)
                unique_sessions = set(existing_data.get("unique_session_ids", "").split(","))
                unique_sessions.add(session_id)
                
                model_data = {
                    "request_count": total_requests,
                    "total_tokens": total_tokens,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "estimated_cost": total_cost,
                    "total_response_time": total_response_time,
                    "avg_response_time": total_response_time / total_requests,
                    "error_count": error_count,
                    "success_rate": ((total_requests - error_count) / total_requests) * 100,
                    "unique_users": len(unique_users),
                    "unique_sessions": len(unique_sessions),
                    "unique_user_ids": ",".join(filter(None, unique_users)),
                    "unique_session_ids": ",".join(filter(None, unique_sessions))
                }
            else:
                # Create new model metrics
                model_data = {
                    "model_name": model_name,
                    "canonical_name": canonical_name,
                    "provider": provider,
                    "date": date_str,
                    "request_count": 1,
                    "total_tokens": input_tokens + output_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost": estimated_cost,
                    "total_response_time": response_time,
                    "avg_response_time": response_time,
                    "error_count": 0 if success else 1,
                    "success_rate": 100.0 if success else 0.0,
                    "unique_users": 1,
                    "unique_sessions": 1,
                    "unique_user_ids": user_id,
                    "unique_session_ids": session_id
                }
            
            # Store model metrics
            pipe = self.redis_client.pipeline()
            pipe.hset(model_key, mapping=model_data)
            pipe.expire(model_key, self.model_retention)
            
            # Add to daily model index
            daily_models_key = f"analytics:models:daily:{date_str}"
            pipe.sadd(daily_models_key, model_name)
            pipe.expire(daily_models_key, self.model_retention)
            
            pipe.execute()
            
            logger.debug("Model usage tracked", model=model_name, tokens=input_tokens + output_tokens, cost=estimated_cost)
            
        except Exception as e:
            logger.error("Error tracking model usage", error=str(e), model=model_name)
    
    async def track_error(
        self,
        error_type: str,
        error_message: str,
        component: str,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        model_name: Optional[str] = None,
        repository_url: Optional[str] = None,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Track error occurrences and trigger alerts if needed.
        
        Args:
            error_type: Type of error
            error_message: Error message
            component: Component where error occurred
            severity: Error severity level
            session_id: Session ID if applicable
            user_id: User ID if applicable
            model_name: Model name if applicable
            repository_url: Repository URL if applicable
            stack_trace: Stack trace if available
            context: Additional error context
            
        Returns:
            Error ID
        """
        try:
            error_id = str(uuid.uuid4())
            timestamp = datetime.now()
            
            error_data = {
                "error_id": error_id,
                "timestamp": timestamp.isoformat(),
                "error_type": error_type,
                "error_message": error_message,
                "component": component,
                "severity": severity.value,
                "session_id": session_id or "",
                "user_id": user_id or "",
                "model_name": model_name or "",
                "repository_url": repository_url or "",
                "stack_trace": stack_trace or "",
                "context": json.dumps(context or {}),
                "resolved": False
            }
            
            # Store error
            error_key = f"{self.error_metrics_prefix}{error_id}"
            pipe = self.redis_client.pipeline()
            pipe.hset(error_key, mapping=error_data)
            pipe.expire(error_key, self.error_retention)
            
            # Add to error indexes
            date_str = timestamp.strftime('%Y-%m-%d')
            hour_str = timestamp.strftime('%Y-%m-%d:%H')
            
            pipe.sadd(f"analytics:errors:daily:{date_str}", error_id)
            pipe.expire(f"analytics:errors:daily:{date_str}", self.error_retention)
            
            pipe.sadd(f"analytics:errors:hourly:{hour_str}", error_id)
            pipe.expire(f"analytics:errors:hourly:{hour_str}", self.error_retention)
            
            pipe.sadd(f"analytics:errors:type:{error_type}", error_id)
            pipe.expire(f"analytics:errors:type:{error_type}", self.error_retention)
            
            pipe.sadd(f"analytics:errors:component:{component}", error_id)
            pipe.expire(f"analytics:errors:component:{component}", self.error_retention)
            
            pipe.execute()
            
            # Check for alert conditions
            await self._check_error_alerts(error_type, component, severity, timestamp)
            
            logger.error("Error tracked", error_id=error_id, error_type=error_type, component=component, severity=severity.value)
            
            return error_id
            
        except Exception as e:
            logger.error("Error tracking error metrics", error=str(e))
            return ""
    
    async def track_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str,
        component: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Track performance metrics.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            component: Component being measured
            session_id: Session ID if applicable
            user_id: User ID if applicable
            tags: Additional metric tags
        """
        try:
            timestamp = datetime.now()
            metric_id = f"{metric_name}:{timestamp.strftime('%Y%m%d%H%M%S')}"
            
            metric_data = {
                "metric_name": metric_name,
                "timestamp": timestamp.isoformat(),
                "value": value,
                "unit": unit,
                "component": component,
                "session_id": session_id or "",
                "user_id": user_id or "",
                "tags": json.dumps(tags or {})
            }
            
            # Store performance metric
            metric_key = f"{self.performance_metrics_prefix}{metric_id}"
            pipe = self.redis_client.pipeline()
            pipe.hset(metric_key, mapping=metric_data)
            pipe.expire(metric_key, self.performance_retention)
            
            # Add to metric indexes
            date_str = timestamp.strftime('%Y-%m-%d')
            hour_str = timestamp.strftime('%Y-%m-%d:%H')
            
            pipe.sadd(f"analytics:performance:daily:{date_str}", metric_id)
            pipe.expire(f"analytics:performance:daily:{date_str}", self.performance_retention)
            
            pipe.sadd(f"analytics:performance:metric:{metric_name}", metric_id)
            pipe.expire(f"analytics:performance:metric:{metric_name}", self.performance_retention)
            
            pipe.execute()
            
            # Check for performance alerts
            await self._check_performance_alerts(metric_name, value, component, timestamp)
            
            logger.debug("Performance metric tracked", metric=metric_name, value=value, component=component)
            
        except Exception as e:
            logger.error("Error tracking performance metric", error=str(e), metric=metric_name)
    
    async def track_conversion_operation(
        self,
        session_id: str,
        operation_type: str,
        original_command: str,
        web_equivalent: str,
        success: bool,
        conversion_time: float,
        complexity_score: int = 5,
        user_feedback: Optional[str] = None
    ) -> None:
        """
        Track CLI-to-web conversion operations.
        
        Args:
            session_id: Session identifier
            operation_type: Type of operation converted
            original_command: Original CLI command
            web_equivalent: Web equivalent action
            success: Whether conversion was successful
            conversion_time: Time taken for conversion
            complexity_score: Complexity score (1-10)
            user_feedback: User feedback on conversion
        """
        try:
            timestamp = datetime.now()
            conversion_id = str(uuid.uuid4())
            
            conversion_data = {
                "session_id": session_id,
                "timestamp": timestamp.isoformat(),
                "operation_type": operation_type,
                "original_command": original_command,
                "web_equivalent": web_equivalent,
                "success": success,
                "user_feedback": user_feedback or "",
                "conversion_time": conversion_time,
                "complexity_score": complexity_score
            }
            
            # Store conversion analytics
            conversion_key = f"{self.conversion_metrics_prefix}{conversion_id}"
            pipe = self.redis_client.pipeline()
            pipe.hset(conversion_key, mapping=conversion_data)
            pipe.expire(conversion_key, self.session_retention)
            
            # Add to conversion indexes
            date_str = timestamp.strftime('%Y-%m-%d')
            
            pipe.sadd(f"analytics:conversions:daily:{date_str}", conversion_id)
            pipe.expire(f"analytics:conversions:daily:{date_str}", self.session_retention)
            
            pipe.sadd(f"analytics:conversions:session:{session_id}", conversion_id)
            pipe.expire(f"analytics:conversions:session:{session_id}", self.session_retention)
            
            pipe.sadd(f"analytics:conversions:type:{operation_type}", conversion_id)
            pipe.expire(f"analytics:conversions:type:{operation_type}", self.session_retention)
            
            pipe.execute()
            
            logger.debug("Conversion operation tracked", session_id=session_id, operation_type=operation_type, success=success)
            
        except Exception as e:
            logger.error("Error tracking conversion operation", error=str(e), session_id=session_id)
    
    @cached_response(ttl=60)  # Cache for 1 minute
    async def get_realtime_metrics(self) -> RealtimeMetrics:
        """
        Get real-time system metrics.
        
        Returns:
            RealtimeMetrics object
        """
        try:
            timestamp = datetime.now()
            
            # Get active sessions count
            active_sessions = 0
            session_pattern = f"{self.session_metrics_prefix}*"
            session_keys = self.redis_client.keys(session_pattern)
            
            active_users = set()
            for session_key in session_keys:
                session_data = self.redis_client.hgetall(session_key)
                if session_data.get("is_active") == "True":
                    active_sessions += 1
                    active_users.add(session_data.get("user_id"))
            
            # Calculate messages per minute (last 5 minutes)
            five_min_ago = timestamp - timedelta(minutes=5)
            messages_count = 0
            for i in range(5):
                minute_key = (five_min_ago + timedelta(minutes=i)).strftime('%Y-%m-%d:%H:%M')
                minute_messages = self.redis_client.get(f"analytics:messages:minute:{minute_key}")
                if minute_messages:
                    messages_count += int(minute_messages)
            
            messages_per_minute = messages_count / 5.0
            
            # Calculate errors per minute (last 5 minutes)
            errors_count = 0
            for i in range(5):
                minute_key = (five_min_ago + timedelta(minutes=i)).strftime('%Y-%m-%d:%H:%M')
                minute_errors = self.redis_client.get(f"analytics:errors:minute:{minute_key}")
                if minute_errors:
                    errors_count += int(minute_errors)
            
            errors_per_minute = errors_count / 5.0
            
            # Get system metrics (simplified for demo)
            redis_info = self.redis_client.info()
            redis_connections = redis_info.get('connected_clients', 0)
            memory_usage_mb = redis_info.get('used_memory', 0) / (1024 * 1024)
            
            return RealtimeMetrics(
                timestamp=timestamp,
                active_sessions=active_sessions,
                active_users=len(active_users),
                messages_per_minute=messages_per_minute,
                errors_per_minute=errors_per_minute,
                avg_response_time=2.5,  # Placeholder - would calculate from recent performance metrics
                redis_connections=redis_connections,
                memory_usage_mb=memory_usage_mb,
                cpu_usage_percent=15.0  # Placeholder - would get from system monitoring
            )
            
        except Exception as e:
            logger.error("Error getting realtime metrics", error=str(e))
            return RealtimeMetrics(
                timestamp=datetime.now(),
                active_sessions=0,
                active_users=0,
                messages_per_minute=0.0,
                errors_per_minute=0.0,
                avg_response_time=0.0,
                redis_connections=0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0
            )
    
    async def get_session_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> Tuple[List[SessionMetrics], Dict[str, Any]]:
        """
        Get session analytics with filtering and summary.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            user_id: User ID filter
            limit: Maximum number of sessions to return
            
        Returns:
            Tuple of (session metrics list, summary dict)
        """
        try:
            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            sessions = []
            session_pattern = f"{self.session_metrics_prefix}*"
            session_keys = self.redis_client.keys(session_pattern)
            
            for session_key in session_keys[:limit]:
                session_data = self.redis_client.hgetall(session_key)
                if not session_data:
                    continue
                
                # Apply filters
                session_created = datetime.fromisoformat(session_data["created_at"])
                if session_created < start_date or session_created > end_date:
                    continue
                
                if user_id and session_data.get("user_id") != user_id:
                    continue
                
                # Create SessionMetrics object
                session_metrics = SessionMetrics(
                    session_id=session_data["session_id"],
                    user_id=session_data["user_id"],
                    created_at=session_created,
                    last_activity=datetime.fromisoformat(session_data["last_activity"]),
                    duration_seconds=int(session_data.get("duration_seconds", 0)),
                    message_count=int(session_data.get("message_count", 0)),
                    user_messages=int(session_data.get("user_messages", 0)),
                    assistant_messages=int(session_data.get("assistant_messages", 0)),
                    context_files_count=int(session_data.get("context_files_count", 0)),
                    context_files_size=int(session_data.get("context_files_size", 0)),
                    repository_url=session_data.get("repository_url"),
                    branch=session_data.get("branch"),
                    model_used=session_data["model_used"],
                    conversion_operations=int(session_data.get("conversion_operations", 0)),
                    error_count=int(session_data.get("error_count", 0)),
                    is_active=session_data.get("is_active") == "True"
                )
                sessions.append(session_metrics)
            
            # Calculate summary statistics
            if sessions:
                total_duration = sum(s.duration_seconds for s in sessions)
                total_messages = sum(s.message_count for s in sessions)
                active_sessions = sum(1 for s in sessions if s.is_active)
                
                summary = {
                    "total_sessions": len(sessions),
                    "active_sessions": active_sessions,
                    "avg_duration_minutes": (total_duration / len(sessions)) / 60,
                    "avg_messages_per_session": total_messages / len(sessions),
                    "total_messages": total_messages,
                    "unique_users": len(set(s.user_id for s in sessions)),
                    "unique_repositories": len(set(s.repository_url for s in sessions if s.repository_url)),
                    "models_used": list(set(s.model_used for s in sessions))
                }
            else:
                summary = {
                    "total_sessions": 0,
                    "active_sessions": 0,
                    "avg_duration_minutes": 0,
                    "avg_messages_per_session": 0,
                    "total_messages": 0,
                    "unique_users": 0,
                    "unique_repositories": 0,
                    "models_used": []
                }
            
            return sessions, summary
            
        except Exception as e:
            logger.error("Error getting session analytics", error=str(e))
            return [], {}
    
    async def get_model_usage_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model_name: Optional[str] = None
    ) -> Tuple[List[ModelUsageMetrics], float, Dict[str, Any]]:
        """
        Get model usage analytics with cost calculations.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            model_name: Model name filter
            
        Returns:
            Tuple of (usage metrics list, total cost, summary dict)
        """
        try:
            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            usage_metrics = []
            total_cost = 0.0
            
            # Generate date range for querying
            current_date = start_date.date()
            end_date_only = end_date.date()
            
            while current_date <= end_date_only:
                date_str = current_date.strftime('%Y-%m-%d')
                
                # Get models used on this date
                daily_models_key = f"analytics:models:daily:{date_str}"
                model_names = self.redis_client.smembers(daily_models_key)
                
                for model in model_names:
                    if model_name and model != model_name:
                        continue
                    
                    model_key = f"{self.model_metrics_prefix}{model}:{date_str}"
                    model_data = self.redis_client.hgetall(model_key)
                    
                    if model_data:
                        cost = float(model_data.get("estimated_cost", 0))
                        total_cost += cost
                        
                        usage_metric = ModelUsageMetrics(
                            model_name=model_data["model_name"],
                            canonical_name=model_data["canonical_name"],
                            provider=model_data["provider"],
                            date=datetime.strptime(date_str, '%Y-%m-%d'),
                            request_count=int(model_data.get("request_count", 0)),
                            total_tokens=int(model_data.get("total_tokens", 0)),
                            input_tokens=int(model_data.get("input_tokens", 0)),
                            output_tokens=int(model_data.get("output_tokens", 0)),
                            estimated_cost=cost,
                            avg_response_time=float(model_data.get("avg_response_time", 0)),
                            error_count=int(model_data.get("error_count", 0)),
                            success_rate=float(model_data.get("success_rate", 0)),
                            unique_users=int(model_data.get("unique_users", 0)),
                            unique_sessions=int(model_data.get("unique_sessions", 0))
                        )
                        usage_metrics.append(usage_metric)
                
                current_date += timedelta(days=1)
            
            # Calculate summary
            if usage_metrics:
                total_requests = sum(m.request_count for m in usage_metrics)
                total_tokens = sum(m.total_tokens for m in usage_metrics)
                
                summary = {
                    "total_requests": total_requests,
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                    "avg_cost_per_request": total_cost / total_requests if total_requests > 0 else 0,
                    "avg_tokens_per_request": total_tokens / total_requests if total_requests > 0 else 0,
                    "models_count": len(set(m.model_name for m in usage_metrics)),
                    "providers": list(set(m.provider for m in usage_metrics))
                }
            else:
                summary = {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "avg_cost_per_request": 0,
                    "avg_tokens_per_request": 0,
                    "models_count": 0,
                    "providers": []
                }
            
            return usage_metrics, total_cost, summary
            
        except Exception as e:
            logger.error("Error getting model usage analytics", error=str(e))
            return [], 0.0, {}
    
    async def get_error_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        error_type: Optional[str] = None,
        component: Optional[str] = None,
        severity: Optional[AlertSeverity] = None
    ) -> Tuple[List[ErrorMetrics], float, Dict[str, Any]]:
        """
        Get error analytics with filtering and summary.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            error_type: Error type filter
            component: Component filter
            severity: Severity filter
            
        Returns:
            Tuple of (error metrics list, error rate, summary dict)
        """
        try:
            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            errors = []
            
            # Generate date range for querying
            current_date = start_date.date()
            end_date_only = end_date.date()
            
            while current_date <= end_date_only:
                date_str = current_date.strftime('%Y-%m-%d')
                daily_errors_key = f"analytics:errors:daily:{date_str}"
                error_ids = self.redis_client.smembers(daily_errors_key)
                
                for error_id in error_ids:
                    error_key = f"{self.error_metrics_prefix}{error_id}"
                    error_data = self.redis_client.hgetall(error_key)
                    
                    if not error_data:
                        continue
                    
                    # Apply filters
                    if error_type and error_data.get("error_type") != error_type:
                        continue
                    if component and error_data.get("component") != component:
                        continue
                    if severity and error_data.get("severity") != severity.value:
                        continue
                    
                    error_metrics = ErrorMetrics(
                        error_id=error_data["error_id"],
                        timestamp=datetime.fromisoformat(error_data["timestamp"]),
                        error_type=error_data["error_type"],
                        error_code=error_data.get("error_code"),
                        error_message=error_data["error_message"],
                        component=error_data["component"],
                        session_id=error_data.get("session_id"),
                        user_id=error_data.get("user_id"),
                        model_name=error_data.get("model_name"),
                        repository_url=error_data.get("repository_url"),
                        stack_trace=error_data.get("stack_trace"),
                        context=json.loads(error_data.get("context", "{}")),
                        resolved=error_data.get("resolved") == "True",
                        severity=AlertSeverity(error_data["severity"])
                    )
                    errors.append(error_metrics)
                
                current_date += timedelta(days=1)
            
            # Calculate error rate and summary
            total_errors = len(errors)
            
            # Get total requests for error rate calculation (simplified)
            total_requests = 1000  # Placeholder - would calculate from session/model metrics
            error_rate = (total_errors / total_requests) * 100 if total_requests > 0 else 0
            
            if errors:
                error_types = Counter(e.error_type for e in errors)
                components = Counter(e.component for e in errors)
                severities = Counter(e.severity.value for e in errors)
                
                summary = {
                    "total_errors": total_errors,
                    "error_rate": error_rate,
                    "resolved_errors": sum(1 for e in errors if e.resolved),
                    "unresolved_errors": sum(1 for e in errors if not e.resolved),
                    "top_error_types": dict(error_types.most_common(5)),
                    "top_components": dict(components.most_common(5)),
                    "severity_distribution": dict(severities),
                    "unique_sessions": len(set(e.session_id for e in errors if e.session_id)),
                    "unique_users": len(set(e.user_id for e in errors if e.user_id))
                }
            else:
                summary = {
                    "total_errors": 0,
                    "error_rate": 0,
                    "resolved_errors": 0,
                    "unresolved_errors": 0,
                    "top_error_types": {},
                    "top_components": {},
                    "severity_distribution": {},
                    "unique_sessions": 0,
                    "unique_users": 0
                }
            
            return errors, error_rate, summary
            
        except Exception as e:
            logger.error("Error getting error analytics", error=str(e))
            return [], 0.0, {}
    
    def _initialize_default_alert_rules(self) -> None:
        """Initialize default alert rules."""
        try:
            default_rules = [
                {
                    "rule_id": "high_error_rate",
                    "name": "High Error Rate",
                    "description": "Alert when error rate exceeds 5%",
                    "metric_name": "error_rate",
                    "condition": ">",
                    "threshold": 5.0,
                    "severity": AlertSeverity.HIGH,
                    "cooldown_minutes": 10
                },
                {
                    "rule_id": "slow_response_time",
                    "name": "Slow Response Time",
                    "description": "Alert when average response time exceeds 10 seconds",
                    "metric_name": "avg_response_time",
                    "condition": ">",
                    "threshold": 10.0,
                    "severity": AlertSeverity.MEDIUM,
                    "cooldown_minutes": 5
                },
                {
                    "rule_id": "high_memory_usage",
                    "name": "High Memory Usage",
                    "description": "Alert when memory usage exceeds 80%",
                    "metric_name": "memory_usage_percent",
                    "condition": ">",
                    "threshold": 80.0,
                    "severity": AlertSeverity.HIGH,
                    "cooldown_minutes": 15
                }
            ]
            
            for rule_data in default_rules:
                rule_key = f"{self.alert_rules_prefix}{rule_data['rule_id']}"
                if not self.redis_client.exists(rule_key):
                    rule_data["created_at"] = datetime.now().isoformat()
                    rule_data["updated_at"] = datetime.now().isoformat()
                    rule_data["enabled"] = "true"  # Convert boolean to string for Redis
                    
                    # Convert all values to strings for Redis
                    redis_data = {k: str(v) for k, v in rule_data.items()}
                    self.redis_client.hset(rule_key, mapping=redis_data)
                    logger.info("Initialized default alert rule", rule_id=rule_data["rule_id"])
            
        except Exception as e:
            logger.error("Error initializing default alert rules", error=str(e))
    
    async def _check_error_alerts(
        self,
        error_type: str,
        component: str,
        severity: AlertSeverity,
        timestamp: datetime
    ) -> None:
        """Check if error conditions trigger any alerts."""
        try:
            # Check for error rate alerts
            hour_str = timestamp.strftime('%Y-%m-%d:%H')
            hourly_errors_key = f"analytics:errors:hourly:{hour_str}"
            error_count = self.redis_client.scard(hourly_errors_key)
            
            # Simple error rate calculation (errors per hour)
            if error_count > 10:  # More than 10 errors per hour
                await self._trigger_alert(
                    "high_error_rate",
                    "error_rate",
                    error_count,
                    10.0,
                    f"High error rate detected: {error_count} errors in the last hour"
                )
            
        except Exception as e:
            logger.error("Error checking error alerts", error=str(e))
    
    async def _check_performance_alerts(
        self,
        metric_name: str,
        value: float,
        component: str,
        timestamp: datetime
    ) -> None:
        """Check if performance metrics trigger any alerts."""
        try:
            # Get alert rules for this metric
            rules_pattern = f"{self.alert_rules_prefix}*"
            rule_keys = self.redis_client.keys(rules_pattern)
            
            for rule_key in rule_keys:
                rule_data = self.redis_client.hgetall(rule_key)
                if not rule_data or rule_data.get("enabled") != "True":
                    continue
                
                if rule_data.get("metric_name") != metric_name:
                    continue
                
                threshold = float(rule_data.get("threshold", 0))
                condition = rule_data.get("condition", ">")
                
                # Check condition
                triggered = False
                if condition == ">" and value > threshold:
                    triggered = True
                elif condition == "<" and value < threshold:
                    triggered = True
                elif condition == "==" and value == threshold:
                    triggered = True
                
                if triggered:
                    await self._trigger_alert(
                        rule_data["rule_id"],
                        metric_name,
                        value,
                        threshold,
                        f"Performance alert: {metric_name} = {value} {condition} {threshold}"
                    )
            
        except Exception as e:
            logger.error("Error checking performance alerts", error=str(e))
    
    async def _trigger_alert(
        self,
        rule_id: str,
        metric_name: str,
        current_value: float,
        threshold: float,
        message: str
    ) -> None:
        """Trigger an alert."""
        try:
            # Check cooldown
            cooldown_key = f"analytics:alert_cooldown:{rule_id}"
            if self.redis_client.exists(cooldown_key):
                return  # Still in cooldown
            
            alert_id = str(uuid.uuid4())
            timestamp = datetime.now()
            
            # Get rule details
            rule_key = f"{self.alert_rules_prefix}{rule_id}"
            rule_data = self.redis_client.hgetall(rule_key)
            
            alert_data = {
                "alert_id": alert_id,
                "rule_id": rule_id,
                "rule_name": rule_data.get("name", "Unknown Rule"),
                "timestamp": timestamp.isoformat(),
                "severity": rule_data.get("severity", AlertSeverity.MEDIUM.value),
                "metric_name": metric_name,
                "current_value": current_value,
                "threshold": threshold,
                "message": message,
                "context": json.dumps({}),
                "acknowledged": False,
                "resolved": False
            }
            
            # Store alert
            alert_key = f"{self.alert_prefix}{alert_id}"
            pipe = self.redis_client.pipeline()
            pipe.hset(alert_key, mapping=alert_data)
            pipe.expire(alert_key, self.alert_retention)
            
            # Set cooldown
            cooldown_minutes = int(rule_data.get("cooldown_minutes", 5))
            pipe.setex(cooldown_key, cooldown_minutes * 60, "1")
            
            # Add to alert indexes
            pipe.sadd("analytics:alerts:active", alert_id)
            pipe.sadd(f"analytics:alerts:rule:{rule_id}", alert_id)
            
            pipe.execute()
            
            logger.warning("Alert triggered", alert_id=alert_id, rule_id=rule_id, message=message)
            
        except Exception as e:
            logger.error("Error triggering alert", error=str(e))


# Global analytics service instance
chat_analytics_service = ChatAnalyticsService()


# Convenience functions for easy access
async def track_session_metrics(**kwargs):
    """Track session metrics."""
    return await chat_analytics_service.track_session_metrics(**kwargs)


async def track_user_engagement(**kwargs):
    """Track user engagement."""
    return await chat_analytics_service.track_user_engagement(**kwargs)


async def track_model_usage(**kwargs):
    """Track model usage."""
    return await chat_analytics_service.track_model_usage(**kwargs)


async def track_error(**kwargs):
    """Track error."""
    return await chat_analytics_service.track_error(**kwargs)


async def track_performance_metric(**kwargs):
    """Track performance metric."""
    return await chat_analytics_service.track_performance_metric(**kwargs)


async def track_conversion_operation(**kwargs):
    """Track conversion operation."""
    return await chat_analytics_service.track_conversion_operation(**kwargs)


async def get_realtime_metrics():
    """Get realtime metrics."""
    return await chat_analytics_service.get_realtime_metrics()