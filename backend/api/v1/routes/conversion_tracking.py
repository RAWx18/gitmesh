"""
Conversion Tracking API Routes

API endpoints for managing progressive shell-to-web conversion tracking,
progress monitoring, and effectiveness metrics.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

try:
    from ....services.conversion_tracking_service import conversion_tracking_service
    from ....models.api.conversion_tracking import (
        ConversionOperation, ConversionProgress, ConversionMetrics,
        ConversionNote, ConversionReport, ConversionRequest, ConversionUpdateRequest,
        ConversionListResponse, ConversionStatsResponse, ConversionStatus, ConversionType
    )
except ImportError:
    from services.conversion_tracking_service import conversion_tracking_service
    from models.api.conversion_tracking import (
        ConversionOperation, ConversionProgress, ConversionMetrics,
        ConversionNote, ConversionReport, ConversionRequest, ConversionUpdateRequest,
        ConversionListResponse, ConversionStatsResponse, ConversionStatus, ConversionType
    )

router = APIRouter(prefix="/conversion", tags=["conversion-tracking"])


@router.post("/operations", response_model=Dict[str, str])
async def create_conversion_operation(request: ConversionRequest):
    """
    Create a new conversion operation for tracking.
    
    Args:
        request: Conversion operation details
        
    Returns:
        Dictionary with operation ID
    """
    try:
        operation_id = await conversion_tracking_service.create_operation(request)
        return {"operation_id": operation_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create operation: {str(e)}")


@router.put("/operations/{operation_id}", response_model=Dict[str, str])
async def update_conversion_operation(operation_id: str, request: ConversionUpdateRequest):
    """
    Update an existing conversion operation.
    
    Args:
        operation_id: Operation identifier
        request: Update details
        
    Returns:
        Dictionary with update status
    """
    try:
        # Set the operation ID in the request
        request.operation_id = operation_id
        
        success = await conversion_tracking_service.update_operation(request)
        if not success:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        return {"operation_id": operation_id, "status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update operation: {str(e)}")


@router.get("/operations/{operation_id}", response_model=ConversionOperation)
async def get_conversion_operation(operation_id: str):
    """
    Get a specific conversion operation.
    
    Args:
        operation_id: Operation identifier
        
    Returns:
        ConversionOperation object
    """
    try:
        operation = await conversion_tracking_service.get_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        return operation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get operation: {str(e)}")


@router.get("/sessions/{session_id}/operations", response_model=ConversionListResponse)
async def get_session_operations(
    session_id: str,
    status: Optional[ConversionStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page")
):
    """
    Get conversion operations for a specific session.
    
    Args:
        session_id: Session identifier
        status: Optional status filter
        page: Page number (1-based)
        page_size: Number of items per page
        
    Returns:
        ConversionListResponse with operations and metadata
    """
    try:
        offset = (page - 1) * page_size
        
        # Get operations
        operations = await conversion_tracking_service.get_session_operations(
            session_id=session_id,
            status_filter=status,
            limit=page_size + 1,  # Get one extra to check if there are more
            offset=offset
        )
        
        # Check if there are more pages
        has_next = len(operations) > page_size
        if has_next:
            operations = operations[:page_size]
        
        # Get total count (simplified - in production you'd want a more efficient count)
        all_operations = await conversion_tracking_service.get_session_operations(
            session_id=session_id,
            status_filter=status,
            limit=10000
        )
        total_count = len(all_operations)
        
        # Get progress summary
        progress = await conversion_tracking_service.get_session_progress(session_id)
        
        return ConversionListResponse(
            operations=operations,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_next=has_next,
            progress=progress
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session operations: {str(e)}")


@router.get("/sessions/{session_id}/progress", response_model=ConversionProgress)
async def get_session_progress(session_id: str):
    """
    Get conversion progress for a specific session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        ConversionProgress object
    """
    try:
        progress = await conversion_tracking_service.get_session_progress(session_id)
        return progress
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session progress: {str(e)}")


@router.get("/progress/global", response_model=ConversionProgress)
async def get_global_progress():
    """
    Get global conversion progress across all sessions.
    
    Returns:
        ConversionProgress object
    """
    try:
        progress = await conversion_tracking_service.get_global_progress()
        return progress
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get global progress: {str(e)}")


@router.get("/metrics", response_model=ConversionMetrics)
async def get_conversion_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date for metrics"),
    end_date: Optional[datetime] = Query(None, description="End date for metrics"),
    days: Optional[int] = Query(30, ge=1, le=365, description="Number of days back from now")
):
    """
    Get detailed conversion metrics.
    
    Args:
        start_date: Start date for metrics
        end_date: End date for metrics
        days: Number of days back from now (used if start_date not provided)
        
    Returns:
        ConversionMetrics object
    """
    try:
        if not start_date:
            start_date = datetime.now() - timedelta(days=days)
        if not end_date:
            end_date = datetime.now()
        
        metrics = await conversion_tracking_service.get_conversion_metrics(start_date, end_date)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversion metrics: {str(e)}")


@router.get("/stats", response_model=ConversionStatsResponse)
async def get_conversion_stats(
    session_id: Optional[str] = Query(None, description="Optional session filter")
):
    """
    Get comprehensive conversion statistics.
    
    Args:
        session_id: Optional session identifier for filtering
        
    Returns:
        ConversionStatsResponse with detailed statistics
    """
    try:
        # Get progress
        if session_id:
            progress = await conversion_tracking_service.get_session_progress(session_id)
            recent_operations = await conversion_tracking_service.get_session_operations(
                session_id, limit=10
            )
        else:
            progress = await conversion_tracking_service.get_global_progress()
            recent_operations = []  # Would need global recent operations method
        
        # Get metrics
        metrics = await conversion_tracking_service.get_conversion_metrics()
        
        # Prepare top commands from metrics
        top_commands = metrics.most_common_commands[:5] if metrics.most_common_commands else []
        
        # Prepare conversion trends (simplified)
        conversion_trends = {
            "daily_conversions": metrics.daily_conversions,
            "success_rate_trend": [],  # Would calculate from historical data
            "error_rate_trend": []     # Would calculate from historical data
        }
        
        return ConversionStatsResponse(
            progress=progress,
            metrics=metrics,
            recent_operations=recent_operations,
            top_commands=top_commands,
            conversion_trends=conversion_trends
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversion stats: {str(e)}")


@router.post("/operations/{operation_id}/notes", response_model=Dict[str, str])
async def create_conversion_note(
    operation_id: str,
    note_type: str,
    title: str,
    content: str,
    author: str,
    tags: Optional[List[str]] = None,
    is_public: bool = True
):
    """
    Create a note for a conversion operation.
    
    Args:
        operation_id: Operation identifier
        note_type: Type of note (info, warning, error, success, tip, documentation)
        title: Note title
        content: Note content
        author: Note author
        tags: Optional tags for categorization
        is_public: Whether note is visible to other users
        
    Returns:
        Dictionary with note ID
    """
    try:
        note_id = await conversion_tracking_service.create_note(
            operation_id=operation_id,
            note_type=note_type,
            title=title,
            content=content,
            author=author,
            tags=tags,
            is_public=is_public
        )
        return {"note_id": note_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")


@router.get("/operations/{operation_id}/notes", response_model=List[ConversionNote])
async def get_operation_notes(operation_id: str):
    """
    Get notes for a conversion operation.
    
    Args:
        operation_id: Operation identifier
        
    Returns:
        List of ConversionNote objects
    """
    try:
        notes = await conversion_tracking_service.get_operation_notes(operation_id)
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get operation notes: {str(e)}")


@router.post("/reports/generate", response_model=ConversionReport)
async def generate_conversion_report(
    start_date: datetime,
    end_date: datetime,
    generated_by: str,
    session_id: Optional[str] = None
):
    """
    Generate a comprehensive conversion report.
    
    Args:
        start_date: Report start date
        end_date: Report end date
        generated_by: User generating the report
        session_id: Optional session filter
        
    Returns:
        ConversionReport object
    """
    try:
        report = await conversion_tracking_service.generate_report(
            start_date=start_date,
            end_date=end_date,
            generated_by=generated_by,
            session_id=session_id
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/health", response_model=Dict[str, Any])
async def conversion_tracking_health():
    """
    Health check endpoint for conversion tracking service.
    
    Returns:
        Dictionary with health status
    """
    try:
        # Test Redis connection
        test_key = "conversion:health_check"
        conversion_tracking_service.redis_client.set(test_key, "ok", ex=60)
        redis_status = conversion_tracking_service.redis_client.get(test_key) == "ok"
        
        # Get basic stats
        global_progress = await conversion_tracking_service.get_global_progress()
        
        return {
            "status": "healthy" if redis_status else "unhealthy",
            "redis_connection": redis_status,
            "total_operations": global_progress.total_operations,
            "conversion_percentage": global_progress.conversion_percentage,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }