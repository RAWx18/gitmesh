"""
Chat Analytics API Routes for Cosmos Web Chat Integration
Provides REST endpoints for monitoring and analytics functionality.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta
import structlog

try:
    # Try relative imports first (when used as module)
    from ....services.chat_analytics_service import chat_analytics_service
    from ....models.api.chat_analytics_models import (
        SessionAnalyticsRequest, SessionAnalyticsResponse,
        UserEngagementResponse, ModelUsageRequest, ModelUsageResponse,
        ErrorAnalyticsRequest, ErrorAnalyticsResponse,
        PerformanceAnalyticsResponse, SystemHealthResponse,
        AlertsResponse, AnalyticsDashboardResponse,
        RealtimeMetrics, AnalyticsSummary, AlertSeverity
    )
    from ....utils.auth_utils import get_current_user
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.chat_analytics_service import chat_analytics_service
    from models.api.chat_analytics_models import (
        SessionAnalyticsRequest, SessionAnalyticsResponse,
        UserEngagementResponse, ModelUsageRequest, ModelUsageResponse,
        ErrorAnalyticsRequest, ErrorAnalyticsResponse,
        PerformanceAnalyticsResponse, SystemHealthResponse,
        AlertsResponse, AnalyticsDashboardResponse,
        RealtimeMetrics, AnalyticsSummary, AlertSeverity
    )
    from utils.auth_utils import get_current_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Chat Analytics"])


@router.get("/realtime", response_model=RealtimeMetrics)
async def get_realtime_metrics(
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time system metrics.
    
    Returns current system status including active sessions, users,
    performance metrics, and error rates.
    """
    try:
        logger.info("Getting realtime metrics", user_id=current_user.get("user_id"))
        
        metrics = await chat_analytics_service.get_realtime_metrics()
        return metrics
        
    except Exception as e:
        logger.error("Error getting realtime metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting realtime metrics: {str(e)}")


