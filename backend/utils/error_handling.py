"""
Comprehensive Error Handling and User Feedback System

Provides centralized error handling, user-friendly error messages,
and graceful degradation for the Cosmos Web Chat Integration.
"""

import logging
import traceback
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from fastapi import HTTPException, status
import redis
import json

# Configure logging
logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error category enumeration for classification."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    REPOSITORY = "repository"
    MODEL = "model"
    RATE_LIMIT = "rate_limit"
    SYSTEM = "system"
    NETWORK = "network"
    STORAGE = "storage"
    EXTERNAL_API = "external_api"


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorContext:
    """Additional context information for errors."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class SuggestedAction:
    """Suggested action for error resolution."""
    action_type: str  # 'retry', 'contact_support', 'check_settings', 'upgrade_tier'
    description: str
    action_url: Optional[str] = None
    action_data: Optional[Dict[str, Any]] = None


@dataclass
class ErrorResponse:
    """Standardized error response structure."""
    error_code: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    details: Optional[Dict[str, Any]] = None
    suggested_actions: List[SuggestedAction] = None
    retry_after: Optional[int] = None  # For rate limiting
    correlation_id: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.suggested_actions is None:
            self.suggested_actions = []


class CosmosError(Exception):
    """Base exception class for Cosmos Web Chat errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        category: ErrorCategory,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        suggested_actions: Optional[List[SuggestedAction]] = None,
        retry_after: Optional[int] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.suggested_actions = suggested_actions or []
        self.retry_after = retry_after
        self.cause = cause
        self.timestamp = datetime.now()


