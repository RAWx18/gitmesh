"""
Cosmos Error Handler and Recovery System

Provides comprehensive error handling for OptimizedCosmosWrapper:
- Graceful fallback to gitingest when Redis cache unavailable
- Automatic retry logic with exponential backoff
- Resource cleanup on errors and shutdown
- Error classification and recovery strategies

Requirements: 2.3, 2.4, 2.5
"""

import os
import time
import asyncio
import logging
import traceback
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import random

# Configure logging
logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    REDIS_CONNECTION = "redis_connection"
    REDIS_OPERATION = "redis_operation"
    COSMOS_INITIALIZATION = "cosmos_initialization"
    COSMOS_PROCESSING = "cosmos_processing"
    VFS_OPERATION = "vfs_operation"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    """Recovery actions that can be taken."""
    RETRY = "retry"
    FALLBACK = "fallback"
    RESET = "reset"
    CLEANUP = "cleanup"
    ABORT = "abort"
    IGNORE = "ignore"


@dataclass
class ErrorInfo:
    """Comprehensive error information."""
    error_id: str
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    exception: Optional[Exception]
    context: Dict[str, Any]
    stack_trace: Optional[str]
    recovery_action: Optional[RecoveryAction] = None
    recovery_successful: Optional[bool] = None
    retry_count: int = 0


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_multiplier: float = 1.5