@router.get("/dashboard", response_model=AnalyticsDashboardResponse)
async def get_analytics_dashboard(
    days: int = Query(7, ge=1, le=90, description="Number of days to include in analytics"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive analytics dashboard data.
    
    Provides summary analytics, real-time metrics, recent errors,
    active alerts, and usage trends for the specified time period.
    """
    try:
        logger.info("Getting analytics dashboard", user_id=current_user.get("user_id"), days=days)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get various analytics in parallel
        import asyncio
        
        realtime_task = chat_analytics_service.get_realtime_metrics()
        sessions_task = chat_analytics_service.get_session_analytics(start_date, end_date)
        model_usage_task = chat_analytics_service.get_model_usage_analytics(start_date, end_date)
        errors_task = chat_analytics_service.get_error_analytics(start_date, end_date)
        
        realtime_metrics, (sessions, session_summary), (model_usage, total_cost, model_summary), (errors, error_rate, error_summary) = await asyncio.gather(
            realtime_task, sessions_task, model_usage_task, errors_task
        )
        
        # Calculate summary analytics
        total_sessions = len(sessions)
        total_users = session_summary.get("unique_users", 0)
        total_messages = session_summary.get("total_messages", 0)
        total_errors = len(errors)
        avg_session_duration = session_summary.get("avg_duration_minutes", 0)
        
        # Get most used model
        model_usage_counts = {}
        for session in sessions:
            model_usage_counts[session.model_used] = model_usage_counts.get(session.model_used, 0) + 1
        most_used_model = max(model_usage_counts.items(), key=lambda x: x[1])[0] if model_usage_counts else "N/A"
        
        # Get top repositories
        repo_usage = {}
        for session in sessions:
            if session.repository_url:
                repo_usage[session.repository_url] = repo_usage.get(session.repository_url, 0) + 1
        
        top_repositories = [
            {"url": repo, "usage_count": count}
            for repo, count in sorted(repo_usage.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # Calculate growth (simplified - comparing with previous period)
        prev_start = start_date - timedelta(days=days)
        prev_sessions, prev_summary = await chat_analytics_service.get_session_analytics(prev_start, start_date)
        
        prev_total_sessions = len(prev_sessions)
        prev_total_users = prev_summary.get("unique_users", 0)
        
        session_growth = ((total_sessions - prev_total_sessions) / prev_total_sessions * 100) if prev_total_sessions > 0 else 0
        user_growth = ((total_users - prev_total_users) / prev_total_users * 100) if prev_total_users > 0 else 0
        
        summary = AnalyticsSummary(
            period_start=start_date,
            period_end=end_date,
            total_sessions=total_sessions,
            total_users=total_users,
            total_messages=total_messages,
            total_errors=total_errors,
            avg_session_duration=avg_session_duration,
            most_used_model=most_used_model,
            top_repositories=top_repositories,
            error_rate=error_rate,
            user_growth=user_growth,
            session_growth=session_growth
        )
        
        # Get recent errors (last 10)
        recent_errors = sorted(errors, key=lambda e: e.timestamp, reverse=True)[:10]
        
        # Get active alerts (placeholder - would implement alert system)
        active_alerts = []
        
        # Get top models by usage
        top_models = [
            {"model": model, "usage_count": count}
            for model, count in sorted(model_usage_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # Get user activity trends (simplified)
        user_activity = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            day_sessions = [s for s in sessions if s.created_at.date() == date.date()]
            user_activity.append({
                "date": date.isoformat(),
                "sessions": len(day_sessions),
                "users": len(set(s.user_id for s in day_sessions)),
                "messages": sum(s.message_count for s in day_sessions)
            })
        
        return AnalyticsDashboardResponse(
            summary=summary,
            realtime=realtime_metrics,
            recent_errors=recent_errors,
            active_alerts=active_alerts,
            top_models=top_models,
            user_activity=user_activity
        )
        
    except Exception as e:
        logger.error("Error getting analytics dashboard", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting analytics dashboard: {str(e)}")


@router.get("/sessions", response_model=SessionAnalyticsResponse)
async def get_session_analytics(
    start_date: Optional[datetime] = Query(None, description="Start date for analytics"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of sessions to return"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get session analytics with filtering options.
    
    Returns detailed session metrics including duration, message counts,
    context files, and conversion operations.
    """
    try:
        logger.info("Getting session analytics", 
                   user_id=current_user.get("user_id"), 
                   filter_user_id=user_id,
                   start_date=start_date,
                   end_date=end_date)
        
        sessions, summary = await chat_analytics_service.get_session_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=limit
        )
        
        return SessionAnalyticsResponse(
            sessions=sessions,
            total_count=len(sessions),
            summary=summary
        )
        
    except Exception as e:
        logger.error("Error getting session analytics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting session analytics: {str(e)}")


@router.get("/models", response_model=ModelUsageResponse)
async def get_model_usage_analytics(
    start_date: Optional[datetime] = Query(None, description="Start date for analytics"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get AI model usage analytics and cost tracking.
    
    Returns detailed model usage metrics including token counts,
    estimated costs, response times, and success rates.
    """
    try:
        logger.info("Getting model usage analytics", 
                   user_id=current_user.get("user_id"),
                   model_name=model_name,
                   provider=provider)
        
        usage_metrics, total_cost, summary = await chat_analytics_service.get_model_usage_analytics(
            start_date=start_date,
            end_date=end_date,
            model_name=model_name
        )
        
        # Filter by provider if specified
        if provider:
            usage_metrics = [m for m in usage_metrics if m.provider == provider]
            # Recalculate total cost for filtered results
            total_cost = sum(m.estimated_cost for m in usage_metrics)
        
        return ModelUsageResponse(
            usage=usage_metrics,
            total_cost=total_cost,
            summary=summary
        )
        
    except Exception as e:
        logger.error("Error getting model usage analytics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting model usage analytics: {str(e)}")


@router.get("/errors", response_model=ErrorAnalyticsResponse)
async def get_error_analytics(
    start_date: Optional[datetime] = Query(None, description="Start date for analytics"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    component: Optional[str] = Query(None, description="Filter by component"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get error analytics and monitoring data.
    
    Returns detailed error metrics including error types, components,
    severity levels, and resolution status.
    """
    try:
        logger.info("Getting error analytics", 
                   user_id=current_user.get("user_id"),
                   error_type=error_type,
                   component=component,
                   severity=severity)
        
        errors, error_rate, summary = await chat_analytics_service.get_error_analytics(
            start_date=start_date,
            end_date=end_date,
            error_type=error_type,
            component=component,
            severity=severity
        )
        
        # Filter by resolution status if specified
        if resolved is not None:
            errors = [e for e in errors if e.resolved == resolved]
        
        return ErrorAnalyticsResponse(
            errors=errors,
            total_count=len(errors),
            error_rate=error_rate,
            summary=summary
        )
        
    except Exception as e:
        logger.error("Error getting error analytics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting error analytics: {str(e)}")


@router.post("/track/session")
async def track_session_metrics(
    session_id: str,
    user_id: str,
    model_used: str,
    repository_url: Optional[str] = None,
    branch: Optional[str] = None,
    message_increment: int = 0,
    context_files_count: int = 0,
    context_files_size: int = 0,
    conversion_increment: int = 0,
    error_increment: int = 0,
    is_active: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """
    Track session-level metrics.
    
    Records session activity including message counts, context files,
    conversion operations, and error counts.
    """
    try:
        logger.info("Tracking session metrics", 
                   session_id=session_id,
                   user_id=user_id,
                   model_used=model_used)
        
        await chat_analytics_service.track_session_metrics(
            session_id=session_id,
            user_id=user_id,
            model_used=model_used,
            repository_url=repository_url,
            branch=branch,
            message_increment=message_increment,
            context_files_count=context_files_count,
            context_files_size=context_files_size,
            conversion_increment=conversion_increment,
            error_increment=error_increment,
            is_active=is_active
        )
        
        return {"status": "success", "message": "Session metrics tracked successfully"}
        
    except Exception as e:
        logger.error("Error tracking session metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error tracking session metrics: {str(e)}")


@router.post("/track/model-usage")
async def track_model_usage(
    model_name: str,
    canonical_name: str,
    provider: str,
    session_id: str,
    user_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    response_time: float = 0.0,
    success: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """
    Track AI model usage and cost metrics.
    
    Records model usage including token counts, response times,
    and estimated costs for billing and optimization.
    """
    try:
        logger.info("Tracking model usage", 
                   model_name=model_name,
                   session_id=session_id,
                   tokens=input_tokens + output_tokens)
        
        await chat_analytics_service.track_model_usage(
            model_name=model_name,
            canonical_name=canonical_name,
            provider=provider,
            session_id=session_id,
            user_id=user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time=response_time,
            success=success
        )
        
        return {"status": "success", "message": "Model usage tracked successfully"}
        
    except Exception as e:
        logger.error("Error tracking model usage", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error tracking model usage: {str(e)}")


@router.post("/track/error")
async def track_error(
    error_type: str,
    error_message: str,
    component: str,
    severity: AlertSeverity = AlertSeverity.MEDIUM,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model_name: Optional[str] = None,
    repository_url: Optional[str] = None,
    stack_trace: Optional[str] = None,
    context: Optional[dict] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Track error occurrences for monitoring and alerting.
    
    Records errors with detailed context for debugging and
    system health monitoring.
    """
    try:
        logger.info("Tracking error", 
                   error_type=error_type,
                   component=component,
                   severity=severity.value)
        
        error_id = await chat_analytics_service.track_error(
            error_type=error_type,
            error_message=error_message,
            component=component,
            severity=severity,
            session_id=session_id,
            user_id=user_id,
            model_name=model_name,
            repository_url=repository_url,
            stack_trace=stack_trace,
            context=context
        )
        
        return {"status": "success", "message": "Error tracked successfully", "error_id": error_id}
        
    except Exception as e:
        logger.error("Error tracking error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error tracking error: {str(e)}")


@router.post("/track/performance")
async def track_performance_metric(
    metric_name: str,
    value: float,
    unit: str,
    component: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[dict] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Track performance metrics for system monitoring.
    
    Records performance measurements for optimization and
    capacity planning.
    """
    try:
        logger.info("Tracking performance metric", 
                   metric_name=metric_name,
                   value=value,
                   component=component)
        
        await chat_analytics_service.track_performance_metric(
            metric_name=metric_name,
            value=value,
            unit=unit,
            component=component,
            session_id=session_id,
            user_id=user_id,
            tags=tags
        )
        
        return {"status": "success", "message": "Performance metric tracked successfully"}
        
    except Exception as e:
        logger.error("Error tracking performance metric", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error tracking performance metric: {str(e)}")


@router.post("/track/conversion")
async def track_conversion_operation(
    session_id: str,
    operation_type: str,
    original_command: str,
    web_equivalent: str,
    success: bool,
    conversion_time: float,
    complexity_score: int = 5,
    user_feedback: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Track CLI-to-web conversion operations.
    
    Records conversion attempts and success rates for
    improving the web adaptation process.
    """
    try:
        logger.info("Tracking conversion operation", 
                   session_id=session_id,
                   operation_type=operation_type,
                   success=success)
        
        await chat_analytics_service.track_conversion_operation(
            session_id=session_id,
            operation_type=operation_type,
            original_command=original_command,
            web_equivalent=web_equivalent,
            success=success,
            conversion_time=conversion_time,
            complexity_score=complexity_score,
            user_feedback=user_feedback
        )
        
        return {"status": "success", "message": "Conversion operation tracked successfully"}
        
    except Exception as e:
        logger.error("Error tracking conversion operation", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error tracking conversion operation: {str(e)}")


@router.get("/health")
async def get_system_health(
    current_user: dict = Depends(get_current_user)
):
    """
    Get system health status and metrics.
    
    Returns current system health including Redis status,
    active sessions, error rates, and performance metrics.
    """
    try:
        logger.info("Getting system health", user_id=current_user.get("user_id"))
        
        # Get real-time metrics as a proxy for system health
        realtime_metrics = await chat_analytics_service.get_realtime_metrics()
        
        # Calculate health status based on metrics
        health_status = "healthy"
        if realtime_metrics.errors_per_minute > 5:
            health_status = "degraded"
        if realtime_metrics.errors_per_minute > 20:
            health_status = "unhealthy"
        
        return {
            "status": health_status,
            "timestamp": realtime_metrics.timestamp.isoformat(),
            "metrics": {
                "active_sessions": realtime_metrics.active_sessions,
                "active_users": realtime_metrics.active_users,
                "messages_per_minute": realtime_metrics.messages_per_minute,
                "errors_per_minute": realtime_metrics.errors_per_minute,
                "avg_response_time": realtime_metrics.avg_response_time,
                "redis_connections": realtime_metrics.redis_connections,
                "memory_usage_mb": realtime_metrics.memory_usage_mb,
                "cpu_usage_percent": realtime_metrics.cpu_usage_percent
            }
        }
        
    except Exception as e:
        logger.error("Error getting system health", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error getting system health: {str(e)}")


@router.delete("/clear-cache")
async def clear_analytics_cache(
    cache_type: Optional[str] = Query(None, description="Type of cache to clear (optional)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Clear analytics cache for fresh data.
    
    Clears cached analytics data to ensure fresh calculations.
    Use with caution as this may impact performance temporarily.
    """
    try:
        logger.info("Clearing analytics cache", 
                   user_id=current_user.get("user_id"),
                   cache_type=cache_type)
        
        # Clear performance service cache
        chat_analytics_service.performance_service.clear_cache(cache_type)
        
        return {"status": "success", "message": f"Analytics cache cleared successfully"}
        
    except Exception as e:
        logger.error("Error clearing analytics cache", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error clearing analytics cache: {str(e)}")