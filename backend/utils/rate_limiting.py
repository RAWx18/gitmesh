"""
Advanced Rate Limiting and Abuse Prevention System

Provides comprehensive rate limiting, abuse detection, and prevention
mechanisms for the Cosmos Web Chat Integration.
"""

import time
import json
import logging
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import redis
from collections import defaultdict, deque

from utils.error_handling import RateLimitError, CosmosError, ErrorCategory, ErrorSeverity
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimitType(str, Enum):
    """Types of rate limits."""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    REQUESTS_PER_DAY = "requests_per_day"
    MESSAGES_PER_MINUTE = "messages_per_minute"
    MESSAGES_PER_HOUR = "messages_per_hour"
    CONTEXT_FILES_PER_HOUR = "context_files_per_hour"
    REPOSITORY_FETCHES_PER_DAY = "repository_fetches_per_day"
    MODEL_SWITCHES_PER_HOUR = "model_switches_per_hour"


class AbuseType(str, Enum):
    """Types of abuse patterns."""
    RAPID_REQUESTS = "rapid_requests"
    LARGE_PAYLOADS = "large_payloads"
    REPEATED_ERRORS = "repeated_errors"
    SUSPICIOUS_PATTERNS = "suspicious_patterns"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""
    limit_type: RateLimitType
    max_requests: int
    window_seconds: int
    burst_allowance: int = 0  # Additional requests allowed in burst
    tier_multipliers: Dict[str, float] = None  # Multipliers for different tiers
    
    def __post_init__(self):
        if self.tier_multipliers is None:
            self.tier_multipliers = {
                "free": 1.0,
                "pro": 3.0,
                "enterprise": 10.0
            }


@dataclass
class RateLimitStatus:
    """Current rate limit status."""
    limit_type: RateLimitType
    max_requests: int
    current_count: int
    remaining: int
    reset_time: datetime
    is_limited: bool
    retry_after: Optional[int] = None


@dataclass
class AbusePattern:
    """Detected abuse pattern."""
    abuse_type: AbuseType
    severity: int  # 1-10 scale
    description: str
    first_detected: datetime
    last_detected: datetime
    occurrence_count: int
    evidence: Dict[str, Any]