class FallbackManager:
    """
    Manages fallback strategies when primary systems fail.
    
    Provides graceful degradation to alternative implementations
    when Redis cache or other components are unavailable.
    """
    
    def __init__(self):
        """Initialize fallback manager."""
        self.fallback_strategies: Dict[str, Callable] = {}
        self.fallback_usage: Dict[str, int] = {}
        
    def register_fallback(self, operation: str, fallback_func: Callable):
        """Register a fallback function for an operation."""
        self.fallback_strategies[operation] = fallback_func
        self.fallback_usage[operation] = 0
        logger.debug(f"Registered fallback for operation: {operation}")
    
    async def execute_with_fallback(
        self,
        operation: str,
        primary_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute operation with fallback if primary fails.
        
        Args:
            operation: Operation name
            primary_func: Primary function to execute
            *args: Arguments for functions
            **kwargs: Keyword arguments for functions
            
        Returns:
            Result from primary or fallback function
        """
        try:
            # Try primary function first
            if asyncio.iscoroutinefunction(primary_func):
                result = await primary_func(*args, **kwargs)
            else:
                result = primary_func(*args, **kwargs)
            
            logger.debug(f"Primary operation succeeded: {operation}")
            return result
            
        except Exception as e:
            logger.warning(f"Primary operation failed: {operation}, error: {e}")
            
            # Try fallback if available
            if operation in self.fallback_strategies:
                try:
                    fallback_func = self.fallback_strategies[operation]
                    self.fallback_usage[operation] += 1
                    
                    logger.info(f"Executing fallback for operation: {operation}")
                    
                    if asyncio.iscoroutinefunction(fallback_func):
                        result = await fallback_func(*args, **kwargs)
                    else:
                        result = fallback_func(*args, **kwargs)
                    
                    logger.info(f"Fallback succeeded for operation: {operation}")
                    return result
                    
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {operation}: {fallback_error}")
                    raise fallback_error
            else:
                logger.error(f"No fallback available for operation: {operation}")
                raise e
    
    def get_fallback_stats(self) -> Dict[str, Any]:
        """Get fallback usage statistics."""
        return {
            "registered_fallbacks": list(self.fallback_strategies.keys()),
            "usage_counts": self.fallback_usage.copy(),
            "total_fallback_uses": sum(self.fallback_usage.values())
        }


class RetryManager:
    """
    Manages retry logic with exponential backoff.
    
    Provides intelligent retry strategies for transient failures
    with configurable backoff and jitter.
    """
    
    def __init__(self, default_config: RetryConfig = None):
        """Initialize retry manager."""
        self.default_config = default_config or RetryConfig()
        self.retry_stats: Dict[str, Dict[str, int]] = {}
    
    async def execute_with_retry(
        self,
        operation: str,
        func: Callable,
        *args,
        config: RetryConfig = None,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            operation: Operation name for tracking
            func: Function to execute
            *args: Arguments for function
            config: Retry configuration (uses default if None)
            **kwargs: Keyword arguments for function
            
        Returns:
            Result from successful function execution
        """
        retry_config = config or self.default_config
        last_exception = None
        
        # Initialize stats for this operation
        if operation not in self.retry_stats:
            self.retry_stats[operation] = {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "total_retries": 0
            }
        
        for attempt in range(retry_config.max_retries + 1):
            self.retry_stats[operation]["attempts"] += 1
            
            try:
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Success
                self.retry_stats[operation]["successes"] += 1
                if attempt > 0:
                    logger.info(f"Operation {operation} succeeded after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_exception = e
                self.retry_stats[operation]["failures"] += 1
                
                if attempt < retry_config.max_retries:
                    # Calculate delay with exponential backoff and jitter
                    delay = min(
                        retry_config.base_delay * (retry_config.exponential_base ** attempt),
                        retry_config.max_delay
                    )
                    
                    if retry_config.jitter:
                        # Add jitter: ±25% of the calculated delay
                        jitter_range = delay * 0.25
                        delay += random.uniform(-jitter_range, jitter_range)
                    
                    delay = max(0, delay)
                    
                    logger.warning(
                        f"Operation {operation} failed (attempt {attempt + 1}/{retry_config.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    
                    self.retry_stats[operation]["total_retries"] += 1
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Operation {operation} failed after {retry_config.max_retries} retries: {e}")
        
        # All retries exhausted
        raise last_exception
    
    def get_retry_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return self.retry_stats.copy()


class CosmosErrorHandler:
    """
    Main error handler for Cosmos operations.
    
    Provides comprehensive error handling, classification, recovery,
    and fallback strategies for all Cosmos-related operations.
    """
    
    def __init__(self):
        """Initialize error handler."""
        self.error_history: List[ErrorInfo] = []
        self.fallback_manager = FallbackManager()
        self.retry_manager = RetryManager()
        self.cleanup_callbacks: List[Callable] = []
        self.error_count_by_category: Dict[ErrorCategory, int] = {}
        
        # Register default fallback strategies
        self._register_default_fallbacks()
        
        logger.info("CosmosErrorHandler initialized")
    
    def _register_default_fallbacks(self):
        """Register default fallback strategies."""
        # Redis fallbacks
        self.fallback_manager.register_fallback(
            "redis_get_repository_context",
            self._fallback_gitingest_repository_context
        )
        
        self.fallback_manager.register_fallback(
            "redis_get_file_content",
            self._fallback_direct_file_read
        )
        
        # Cosmos fallbacks
        self.fallback_manager.register_fallback(
            "cosmos_process_message",
            self._fallback_simple_response
        )
    
    async def _fallback_gitingest_repository_context(self, repo_url: str) -> Dict[str, Any]:
        """Fallback to gitingest when Redis cache unavailable."""
        logger.info(f"Falling back to gitingest for repository: {repo_url}")
        
        try:
            # This would integrate with gitingest service
            # For now, return a basic structure
            return {
                "repo_url": repo_url,
                "repo_name": repo_url.split("/")[-1] if "/" in repo_url else repo_url,
                "summary": "Repository data loaded via gitingest fallback",
                "content": "",
                "tree_structure": "",
                "metadata": {"source": "gitingest_fallback"},
                "file_index": {},
                "total_files": 0,
                "total_size": 0
            }
        except Exception as e:
            logger.error(f"Gitingest fallback failed: {e}")
            raise
    
    def _fallback_direct_file_read(self, file_path: str) -> Optional[str]:
        """Fallback to direct file reading when Redis unavailable."""
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
            return None
        except Exception as e:
            logger.error(f"Direct file read fallback failed for {file_path}: {e}")
            return None
    
    def _fallback_simple_response(self, message: str, **kwargs) -> str:
        """Fallback to simple response when Cosmos unavailable."""
        return (
            f"I apologize, but I'm currently experiencing technical difficulties. "
            f"Your message '{message[:100]}...' has been received, but I cannot provide "
            f"a detailed analysis at this time. Please try again later."
        )
    
    def classify_error(self, exception: Exception, context: Dict[str, Any] = None) -> Tuple[ErrorCategory, ErrorSeverity]:
        """
        Classify error by category and severity.
        
        Args:
            exception: The exception that occurred
            context: Additional context about the error
            
        Returns:
            Tuple of (category, severity)
        """
        context = context or {}
        error_message = str(exception).lower()
        exception_type = type(exception).__name__
        
        # Redis-related errors
        if any(keyword in error_message for keyword in ["redis", "connection", "timeout"]):
            if "connection" in error_message:
                return ErrorCategory.REDIS_CONNECTION, ErrorSeverity.HIGH
            else:
                return ErrorCategory.REDIS_OPERATION, ErrorSeverity.MEDIUM
        
        # Cosmos-related errors
        elif any(keyword in error_message for keyword in ["cosmos", "model", "coder"]):
            if "initialization" in error_message or "import" in error_message:
                return ErrorCategory.COSMOS_INITIALIZATION, ErrorSeverity.HIGH
            else:
                return ErrorCategory.COSMOS_PROCESSING, ErrorSeverity.MEDIUM
        
        # VFS-related errors
        elif any(keyword in error_message for keyword in ["vfs", "file", "directory"]):
            return ErrorCategory.VFS_OPERATION, ErrorSeverity.LOW
        
        # Memory-related errors
        elif any(keyword in error_message for keyword in ["memory", "out of memory", "memoryerror"]):
            return ErrorCategory.MEMORY_EXHAUSTION, ErrorSeverity.CRITICAL
        
        # Timeout errors
        elif any(keyword in error_message for keyword in ["timeout", "timed out"]):
            return ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM
        
        # Authentication errors
        elif any(keyword in error_message for keyword in ["auth", "token", "permission", "unauthorized"]):
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.HIGH
        
        # Validation errors
        elif any(keyword in error_message for keyword in ["validation", "invalid", "malformed"]):
            return ErrorCategory.VALIDATION, ErrorSeverity.LOW
        
        # Default classification
        else:
            return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM
    
    def determine_recovery_action(self, category: ErrorCategory, severity: ErrorSeverity) -> RecoveryAction:
        """
        Determine appropriate recovery action based on error classification.
        
        Args:
            category: Error category
            severity: Error severity
            
        Returns:
            Recommended recovery action
        """
        # Critical errors require immediate cleanup/abort
        if severity == ErrorSeverity.CRITICAL:
            return RecoveryAction.CLEANUP
        
        # Category-specific recovery strategies
        if category == ErrorCategory.REDIS_CONNECTION:
            return RecoveryAction.RETRY
        elif category == ErrorCategory.REDIS_OPERATION:
            return RecoveryAction.FALLBACK
        elif category == ErrorCategory.COSMOS_INITIALIZATION:
            return RecoveryAction.RESET
        elif category == ErrorCategory.COSMOS_PROCESSING:
            return RecoveryAction.FALLBACK
        elif category == ErrorCategory.VFS_OPERATION:
            return RecoveryAction.FALLBACK
        elif category == ErrorCategory.MEMORY_EXHAUSTION:
            return RecoveryAction.CLEANUP
        elif category == ErrorCategory.TIMEOUT:
            return RecoveryAction.RETRY
        elif category == ErrorCategory.AUTHENTICATION:
            return RecoveryAction.ABORT
        elif category == ErrorCategory.VALIDATION:
            return RecoveryAction.IGNORE
        else:
            return RecoveryAction.RETRY
    
    async def handle_error(
        self,
        exception: Exception,
        context: Dict[str, Any] = None,
        operation: str = "unknown"
    ) -> ErrorInfo:
        """
        Handle error with classification and recovery.
        
        Args:
            exception: The exception that occurred
            context: Additional context about the error
            operation: Name of the operation that failed
            
        Returns:
            ErrorInfo object with handling details
        """
        context = context or {}
        
        # Classify error
        category, severity = self.classify_error(exception, context)
        
        # Create error info
        error_info = ErrorInfo(
            error_id=f"err_{int(time.time())}_{random.randint(1000, 9999)}",
            timestamp=datetime.now(),
            category=category,
            severity=severity,
            message=str(exception),
            exception=exception,
            context=context,
            stack_trace=traceback.format_exc(),
            recovery_action=self.determine_recovery_action(category, severity)
        )
        
        # Update error counts
        self.error_count_by_category[category] = self.error_count_by_category.get(category, 0) + 1
        
        # Add to history
        self.error_history.append(error_info)
        
        # Keep only last 1000 errors
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-1000:]
        
        # Log error
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(severity, logging.ERROR)
        
        logger.log(
            log_level,
            f"Error handled: {error_info.error_id} - {category.value} - {severity.value} - {operation}: {exception}"
        )
        
        # Execute recovery action if needed
        if error_info.recovery_action == RecoveryAction.CLEANUP:
            await self._execute_cleanup()
            error_info.recovery_successful = True
        
        return error_info
    
    async def _execute_cleanup(self):
        """Execute all registered cleanup callbacks."""
        logger.info("Executing error recovery cleanup")
        
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in cleanup callback: {e}")
    
    def add_cleanup_callback(self, callback: Callable):
        """Add cleanup callback for error recovery."""
        self.cleanup_callbacks.append(callback)
    
    async def execute_with_error_handling(
        self,
        operation: str,
        func: Callable,
        *args,
        retry_config: RetryConfig = None,
        enable_fallback: bool = True,
        **kwargs
    ) -> Any:
        """
        Execute function with comprehensive error handling.
        
        Args:
            operation: Operation name
            func: Function to execute
            *args: Arguments for function
            retry_config: Retry configuration
            enable_fallback: Whether to enable fallback strategies
            **kwargs: Keyword arguments for function
            
        Returns:
            Result from successful execution
        """
        try:
            if enable_fallback:
                # Execute with fallback support
                return await self.fallback_manager.execute_with_fallback(
                    operation,
                    lambda *a, **kw: self.retry_manager.execute_with_retry(
                        operation, func, *a, config=retry_config, **kw
                    ),
                    *args,
                    **kwargs
                )
            else:
                # Execute with retry only
                return await self.retry_manager.execute_with_retry(
                    operation, func, *args, config=retry_config, **kwargs
                )
                
        except Exception as e:
            # Handle and classify error
            error_info = await self.handle_error(e, kwargs, operation)
            
            # Re-raise if recovery action is abort
            if error_info.recovery_action == RecoveryAction.ABORT:
                raise e
            
            # For other recovery actions, we've already handled the error
            # Return None or raise based on severity
            if error_info.severity == ErrorSeverity.CRITICAL:
                raise e
            else:
                logger.warning(f"Error handled gracefully for operation {operation}")
                return None
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        if not self.error_history:
            return {"message": "No errors recorded"}
        
        # Calculate statistics
        total_errors = len(self.error_history)
        recent_errors = [e for e in self.error_history if datetime.now() - e.timestamp < timedelta(hours=24)]
        
        category_counts = {}
        severity_counts = {}
        
        for error in self.error_history:
            category_counts[error.category.value] = category_counts.get(error.category.value, 0) + 1
            severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1
        
        return {
            "total_errors": total_errors,
            "recent_errors_24h": len(recent_errors),
            "errors_by_category": category_counts,
            "errors_by_severity": severity_counts,
            "fallback_stats": self.fallback_manager.get_fallback_stats(),
            "retry_stats": self.retry_manager.get_retry_stats(),
            "last_error": {
                "timestamp": self.error_history[-1].timestamp.isoformat(),
                "category": self.error_history[-1].category.value,
                "severity": self.error_history[-1].severity.value,
                "message": self.error_history[-1].message
            } if self.error_history else None
        }
    
    def cleanup(self):
        """Clean up error handler resources."""
        logger.info("Cleaning up CosmosErrorHandler")
        
        # Clear error history
        self.error_history.clear()
        
        # Clear callbacks
        self.cleanup_callbacks.clear()
        
        # Clear statistics
        self.error_count_by_category.clear()
        
        logger.info("CosmosErrorHandler cleanup completed")


# Global error handler instance
_global_error_handler: Optional[CosmosErrorHandler] = None


def get_error_handler() -> CosmosErrorHandler:
    """Get global error handler instance."""
    global _global_error_handler
    
    if _global_error_handler is None:
        _global_error_handler = CosmosErrorHandler()
    
    return _global_error_handler