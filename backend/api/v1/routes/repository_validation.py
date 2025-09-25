"""
Repository Validation API routes
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
import structlog

from .dependencies import get_current_user
from models.api.auth_models import User
from services.repository_validation_service import repository_validation_service

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/validate")
async def validate_repository(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Validate a repository for chat functionality"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        repo_url = request.get("repository_url")
        if not repo_url:
            raise HTTPException(status_code=400, detail="repository_url is required")
        
        # Validate the repository
        validation_result = repository_validation_service.validate_repository_for_chat(
            repo_url, str(current_user.id)
        )
        
        return {
            "success": True,
            "validation": {
                "is_valid": validation_result.is_valid,
                "error_type": validation_result.error_type,
                "error_message": validation_result.error_message,
                "size_mb": validation_result.size_mb,
                "size_kb": validation_result.size_kb,
                "should_block_chat": validation_result.should_block_chat,
                "user_message": validation_result.user_message
            }
        }
    
    except Exception as e:
        logger.error(f"Error validating repository: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate repository: {str(e)}")


@router.get("/cache/status")
async def get_cache_status(
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get repository validation cache status"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        cache_status = repository_validation_service.get_cache_status()
        return {
            "success": True,
            "cache_status": cache_status
        }
    
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache status: {str(e)}")


@router.delete("/cache")
async def clear_cache(
    request: Dict[str, Any] = None,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Clear repository validation cache"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        repo_url = None
        if request:
            repo_url = request.get("repository_url")
        
        repository_validation_service.clear_blocked_cache(repo_url)
        
        return {
            "success": True,
            "message": f"Cache cleared for {'all repositories' if not repo_url else repo_url}"
        }
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.put("/settings")
async def update_validation_settings(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Update repository validation settings"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        max_size_mb = request.get("max_size_mb")
        if max_size_mb is not None:
            if not isinstance(max_size_mb, (int, float)) or max_size_mb <= 0:
                raise HTTPException(status_code=400, detail="max_size_mb must be a positive number")
            
            repository_validation_service.set_max_size_mb(int(max_size_mb))
        
        return {
            "success": True,
            "message": "Validation settings updated",
            "settings": {
                "max_size_mb": repository_validation_service.max_size_mb
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating validation settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")