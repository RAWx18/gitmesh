"""
Chat Analytics Models for Cosmos Web Chat Integration
Provides data models for monitoring and analytics functionality.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum


class MetricType(str, Enum):
    """Types of metrics that can be tracked."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SessionMetrics(BaseModel):
    """Chat session metrics."""
    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    created_at: datetime = Field(..., description="Session creation time")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    duration_seconds: int = Field(..., description="Session duration in seconds")
    message_count: int = Field(..., description="Total messages in session")
    user_messages: int = Field(..., description="User messages count")
    assistant_messages: int = Field(..., description="Assistant messages count")
    context_files_count: int = Field(..., description="Number of context files")
    context_files_size: int = Field(..., description="Total size of context files in bytes")
    repository_url: Optional[str] = Field(None, description="Repository URL if used")
    branch: Optional[str] = Field(None, description="Branch name if used")
    model_used: str = Field(..., description="AI model used")
    conversion_operations: int = Field(default=0, description="Number of CLI-to-web conversions")
    error_count: int = Field(default=0, description="Number of errors encountered")
    is_active: bool = Field(..., description="Whether session is currently active")


class UserEngagementMetrics(BaseModel):
    """User engagement tracking metrics."""
    user_id: str = Field(..., description="User identifier")
    date: datetime = Field(..., description="Metrics date")
    total_sessions: int = Field(..., description="Total sessions created")
    active_sessions: int = Field(..., description="Currently active sessions")
    total_messages: int = Field(..., description="Total messages sent")
    avg_session_duration: float = Field(..., description="Average session duration in minutes")
    avg_messages_per_session: float = Field(..., description="Average messages per session")
    repositories_used: int = Field(..., description="Number of unique repositories used")
    models_used: List[str] = Field(..., description="List of AI models used")
    context_files_added: int = Field(..., description="Total context files added")
    conversion_operations: int = Field(..., description="Total CLI-to-web conversions")
    error_rate: float = Field(..., description="Error rate percentage")
    last_activity: datetime = Field(..., description="Last activity timestamp")


class ModelUsageMetrics(BaseModel):
    """AI model usage and cost tracking."""
    model_name: str = Field(..., description="Model name/alias")
    canonical_name: str = Field(..., description="Canonical model name")
    provider: str = Field(..., description="Model provider")
    date: datetime = Field(..., description="Usage date")
    request_count: int = Field(..., description="Number of requests")
    total_tokens: int = Field(..., description="Total tokens processed")
    input_tokens: int = Field(..., description="Input tokens")
    output_tokens: int = Field(..., description="Output tokens")
    estimated_cost: float = Field(..., description="Estimated cost in USD")
    avg_response_time: float = Field(..., description="Average response time in seconds")
    error_count: int = Field(..., description="Number of errors")
    success_rate: float = Field(..., description="Success rate percentage")
    unique_users: int = Field(..., description="Number of unique users")
    unique_sessions: int = Field(..., description="Number of unique sessions")


class ErrorMetrics(BaseModel):
    """Error tracking and monitoring."""
    error_id: str = Field(..., description="Unique error identifier")
    timestamp: datetime = Field(..., description="Error timestamp")
    error_type: str = Field(..., description="Type of error")
    error_code: Optional[str] = Field(None, description="Error code if available")
    error_message: str = Field(..., description="Error message")
    component: str = Field(..., description="Component where error occurred")
    session_id: Optional[str] = Field(None, description="Session ID if applicable")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    model_name: Optional[str] = Field(None, description="Model name if applicable")
    repository_url: Optional[str] = Field(None, description="Repository URL if applicable")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional error context")
    resolved: bool = Field(default=False, description="Whether error has been resolved")
    severity: AlertSeverity = Field(..., description="Error severity level")


class PerformanceMetrics(BaseModel):
    """Performance monitoring metrics."""
    metric_name: str = Field(..., description="Name of the performance metric")
    timestamp: datetime = Field(..., description="Measurement timestamp")
    value: float = Field(..., description="Metric value")
    unit: str = Field(..., description="Unit of measurement")
    component: str = Field(..., description="Component being measured")
    session_id: Optional[str] = Field(None, description="Session ID if applicable")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    tags: Dict[str, str] = Field(default_factory=dict, description="Additional metric tags")


