"""
Tier validation middleware for chat endpoints.

This middleware provides tier-based access control for chat API endpoints,
integrating with the WebTierAccessController to enforce limits and restrictions.
"""

from typing import Optional, Callable, Dict, Any
from functools import wraps
import structlog

from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from models.api.auth_models import User
from services.tier_access_service import get_web_tier_access_controller, AccessValidationResult
from .dependencies import get_current_user

logger = structlog.get_logger(__name__)


class TierValidationMiddleware:
    """
    Middleware for tier-based access validation in chat endpoints.
    """
    
    def __init__(self):
        self.controller = get_web_tier_access_controller()
    
    def validate_repository_access(
        self, 
        repository_url: str, 
        repository_size_mb: float,
        branch: str = "main"
    ):
        """
        Decorator to validate repository access based on user tier.
        
        Args:
            repository_url: Repository URL to validate
            repository_size_mb: Repository size in MB
            branch: Repository branch
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from dependencies
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    # Try to get user from kwargs
                    user = kwargs.get('current_user')
                
                if not user:
                    raise HTTPException(
                        status_code=401, 
                        detail="Authentication required for tier validation"
                    )
                
                # Validate repository access
                result = self.controller.validate_repository_access(
                    user=user,
                    repository_url=repository_url,
                    repository_size_mb=repository_size_mb,
                    branch=branch
                )
                
                if not result.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "repository_access_denied",
                            "message": result.message,
                            "tier": result.tier,
                            "limits": result.limits.__dict__ if result.limits else None
                        }
                    )
                
                # Add tier info to kwargs for the endpoint
                kwargs['tier_validation'] = result
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def validate_model_access(self, model_name: str):
        """
        Decorator to validate model access based on user tier.
        
        Args:
            model_name: Model name to validate
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from dependencies
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    user = kwargs.get('current_user')
                
                if not user:
                    raise HTTPException(
                        status_code=401, 
                        detail="Authentication required for tier validation"
                    )
                
                # Validate model access
                result = self.controller.validate_model_access(
                    user=user,
                    model_name=model_name
                )
                
                if not result.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "model_access_denied",
                            "message": result.message,
                            "tier": result.tier,
                            "allowed_models": result.limits.allowed_models if result.limits else []
                        }
                    )
                
                # Add tier info to kwargs for the endpoint
                kwargs['tier_validation'] = result
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def check_rate_limits(self):
        """
        Decorator to check rate limits based on user tier.
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from dependencies
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    user = kwargs.get('current_user')
                
                if not user:
                    raise HTTPException(
                        status_code=401, 
                        detail="Authentication required for rate limit check"
                    )
                
                # Check rate limits
                result = self.controller.check_rate_limits(user=user)
                
                if not result.allowed:
                    # Return 429 Too Many Requests with retry information
                    headers = {}
                    if result.retry_after:
                        headers["Retry-After"] = str(result.retry_after)
                    
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "rate_limit_exceeded",
                            "message": result.message,
                            "tier": result.tier,
                            "usage": result.usage,
                            "retry_after": result.retry_after
                        },
                        headers=headers
                    )
                
                # Add tier info to kwargs for the endpoint
                kwargs['tier_validation'] = result
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def validate_context_files(self, file_count: int):
        """
        Decorator to validate context file count based on user tier.
        
        Args:
            file_count: Number of files in context
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from dependencies
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    user = kwargs.get('current_user')
                
                if not user:
                    raise HTTPException(
                        status_code=401, 
                        detail="Authentication required for tier validation"
                    )
                
                # Validate context files
                result = self.controller.validate_context_files(
                    user=user,
                    file_count=file_count
                )
                
                if not result.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "context_files_limit_exceeded",
                            "message": result.message,
                            "tier": result.tier,
                            "max_context_files": result.limits.max_context_files if result.limits else 0
                        }
                    )
                
                # Add tier info to kwargs for the endpoint
                kwargs['tier_validation'] = result
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def validate_session_limits(self, session_id: str):
        """
        Decorator to validate session limits based on user tier.
        
        Args:
            session_id: Session ID to validate
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user from dependencies
                user = None
                for arg in args:
                    if isinstance(arg, User):
                        user = arg
                        break
                
                if not user:
                    user = kwargs.get('current_user')
                
                if not user:
                    raise HTTPException(
                        status_code=401, 
                        detail="Authentication required for tier validation"
                    )
                
                # Validate session limits
                result = self.controller.validate_session_limits(
                    user=user,
                    session_id=session_id
                )
                
                if not result.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "session_limit_exceeded",
                            "message": result.message,
                            "tier": result.tier,
                            "max_concurrent_sessions": result.limits.max_concurrent_sessions if result.limits else 0
                        }
                    )
                
                # Add tier info to kwargs for the endpoint
                kwargs['tier_validation'] = result
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator


# Global middleware instance
tier_middleware = TierValidationMiddleware()


# Dependency functions for FastAPI
async def validate_tier_access(
    current_user: User = Depends(get_current_user)
) -> AccessValidationResult:
    """
    FastAPI dependency to validate basic tier access.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        AccessValidationResult with basic validation
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    controller = get_web_tier_access_controller()
    
    # Basic rate limit check
    result = controller.check_rate_limits(current_user)
    
    if not result.allowed:
        headers = {}
        if result.retry_after:
            headers["Retry-After"] = str(result.retry_after)
        
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": result.message,
                "tier": result.tier,
                "usage": result.usage,
                "retry_after": result.retry_after
            },
            headers=headers
        )
    
    return result


