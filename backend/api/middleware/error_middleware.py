"""
Enhanced Error Middleware for Cosmos Web Chat

Provides centralized error handling, logging, and user-friendly error responses
for all API endpoints. Integrates with the comprehensive error handling system.
"""

import logging
import traceback
import time
from typing import Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import uuid

try:
    from ...utils.error_handling import (
        ErrorHandler, CosmosError, ErrorContext, ErrorCategory,
        ErrorSeverity, handle_cosmos_error, create_http_exception
    )
    from ...services.graceful_degradation import get_graceful_degradation_service
    from ...config.settings import get_settings
except ImportError:
    from utils.error_handling import (
        ErrorHandler, CosmosError, ErrorContext, ErrorCategory,
        ErrorSeverity, handle_cosmos_error, create_http_exception
    )
    from services.graceful_degradation import get_graceful_degradation_service
    from config.settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseHTTPMiddleware):
    """
    Enhanced Error Middleware
    
    Provides centralized error handling, logging, monitoring integration,
    and user-friendly error responses for all API endpoints.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the error middleware."""
        super().__init__(app)
        self.settings = get_settings()
        self.error_handler = ErrorHandler()
        self.degradation_service = get_graceful_degradation_service()
        
        # Request tracking
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        
        # Error rate tracking
        self.error_counts = {
            "total_requests": 0,
            "error_requests": 0,
            "errors_by_endpoint": {},
            "errors_by_status": {}
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request through error handling middleware.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response with error handling applied
        """
        # Generate request ID for tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Create error context
        error_context = ErrorContext(
            request_id=request_id,
            endpoint=str(request.url.path),
            method=request.method,
            user_agent=request.headers.get("user-agent"),
            ip_address=self._get_client_ip(request)
        )
        
        # Add user context if available
        if hasattr(request.state, "user") and request.state.user:
            error_context.user_id = getattr(request.state.user, "id", None)
        
        # Track request start
        start_time = time.time()
        self.active_requests[request_id] = {
            "start_time": start_time,
            "endpoint": error_context.endpoint,
            "method": error_context.method,
            "user_id": error_context.user_id
        }
        
        # Update request metrics
        self.error_counts["total_requests"] += 1
        
        try:
            # Check system health before processing
            system_health = await self.degradation_service.get_system_health()
            
            # Add health information to request state
            request.state.system_health = system_health
            request.state.error_context = error_context
            
            # Process request
            response = await call_next(request)
            
            # Track successful request
            self._track_successful_request(request_id, error_context, start_time)
            
            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-System-Health"] = system_health["overall_status"]
            
            return response
            
        except Exception as e:
            # Handle error
            return await self._handle_error(e, error_context, request_id, start_time)
        
        finally:
            # Clean up request tracking
            self.active_requests.pop(request_id, None)
    
    async def _handle_error(
        self,
        error: Exception,
        context: ErrorContext,
        request_id: str,
        start_time: float
    ) -> JSONResponse:
        """
        Handle an error and return appropriate response.
        
        Args:
            error: The error that occurred
            context: Error context information
            request_id: Request ID for tracking
            start_time: Request start time
            
        Returns:
            JSONResponse with error information
        """
        try:
            # Calculate request duration
            duration = time.time() - start_time
            
            # Update error metrics
            self._track_error_request(context, duration)
            
            # Handle different error types
            if isinstance(error, HTTPException):
                # FastAPI HTTPException
                error_response = self._handle_http_exception(error, context)
            elif isinstance(error, CosmosError):
                # Our custom error types
                error_response = self.error_handler.handle_error(error, context)
            else:
                # Generic exceptions
                error_response = self.error_handler.handle_error(error, context)
            
            # Create HTTP response
            http_exception = create_http_exception(error_response)
            
            # Log error with appropriate level
            self._log_error(error, error_response, context, duration)
            
            # Create JSON response
            response_data = {
                "error": http_exception.detail,
                "request_id": request_id,
                "timestamp": error_response.timestamp.isoformat(),
                "path": context.endpoint,
                "method": context.method
            }
            
            # Add system health information
            try:
                system_health = await self.degradation_service.get_system_health()
                response_data["system_health"] = {
                    "status": system_health["overall_status"],
                    "degradation_level": system_health.get("degradation_level", "none")
                }
            except Exception:
                # Don't fail the error response if health check fails
                pass
            
            # Create response with appropriate status code and headers
            response = JSONResponse(
                content=response_data,
                status_code=http_exception.status_code,
                headers={
                    "X-Request-ID": request_id,
                    "X-Error-Code": error_response.error_code,
                    "X-Error-Category": error_response.category.value,
                    "X-Correlation-ID": error_response.correlation_id,
                    **(http_exception.headers or {})
                }
            )
            
            return response
            
        except Exception as handler_error:
            # Fallback error handling if our error handler fails
            logger.critical(f"Error in error handler: {handler_error}")
            
            return JSONResponse(
                content={
                    "error": {
                        "error_code": "CRITICAL_ERROR",
                        "message": "A critical system error occurred. Please contact support.",
                        "category": "system",
                        "severity": "critical",
                        "correlation_id": str(uuid.uuid4())
                    },
                    "request_id": request_id,
                    "timestamp": context.timestamp.isoformat()
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                headers={"X-Request-ID": request_id}
            )
    
    def _handle_http_exception(self, http_exc: HTTPException, context: ErrorContext):
        """Handle FastAPI HTTPException."""
        # Map HTTP status codes to our error categories
        category_map = {
            400: ErrorCategory.VALIDATION,
            401: ErrorCategory.AUTHENTICATION,
            403: ErrorCategory.AUTHORIZATION,
            404: ErrorCategory.REPOSITORY,
            429: ErrorCategory.RATE_LIMIT,
            500: ErrorCategory.SYSTEM,
            502: ErrorCategory.EXTERNAL_API,
            503: ErrorCategory.SYSTEM,
            504: ErrorCategory.NETWORK
        }
        
        category = category_map.get(http_exc.status_code, ErrorCategory.SYSTEM)
        
        # Create CosmosError from HTTPException
        cosmos_error = CosmosError(
            message=str(http_exc.detail),
            error_code=f"HTTP_{http_exc.status_code}",
            category=category,
            severity=ErrorSeverity.HIGH if http_exc.status_code >= 500 else ErrorSeverity.MEDIUM,
            details={"status_code": http_exc.status_code}
        )
        
        return self.error_handler.handle_error(cosmos_error, context)
    
    def _track_successful_request(self, request_id: str, context: ErrorContext, start_time: float):
        """Track successful request metrics."""
        duration = time.time() - start_time
        
        logger.debug(
            f"Request completed successfully",
            extra={
                "request_id": request_id,
                "endpoint": context.endpoint,
                "method": context.method,
                "duration": duration,
                "user_id": context.user_id
            }
        )
    
    def _track_error_request(self, context: ErrorContext, duration: float):
        """Track error request metrics."""
        self.error_counts["error_requests"] += 1
        
        # Track by endpoint
        endpoint = context.endpoint
        if endpoint not in self.error_counts["errors_by_endpoint"]:
            self.error_counts["errors_by_endpoint"][endpoint] = 0
        self.error_counts["errors_by_endpoint"][endpoint] += 1
        
        # Log error metrics periodically
        if self.error_counts["error_requests"] % 10 == 0:
            error_rate = (self.error_counts["error_requests"] / self.error_counts["total_requests"]) * 100
            logger.warning(
                f"Error rate: {error_rate:.2f}% ({self.error_counts['error_requests']}/{self.error_counts['total_requests']})"
            )
    
    def _log_error(
        self,
        error: Exception,
        error_response,
        context: ErrorContext,
        duration: float
    ):
        """Log error with appropriate level and context."""
        log_data = {
            "request_id": context.request_id,
            "correlation_id": error_response.correlation_id,
            "endpoint": context.endpoint,
            "method": context.method,
            "user_id": context.user_id,
            "duration": duration,
            "error_code": error_response.error_code,
            "error_category": error_response.category.value,
            "error_severity": error_response.severity.value,
            "user_agent": context.user_agent,
            "ip_address": context.ip_address
        }
        
        # Add traceback for system errors
        if error_response.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            log_data["traceback"] = traceback.format_exc()
        
        # Log with appropriate level
        if error_response.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error in API request", extra=log_data)
        elif error_response.severity == ErrorSeverity.HIGH:
            logger.error("High severity error in API request", extra=log_data)
        elif error_response.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error in API request", extra=log_data)
        else:
            logger.info("Low severity error in API request", extra=log_data)
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Get client IP address from request."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to client host
        if hasattr(request.client, "host"):
            return request.client.host
        
        return None
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        total_requests = self.error_counts["total_requests"]
        error_requests = self.error_counts["error_requests"]
        
        error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "total_requests": total_requests,
            "error_requests": error_requests,
            "error_rate_percentage": round(error_rate, 2),
            "active_requests": len(self.active_requests),
            "errors_by_endpoint": dict(self.error_counts["errors_by_endpoint"]),
            "errors_by_status": dict(self.error_counts["errors_by_status"]),
            "top_error_endpoints": sorted(
                self.error_counts["errors_by_endpoint"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request Logging Middleware
    
    Logs all requests with timing and context information.
    Complements the error middleware with detailed request logging.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the request logging middleware."""
        super().__init__(app)
        self.settings = get_settings()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Log request and response information.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain
            
        Returns:
            Response with logging applied
        """
        start_time = time.time()
        
        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "user_agent": request.headers.get("user-agent"),
                "request_id": getattr(request.state, "request_id", None)
            }
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log request completion
        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration": duration,
                "request_id": getattr(request.state, "request_id", None)
            }
        )
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        return response


# Middleware instances for easy import
error_middleware = ErrorMiddleware
request_logging_middleware = RequestLoggingMiddleware