class RateLimiter:
    """
    Advanced rate limiter with Redis backend and abuse detection.
    
    Supports multiple rate limit types, tier-based limits, burst allowances,
    and sophisticated abuse pattern detection.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the rate limiter."""
        self.redis_client = redis_client
        self.memory_store = defaultdict(lambda: defaultdict(deque))
        
        # Default rate limit rules
        self.default_rules = {
            RateLimitType.REQUESTS_PER_MINUTE: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_MINUTE,
                max_requests=60,
                window_seconds=60,
                burst_allowance=10
            ),
            RateLimitType.REQUESTS_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_HOUR,
                max_requests=1000,
                window_seconds=3600,
                burst_allowance=50
            ),
            RateLimitType.REQUESTS_PER_DAY: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_DAY,
                max_requests=10000,
                window_seconds=86400,
                burst_allowance=100
            ),
            RateLimitType.MESSAGES_PER_MINUTE: RateLimitRule(
                limit_type=RateLimitType.MESSAGES_PER_MINUTE,
                max_requests=10,
                window_seconds=60,
                burst_allowance=2
            ),
            RateLimitType.MESSAGES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.MESSAGES_PER_HOUR,
                max_requests=100,
                window_seconds=3600,
                burst_allowance=10
            ),
            RateLimitType.CONTEXT_FILES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.CONTEXT_FILES_PER_HOUR,
                max_requests=500,
                window_seconds=3600,
                burst_allowance=20
            ),
            RateLimitType.REPOSITORY_FETCHES_PER_DAY: RateLimitRule(
                limit_type=RateLimitType.REPOSITORY_FETCHES_PER_DAY,
                max_requests=50,
                window_seconds=86400,
                burst_allowance=5
            ),
            RateLimitType.MODEL_SWITCHES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.MODEL_SWITCHES_PER_HOUR,
                max_requests=20,
                window_seconds=3600,
                burst_allowance=5
            )
        }
        
        # Abuse detection thresholds
        self.abuse_thresholds = {
            AbuseType.RAPID_REQUESTS: {
                "requests_per_second": 10,
                "window_seconds": 10,
                "severity": 7
            },
            AbuseType.LARGE_PAYLOADS: {
                "max_payload_size": 5 * 1024 * 1024,  # 5MB
                "frequency_threshold": 5,
                "severity": 6
            },
            AbuseType.REPEATED_ERRORS: {
                "error_count": 20,
                "window_seconds": 300,  # 5 minutes
                "severity": 5
            },
            AbuseType.SUSPICIOUS_PATTERNS: {
                "pattern_threshold": 10,
                "severity": 8
            },
            AbuseType.RESOURCE_EXHAUSTION: {
                "resource_threshold": 0.9,  # 90% resource usage
                "severity": 9
            }
        }
    
    def check_rate_limit(
        self,
        identifier: str,
        limit_type: RateLimitType,
        user_tier: str = "free",
        increment: bool = True
    ) -> RateLimitStatus:
        """
        Check if an identifier is within rate limits.
        
        Args:
            identifier: Unique identifier (user ID, IP, etc.)
            limit_type: Type of rate limit to check
            user_tier: User tier for tier-based limits
            increment: Whether to increment the counter
            
        Returns:
            RateLimitStatus with current limit information
        """
        rule = self.default_rules.get(limit_type)
        if not rule:
            # No rule defined, allow request
            return RateLimitStatus(
                limit_type=limit_type,
                max_requests=float('inf'),
                current_count=0,
                remaining=float('inf'),
                reset_time=datetime.now() + timedelta(hours=1),
                is_limited=False
            )
        
        # Apply tier multiplier
        tier_multiplier = rule.tier_multipliers.get(user_tier, 1.0)
        effective_limit = int(rule.max_requests * tier_multiplier)
        effective_burst = int(rule.burst_allowance * tier_multiplier)
        
        # Get current count and check limit
        current_count = self._get_current_count(identifier, limit_type, rule.window_seconds)
        
        # Calculate reset time
        reset_time = datetime.now() + timedelta(seconds=rule.window_seconds)
        
        # Check if over limit (including burst allowance)
        total_allowed = effective_limit + effective_burst
        is_limited = current_count >= total_allowed
        
        # Increment counter if requested and not limited
        if increment and not is_limited:
            self._increment_counter(identifier, limit_type, rule.window_seconds)
            current_count += 1
        
        # Calculate retry after for limited requests
        retry_after = None
        if is_limited:
            retry_after = self._calculate_retry_after(identifier, limit_type, rule.window_seconds)
        
        return RateLimitStatus(
            limit_type=limit_type,
            max_requests=effective_limit,
            current_count=current_count,
            remaining=max(0, total_allowed - current_count),
            reset_time=reset_time,
            is_limited=is_limited,
            retry_after=retry_after
        )
    
    def check_multiple_limits(
        self,
        identifier: str,
        limit_types: List[RateLimitType],
        user_tier: str = "free",
        increment: bool = True
    ) -> Dict[RateLimitType, RateLimitStatus]:
        """
        Check multiple rate limits for an identifier.
        
        Args:
            identifier: Unique identifier
            limit_types: List of rate limit types to check
            user_tier: User tier for tier-based limits
            increment: Whether to increment counters
            
        Returns:
            Dictionary mapping limit types to their status
        """
        results = {}
        any_limited = False
        
        # Check all limits first without incrementing
        for limit_type in limit_types:
            status = self.check_rate_limit(identifier, limit_type, user_tier, increment=False)
            results[limit_type] = status
            if status.is_limited:
                any_limited = True
        
        # Only increment if no limits are exceeded and increment is requested
        if increment and not any_limited:
            for limit_type in limit_types:
                self.check_rate_limit(identifier, limit_type, user_tier, increment=True)
                # Update the status with incremented count
                results[limit_type] = self.check_rate_limit(identifier, limit_type, user_tier, increment=False)
        
        return results
    
    def _get_current_count(self, identifier: str, limit_type: RateLimitType, window_seconds: int) -> int:
        """Get current request count for the time window."""
        if self.redis_client:
            return self._get_redis_count(identifier, limit_type, window_seconds)
        else:
            return self._get_memory_count(identifier, limit_type, window_seconds)
    
    def _increment_counter(self, identifier: str, limit_type: RateLimitType, window_seconds: int):
        """Increment the request counter."""
        if self.redis_client:
            self._increment_redis_counter(identifier, limit_type, window_seconds)
        else:
            self._increment_memory_counter(identifier, limit_type, window_seconds)
    
    def _get_redis_count(self, identifier: str, limit_type: RateLimitType, window_seconds: int) -> int:
        """Get count from Redis using sliding window."""
        key = f"rate_limit:{identifier}:{limit_type.value}"
        now = time.time()
        window_start = now - window_seconds
        
        try:
            # Remove old entries and count current entries
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.expire(key, window_seconds + 60)  # Extra TTL for cleanup
            results = pipe.execute()
            
            return results[1] if len(results) > 1 else 0
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            return 0
    
    def _increment_redis_counter(self, identifier: str, limit_type: RateLimitType, window_seconds: int):
        """Increment Redis counter using sorted set."""
        key = f"rate_limit:{identifier}:{limit_type.value}"
        now = time.time()
        
        try:
            pipe = self.redis_client.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds + 60)
            pipe.execute()
        except Exception as e:
            logger.error(f"Redis rate limit increment failed: {e}")
    
    def _get_memory_count(self, identifier: str, limit_type: RateLimitType, window_seconds: int) -> int:
        """Get count from memory store."""
        now = time.time()
        window_start = now - window_seconds
        
        # Clean old entries
        timestamps = self.memory_store[identifier][limit_type.value]
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()
        
        return len(timestamps)
    
    def _increment_memory_counter(self, identifier: str, limit_type: RateLimitType, window_seconds: int):
        """Increment memory counter."""
        now = time.time()
        self.memory_store[identifier][limit_type.value].append(now)
    
    def _calculate_retry_after(self, identifier: str, limit_type: RateLimitType, window_seconds: int) -> int:
        """Calculate retry after time in seconds."""
        if self.redis_client:
            key = f"rate_limit:{identifier}:{limit_type.value}"
            try:
                # Get the oldest entry in the current window
                oldest_entries = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_entries:
                    oldest_time = oldest_entries[0][1]
                    retry_after = int(oldest_time + window_seconds - time.time())
                    return max(1, retry_after)
            except Exception as e:
                logger.error(f"Error calculating retry after: {e}")
        
        # Fallback to window size
        return window_seconds
    
    def get_rate_limit_headers(self, status: RateLimitStatus) -> Dict[str, str]:
        """Get HTTP headers for rate limit information."""
        headers = {
            "X-RateLimit-Limit": str(status.max_requests),
            "X-RateLimit-Remaining": str(status.remaining),
            "X-RateLimit-Reset": str(int(status.reset_time.timestamp())),
            "X-RateLimit-Type": status.limit_type.value
        }
        
        if status.retry_after:
            headers["Retry-After"] = str(status.retry_after)
        
        return headers


