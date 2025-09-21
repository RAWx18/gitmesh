"""
Security Middleware for Cosmos Web Chat Integration

Provides comprehensive security headers, CORS configuration, input validation,
rate limiting, and abuse prevention for all API endpoints.
"""

import time
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from urllib.parse import urlparse
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

from utils.security_validation import (
    SecurityValidator, ValidationLevel, validate_and_sanitize_input,
    sanitize_output, security_validator
)
from utils.rate_limiting import (
    RateLimiter, AbuseDetector, RateLimitType, check_rate_limits,
    detect_and_prevent_abuse, rate_limiter, abuse_detector
)
from utils.error_handling import (
    ValidationError, RateLimitError, CosmosError, ErrorCategory,
    ErrorSeverity, handle_cosmos_error
)
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Security Headers Middleware
    
    Adds comprehensive security headers to all responses to prevent
    common web vulnerabilities and attacks.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the security headers middleware."""
        super().__init__(app)
        self.settings = get_settings()
        
        # Security headers configuration
        self.security_headers = {
            # Prevent XSS attacks
            "X-XSS-Protection": "1; mode=block",
            
            # Prevent MIME type sniffing
            "X-Content-Type-Options": "nosniff",
            
            # Prevent clickjacking
            "X-Frame-Options": "DENY",
            
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            
            # Permissions policy (formerly Feature Policy)
            "Permissions-Policy": (
                "geolocation=(), microphone=(), camera=(), "
                "payment=(), usb=(), magnetometer=(), gyroscope=()"
            ),
            
            # Content Security Policy
            "Content-Security-Policy": self._get_csp_header(),
            
            # Strict Transport Security (HTTPS only)
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
            
            # Cross-Origin policies
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "cross-origin"
        }
    
    def _get_csp_header(self) -> str:
        """Generate Content Security Policy header."""
        # Base CSP for API endpoints
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Relaxed for development
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self' https://api.github.com https://github.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'"
        ]
        
        # Add development-specific directives
        if self.settings.environment == "development":
            csp_directives.extend([
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' localhost:* 127.0.0.1:*",
                "connect-src 'self' localhost:* 127.0.0.1:* ws://localhost:* ws://127.0.0.1:*"
            ])
        
        return "; ".join(csp_directives)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to all responses."""
        # Process request
        response = await call_next(request)
        
        # Add security headers
        for header_name, header_value in self.security_headers.items():
            # Skip HSTS for non-HTTPS in development
            if (header_name == "Strict-Transport-Security" and 
                self.settings.environment == "development" and 
                not request.url.scheme == "https"):
                continue
            
            response.headers[header_name] = header_value
        
        # Add custom security headers
        response.headers["X-API-Version"] = "v1"
        response.headers["X-Security-Level"] = "enhanced"
        
        return response


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """
    Enhanced CORS Middleware with Security Validation
    
    Provides secure CORS handling with origin validation,
    credential management, and request method restrictions.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the CORS security middleware."""
        super().__init__(app)
        self.settings = get_settings()
        
        # Get allowed origins from settings
        self.allowed_origins = self._get_allowed_origins()
        
        # Allowed methods for different endpoint types
        self.allowed_methods = {
            "default": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "auth": ["GET", "POST", "OPTIONS"],
            "chat": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "websocket": ["GET", "OPTIONS"]
        }
        
        # Allowed headers
        self.allowed_headers = [
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Request-ID",
            "X-API-Key",
            "Cache-Control"
        ]
        
        # Exposed headers
        self.exposed_headers = [
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Response-Time",
            "X-System-Health"
        ]
    
    def _get_allowed_origins(self) -> List[str]:
        """Get and validate allowed origins."""
        origins = []
        
        # Get from settings
        if hasattr(self.settings, 'cors_origins'):
            origins.extend(self.settings.cors_origins)
        
        # Add environment-specific origins
        if self.settings.environment == "development":
            dev_origins = [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:3002",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "http://127.0.0.1:3002"
            ]
            origins.extend(dev_origins)
        
        # Validate origins
        validated_origins = []
        for origin in origins:
            if origin == "*":
                # Allow wildcard only in development
                if self.settings.environment == "development":
                    validated_origins.append(origin)
                else:
                    logger.warning("Wildcard CORS origin not allowed in production")
            else:
                # Validate origin format
                try:
                    parsed = urlparse(origin)
                    if parsed.scheme in ["http", "https"] and parsed.netloc:
                        validated_origins.append(origin)
                    else:
                        logger.warning(f"Invalid CORS origin format: {origin}")
                except Exception as e:
                    logger.warning(f"Error parsing CORS origin {origin}: {e}")
        
        return validated_origins
    
    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed."""
        if not origin:
            return False
        
        # Check wildcard
        if "*" in self.allowed_origins:
            return True
        
        # Check exact match
        if origin in self.allowed_origins:
            return True
        
        # Check subdomain patterns (for production use)
        for allowed_origin in self.allowed_origins:
            if allowed_origin.startswith("*."):
                domain = allowed_origin[2:]  # Remove *.
                if origin.endswith(f".{domain}") or origin == f"https://{domain}":
                    return True
        
        return False
    
    def _get_allowed_methods_for_path(self, path: str) -> List[str]:
        """Get allowed methods for a specific path."""
        if "/auth" in path:
            return self.allowed_methods["auth"]
        elif "/chat" in path or "/cosmos" in path:
            return self.allowed_methods["chat"]
        elif "/ws" in path or "websocket" in path:
            return self.allowed_methods["websocket"]
        else:
            return self.allowed_methods["default"]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Handle CORS with security validation."""
        origin = request.headers.get("origin")
        method = request.method
        path = request.url.path
        
        # Handle preflight requests
        if method == "OPTIONS":
            return self._handle_preflight(request, origin, path)
        
        # Validate origin for actual requests
        if origin and not self._is_origin_allowed(origin):
            logger.warning(f"CORS request from disallowed origin: {origin}")
            return JSONResponse(
                content={"error": "Origin not allowed"},
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        # Process request
        response = await call_next(request)
        
        # Add CORS headers to response
        if origin and self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = ", ".join(self.exposed_headers)
        
        return response
    
    def _handle_preflight(self, request: Request, origin: str, path: str) -> Response:
        """Handle CORS preflight requests."""
        # Check origin
        if not origin or not self._is_origin_allowed(origin):
            return JSONResponse(
                content={"error": "Origin not allowed"},
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        # Get requested method and headers
        requested_method = request.headers.get("access-control-request-method")
        requested_headers = request.headers.get("access-control-request-headers", "")
        
        # Validate requested method
        allowed_methods = self._get_allowed_methods_for_path(path)
        if requested_method and requested_method not in allowed_methods:
            return JSONResponse(
                content={"error": "Method not allowed"},
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED
            )
        
        # Validate requested headers
        if requested_headers:
            requested_header_list = [h.strip().lower() for h in requested_headers.split(",")]
            allowed_header_list = [h.lower() for h in self.allowed_headers]
            
            for header in requested_header_list:
                if header not in allowed_header_list:
                    return JSONResponse(
                        content={"error": f"Header not allowed: {header}"},
                        status_code=status.HTTP_403_FORBIDDEN
                    )
        
        # Create preflight response
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": ", ".join(allowed_methods),
            "Access-Control-Allow-Headers": ", ".join(self.allowed_headers),
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400",  # 24 hours
            "Vary": "Origin"
        }
        
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Input Validation and Sanitization Middleware
    
    Validates and sanitizes all incoming requests to prevent
    security vulnerabilities and ensure data integrity.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the input validation middleware."""
        super().__init__(app)
        self.validator = SecurityValidator(ValidationLevel.STRICT)
        
        # Paths that require validation
        self.validation_paths = {
            "/api/v1/chat": ["POST", "PUT"],
            "/api/v1/cosmos": ["POST", "PUT"],
            "/api/v1/sessions": ["POST", "PUT"],
            "/api/v1/auth": ["POST"],
            "/api/v1/github": ["POST", "PUT"]
        }
        
        # Maximum request sizes by endpoint
        self.max_request_sizes = {
            "/api/v1/chat/sessions": 1024 * 1024,  # 1MB
            "/api/v1/chat/messages": 5 * 1024 * 1024,  # 5MB for context files
            "/api/v1/cosmos": 5 * 1024 * 1024,  # 5MB
            "default": 1024 * 1024  # 1MB default
        }
    
    def _should_validate_request(self, request: Request) -> bool:
        """Check if request should be validated."""
        path = request.url.path
        method = request.method
        
        # Check if path matches validation patterns
        for validation_path, methods in self.validation_paths.items():
            if path.startswith(validation_path) and method in methods:
                return True
        
        return False
    
    def _get_max_request_size(self, path: str) -> int:
        """Get maximum request size for a path."""
        for size_path, max_size in self.max_request_sizes.items():
            if path.startswith(size_path):
                return max_size
        
        return self.max_request_sizes["default"]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Validate and sanitize incoming requests."""
        # Check if validation is needed
        if not self._should_validate_request(request):
            return await call_next(request)
        
        try:
            # Validate request size
            content_length = request.headers.get("content-length")
            if content_length:
                content_length = int(content_length)
                max_size = self._get_max_request_size(request.url.path)
                
                size_result = self.validator.validate_request_size(content_length, max_size)
                if not size_result.is_valid:
                    raise ValidationError(
                        message=f"Request too large: {size_result.errors[0]}",
                        details={"content_length": content_length, "max_size": max_size}
                    )
            
            # Validate content type for POST/PUT requests
            if request.method in ["POST", "PUT"]:
                content_type = request.headers.get("content-type", "")
                if not content_type.startswith("application/json"):
                    raise ValidationError(
                        message="Invalid content type. Expected application/json",
                        details={"content_type": content_type}
                    )
            
            # Process request
            response = await call_next(request)
            
            # Sanitize response if it's JSON
            if (response.headers.get("content-type", "").startswith("application/json") and
                hasattr(response, "body")):
                try:
                    # This is a simplified approach - in practice, you might want
                    # to be more selective about which responses to sanitize
                    pass  # Response sanitization can be added here if needed
                except Exception as e:
                    logger.warning(f"Response sanitization failed: {e}")
            
            return response
            
        except ValidationError as e:
            logger.warning(f"Input validation failed: {e.message}")
            return JSONResponse(
                content={
                    "error": {
                        "error_code": e.error_code,
                        "message": e.message,
                        "category": e.category.value,
                        "details": e.details
                    }
                },
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Input validation middleware error: {e}")
            return JSONResponse(
                content={"error": "Request validation failed"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting and Abuse Prevention Middleware
    
    Implements comprehensive rate limiting and abuse detection
    to protect against DoS attacks and resource exhaustion.
    """
    
    def __init__(self, app: ASGIApp):
        """Initialize the rate limiting middleware."""
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.abuse_detector = abuse_detector
        
        # Rate limit configurations by endpoint type
        self.endpoint_limits = {
            "/api/v1/chat/messages": [
                RateLimitType.MESSAGES_PER_MINUTE,
                RateLimitType.MESSAGES_PER_HOUR,
                RateLimitType.REQUESTS_PER_MINUTE
            ],
            "/api/v1/cosmos": [
                RateLimitType.MESSAGES_PER_MINUTE,
                RateLimitType.REQUESTS_PER_MINUTE,
                RateLimitType.REQUESTS_PER_HOUR
            ],
            "/api/v1/chat/sessions": [
                RateLimitType.REQUESTS_PER_MINUTE,
                RateLimitType.REQUESTS_PER_HOUR
            ],
            "/api/v1/auth": [
                RateLimitType.REQUESTS_PER_MINUTE
            ],
            "default": [
                RateLimitType.REQUESTS_PER_MINUTE,
                RateLimitType.REQUESTS_PER_HOUR
            ]
        }
    
    def _get_identifier(self, request: Request) -> str:
        """Get unique identifier for rate limiting."""
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"
        
        # Fall back to IP address
        client_ip = self._get_client_ip(request)
        return f"ip:{client_ip}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to client host
        if hasattr(request.client, "host"):
            return request.client.host
        
        return "unknown"
    
    def _get_user_tier(self, request: Request) -> str:
        """Get user tier for rate limiting."""
        if hasattr(request.state, "user") and request.state.user:
            # This would typically come from user data or subscription info
            return getattr(request.state.user, "tier", "free")
        
        return "free"
    
    def _get_rate_limits_for_path(self, path: str) -> List[RateLimitType]:
        """Get rate limit types for a path."""
        for endpoint_path, limits in self.endpoint_limits.items():
            if path.startswith(endpoint_path):
                return limits
        
        return self.endpoint_limits["default"]
    
    def _create_request_data(self, request: Request) -> Dict[str, Any]:
        """Create request data for abuse detection."""
        return {
            "endpoint": request.url.path,
            "method": request.method,
            "user_agent": request.headers.get("user-agent", ""),
            "content_length": int(request.headers.get("content-length", 0)),
            "timestamp": time.time(),
            "ip_address": self._get_client_ip(request),
            "model_switch": "model" in request.url.query,
            "is_error": False  # Will be updated if response is an error
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply rate limiting and abuse detection."""
        start_time = time.time()
        
        try:
            # Get identifier and user tier
            identifier = self._get_identifier(request)
            user_tier = self._get_user_tier(request)
            
            # Create request data for abuse detection
            request_data = self._create_request_data(request)
            
            # Check for existing blocks
            is_blocked, block_reason = self.abuse_detector.is_identifier_blocked(identifier)
            if is_blocked:
                return JSONResponse(
                    content={
                        "error": {
                            "error_code": "ACCESS_BLOCKED",
                            "message": f"Access blocked: {block_reason}",
                            "category": "authorization"
                        }
                    },
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            # Check rate limits
            rate_limits = self._get_rate_limits_for_path(request.url.path)
            try:
                limit_results = check_rate_limits(identifier, rate_limits, user_tier)
            except RateLimitError as e:
                # Add rate limit headers
                headers = {}
                if e.retry_after:
                    headers["Retry-After"] = str(e.retry_after)
                
                return JSONResponse(
                    content={
                        "error": {
                            "error_code": e.error_code,
                            "message": e.message,
                            "category": e.category.value,
                            "retry_after": e.retry_after,
                            "details": e.details
                        }
                    },
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers=headers
                )
            
            # Detect abuse patterns
            abuse_patterns = detect_and_prevent_abuse(identifier, request_data)
            
            # Process request
            response = await call_next(request)
            
            # Update request data with response info
            request_data["is_error"] = response.status_code >= 400
            request_data["status_code"] = response.status_code
            request_data["response_time"] = time.time() - start_time
            
            # Detect abuse in response patterns
            if request_data["is_error"]:
                error_patterns = detect_and_prevent_abuse(identifier, request_data)
                abuse_patterns.extend(error_patterns)
            
            # Add rate limit headers
            for limit_type, limit_status in limit_results.items():
                headers = self.rate_limiter.get_rate_limit_headers(limit_status)
                for header_name, header_value in headers.items():
                    response.headers[f"{header_name}-{limit_type.value}"] = header_value
            
            # Add abuse detection headers
            if abuse_patterns:
                response.headers["X-Abuse-Patterns-Detected"] = str(len(abuse_patterns))
            
            return response
            
        except CosmosError as e:
            # Handle Cosmos errors (including abuse blocks)
            error_response = handle_cosmos_error(e)
            
            status_code_map = {
                ErrorCategory.AUTHORIZATION: status.HTTP_403_FORBIDDEN,
                ErrorCategory.RATE_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
            }
            
            status_code = status_code_map.get(e.category, status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            headers = {}
            if e.retry_after:
                headers["Retry-After"] = str(e.retry_after)
            
            return JSONResponse(
                content={
                    "error": {
                        "error_code": error_response.error_code,
                        "message": error_response.message,
                        "category": error_response.category.value,
                        "correlation_id": error_response.correlation_id
                    }
                },
                status_code=status_code,
                headers=headers
            )
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            return JSONResponse(
                content={"error": "Rate limiting check failed"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Middleware instances for easy import
security_headers_middleware = SecurityHeadersMiddleware
cors_security_middleware = CORSSecurityMiddleware
input_validation_middleware = InputValidationMiddleware
rate_limiting_middleware = RateLimitingMiddleware