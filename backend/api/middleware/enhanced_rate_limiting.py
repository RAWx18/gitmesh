"""
Enhanced Rate Limiting Middleware with Supabase Integration
Provides comprehensive rate limiting with persistent storage and analytics
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import structlog

from utils.rate_limiting import RateLimiter, RateLimitType, check_rate_limits
from services.supabase_service import supabase_service
from utils.error_handling import RateLimitError

logger = structlog.get_logger(__name__)


class EnhancedRateLimitingMiddleware:
    """Enhanced rate limiting middleware with Supabase persistence."""
    
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.github_endpoints = {
            '/api/v1/github/repositories': [RateLimitType.REQUESTS_PER_MINUTE, RateLimitType.REQUESTS_PER_HOUR],
            '/api/v1/github/search': [RateLimitType.REQUESTS_PER_MINUTE],
            '/api/v1/github/activity': [RateLimitType.REQUESTS_PER_MINUTE],
            '/api/v1/github/starred': [RateLimitType.REQUESTS_PER_MINUTE],
            '/api/v1/github/trending': [RateLimitType.REQUESTS_PER_MINUTE],
        }
        
        # Rate limits per endpoint (requests per minute)
        self.endpoint_limits = {
            '/api/v1/github/repositories': 60,
            '/api/v1/github/search': 30,
            '/api/v1/github/activity': 30,
            '/api/v1/github/starred': 30,
            '/api/v1/github/trending': 20,
            '/api/v1/github/users': 40,
            '/api/v1/github/rate-limit': 10,
        }
    
    async def __call__(self, request: Request, call_next):
        """Process request with enhanced rate limiting."""
        start_time = time.time()
        
        try:
            # Extract user identifier
            user_id = await self._get_user_identifier(request)
            endpoint = self._normalize_endpoint(request.url.path)
            
            # Check if this endpoint needs rate limiting
            if not self._should_rate_limit(endpoint):
                response = await call_next(request)
                return response
            
            # Get user tier for tier-based limits
            user_tier = await self._get_user_tier(request)
            
            # Check rate limits
            await self._check_enhanced_rate_limits(user_id, endpoint, user_tier, request)
            
            # Process the request
            response = await call_next(request)
            
            # Record successful request
            await self._record_successful_request(
                user_id, endpoint, request.method, 
                response.status_code, int((time.time() - start_time) * 1000)
            )
            
            # Add rate limit headers
            self._add_rate_limit_headers(response, user_id, endpoint, user_tier)
            
            return response
            
        except RateLimitError as e:
            # Handle rate limit exceeded
            return await self._handle_rate_limit_exceeded(e, request, user_id, endpoint)
            
        except HTTPException as e:
            # Record failed request
            if 'user_id' in locals() and 'endpoint' in locals():
                await self._record_failed_request(
                    user_id, endpoint, request.method, 
                    e.status_code, int((time.time() - start_time) * 1000)
                )
            raise
            
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # Continue with request on middleware error
            return await call_next(request)
    
    async def _get_user_identifier(self, request: Request) -> str:
        """Get user identifier from request."""
        # Try to get user ID from JWT token
        if hasattr(request.state, 'user') and request.state.user:
            return str(request.state.user.get('id', request.state.user.get('login', 'anonymous')))
        
        # Try to get from authorization header
        auth_header = request.headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            # Use a hash of the token as identifier
            import hashlib
            token_hash = hashlib.md5(auth_header.encode()).hexdigest()[:16]
            return f"token_{token_hash}"
        
        # Fallback to IP address
        client_ip = request.client.host if request.client else 'unknown'
        forwarded_for = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        return forwarded_for or client_ip or 'anonymous'
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for rate limiting."""
        # Remove query parameters
        path = path.split('?')[0]
        
        # Normalize dynamic segments
        path_parts = path.split('/')
        normalized_parts = []
        
        for part in path_parts:
            if part and part not in ['api', 'v1']:
                # Replace dynamic segments with placeholders
                if part.isdigit() or len(part) > 20:
                    normalized_parts.append('{id}')
                else:
                    normalized_parts.append(part)
        
        return '/' + '/'.join(['api', 'v1'] + normalized_parts)
    
    def _should_rate_limit(self, endpoint: str) -> bool:
        """Check if endpoint should be rate limited."""
        # Rate limit GitHub API endpoints
        if '/github/' in endpoint:
            return True
        
        # Rate limit other sensitive endpoints
        sensitive_endpoints = ['/auth/', '/chat/', '/upload/']
        return any(sensitive in endpoint for sensitive in sensitive_endpoints)
    
    async def _get_user_tier(self, request: Request) -> str:
        """Get user tier from request."""
        if hasattr(request.state, 'user_tier'):
            return request.state.user_tier
        
        # Default to free tier
        return 'free'
    
    async def _check_enhanced_rate_limits(
        self, 
        user_id: str, 
        endpoint: str, 
        user_tier: str, 
        request: Request
    ):
        """Check rate limits with Supabase persistence."""
        try:
            # Check local rate limits first
            limit_types = self.github_endpoints.get(endpoint, [RateLimitType.REQUESTS_PER_MINUTE])
            local_results = check_rate_limits(user_id, limit_types, user_tier)
            
            # Check Supabase rate limits
            await self._check_supabase_rate_limits(user_id, endpoint)
            
            # Record the request in Supabase
            await supabase_service.record_rate_limit(user_id, endpoint)
            
        except RateLimitError as e:
            # Block user in Supabase if severe rate limiting
            if e.details and e.details.get('current_count', 0) > 100:
                await supabase_service.block_user_endpoint(user_id, endpoint, 60)
            
            # Record analytics event
            await supabase_service.record_user_event(
                user_id, 
                'rate_limit_exceeded',
                {
                    'endpoint': endpoint,
                    'tier': user_tier,
                    'details': e.details
                },
                self._get_client_ip(request),
                request.headers.get('user-agent')
            )
            
            raise
    
    async def _check_supabase_rate_limits(self, user_id: str, endpoint: str):
        """Check rate limits stored in Supabase."""
        rate_limit_record = await supabase_service.get_rate_limit_status(user_id, endpoint)
        
        if rate_limit_record and rate_limit_record.is_blocked:
            raise RateLimitError(
                message=f"User blocked for endpoint {endpoint}",
                retry_after=3600,  # 1 hour
                tier='unknown',
                details={
                    'endpoint': endpoint,
                    'blocked_until': rate_limit_record.window_end.isoformat(),
                    'reason': 'Excessive rate limit violations'
                }
            )
        
        # Check if user has exceeded endpoint-specific limits
        if rate_limit_record:
            endpoint_limit = self.endpoint_limits.get(endpoint, 60)
            if rate_limit_record.request_count > endpoint_limit:
                raise RateLimitError(
                    message=f"Rate limit exceeded for {endpoint}",
                    retry_after=60,
                    tier='unknown',
                    details={
                        'endpoint': endpoint,
                        'current_count': rate_limit_record.request_count,
                        'limit': endpoint_limit,
                        'reset_time': rate_limit_record.window_end.isoformat()
                    }
                )
    
    async def _record_successful_request(
        self, 
        user_id: str, 
        endpoint: str, 
        method: str, 
        status_code: int, 
        response_time_ms: int
    ):
        """Record successful request in Supabase."""
        try:
            await supabase_service.record_github_api_usage(
                user_id, endpoint, method, status_code, response_time_ms
            )
        except Exception as e:
            logger.warning(f"Failed to record successful request: {e}")
    
    async def _record_failed_request(
        self, 
        user_id: str, 
        endpoint: str, 
        method: str, 
        status_code: int, 
        response_time_ms: int
    ):
        """Record failed request in Supabase."""
        try:
            await supabase_service.record_github_api_usage(
                user_id, endpoint, method, status_code, response_time_ms
            )
            
            # Record analytics event for errors
            await supabase_service.record_user_event(
                user_id,
                'api_error',
                {
                    'endpoint': endpoint,
                    'method': method,
                    'status_code': status_code,
                    'response_time_ms': response_time_ms
                }
            )
        except Exception as e:
            logger.warning(f"Failed to record failed request: {e}")
    
    def _add_rate_limit_headers(self, response, user_id: str, endpoint: str, user_tier: str):
        """Add rate limit headers to response."""
        try:
            # Get current rate limit status
            limit_types = self.github_endpoints.get(endpoint, [RateLimitType.REQUESTS_PER_MINUTE])
            if limit_types:
                status = self.rate_limiter.check_rate_limit(
                    user_id, limit_types[0], user_tier, increment=False
                )
                
                headers = self.rate_limiter.get_rate_limit_headers(status)
                for key, value in headers.items():
                    response.headers[key] = value
                    
        except Exception as e:
            logger.warning(f"Failed to add rate limit headers: {e}")
    
    async def _handle_rate_limit_exceeded(
        self, 
        error: RateLimitError, 
        request: Request, 
        user_id: str, 
        endpoint: str
    ) -> JSONResponse:
        """Handle rate limit exceeded with proper response."""
        
        # Determine retry after time
        retry_after = error.retry_after or 60
        
        # Create detailed error response
        error_response = {
            "error": {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded for requests_per_minute",
                "category": "rate_limit",
                "retry_after": retry_after,
                "details": {
                    "limit_type": "requests_per_minute",
                    "max_requests": error.details.get('max_requests', 60) if error.details else 60,
                    "current_count": error.details.get('current_count', 0) if error.details else 0,
                    "reset_time": (datetime.utcnow() + timedelta(seconds=retry_after)).isoformat()
                }
            }
        }
        
        # Add helpful suggestions
        suggestions = [
            "Wait for the rate limit to reset",
            "Reduce request frequency",
            "Consider upgrading to a higher tier for increased limits"
        ]
        
        if error.tier == 'free':
            suggestions.append("Upgrade to Pro tier for 3x higher limits")
        
        error_response["error"]["suggestions"] = suggestions
        
        # Create response with proper headers
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_response
        )
        
        # Add rate limit headers
        response.headers["Retry-After"] = str(retry_after)
        response.headers["X-RateLimit-Limit"] = str(error.details.get('max_requests', 60) if error.details else 60)
        response.headers["X-RateLimit-Remaining"] = "0"
        response.headers["X-RateLimit-Reset"] = str(int((datetime.utcnow() + timedelta(seconds=retry_after)).timestamp()))
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        return forwarded_for or (request.client.host if request.client else 'unknown')


# Global middleware instance
enhanced_rate_limiting_middleware = EnhancedRateLimitingMiddleware()