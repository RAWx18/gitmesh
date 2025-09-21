"""
Chat API routes with tier-based access control integration.

This module provides enhanced chat endpoints that integrate with the tier access control system,
enforcing repository size limits, model access restrictions, and rate limiting.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
import structlog

from models.api.auth_models import User
from .dependencies import get_current_user
from .tier_middleware import (
    validate_tier_access,
    validate_repository_tier_access,
    validate_model_tier_access,
    get_user_tier_info,
    validate_request_tier_access,
    validate_request_repository_access,
    validate_request_model_access,
    cleanup_user_session
)
from services.tier_access_service import get_web_tier_access_controller, AccessValidationResult

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/tier/info")
async def get_tier_information(
    tier_info: Dict[str, Any] = Depends(get_user_tier_info)
):
    """
    Get user tier information and usage statistics.
    
    Returns:
        Dictionary with tier limits and current usage
    """
    return {
        "success": True,
        "tier_info": tier_info
    }


@router.post("/tier/validate/repository")
async def validate_repository_access_endpoint(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Validate repository access based on user tier.
    
    Request body:
        - repository_url: Repository URL to validate
        - repository_size_tokens: Repository size in tokens (optional - will fetch from Redis if not provided)
        - branch: Repository branch (optional, defaults to "main")
    
    Returns:
        Validation result with access details
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        repository_url = request.get("repository_url")
        repository_size_tokens = request.get("repository_size_tokens")
        branch = request.get("branch", "main")
        
        if not repository_url:
            raise HTTPException(status_code=400, detail="repository_url is required")
        
        controller = get_web_tier_access_controller()
        
        # Validate repository access - fetch tokens from Redis if not provided
        if repository_size_tokens is not None:
            result = controller.validate_repository_access(
                user=current_user,
                repository_url=repository_url,
                repository_size_tokens=int(repository_size_tokens),
                branch=branch
            )
        else:
            # Fetch token count from Redis (gitingest data)
            result = controller.validate_repository_access_from_url(
                user=current_user,
                repository_url=repository_url,
                branch=branch
            )
        
        return {
            "success": True,
            "validation": {
                "allowed": result.allowed,
                "message": result.message,
                "tier": result.tier,
                "limits": result.limits.__dict__ if result.limits else None,
                "usage": result.usage
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Repository validation failed: {e}")
        raise HTTPException(status_code=500, detail="Repository validation failed")


@router.post("/tier/validate/model")
async def validate_model_access_endpoint(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Validate model access based on user tier.
    
    Request body:
        - model_name: Model name to validate
    
    Returns:
        Validation result with access details
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        model_name = request.get("model_name")
        
        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")
        
        # Validate model access
        result = validate_request_model_access(
            user=current_user,
            model_name=model_name
        )
        
        return {
            "success": True,
            "validation": {
                "allowed": result.allowed,
                "message": result.message,
                "tier": result.tier,
                "limits": result.limits.__dict__ if result.limits else None,
                "allowed_models": result.limits.allowed_models if result.limits else []
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model validation failed: {e}")
        raise HTTPException(status_code=500, detail="Model validation failed")


@router.post("/tier/validate/context")
async def validate_context_files_endpoint(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Validate context file count based on user tier.
    
    Request body:
        - file_count: Number of files in context
    
    Returns:
        Validation result with access details
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        file_count = request.get("file_count")
        
        if file_count is None:
            raise HTTPException(status_code=400, detail="file_count is required")
        
        controller = get_web_tier_access_controller()
        
        # Validate context files
        result = controller.validate_context_files(
            user=current_user,
            file_count=int(file_count)
        )
        
        return {
            "success": True,
            "validation": {
                "allowed": result.allowed,
                "message": result.message,
                "tier": result.tier,
                "limits": result.limits.__dict__ if result.limits else None,
                "max_context_files": result.limits.max_context_files if result.limits else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Context validation failed: {e}")
        raise HTTPException(status_code=500, detail="Context validation failed")


@router.post("/sessions/tier-aware")
async def create_tier_aware_chat_session(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Create a new chat session with tier-based validation.
    
    Request body:
        - title: Session title (optional)
        - repository_id: Repository ID
        - repository_url: Repository URL (optional)
        - repository_size_tokens: Repository size in tokens (optional - will fetch from Redis if not provided)
        - branch: Repository branch (optional, defaults to "main")
    
    Returns:
        Created session with tier validation results
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Extract request parameters
        title = request.get("title")
        repository_id = request.get("repository_id")
        repository_url = request.get("repository_url")
        repository_size_tokens = request.get("repository_size_tokens")
        branch = request.get("branch", "main")
        
        if not repository_id:
            raise HTTPException(status_code=400, detail="repository_id is required")
        
        # Build repository URL if not provided
        if not repository_url:
            if "/" in repository_id and not repository_id.startswith("http"):
                repository_url = f"https://github.com/{repository_id}"
            else:
                repository_url = repository_id
        
        controller = get_web_tier_access_controller()
        
        # Validate tier access
        tier_result = validate_request_tier_access(current_user)
        if not tier_result.allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": tier_result.message,
                    "tier": tier_result.tier,
                    "retry_after": tier_result.retry_after
                }
            )
        
        # Validate repository access - fetch tokens from Redis if not provided
        if repository_size_tokens is not None:
            repo_result = controller.validate_repository_access(
                user=current_user,
                repository_url=repository_url,
                repository_size_tokens=int(repository_size_tokens),
                branch=branch
            )
        else:
            # Fetch token count from Redis (gitingest data)
            repo_result = controller.validate_repository_access_from_url(
                user=current_user,
                repository_url=repository_url,
                branch=branch
            )
        
        if not repo_result.allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "repository_access_denied",
                    "message": repo_result.message,
                    "tier": repo_result.tier,
                    "limits": repo_result.limits.__dict__ if repo_result.limits else None
                }
            )
        
        # Import chat service to create session
        try:
            from .chat import chat_service
        except ImportError:
            raise HTTPException(status_code=500, detail="Chat service not available")
        
        # Create session
        session = await chat_service.create_session(
            user_id=str(current_user.id),
            title=title,
            repository_id=repository_id,
            repository_url=repository_url,
            branch=branch
        )
        
        # Validate session limits
        session_result = controller.validate_session_limits(
            user=current_user,
            session_id=session["id"]
        )
        
        if not session_result.allowed:
            # Clean up the created session
            try:
                from .chat import chat_sessions, chat_messages
                if session["id"] in chat_sessions:
                    del chat_sessions[session["id"]]
                if session["id"] in chat_messages:
                    del chat_messages[session["id"]]
            except:
                pass
            
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "session_limit_exceeded",
                    "message": session_result.message,
                    "tier": session_result.tier,
                    "max_concurrent_sessions": session_result.limits.max_concurrent_sessions if session_result.limits else 0
                }
            )
        
        # Add tier information to session
        session["tier_info"] = {
            "tier": tier_result.tier,
            "limits": tier_result.limits.__dict__ if tier_result.limits else None,
            "repository_validated": True,
            "repository_size_tokens": repository_size_tokens or "fetched_from_redis"
        }
        
        return {
            "success": True,
            "session": session,
            "tier_validation": {
                "tier": tier_result.tier,
                "repository_access": repo_result.allowed,
                "session_limits": session_result.allowed
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tier-aware session creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.post("/sessions/{session_id}/messages/tier-aware")
async def send_tier_aware_message(
    session_id: str,
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    Send a message with tier-based validation.
    
    Request body:
        - message: Message content
        - model: Model name (optional, defaults to gpt-4o-mini)
        - context: Message context (optional)
    
    Returns:
        Message response with tier validation
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        message = request.get("message", "")
        model_name = request.get("model", "gpt-4o-mini")
        context = request.get("context", {})
        
        if not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        controller = get_web_tier_access_controller()
        
        # Validate tier access and rate limits
        tier_result = validate_request_tier_access(current_user)
        if not tier_result.allowed:
            headers = {}
            if tier_result.retry_after:
                headers["Retry-After"] = str(tier_result.retry_after)
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": tier_result.message,
                    "tier": tier_result.tier,
                    "retry_after": tier_result.retry_after
                },
                headers=headers
            )
        
        # Validate model access
        model_result = validate_request_model_access(
            user=current_user,
            model_name=model_name
        )
        
        if not model_result.allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_access_denied",
                    "message": model_result.message,
                    "tier": model_result.tier,
                    "allowed_models": model_result.limits.allowed_models if model_result.limits else []
                }
            )
        
        # Validate context files if provided
        if context and context.get("files"):
            files = context["files"]
            file_count = len(files)
            
            context_result = controller.validate_context_files(
                user=current_user,
                file_count=file_count
            )
            
            if not context_result.allowed:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "context_files_limit_exceeded",
                        "message": context_result.message,
                        "tier": context_result.tier,
                        "max_context_files": context_result.limits.max_context_files if context_result.limits else 0
                    }
                )
        
        # Import chat service to send message
        try:
            from .chat import chat_service
        except ImportError:
            raise HTTPException(status_code=500, detail="Chat service not available")
        
        # Send message
        result = await chat_service.send_message(
            session_id=session_id,
            user_id=str(current_user.id),
            message=message,
            context=context,
            model_name=model_name
        )
        
        # Add tier information to response
        result["tier_validation"] = {
            "tier": tier_result.tier,
            "model_access": model_result.allowed,
            "rate_limit_status": tier_result.usage
        }
        
        return {
            "success": True,
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tier-aware message sending failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.delete("/sessions/{session_id}/tier-cleanup")
async def cleanup_tier_aware_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Clean up a session with tier tracking cleanup.
    
    Returns:
        Cleanup confirmation
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Clean up tier tracking
        cleanup_user_session(current_user, session_id)
        
        # Import chat service to clean up session
        try:
            from .chat import chat_service, chat_sessions, chat_messages
        except ImportError:
            raise HTTPException(status_code=500, detail="Chat service not available")
        
        # Verify session exists and user has access
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Clean up session
        del chat_sessions[session_id]
        if session_id in chat_messages:
            del chat_messages[session_id]
        
        # Clean up Cosmos session if available
        try:
            from integrations.cosmos.v1.cosmos_wrapper import session_manager
            repository_id = session.get("repositoryId", "default")
            branch = session.get("branch", "main")
            session_manager.cleanup_session(str(current_user.id), repository_id, branch)
        except:
            pass  # Cosmos cleanup is optional
        
        return {
            "success": True,
            "message": "Session cleaned up successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tier-aware session cleanup failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup session")


@router.get("/tier/models")
async def get_tier_available_models(
    current_user: User = Depends(get_current_user)
):
    """
    Get available models based on user tier.
    
    Returns:
        List of models available for the user's tier
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        controller = get_web_tier_access_controller()
        tier_limits = controller.get_tier_limits(current_user)
        
        if not tier_limits:
            raise HTTPException(status_code=500, detail="Failed to get tier limits")
        
        # Get all available models
        try:
            from .chat import COSMOS_AVAILABLE
            if COSMOS_AVAILABLE:
                from integrations.cosmos.v1.cosmos_wrapper import list_all_models
                all_models = list_all_models()
            else:
                # Fallback models
                all_models = [
                    {
                        "name": "gpt-4o-mini",
                        "display_name": "GPT-4o Mini",
                        "provider": "openai",
                        "available": False,
                        "context_length": 128000,
                        "supports_streaming": True,
                        "error": "Cosmos not available"
                    }
                ]
        except Exception as e:
            logger.warning(f"Failed to get models from Cosmos: {e}")
            all_models = []
        
        # Filter models based on tier
        allowed_models = tier_limits.allowed_models
        
        if "*" in allowed_models:
            # Enterprise tier - all models
            available_models = all_models
        else:
            # Filter models by allowed list
            available_models = [
                model for model in all_models
                if model.get("name") in allowed_models
            ]
        
        # Add tier information to each model
        for model in available_models:
            model["tier_restricted"] = "*" not in allowed_models
            model["user_tier"] = controller._get_user_tier(current_user)
        
        return {
            "success": True,
            "models": available_models,
            "tier_info": {
                "tier": controller._get_user_tier(current_user),
                "allowed_models": allowed_models,
                "total_available": len(available_models)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tier-available models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get available models")


@router.get("/tier/usage")
async def get_tier_usage_details(
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed tier usage information.
    
    Returns:
        Detailed usage statistics and limits
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        controller = get_web_tier_access_controller()
        usage_summary = controller.get_usage_summary(current_user)
        
        # Add additional usage details
        tier_limits = controller.get_tier_limits(current_user)
        if tier_limits:
            usage_summary["detailed_limits"] = {
                "repository_size": {
                    "max_mb": tier_limits.max_repository_size_mb,
                    "description": f"Maximum repository size in MB"
                },
                "requests": {
                    "max_per_hour": tier_limits.max_requests_per_hour,
                    "description": "Maximum API requests per hour (-1 = unlimited)"
                },
                "context_files": {
                    "max_files": tier_limits.max_context_files,
                    "description": "Maximum files that can be added to context"
                },
                "sessions": {
                    "max_concurrent": tier_limits.max_concurrent_sessions,
                    "max_duration_hours": tier_limits.max_session_duration_hours,
                    "description": "Maximum concurrent sessions and duration"
                },
                "models": {
                    "allowed": tier_limits.allowed_models,
                    "description": "AI models available for this tier"
                }
            }
        
        return {
            "success": True,
            "usage": usage_summary
        }
        
    except Exception as e:
        logger.error(f"Failed to get tier usage details: {e}")
        raise HTTPException(status_code=500, detail="Failed to get usage details")