class AbuseDetector:
    """
    Sophisticated abuse detection system.
    
    Monitors request patterns, payload sizes, error rates, and other
    indicators to detect and prevent abuse.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the abuse detector."""
        self.redis_client = redis_client
        self.memory_patterns = defaultdict(list)
        
        # Abuse detection thresholds
        self.abuse_thresholds = {
            AbuseType.RAPID_REQUESTS: {
                "requests_per_second": 10,
                "window_seconds": 10,
                "severity": 7
            },
            AbuseType.LARGE_PAYLOADS: {
                "max_payload_size": 5 * 1024 * 1024,  # 5MB
                "frequency_threshold": 5,
                "severity": 6
            },
            AbuseType.REPEATED_ERRORS: {
                "error_count": 20,
                "window_seconds": 300,  # 5 minutes
                "severity": 5
            },
            AbuseType.SUSPICIOUS_PATTERNS: {
                "pattern_threshold": 10,
                "severity": 8
            },
            AbuseType.RESOURCE_EXHAUSTION: {
                "resource_threshold": 0.9,  # 90% resource usage
                "severity": 9
            }
        }
        
        # Pattern detection windows
        self.detection_windows = {
            AbuseType.RAPID_REQUESTS: 60,  # 1 minute
            AbuseType.LARGE_PAYLOADS: 300,  # 5 minutes
            AbuseType.REPEATED_ERRORS: 300,  # 5 minutes
            AbuseType.SUSPICIOUS_PATTERNS: 600,  # 10 minutes
            AbuseType.RESOURCE_EXHAUSTION: 120  # 2 minutes
        }
    
    def detect_abuse(
        self,
        identifier: str,
        request_data: Dict[str, Any]
    ) -> List[AbusePattern]:
        """
        Detect abuse patterns for a request.
        
        Args:
            identifier: Unique identifier for the requester
            request_data: Request information for analysis
            
        Returns:
            List of detected abuse patterns
        """
        detected_patterns = []
        
        # Check for rapid requests
        rapid_pattern = self._detect_rapid_requests(identifier, request_data)
        if rapid_pattern:
            detected_patterns.append(rapid_pattern)
        
        # Check for large payloads
        payload_pattern = self._detect_large_payloads(identifier, request_data)
        if payload_pattern:
            detected_patterns.append(payload_pattern)
        
        # Check for repeated errors
        error_pattern = self._detect_repeated_errors(identifier, request_data)
        if error_pattern:
            detected_patterns.append(error_pattern)
        
        # Check for suspicious patterns
        suspicious_pattern = self._detect_suspicious_patterns(identifier, request_data)
        if suspicious_pattern:
            detected_patterns.append(suspicious_pattern)
        
        # Store patterns for future analysis
        if detected_patterns:
            self._store_abuse_patterns(identifier, detected_patterns)
        
        return detected_patterns
    
    def _detect_rapid_requests(self, identifier: str, request_data: Dict[str, Any]) -> Optional[AbusePattern]:
        """Detect rapid request patterns."""
        threshold = self.abuse_thresholds[AbuseType.RAPID_REQUESTS]
        window = self.detection_windows[AbuseType.RAPID_REQUESTS]
        
        # Track request timestamps
        now = time.time()
        key = f"rapid_requests:{identifier}"
        
        if self.redis_client:
            try:
                # Add current request and clean old ones
                pipe = self.redis_client.pipeline()
                pipe.zadd(key, {str(now): now})
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zcard(key)
                pipe.expire(key, window + 60)
                results = pipe.execute()
                
                request_count = results[2] if len(results) > 2 else 0
            except Exception as e:
                logger.error(f"Redis abuse detection failed: {e}")
                return None
        else:
            # Use memory store
            if key not in self.memory_patterns:
                self.memory_patterns[key] = []
            
            # Clean old entries
            self.memory_patterns[key] = [
                ts for ts in self.memory_patterns[key] 
                if ts > now - window
            ]
            
            # Add current request
            self.memory_patterns[key].append(now)
            request_count = len(self.memory_patterns[key])
        
        # Check if threshold exceeded
        requests_per_second = request_count / window
        if requests_per_second > threshold["requests_per_second"]:
            return AbusePattern(
                abuse_type=AbuseType.RAPID_REQUESTS,
                severity=threshold["severity"],
                description=f"Rapid requests detected: {requests_per_second:.2f} req/sec",
                first_detected=datetime.now(),
                last_detected=datetime.now(),
                occurrence_count=1,
                evidence={
                    "requests_per_second": requests_per_second,
                    "window_seconds": window,
                    "total_requests": request_count
                }
            )
        
        return None
    
    def _detect_large_payloads(self, identifier: str, request_data: Dict[str, Any]) -> Optional[AbusePattern]:
        """Detect large payload abuse."""
        threshold = self.abuse_thresholds[AbuseType.LARGE_PAYLOADS]
        payload_size = request_data.get("content_length", 0)
        
        if payload_size > threshold["max_payload_size"]:
            return AbusePattern(
                abuse_type=AbuseType.LARGE_PAYLOADS,
                severity=threshold["severity"],
                description=f"Large payload detected: {payload_size} bytes",
                first_detected=datetime.now(),
                last_detected=datetime.now(),
                occurrence_count=1,
                evidence={
                    "payload_size": payload_size,
                    "max_allowed": threshold["max_payload_size"],
                    "endpoint": request_data.get("endpoint", "unknown")
                }
            )
        
        return None
    
    def _detect_repeated_errors(self, identifier: str, request_data: Dict[str, Any]) -> Optional[AbusePattern]:
        """Detect repeated error patterns."""
        threshold = self.abuse_thresholds[AbuseType.REPEATED_ERRORS]
        window = self.detection_windows[AbuseType.REPEATED_ERRORS]
        
        # Only check if this is an error response
        if not request_data.get("is_error", False):
            return None
        
        now = time.time()
        key = f"error_count:{identifier}"
        
        if self.redis_client:
            try:
                pipe = self.redis_client.pipeline()
                pipe.zadd(key, {str(now): now})
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zcard(key)
                pipe.expire(key, window + 60)
                results = pipe.execute()
                
                error_count = results[2] if len(results) > 2 else 0
            except Exception as e:
                logger.error(f"Redis error detection failed: {e}")
                return None
        else:
            if key not in self.memory_patterns:
                self.memory_patterns[key] = []
            
            self.memory_patterns[key] = [
                ts for ts in self.memory_patterns[key] 
                if ts > now - window
            ]
            self.memory_patterns[key].append(now)
            error_count = len(self.memory_patterns[key])
        
        if error_count > threshold["error_count"]:
            return AbusePattern(
                abuse_type=AbuseType.REPEATED_ERRORS,
                severity=threshold["severity"],
                description=f"Repeated errors detected: {error_count} errors in {window}s",
                first_detected=datetime.now(),
                last_detected=datetime.now(),
                occurrence_count=1,
                evidence={
                    "error_count": error_count,
                    "window_seconds": window,
                    "error_type": request_data.get("error_type", "unknown")
                }
            )
        
        return None
    
    def _detect_suspicious_patterns(self, identifier: str, request_data: Dict[str, Any]) -> Optional[AbusePattern]:
        """Detect suspicious request patterns."""
        suspicious_indicators = []
        
        # Check for suspicious user agents
        user_agent = request_data.get("user_agent", "").lower()
        suspicious_agents = ["bot", "crawler", "scraper", "automated", "script"]
        if any(agent in user_agent for agent in suspicious_agents):
            suspicious_indicators.append("suspicious_user_agent")
        
        # Check for unusual request patterns
        endpoint = request_data.get("endpoint", "")
        if endpoint.count("/") > 10:  # Unusually deep endpoint
            suspicious_indicators.append("deep_endpoint")
        
        # Check for path traversal in endpoint
        if ".." in endpoint or "etc/passwd" in endpoint:
            suspicious_indicators.append("path_traversal_attempt")
        
        # Check for rapid model switching
        if request_data.get("model_switch", False):
            key = f"model_switches:{identifier}"
            now = time.time()
            window = 300  # 5 minutes
            
            if self.redis_client:
                try:
                    pipe = self.redis_client.pipeline()
                    pipe.zadd(key, {str(now): now})
                    pipe.zremrangebyscore(key, 0, now - window)
                    pipe.zcard(key)
                    pipe.expire(key, window + 60)
                    results = pipe.execute()
                    
                    switch_count = results[2] if len(results) > 2 else 0
                    if switch_count > 10:  # More than 10 switches in 5 minutes
                        suspicious_indicators.append("rapid_model_switching")
                except Exception:
                    pass
        
        if len(suspicious_indicators) >= 2:  # Multiple indicators
            threshold = self.abuse_thresholds[AbuseType.SUSPICIOUS_PATTERNS]
            return AbusePattern(
                abuse_type=AbuseType.SUSPICIOUS_PATTERNS,
                severity=threshold["severity"],
                description=f"Suspicious patterns detected: {', '.join(suspicious_indicators)}",
                first_detected=datetime.now(),
                last_detected=datetime.now(),
                occurrence_count=1,
                evidence={
                    "indicators": suspicious_indicators,
                    "user_agent": user_agent,
                    "endpoint": endpoint
                }
            )
        
        return None
    
    def _store_abuse_patterns(self, identifier: str, patterns: List[AbusePattern]):
        """Store detected abuse patterns for analysis."""
        if not self.redis_client:
            return
        
        try:
            for pattern in patterns:
                key = f"abuse_pattern:{identifier}:{pattern.abuse_type.value}"
                data = asdict(pattern)
                
                # Convert datetime objects to strings
                data["first_detected"] = pattern.first_detected.isoformat()
                data["last_detected"] = pattern.last_detected.isoformat()
                
                self.redis_client.setex(
                    key,
                    86400,  # 24 hours
                    json.dumps(data, default=str)
                )
                
                # Add to abuse index
                abuse_index_key = f"abuse_index:{datetime.now().strftime('%Y-%m-%d')}"
                self.redis_client.lpush(abuse_index_key, key)
                self.redis_client.expire(abuse_index_key, 604800)  # 7 days
                
        except Exception as e:
            logger.error(f"Failed to store abuse patterns: {e}")
    
    def is_identifier_blocked(self, identifier: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an identifier is blocked due to abuse.
        
        Args:
            identifier: Identifier to check
            
        Returns:
            Tuple of (is_blocked, reason)
        """
        if not self.redis_client:
            return False, None
        
        try:
            # Check for active blocks
            block_key = f"blocked:{identifier}"
            block_data = self.redis_client.get(block_key)
            
            if block_data:
                block_info = json.loads(block_data)
                return True, block_info.get("reason", "Blocked due to abuse")
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking block status: {e}")
            return False, None
    
    def block_identifier(
        self,
        identifier: str,
        reason: str,
        duration_seconds: int = 3600,
        severity: int = 5
    ):
        """
        Block an identifier due to abuse.
        
        Args:
            identifier: Identifier to block
            reason: Reason for blocking
            duration_seconds: Block duration in seconds
            severity: Severity level (1-10)
        """
        if not self.redis_client:
            return
        
        try:
            block_data = {
                "reason": reason,
                "blocked_at": datetime.now().isoformat(),
                "duration_seconds": duration_seconds,
                "severity": severity,
                "expires_at": (datetime.now() + timedelta(seconds=duration_seconds)).isoformat()
            }
            
            block_key = f"blocked:{identifier}"
            self.redis_client.setex(
                block_key,
                duration_seconds,
                json.dumps(block_data)
            )
            
            logger.warning(f"Blocked identifier {identifier}: {reason} (duration: {duration_seconds}s)")
            
        except Exception as e:
            logger.error(f"Failed to block identifier: {e}")


# Global instances
rate_limiter = RateLimiter()
abuse_detector = AbuseDetector()


def check_rate_limits(
    identifier: str,
    limit_types: List[RateLimitType],
    user_tier: str = "free"
) -> Dict[RateLimitType, RateLimitStatus]:
    """
    Convenience function to check multiple rate limits.
    
    Args:
        identifier: Unique identifier
        limit_types: List of rate limit types to check
        user_tier: User tier for tier-based limits
        
    Returns:
        Dictionary mapping limit types to their status
        
    Raises:
        RateLimitError: If any rate limit is exceeded
    """
    results = rate_limiter.check_multiple_limits(identifier, limit_types, user_tier)
    
    # Check if any limits are exceeded
    for limit_type, status in results.items():
        if status.is_limited:
            raise RateLimitError(
                message=f"Rate limit exceeded for {limit_type.value}",
                retry_after=status.retry_after or 60,
                tier=user_tier,
                details={
                    "limit_type": limit_type.value,
                    "max_requests": status.max_requests,
                    "current_count": status.current_count,
                    "reset_time": status.reset_time.isoformat()
                }
            )
    
    return results


def detect_and_prevent_abuse(
    identifier: str,
    request_data: Dict[str, Any]
) -> List[AbusePattern]:
    """
    Convenience function to detect abuse and apply prevention measures.
    
    Args:
        identifier: Unique identifier
        request_data: Request information for analysis
        
    Returns:
        List of detected abuse patterns
        
    Raises:
        CosmosError: If identifier is blocked or severe abuse is detected
    """
    # Check if identifier is already blocked
    is_blocked, block_reason = abuse_detector.is_identifier_blocked(identifier)
    if is_blocked:
        raise CosmosError(
            message=f"Access blocked: {block_reason}",
            error_code="ACCESS_BLOCKED",
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.HIGH,
            details={"block_reason": block_reason}
        )
    
    # Detect abuse patterns
    patterns = abuse_detector.detect_abuse(identifier, request_data)
    
    # Apply automatic blocking for severe patterns
    for pattern in patterns:
        if pattern.severity >= 8:  # High severity
            duration = 3600 * pattern.severity  # 1 hour per severity point
            abuse_detector.block_identifier(
                identifier,
                f"Automatic block: {pattern.description}",
                duration,
                pattern.severity
            )
            
            raise CosmosError(
                message=f"Access blocked due to abuse: {pattern.description}",
                error_code="ABUSE_DETECTED",
                category=ErrorCategory.AUTHORIZATION,
                severity=ErrorSeverity.HIGH,
                details={
                    "abuse_type": pattern.abuse_type.value,
                    "severity": pattern.severity,
                    "block_duration": duration
                }
            )
    
    return patterns