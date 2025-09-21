"""
Session Persistence and Recovery API Routes
Provides endpoints for session backup, recovery, sharing, and export functionality.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

try:
    from ....services.session_persistence_service import (
        session_persistence_service,
        SessionShareType,
        SessionBackupStatus
    )
    from ....utils.auth_utils import get_current_user
    from ....models.api.session_models import SessionStatus
except ImportError:
    from services.session_persistence_service import (
        session_persistence_service,
        SessionShareType,
        SessionBackupStatus
    )
    from utils.auth_utils import get_current_user
    from models.api.session_models import SessionStatus

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session-persistence", tags=["Session Persistence"])


# Request/Response Models
class CreateBackupRequest(BaseModel):
    """Request model for creating session backup."""
    session_id: str = Field(..., description="Session identifier")
    backup_type: str = Field(default="manual", description="Backup type")
    include_messages: bool = Field(default=True, description="Include messages in backup")
    include_context: bool = Field(default=True, description="Include context files in backup")


class BackupResponse(BaseModel):
    """Response model for backup operations."""
    backup_id: str = Field(..., description="Backup identifier")
    status: str = Field(..., description="Backup status")
    created_at: str = Field(..., description="Creation timestamp")
    size_bytes: int = Field(default=0, description="Backup size in bytes")
    compressed_size_bytes: int = Field(default=0, description="Compressed size in bytes")


class RestoreSessionRequest(BaseModel):
    """Request model for restoring session from backup."""
    backup_id: str = Field(..., description="Backup identifier")
    new_session_id: Optional[str] = Field(default=None, description="Optional new session ID")


class CreateShareRequest(BaseModel):
    """Request model for creating session share."""
    session_id: str = Field(..., description="Session identifier")
    share_type: str = Field(default="read_only", description="Share type")
    expires_in_hours: Optional[int] = Field(default=None, description="Expiration in hours")
    allowed_users: Optional[List[str]] = Field(default=None, description="Allowed user IDs")


class ShareResponse(BaseModel):
    """Response model for share operations."""
    share_id: str = Field(..., description="Share identifier")
    share_url: str = Field(..., description="Shareable URL")
    share_type: str = Field(..., description="Share type")
    expires_at: Optional[str] = Field(default=None, description="Expiration timestamp")


class ExportSessionRequest(BaseModel):
    """Request model for exporting session."""
    session_id: str = Field(..., description="Session identifier")
    export_format: str = Field(default="json", description="Export format")
    include_context: bool = Field(default=True, description="Include context files")


class ExportResponse(BaseModel):
    """Response model for export operations."""
    export_id: str = Field(..., description="Export identifier")
    download_url: str = Field(..., description="Download URL")
    export_format: str = Field(..., description="Export format")
    expires_at: str = Field(..., description="Expiration timestamp")


# Backup Endpoints
@router.post("/backups", response_model=BackupResponse)
async def create_backup(
    request: CreateBackupRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a backup of a chat session.
    
    Creates a compressed backup of the session including messages and context files.
    The backup can be used to restore the session later.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        backup_id = await session_persistence_service.create_session_backup(
            session_id=request.session_id,
            user_id=user_id,
            backup_type=request.backup_type,
            include_messages=request.include_messages,
            include_context=request.include_context
        )
        
        # Get backup info
        backup = await session_persistence_service.get_backup(backup_id)
        if not backup:
            raise HTTPException(status_code=500, detail="Failed to create backup")
        
        return BackupResponse(
            backup_id=backup.backup_id,
            status=backup.status.value,
            created_at=backup.created_at.isoformat(),
            size_bytes=backup.size_bytes,
            compressed_size_bytes=backup.compressed_size_bytes
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/backups", response_model=List[BackupResponse])
async def get_user_backups(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get user's session backups.
    
    Returns a paginated list of backups created by the current user.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        backups = await session_persistence_service.get_user_backups(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        return [
            BackupResponse(
                backup_id=backup.backup_id,
                status=backup.status.value,
                created_at=backup.created_at.isoformat(),
                size_bytes=backup.size_bytes,
                compressed_size_bytes=backup.compressed_size_bytes
            )
            for backup in backups
        ]
        
    except Exception as e:
        logger.error(f"Error getting user backups: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/backups/{backup_id}/restore")
async def restore_session(
    backup_id: str,
    request: RestoreSessionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Restore a session from backup.
    
    Creates a new session with the data from the specified backup.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        new_session_id = await session_persistence_service.restore_session_from_backup(
            backup_id=backup_id,
            user_id=user_id,
            new_session_id=request.new_session_id
        )
        
        return {
            "success": True,
            "message": "Session restored successfully",
            "session_id": new_session_id,
            "backup_id": backup_id
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a session backup.
    
    Permanently removes the backup and its data.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        success = await session_persistence_service.delete_backup(
            backup_id=backup_id,
            user_id=user_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Backup not found")
        
        return {
            "success": True,
            "message": "Backup deleted successfully"
        }
        
    except Exception as e:
        logger.error(f"Error deleting backup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Sharing Endpoints
@router.post("/shares", response_model=ShareResponse)
async def create_share(
    request: CreateShareRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a shareable link for a session.
    
    Allows sharing sessions with other users with different permission levels.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        # Validate share type
        try:
            share_type = SessionShareType(request.share_type)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid share type. Must be one of: {[t.value for t in SessionShareType]}"
            )
        
        share_id = await session_persistence_service.create_session_share(
            session_id=request.session_id,
            owner_id=user_id,
            share_type=share_type,
            expires_in_hours=request.expires_in_hours,
            allowed_users=request.allowed_users
        )
        
        # Get share info
        share = await session_persistence_service.get_share(share_id)
        if not share:
            raise HTTPException(status_code=500, detail="Failed to create share")
        
        # Generate share URL (this would be your frontend URL)
        share_url = f"/shared/{share_id}"  # Adjust based on your frontend routing
        
        return ShareResponse(
            share_id=share.share_id,
            share_url=share_url,
            share_type=share.share_type.value,
            expires_at=share.expires_at.isoformat() if share.expires_at else None
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating share: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/shares/{share_id}")
async def get_shared_session(
    share_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a shared session by share ID.
    
    Returns session data if the user has access to the shared session.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        shared_session = await session_persistence_service.get_shared_session(
            share_id=share_id,
            user_id=user_id
        )
        
        if not shared_session:
            raise HTTPException(status_code=404, detail="Shared session not found or access denied")
        
        return shared_session
        
    except Exception as e:
        logger.error(f"Error getting shared session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/shares/{share_id}")
async def revoke_share(
    share_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Revoke a session share.
    
    Removes the shareable link and prevents further access.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        success = await session_persistence_service.revoke_share(
            share_id=share_id,
            owner_id=user_id
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Share not found")
        
        return {
            "success": True,
            "message": "Share revoked successfully"
        }
        
    except Exception as e:
        logger.error(f"Error revoking share: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Export Endpoints
@router.post("/exports", response_model=ExportResponse)
async def export_session(
    request: ExportSessionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Export a session to various formats.
    
    Creates an exportable file in the specified format (JSON, Markdown, HTML).
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        # Validate export format
        valid_formats = ["json", "markdown", "html"]
        if request.export_format not in valid_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid export format. Must be one of: {valid_formats}"
            )
        
        export_id = await session_persistence_service.export_session(
            session_id=request.session_id,
            user_id=user_id,
            export_format=request.export_format,
            include_context=request.include_context
        )
        
        # Get export info
        export_record = await session_persistence_service.get_export(export_id)
        if not export_record:
            raise HTTPException(status_code=500, detail="Failed to create export")
        
        # Generate download URL
        download_url = f"/api/v1/session-persistence/exports/{export_id}/download"
        
        return ExportResponse(
            export_id=export_record.export_id,
            download_url=download_url,
            export_format=export_record.export_format,
            expires_at=export_record.expires_at.isoformat() if export_record.expires_at else ""
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Download an exported session file.
    
    Returns the exported content as a downloadable file.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        # Get export record
        export_record = await session_persistence_service.get_export(export_id)
        if not export_record or export_record.user_id != user_id:
            raise HTTPException(status_code=404, detail="Export not found")
        
        # Get export content
        content = await session_persistence_service.get_export_content(export_id, user_id)
        if not content:
            raise HTTPException(status_code=404, detail="Export content not found or expired")
        
        # Determine content type and filename
        content_types = {
            "json": "application/json",
            "markdown": "text/markdown",
            "html": "text/html"
        }
        
        extensions = {
            "json": "json",
            "markdown": "md",
            "html": "html"
        }
        
        content_type = content_types.get(export_record.export_format, "text/plain")
        extension = extensions.get(export_record.export_format, "txt")
        filename = f"session_export_{export_id}.{extension}"
        
        from fastapi.responses import Response
        
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error(f"Error downloading export: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Recovery Endpoints
@router.post("/recovery/check-connection")
async def check_connection_recovery():
    """
    Check if session persistence service is available and healthy.
    
    Used by clients to determine if they need to implement recovery mechanisms.
    """
    try:
        # Test Redis connection
        session_persistence_service.redis_client.ping()
        
        return {
            "status": "healthy",
            "message": "Session persistence service is available",
            "features": {
                "backup_restore": True,
                "session_sharing": True,
                "session_export": True,
                "auto_recovery": True
            }
        }
        
    except Exception as e:
        logger.error(f"Session persistence service health check failed: {e}")
        return {
            "status": "degraded",
            "message": "Session persistence service is unavailable",
            "features": {
                "backup_restore": False,
                "session_sharing": False,
                "session_export": False,
                "auto_recovery": False
            },
            "error": str(e)
        }


@router.get("/recovery/session/{session_id}")
async def get_session_recovery_info(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get recovery information for a session.
    
    Returns available backups and recovery options for the session.
    """
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found")
        
        # Get user backups and filter by session
        backups = await session_persistence_service.get_user_backups(user_id, limit=100)
        session_backups = [b for b in backups if b.session_id == session_id]
        
        # Get session shares
        # Note: This would require additional methods in the service
        # For now, we'll return basic recovery info
        
        return {
            "session_id": session_id,
            "available_backups": len(session_backups),
            "latest_backup": session_backups[0].created_at.isoformat() if session_backups else None,
            "recovery_options": {
                "can_restore_from_backup": len(session_backups) > 0,
                "can_create_backup": True,
                "auto_backup_enabled": True
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting session recovery info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")