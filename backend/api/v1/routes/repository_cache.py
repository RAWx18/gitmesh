"""
Repository Cache Management API Routes

API endpoints for managing repository caching when users navigate to/from contribution pages.
"""

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import Dict, Any, Optional
import logging
from datetime import datetime
from pydantic import BaseModel

# Use the optimized service instead of the async version
from backend.services.optimized_repo_service import get_optimized_repo_service
from backend.config.auth import get_current_user
import os

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/repository-cache", tags=["repository-cache"])


class CacheRepositoryRequest(BaseModel):
    """Request model for caching a repository."""
    repo_url: str
    branch: str = "main"
    user_tier: str = "free"


class CacheRepositoryResponse(BaseModel):
    """Response model for repository caching."""
    success: bool
    message: str
    repository_name: str
    cached_at: str
    file_count: Optional[int] = None
    estimated_tokens: Optional[int] = None


class ClearCacheRequest(BaseModel):
    """Request model for clearing repository cache."""
    repo_url: Optional[str] = None  # If None, clears all user's cached repos


class ClearCacheResponse(BaseModel):
    """Response model for cache clearing."""
    success: bool
    message: str
    cleared_repositories: list[str]


@router.post("/cache", response_model=CacheRepositoryResponse)
async def cache_repository(
    request: CacheRepositoryRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
) -> CacheRepositoryResponse:
    """
    Cache a repository for immediate access in contribution chat.
    
    This endpoint is called when a user navigates to the /contribution page
    to pre-fetch and cache the repository data using GitIngest.
    """
    try:
        username = current_user.get("username") or current_user.get("login")
        user_id = current_user.get("user_id") or current_user.get("id")
        
        logger.info(f"Caching repository for user {username}: {request.repo_url}")
        
        # Use optimized service for caching
        repo_service = get_optimized_repo_service(username)
        
        # Start caching in background to avoid blocking the UI
        background_tasks.add_task(
            _cache_repository_background,
            repo_service,
            request.repo_url,
            username
        )
        
        # Extract repo name for response
        from backend.integrations.cosmos.v1.cosmos.repo_fetch import _get_repo_name_from_url
        repo_name = _get_repo_name_from_url(request.repo_url)
        
        return CacheRepositoryResponse(
            success=True,
            message=f"Repository caching started for {repo_name}",
            repository_name=repo_name,
            cached_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error starting repository cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start repository caching: {str(e)}"
        )