async def validate_repository_tier_access(
    repository_url: str,
    repository_size_tokens: Optional[int] = None,
    branch: str = "main",
    current_user: User = Depends(get_current_user)
) -> AccessValidationResult:
    """
    FastAPI dependency to validate repository access based on tier.
    
    Args:
        repository_url: Repository URL
        repository_size_tokens: Repository size in tokens (optional - will fetch from Redis if not provided)
        branch: Repository branch
        current_user: Authenticated user
        
    Returns:
        AccessValidationResult with repository validation
        
    Raises:
        HTTPException: If access is denied
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    controller = get_web_tier_access_controller()
    
    # Validate repository access - use URL-based method to fetch tokens from Redis
    if repository_size_tokens is not None:
        result = controller.validate_repository_access(
            user=current_user,
            repository_url=repository_url,
            repository_size_tokens=repository_size_tokens,
            branch=branch
        )
    else:
        # Fetch token count from Redis (gitingest data)
        result = controller.validate_repository_access_from_url(
            user=current_user,
            repository_url=repository_url,
            branch=branch
        )
    
    if not result.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "repository_access_denied",
                "message": result.message,
                "tier": result.tier,
                "limits": result.limits.__dict__ if result.limits else None
            }
        )
    
    return result


async def validate_model_tier_access(
    model_name: str,
    current_user: User = Depends(get_current_user)
) -> AccessValidationResult:
    """
    FastAPI dependency to validate model access based on tier.
    
    Args:
        model_name: Model name
        current_user: Authenticated user
        
    Returns:
        AccessValidationResult with model validation
        
    Raises:
        HTTPException: If access is denied
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    controller = get_web_tier_access_controller()
    
    # Validate model access
    result = controller.validate_model_access(
        user=current_user,
        model_name=model_name
    )
    
    if not result.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "model_access_denied",
                "message": result.message,
                "tier": result.tier,
                "allowed_models": result.limits.allowed_models if result.limits else []
            }
        )
    
    return result


async def get_user_tier_info(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get user tier information.
    
    Args:
        current_user: Authenticated user
        
    Returns:
        Dictionary with tier information and usage
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    controller = get_web_tier_access_controller()
    return controller.get_usage_summary(current_user)


# Utility functions for manual validation
def validate_request_tier_access(user: User) -> AccessValidationResult:
    """
    Manually validate tier access for a user.
    
    Args:
        user: Authenticated user
        
    Returns:
        AccessValidationResult with validation details
    """
    controller = get_web_tier_access_controller()
    return controller.check_rate_limits(user)


def validate_request_repository_access(
    user: User, 
    repository_url: str, 
    repository_size_mb: float,
    branch: str = "main"
) -> AccessValidationResult:
    """
    Manually validate repository access for a user.
    
    Args:
        user: Authenticated user
        repository_url: Repository URL
        repository_size_mb: Repository size in MB
        branch: Repository branch
        
    Returns:
        AccessValidationResult with validation details
    """
    controller = get_web_tier_access_controller()
    return controller.validate_repository_access(
        user=user,
        repository_url=repository_url,
        repository_size_mb=repository_size_mb,
        branch=branch
    )


def validate_request_model_access(user: User, model_name: str) -> AccessValidationResult:
    """
    Manually validate model access for a user.
    
    Args:
        user: Authenticated user
        model_name: Model name
        
    Returns:
        AccessValidationResult with validation details
    """
    controller = get_web_tier_access_controller()
    return controller.validate_model_access(user=user, model_name=model_name)


def cleanup_user_session(user: User, session_id: str) -> None:
    """
    Clean up a user session.
    
    Args:
        user: Authenticated user
        session_id: Session ID to clean up
    """
    controller = get_web_tier_access_controller()
    controller.cleanup_user_session(user=user, session_id=session_id)