class AuthenticationError(CosmosError):
    """Authentication-related errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AUTH_FAILED",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="check_settings",
                    description="Please check your authentication credentials and try again.",
                    action_url="/auth/login"
                )
            ]
        )


class AuthorizationError(CosmosError):
    """Authorization-related errors."""
    
    def __init__(self, message: str, required_tier: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        actions = []
        if required_tier:
            actions.append(SuggestedAction(
                action_type="upgrade_tier",
                description=f"Upgrade to {required_tier} tier to access this feature.",
                action_url="/pricing"
            ))
        else:
            actions.append(SuggestedAction(
                action_type="contact_support",
                description="Contact support if you believe you should have access to this feature.",
                action_url="/support"
            ))
        
        super().__init__(
            message=message,
            error_code="ACCESS_DENIED",
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggested_actions=actions
        )


class ValidationError(CosmosError):
    """Input validation errors."""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_FAILED",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="check_settings",
                    description="Please check your input and try again.",
                )
            ]
        )


class RepositoryError(CosmosError):
    """Repository-related errors."""
    
    def __init__(self, message: str, repo_url: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        actions = [
            SuggestedAction(
                action_type="retry",
                description="Try again in a few moments.",
            )
        ]
        
        if repo_url:
            actions.append(SuggestedAction(
                action_type="check_settings",
                description="Verify the repository URL is correct and accessible.",
                action_data={"repo_url": repo_url}
            ))
        
        super().__init__(
            message=message,
            error_code="REPO_ERROR",
            category=ErrorCategory.REPOSITORY,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=actions
        )


class ModelError(CosmosError):
    """AI model-related errors."""
    
    def __init__(self, message: str, model: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        actions = [
            SuggestedAction(
                action_type="retry",
                description="Try again with a different model or in a few moments.",
            )
        ]
        
        if model:
            actions.append(SuggestedAction(
                action_type="check_settings",
                description="Try selecting a different AI model.",
                action_data={"current_model": model}
            ))
        
        super().__init__(
            message=message,
            error_code="MODEL_ERROR",
            category=ErrorCategory.MODEL,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=actions
        )


class RateLimitError(CosmosError):
    """Rate limiting errors."""
    
    def __init__(self, message: str, retry_after: int, tier: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        actions = [
            SuggestedAction(
                action_type="retry",
                description=f"Please wait {retry_after} seconds before trying again.",
            )
        ]
        
        if tier and tier == "free":
            actions.append(SuggestedAction(
                action_type="upgrade_tier",
                description="Upgrade to Pro or Enterprise for higher rate limits.",
                action_url="/pricing"
            ))
        
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=actions,
            retry_after=retry_after
        )


class SystemError(CosmosError):
    """System-level errors."""
    
    def __init__(self, message: str, service: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="SYSTEM_ERROR",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Please try again in a few moments.",
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if the problem persists.",
                    action_url="/support"
                )
            ]
        )


class NetworkError(CosmosError):
    """Network connectivity errors."""
    
    def __init__(self, message: str, service: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="NETWORK_ERROR",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Check your internet connection and try again.",
                )
            ]
        )


class StorageError(CosmosError):
    """Storage-related errors."""
    
    def __init__(self, message: str, storage_type: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            category=ErrorCategory.STORAGE,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Please try again in a few moments.",
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if the problem persists.",
                    action_url="/support"
                )
            ]
        )


class ExternalAPIError(CosmosError):
    """External API errors."""
    
    def __init__(self, message: str, api_name: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="EXTERNAL_API_ERROR",
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="The external service may be temporarily unavailable. Please try again.",
                )
            ]
        )


class ErrorHandler:
    """
    Centralized error handler for the Cosmos Web Chat system.
    
    Provides error classification, logging, monitoring integration,
    and user-friendly error message generation.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the error handler."""
        self.redis_client = redis_client
        self.error_counts = {}
        
        # Error message templates
        self.error_templates = {
            ErrorCategory.AUTHENTICATION: {
                "title": "Authentication Required",
                "description": "Please log in to access this feature.",
                "icon": "🔐"
            },
            ErrorCategory.AUTHORIZATION: {
                "title": "Access Denied",
                "description": "You don't have permission to access this feature.",
                "icon": "🚫"
            },
            ErrorCategory.VALIDATION: {
                "title": "Invalid Input",
                "description": "Please check your input and try again.",
                "icon": "⚠️"
            },
            ErrorCategory.REPOSITORY: {
                "title": "Repository Error",
                "description": "There was a problem accessing the repository.",
                "icon": "📁"
            },
            ErrorCategory.MODEL: {
                "title": "AI Model Error",
                "description": "There was a problem with the AI model.",
                "icon": "🤖"
            },
            ErrorCategory.RATE_LIMIT: {
                "title": "Rate Limit Exceeded",
                "description": "You've made too many requests. Please wait before trying again.",
                "icon": "⏱️"
            },
            ErrorCategory.SYSTEM: {
                "title": "System Error",
                "description": "An internal system error occurred.",
                "icon": "🔧"
            },
            ErrorCategory.NETWORK: {
                "title": "Connection Error",
                "description": "There was a problem connecting to the service.",
                "icon": "🌐"
            },
            ErrorCategory.STORAGE: {
                "title": "Storage Error",
                "description": "There was a problem with data storage.",
                "icon": "💾"
            },
            ErrorCategory.EXTERNAL_API: {
                "title": "Service Unavailable",
                "description": "An external service is temporarily unavailable.",
                "icon": "🔌"
            }
        }
    
    def handle_error(
        self,
        error: Union[Exception, CosmosError],
        context: Optional[ErrorContext] = None,
        log_error: bool = True
    ) -> ErrorResponse:
        """
        Handle an error and return a standardized error response.
        
        Args:
            error: The error to handle
            context: Additional context information
            log_error: Whether to log the error
            
        Returns:
            ErrorResponse with user-friendly information
        """
        try:
            # Generate correlation ID
            correlation_id = self._generate_correlation_id()
            
            # Convert to CosmosError if needed
            if not isinstance(error, CosmosError):
                cosmos_error = self._convert_to_cosmos_error(error)
            else:
                cosmos_error = error
            
            # Create error response
            error_response = ErrorResponse(
                error_code=cosmos_error.error_code,
                message=self._get_user_friendly_message(cosmos_error),
                category=cosmos_error.category,
                severity=cosmos_error.severity,
                details=self._sanitize_details(cosmos_error.details),
                suggested_actions=cosmos_error.suggested_actions,
                retry_after=cosmos_error.retry_after,
                correlation_id=correlation_id
            )
            
            # Log the error
            if log_error:
                self._log_error(cosmos_error, error_response, context)
            
            # Track error metrics
            self._track_error_metrics(cosmos_error, context)
            
            # Store error for monitoring
            if self.redis_client:
                self._store_error_for_monitoring(error_response, context)
            
            return error_response
            
        except Exception as e:
            # Fallback error handling
            logger.error(f"Error in error handler: {e}")
            return self._create_fallback_error_response()
    
    def _convert_to_cosmos_error(self, error: Exception) -> CosmosError:
        """Convert a generic exception to a CosmosError."""
        error_str = str(error)
        error_type = type(error).__name__
        
        # Map common exceptions to CosmosError types
        if isinstance(error, redis.RedisError):
            return StorageError(
                message="Database connection error",
                storage_type="redis",
                details={"original_error": error_str, "error_type": error_type}
            )
        elif isinstance(error, ConnectionError):
            return NetworkError(
                message="Network connection error",
                details={"original_error": error_str, "error_type": error_type}
            )
        elif isinstance(error, ValueError):
            return ValidationError(
                message=error_str,
                details={"original_error": error_str, "error_type": error_type}
            )
        elif isinstance(error, PermissionError):
            return AuthorizationError(
                message="Permission denied",
                details={"original_error": error_str, "error_type": error_type}
            )
        else:
            return SystemError(
                message="An unexpected error occurred",
                details={"original_error": error_str, "error_type": error_type}
            )
    
    def _get_user_friendly_message(self, error: CosmosError) -> str:
        """Generate a user-friendly error message."""
        template = self.error_templates.get(error.category, {})
        
        # Use template or fallback to error message
        if template:
            return f"{template['icon']} {template['title']}: {template['description']}"
        else:
            return error.message
    
    def _sanitize_details(self, details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Sanitize error details to remove sensitive information."""
        if not details:
            return None
        
        sanitized = {}
        sensitive_keys = {'password', 'token', 'key', 'secret', 'credential'}
        
        for key, value in details.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _log_error(
        self,
        error: CosmosError,
        error_response: ErrorResponse,
        context: Optional[ErrorContext]
    ):
        """Log the error with appropriate level and context."""
        log_data = {
            "error_code": error.error_code,
            "category": error.category.value,
            "severity": error.severity.value,
            "correlation_id": error_response.correlation_id,
            "error_message": error.message
        }
        
        if context:
            log_data.update({
                "user_id": context.user_id,
                "session_id": context.session_id,
                "endpoint": context.endpoint,
                "method": context.method
            })
        
        if error.cause:
            log_data["cause"] = str(error.cause)
            log_data["traceback"] = traceback.format_exc()
        
        # Log with appropriate level based on severity
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error("High severity error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error occurred", extra=log_data)
        else:
            logger.info("Low severity error occurred", extra=log_data)
    
    def _track_error_metrics(self, error: CosmosError, context: Optional[ErrorContext]):
        """Track error metrics for monitoring."""
        metric_key = f"{error.category.value}:{error.error_code}"
        
        if metric_key not in self.error_counts:
            self.error_counts[metric_key] = 0
        
        self.error_counts[metric_key] += 1
        
        # Log metrics periodically (this could be enhanced with proper metrics collection)
        if self.error_counts[metric_key] % 10 == 0:
            logger.info(f"Error metric: {metric_key} occurred {self.error_counts[metric_key]} times")
    
    def _store_error_for_monitoring(
        self,
        error_response: ErrorResponse,
        context: Optional[ErrorContext]
    ):
        """Store error information in Redis for monitoring."""
        try:
            error_data = {
                "error_response": asdict(error_response),
                "context": asdict(context) if context else None,
                "timestamp": datetime.now().isoformat()
            }
            
            # Store with expiration (24 hours)
            key = f"cosmos:error:{error_response.correlation_id}"
            self.redis_client.setex(
                key,
                86400,  # 24 hours
                json.dumps(error_data, default=str)
            )
            
            # Add to error index for monitoring dashboard
            error_index_key = f"cosmos:errors:{datetime.now().strftime('%Y-%m-%d')}"
            self.redis_client.lpush(error_index_key, error_response.correlation_id)
            self.redis_client.expire(error_index_key, 604800)  # 7 days
            
        except Exception as e:
            logger.error(f"Failed to store error for monitoring: {e}")
    
    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for error tracking."""
        import uuid
        return str(uuid.uuid4())
    
    def _create_fallback_error_response(self) -> ErrorResponse:
        """Create a fallback error response when error handling fails."""
        return ErrorResponse(
            error_code="UNKNOWN_ERROR",
            message="🔧 System Error: An unexpected error occurred. Please try again.",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Please try again in a few moments."
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if the problem persists.",
                    action_url="/support"
                )
            ],
            correlation_id=self._generate_correlation_id()
        )
    
    def get_error_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        if not self.redis_client:
            return {"error": "Redis not available"}
        
        try:
            stats = {
                "total_errors": 0,
                "errors_by_category": {},
                "errors_by_day": {},
                "top_errors": []
            }
            
            # Get errors for the specified number of days
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                error_index_key = f"cosmos:errors:{date}"
                
                error_ids = self.redis_client.lrange(error_index_key, 0, -1)
                stats["errors_by_day"][date] = len(error_ids)
                stats["total_errors"] += len(error_ids)
                
                # Analyze error categories for this day
                for error_id in error_ids[:100]:  # Limit to avoid performance issues
                    error_key = f"cosmos:error:{error_id}"
                    error_data = self.redis_client.get(error_key)
                    
                    if error_data:
                        try:
                            error_info = json.loads(error_data)
                            category = error_info.get("error_response", {}).get("category", "unknown")
                            
                            if category not in stats["errors_by_category"]:
                                stats["errors_by_category"][category] = 0
                            stats["errors_by_category"][category] += 1
                            
                        except json.JSONDecodeError:
                            continue
            
            # Get top error types from in-memory counts
            stats["top_errors"] = sorted(
                [(k, v) for k, v in self.error_counts.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting error statistics: {e}")
            return {"error": str(e)}


# Global error handler instance
error_handler = ErrorHandler()


def handle_cosmos_error(
    error: Union[Exception, CosmosError],
    context: Optional[ErrorContext] = None
) -> ErrorResponse:
    """
    Convenience function to handle errors using the global error handler.
    
    Args:
        error: The error to handle
        context: Additional context information
        
    Returns:
        ErrorResponse with user-friendly information
    """
    return error_handler.handle_error(error, context)


def create_http_exception(error_response: ErrorResponse) -> HTTPException:
    """
    Convert an ErrorResponse to a FastAPI HTTPException.
    
    Args:
        error_response: The error response to convert
        
    Returns:
        HTTPException for FastAPI
    """
    # Map error categories to HTTP status codes
    status_code_map = {
        ErrorCategory.AUTHENTICATION: status.HTTP_401_UNAUTHORIZED,
        ErrorCategory.AUTHORIZATION: status.HTTP_403_FORBIDDEN,
        ErrorCategory.VALIDATION: status.HTTP_400_BAD_REQUEST,
        ErrorCategory.REPOSITORY: status.HTTP_404_NOT_FOUND,
        ErrorCategory.MODEL: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCategory.RATE_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
        ErrorCategory.SYSTEM: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCategory.NETWORK: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCategory.STORAGE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCategory.EXTERNAL_API: status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    
    status_code = status_code_map.get(error_response.category, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Create detail with all error information
    detail = {
        "error_code": error_response.error_code,
        "message": error_response.message,
        "category": error_response.category.value,
        "severity": error_response.severity.value,
        "suggested_actions": [asdict(action) for action in error_response.suggested_actions],
        "correlation_id": error_response.correlation_id,
        "timestamp": error_response.timestamp.isoformat()
    }
    
    if error_response.details:
        detail["details"] = error_response.details
    
    if error_response.retry_after:
        detail["retry_after"] = error_response.retry_after
    
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Retry-After": str(error_response.retry_after)} if error_response.retry_after else None
    )