@router.get("/status/{repo_name}")
async def get_cache_status(
    repo_name: str,
    branch: str = "main",
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the caching status of a repository.
    
    Returns information about whether the repository is cached and ready for use.
    """
    try:
        username = current_user.get("username") or current_user.get("login")
        
        # Construct repo URL from repo_name (assuming GitHub)
        if "/" not in repo_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository name must be in format 'owner/repo'"
            )
        
        repo_url = f"https://github.com/{repo_name}"
        
        # Use optimized service for status check
        repo_service = get_optimized_repo_service(username)
        
        # Check if repository data is available
        repo_data = repo_service.get_repository_data(repo_url)
        
        if repo_data:
            # Get repository stats
            stats = repo_service.get_repository_stats(repo_url)
            
            return {
                "cached": True,
                "repository_name": repo_name,
                "branch": branch,
                "file_count": stats.get('total_files', 0),
                "estimated_tokens": stats.get('estimated_tokens'),
                "stored_at": stats.get('stored_at'),
                "has_content": 'content' in repo_data,
                "has_tree": 'tree' in repo_data,
                "ready_for_chat": 'content' in repo_data and 'tree' in repo_data
            }
        else:
            return {
                "cached": False,
                "repository_name": repo_name,
                "branch": branch,
                "ready_for_chat": False,
                "message": "Repository not cached. Call /cache endpoint to cache it."
            }
        
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache status: {str(e)}"
        )


@router.delete("/clear", response_model=ClearCacheResponse)
async def clear_repository_cache(
    request: ClearCacheRequest,
    current_user: dict = Depends(get_current_user)
) -> ClearCacheResponse:
    """
    Clear repository cache when user leaves /contribution page.
    
    This endpoint is called when a user navigates away from the /contribution page
    to /hub to clean up cached repository data and free memory.
    """
    try:
        username = current_user.get("username") or current_user.get("login")
        cleared_repos = []
        
        # Use optimized service for cache clearing
        repo_service = get_optimized_repo_service(username)
        
        if request.repo_url:
            # Clear specific repository
            success = repo_service.clear_cache(request.repo_url)
            
            if success:
                from backend.integrations.cosmos.v1.cosmos.repo_fetch import _get_repo_name_from_url
                repo_name = _get_repo_name_from_url(request.repo_url)
                cleared_repos.append(repo_name)
                logger.info(f"Cleared cache for repository: {repo_name}")
            else:
                logger.warning(f"Failed to clear cache for repository: {request.repo_url}")
        else:
            # Clear all cached repositories for this user
            success = repo_service.clear_cache()
            logger.info(f"Cache clear requested for user: {username}")
        
        return ClearCacheResponse(
            success=True,
            message=f"Cache cleared successfully for {len(cleared_repos)} repositories",
            cleared_repositories=cleared_repos
        )
        
    except Exception as e:
        logger.error(f"Error clearing repository cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear repository cache: {str(e)}"
        )


@router.get("/health")
async def get_cache_health() -> Dict[str, Any]:
    """
    Get repository cache health status.
    
    Returns information about the cache system health and performance.
    """
    try:
        # Use optimized service for health check
        repo_service = get_optimized_repo_service("test_user")
        health_info = repo_service.health_check()
        
        redis_healthy = health_info.get("redis_healthy", False)
        overall_healthy = health_info.get("overall_healthy", False)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "redis_healthy": redis_healthy,
            "overall_healthy": overall_healthy,
            "cache_system": "operational" if overall_healthy else "degraded",
            "message": "Repository cache system is ready" if overall_healthy else "Cache system issues detected",
            "details": health_info
        }
        
    except Exception as e:
        logger.error(f"Error checking cache health: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "redis_healthy": False,
            "overall_healthy": False,
            "cache_system": "error",
            "message": f"Health check failed: {str(e)}"
        }


def _cache_repository_background(
    repo_service,
    repo_url: str,
    username: str
) -> None:
    """
    Background task to cache repository data.
    
    This runs asynchronously to avoid blocking the API response.
    """
    try:
        logger.info(f"Starting background caching for {repo_url}")
        
        # Check if this is a public repository that can be cached without token
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token or github_token.strip() == "" or github_token.startswith("your_github"):
            logger.info(f"No GitHub token available - caching public repository: {repo_url}")
        
        # Fetch and cache the repository using optimized service
        repo_data = repo_service.get_repository_data(repo_url, force_refresh=True)
        
        if repo_data:
            # Get repository stats to log success details
            stats = repo_service.get_repository_stats(repo_url)
            file_count = stats.get('total_files', 0)
            
            from backend.integrations.cosmos.v1.cosmos.repo_fetch import _get_repo_name_from_url
            repo_name = _get_repo_name_from_url(repo_url)
            
            logger.info(
                f"Successfully cached repository {repo_name} "
                f"for user {username}. Files: {file_count}"
            )
        else:
            logger.warning(f"Failed to cache repository {repo_url} for user {username}. "
                         f"This might be due to rate limits or private repository access. "
                         f"Consider adding a GitHub token to your .env file.")
            
    except Exception as e:
        logger.error(f"Error in background repository caching: {e}")
        # Add helpful error message for common issues
        if "rate limit" in str(e).lower():
            logger.error("GitHub rate limit exceeded. Add a GitHub token to increase limits.")
        elif "not found" in str(e).lower():
            logger.error("Repository not found or private. Ensure the URL is correct and accessible.")