class SystemHealthMetrics(BaseModel):
    """System health monitoring."""
    timestamp: datetime = Field(..., description="Health check timestamp")
    redis_status: str = Field(..., description="Redis connection status")
    redis_latency: float = Field(..., description="Redis latency in milliseconds")
    active_sessions: int = Field(..., description="Number of active sessions")
    total_users: int = Field(..., description="Total number of users")
    memory_usage: float = Field(..., description="Memory usage percentage")
    cpu_usage: float = Field(..., description="CPU usage percentage")
    error_rate: float = Field(..., description="Overall error rate percentage")
    avg_response_time: float = Field(..., description="Average response time in seconds")
    requests_per_minute: float = Field(..., description="Requests per minute")


class AlertRule(BaseModel):
    """Alert rule configuration."""
    rule_id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., description="Rule name")
    description: str = Field(..., description="Rule description")
    metric_name: str = Field(..., description="Metric to monitor")
    condition: str = Field(..., description="Alert condition (e.g., '>', '<', '==')")
    threshold: float = Field(..., description="Alert threshold value")
    severity: AlertSeverity = Field(..., description="Alert severity")
    enabled: bool = Field(default=True, description="Whether rule is enabled")
    cooldown_minutes: int = Field(default=5, description="Cooldown period in minutes")
    created_at: datetime = Field(..., description="Rule creation timestamp")
    updated_at: datetime = Field(..., description="Rule last update timestamp")


class Alert(BaseModel):
    """Alert instance."""
    alert_id: str = Field(..., description="Unique alert identifier")
    rule_id: str = Field(..., description="Rule that triggered the alert")
    rule_name: str = Field(..., description="Name of the rule")
    timestamp: datetime = Field(..., description="Alert timestamp")
    severity: AlertSeverity = Field(..., description="Alert severity")
    metric_name: str = Field(..., description="Metric that triggered alert")
    current_value: float = Field(..., description="Current metric value")
    threshold: float = Field(..., description="Alert threshold")
    message: str = Field(..., description="Alert message")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional alert context")
    acknowledged: bool = Field(default=False, description="Whether alert has been acknowledged")
    resolved: bool = Field(default=False, description="Whether alert has been resolved")
    resolved_at: Optional[datetime] = Field(None, description="Alert resolution timestamp")


class AnalyticsSummary(BaseModel):
    """Summary analytics for dashboard."""
    period_start: datetime = Field(..., description="Analytics period start")
    period_end: datetime = Field(..., description="Analytics period end")
    total_sessions: int = Field(..., description="Total sessions in period")
    total_users: int = Field(..., description="Total unique users")
    total_messages: int = Field(..., description="Total messages")
    total_errors: int = Field(..., description="Total errors")
    avg_session_duration: float = Field(..., description="Average session duration in minutes")
    most_used_model: str = Field(..., description="Most frequently used model")
    top_repositories: List[Dict[str, Any]] = Field(..., description="Top repositories by usage")
    error_rate: float = Field(..., description="Overall error rate percentage")
    user_growth: float = Field(..., description="User growth percentage")
    session_growth: float = Field(..., description="Session growth percentage")


class ConversionAnalytics(BaseModel):
    """CLI-to-web conversion analytics."""
    session_id: str = Field(..., description="Session identifier")
    timestamp: datetime = Field(..., description="Conversion timestamp")
    operation_type: str = Field(..., description="Type of operation converted")
    original_command: str = Field(..., description="Original CLI command")
    web_equivalent: str = Field(..., description="Web equivalent action")
    success: bool = Field(..., description="Whether conversion was successful")
    user_feedback: Optional[str] = Field(None, description="User feedback on conversion")
    conversion_time: float = Field(..., description="Time taken for conversion in seconds")
    complexity_score: int = Field(..., description="Complexity score (1-10)")


class RealtimeMetrics(BaseModel):
    """Real-time metrics for live monitoring."""
    timestamp: datetime = Field(..., description="Metrics timestamp")
    active_sessions: int = Field(..., description="Currently active sessions")
    active_users: int = Field(..., description="Currently active users")
    messages_per_minute: float = Field(..., description="Messages per minute")
    errors_per_minute: float = Field(..., description="Errors per minute")
    avg_response_time: float = Field(..., description="Average response time in seconds")
    redis_connections: int = Field(..., description="Active Redis connections")
    memory_usage_mb: float = Field(..., description="Memory usage in MB")
    cpu_usage_percent: float = Field(..., description="CPU usage percentage")


# Request/Response Models

class AnalyticsRequest(BaseModel):
    """Base analytics request."""
    start_date: Optional[datetime] = Field(None, description="Start date for analytics")
    end_date: Optional[datetime] = Field(None, description="End date for analytics")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    session_id: Optional[str] = Field(None, description="Filter by session ID")
    model_name: Optional[str] = Field(None, description="Filter by model name")


class SessionAnalyticsRequest(AnalyticsRequest):
    """Session analytics request."""
    include_inactive: bool = Field(default=False, description="Include inactive sessions")
    min_duration: Optional[int] = Field(None, description="Minimum session duration in seconds")
    max_duration: Optional[int] = Field(None, description="Maximum session duration in seconds")


class ModelUsageRequest(AnalyticsRequest):
    """Model usage analytics request."""
    provider: Optional[str] = Field(None, description="Filter by provider")
    include_costs: bool = Field(default=True, description="Include cost calculations")


class ErrorAnalyticsRequest(AnalyticsRequest):
    """Error analytics request."""
    error_type: Optional[str] = Field(None, description="Filter by error type")
    severity: Optional[AlertSeverity] = Field(None, description="Filter by severity")
    component: Optional[str] = Field(None, description="Filter by component")
    resolved: Optional[bool] = Field(None, description="Filter by resolution status")


class AlertRequest(BaseModel):
    """Alert management request."""
    rule_id: Optional[str] = Field(None, description="Filter by rule ID")
    severity: Optional[AlertSeverity] = Field(None, description="Filter by severity")
    acknowledged: Optional[bool] = Field(None, description="Filter by acknowledgment status")
    resolved: Optional[bool] = Field(None, description="Filter by resolution status")


# Response Models

class SessionAnalyticsResponse(BaseModel):
    """Session analytics response."""
    sessions: List[SessionMetrics] = Field(..., description="Session metrics")
    total_count: int = Field(..., description="Total number of sessions")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class UserEngagementResponse(BaseModel):
    """User engagement analytics response."""
    users: List[UserEngagementMetrics] = Field(..., description="User engagement metrics")
    total_count: int = Field(..., description="Total number of users")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class ModelUsageResponse(BaseModel):
    """Model usage analytics response."""
    usage: List[ModelUsageMetrics] = Field(..., description="Model usage metrics")
    total_cost: float = Field(..., description="Total estimated cost")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class ErrorAnalyticsResponse(BaseModel):
    """Error analytics response."""
    errors: List[ErrorMetrics] = Field(..., description="Error metrics")
    total_count: int = Field(..., description="Total number of errors")
    error_rate: float = Field(..., description="Error rate percentage")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class PerformanceAnalyticsResponse(BaseModel):
    """Performance analytics response."""
    metrics: List[PerformanceMetrics] = Field(..., description="Performance metrics")
    summary: Dict[str, Any] = Field(..., description="Summary statistics")


class SystemHealthResponse(BaseModel):
    """System health response."""
    current_health: SystemHealthMetrics = Field(..., description="Current system health")
    health_history: List[SystemHealthMetrics] = Field(..., description="Historical health data")
    alerts: List[Alert] = Field(..., description="Active alerts")


class AlertsResponse(BaseModel):
    """Alerts response."""
    alerts: List[Alert] = Field(..., description="Alert instances")
    total_count: int = Field(..., description="Total number of alerts")
    active_count: int = Field(..., description="Number of active alerts")
    rules: List[AlertRule] = Field(..., description="Alert rules")


class AnalyticsDashboardResponse(BaseModel):
    """Analytics dashboard response."""
    summary: AnalyticsSummary = Field(..., description="Summary analytics")
    realtime: RealtimeMetrics = Field(..., description="Real-time metrics")
    recent_errors: List[ErrorMetrics] = Field(..., description="Recent errors")
    active_alerts: List[Alert] = Field(..., description="Active alerts")
    top_models: List[Dict[str, Any]] = Field(..., description="Top models by usage")
    user_activity: List[Dict[str, Any]] = Field(..., description="User activity trends")