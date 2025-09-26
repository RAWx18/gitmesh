"""
Cosmos Chat Specific Error Handler

Specialized error handling for Cosmos Web Chat integration scenarios.
Provides context-aware error messages and recovery suggestions specific to AI chat functionality.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import sys
import os

# Add the backend directory to the path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from .error_handling import (
        ErrorHandler, CosmosError, ErrorCategory, ErrorSeverity,
        ErrorContext, SuggestedAction, ErrorResponse,
        AuthenticationError, AuthorizationError, ValidationError,
        RepositoryError, ModelError, RateLimitError, SystemError,
        NetworkError, StorageError, ExternalAPIError
    )
    from ..services.graceful_degradation import get_graceful_degradation_service
except ImportError:
    try:
        from utils.error_handling import (
            ErrorHandler, CosmosError, ErrorCategory, ErrorSeverity,
            ErrorContext, SuggestedAction, ErrorResponse,
            AuthenticationError, AuthorizationError, ValidationError,
            RepositoryError, ModelError, RateLimitError, SystemError,
            NetworkError, StorageError, ExternalAPIError
        )
        from services.graceful_degradation import get_graceful_degradation_service
    except ImportError:
        from error_handling import (
            ErrorHandler, CosmosError, ErrorCategory, ErrorSeverity,
            ErrorContext, SuggestedAction, ErrorResponse,
            AuthenticationError, AuthorizationError, ValidationError,
            RepositoryError, ModelError, RateLimitError, SystemError,
            NetworkError, StorageError, ExternalAPIError
        )
        from graceful_degradation import get_graceful_degradation_service

# Configure logging
logger = logging.getLogger(__name__)


class ChatErrorType(str, Enum):
    """Specific chat error types."""
    SESSION_NOT_FOUND = "session_not_found"
    INVALID_MODEL = "invalid_model"
    CONTEXT_FILE_ERROR = "context_file_error"
    REPOSITORY_ACCESS_DENIED = "repository_access_denied"
    AI_MODEL_UNAVAILABLE = "ai_model_unavailable"
    SHELL_COMMAND_BLOCKED = "shell_command_blocked"
    VIRTUAL_FS_ERROR = "virtual_fs_error"
    TOKEN_RETRIEVAL_ERROR = "token_retrieval_error"
    CONVERSION_ERROR = "conversion_error"


@dataclass
class ChatErrorContext(ErrorContext):
    """Extended error context for chat-specific information."""
    session_id: Optional[str] = None
    model_name: Optional[str] = None
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    context_files: Optional[List[str]] = None
    user_tier: Optional[str] = None
    conversion_stage: Optional[str] = None


class ChatSessionError(CosmosError):
    """Chat session related errors."""
    
    def __init__(self, message: str, session_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CHAT_SESSION_ERROR",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Try starting a new chat session.",
                    action_url="/contribution/chat"
                ),
                SuggestedAction(
                    action_type="check_settings",
                    description="Verify your session is still active and try refreshing the page."
                )
            ]
        )
        self.session_id = session_id


class InvalidModelError(CosmosError):
    """Invalid AI model selection errors."""
    
    def __init__(self, message: str, model: Optional[str] = None, available_models: Optional[List[str]] = None):
        actions = [
            SuggestedAction(
                action_type="check_settings",
                description="Select a different AI model from the available options.",
                action_data={"available_models": available_models or []}
            )
        ]
        
        if available_models:
            actions.append(SuggestedAction(
                action_type="retry",
                description=f"Try using one of these models: {', '.join(available_models[:3])}",
                action_data={"suggested_models": available_models[:3]}
            ))
        
        super().__init__(
            message=message,
            error_code="INVALID_MODEL",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            details={"invalid_model": model, "available_models": available_models},
            suggested_actions=actions
        )


class ContextFileError(CosmosError):
    """Context file management errors."""
    
    def __init__(self, message: str, file_path: Optional[str] = None, operation: Optional[str] = None):
        actions = [
            SuggestedAction(
                action_type="check_settings",
                description="Verify the file path is correct and the file exists in the repository."
            )
        ]
        
        if operation == "add":
            actions.append(SuggestedAction(
                action_type="retry",
                description="Try browsing the repository to find the correct file path."
            ))
        elif operation == "remove":
            actions.append(SuggestedAction(
                action_type="retry",
                description="The file may have already been removed from context."
            ))
        
        super().__init__(
            message=message,
            error_code="CONTEXT_FILE_ERROR",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            details={"file_path": file_path, "operation": operation},
            suggested_actions=actions
        )


class RepositoryAccessError(CosmosError):
    """Repository access and authentication errors."""
    
    def __init__(self, message: str, repo_url: Optional[str] = None, is_private: bool = False):
        actions = []
        
        if is_private:
            actions.extend([
                SuggestedAction(
                    action_type="check_settings",
                    description="Ensure you have access to this private repository and your GitHub token is configured.",
                    action_url="/settings/github"
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if you need help configuring repository access.",
                    action_url="/support"
                )
            ])
        else:
            actions.extend([
                SuggestedAction(
                    action_type="retry",
                    description="Verify the repository URL is correct and publicly accessible."
                ),
                SuggestedAction(
                    action_type="check_settings",
                    description="Try using a different repository or branch."
                )
            ])
        
        super().__init__(
            message=message,
            error_code="REPOSITORY_ACCESS_ERROR",
            category=ErrorCategory.REPOSITORY,
            severity=ErrorSeverity.HIGH if is_private else ErrorSeverity.MEDIUM,
            details={"repo_url": repo_url, "is_private": is_private},
            suggested_actions=actions
        )


class AIModelUnavailableError(CosmosError):
    """AI model service unavailable errors."""
    
    def __init__(self, message: str, model: Optional[str] = None, fallback_models: Optional[List[str]] = None):
        actions = [
            SuggestedAction(
                action_type="retry",
                description="The AI service may be temporarily unavailable. Try again in a few moments."
            )
        ]
        
        if fallback_models:
            actions.append(SuggestedAction(
                action_type="check_settings",
                description=f"Try switching to an alternative model: {', '.join(fallback_models[:2])}",
                action_data={"fallback_models": fallback_models}
            ))
        
        super().__init__(
            message=message,
            error_code="AI_MODEL_UNAVAILABLE",
            category=ErrorCategory.MODEL,
            severity=ErrorSeverity.HIGH,
            details={"model": model, "fallback_models": fallback_models},
            suggested_actions=actions
        )


class ShellCommandBlockedError(CosmosError):
    """Shell command execution blocked for web safety."""
    
    def __init__(self, message: str, command: Optional[str] = None, alternative: Optional[str] = None):
        actions = [
            SuggestedAction(
                action_type="check_settings",
                description=""
            )
        ]
        
        if alternative:
            actions.append(SuggestedAction(
                action_type="retry",
                description=f"Use the web interface equivalent: {alternative}",
                action_data={"alternative": alternative}
            ))
        
        super().__init__(
            message=message,
            error_code="SHELL_COMMAND_BLOCKED",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details={"blocked_command": command, "alternative": alternative},
            suggested_actions=actions
        )


class VirtualFilesystemError(CosmosError):
    """Virtual filesystem operation errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, file_path: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="VIRTUAL_FS_ERROR",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.MEDIUM,
            details={"operation": operation, "file_path": file_path},
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Try the operation again or refresh the repository data."
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if the issue persists.",
                    action_url="/support"
                )
            ]
        )


class TokenRetrievalError(CosmosError):
    """GitHub token retrieval errors."""
    
    def __init__(self, message: str, username: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="TOKEN_RETRIEVAL_ERROR",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            details={"username": username},
            suggested_actions=[
                SuggestedAction(
                    action_type="check_settings",
                    description="Configure your GitHub token in settings.",
                    action_url="/settings/github"
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if you need help with token configuration.",
                    action_url="/support"
                )
            ]
        )


class ConversionError(CosmosError):
    """CLI-to-web conversion errors."""
    
    def __init__(self, message: str, conversion_stage: Optional[str] = None, cli_operation: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="CONVERSION_ERROR",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.MEDIUM,
            details={"conversion_stage": conversion_stage, "cli_operation": cli_operation},
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="The system is adapting CLI functionality for web use. Try again."
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Report this conversion issue to help improve the system.",
                    action_url="/support"
                )
            ]
        )


class CosmosErrorHandler(ErrorHandler):
    """
    Specialized error handler for Cosmos Web Chat.
    
    Extends the base ErrorHandler with chat-specific error handling,
    context-aware messages, and recovery suggestions.
    """
    
    def __init__(self, redis_client=None):
        """Initialize the Cosmos error handler."""
        super().__init__(redis_client)
        
        # Chat-specific error templates
        self.chat_error_templates = {
            ChatErrorType.SESSION_NOT_FOUND: {
                "title": "Session Not Found",
                "description": "Your chat session could not be found or has expired.",
                "icon": "💬",
                "recovery_action": "start_new_session"
            },
            ChatErrorType.INVALID_MODEL: {
                "title": "Invalid AI Model",
                "description": "The selected AI model is not available.",
                "icon": "🤖",
                "recovery_action": "select_different_model"
            },
            ChatErrorType.CONTEXT_FILE_ERROR: {
                "title": "File Context Error",
                "description": "There was a problem managing file context.",
                "icon": "📁",
                "recovery_action": "check_file_path"
            },
            ChatErrorType.REPOSITORY_ACCESS_DENIED: {
                "title": "Repository Access Denied",
                "description": "You don't have access to this repository.",
                "icon": "🔒",
                "recovery_action": "configure_access"
            },
            ChatErrorType.AI_MODEL_UNAVAILABLE: {
                "title": "AI Service Unavailable",
                "description": "The AI model service is temporarily unavailable.",
                "icon": "⚡",
                "recovery_action": "try_different_model"
            },
            ChatErrorType.SHELL_COMMAND_BLOCKED: {
                "title": "Command Blocked",
                "description": "Shell commands are disabled for web safety.",
                "icon": "🛡️",
                "recovery_action": "use_web_interface"
            },
            ChatErrorType.VIRTUAL_FS_ERROR: {
                "title": "File System Error",
                "description": "There was a problem accessing repository files.",
                "icon": "💾",
                "recovery_action": "refresh_repository"
            },
            ChatErrorType.TOKEN_RETRIEVAL_ERROR: {
                "title": "Authentication Error",
                "description": "Could not retrieve your GitHub authentication token.",
                "icon": "🔑",
                "recovery_action": "configure_token"
            },
            ChatErrorType.CONVERSION_ERROR: {
                "title": "Conversion Error",
                "description": "There was a problem adapting CLI functionality for web use.",
                "icon": "🔄",
                "recovery_action": "report_issue"
            }
        }
        
        # Initialize degradation service
        self.degradation_service = get_graceful_degradation_service(redis_client)
    
    def handle_chat_error(
        self,
        error: Union[Exception, CosmosError],
        chat_context: Optional[ChatErrorContext] = None,
        log_error: bool = True
    ) -> ErrorResponse:
        """
        Handle chat-specific errors with enhanced context.
        
        Args:
            error: The error to handle
            chat_context: Chat-specific error context
            log_error: Whether to log the error
            
        Returns:
            ErrorResponse with chat-specific information
        """
        try:
            # Convert chat context to base error context
            base_context = None
            if chat_context:
                base_context = ErrorContext(
                    user_id=chat_context.user_id,
                    session_id=chat_context.session_id,
                    request_id=chat_context.request_id,
                    endpoint=chat_context.endpoint,
                    method=chat_context.method,
                    user_agent=chat_context.user_agent,
                    ip_address=chat_context.ip_address,
                    timestamp=chat_context.timestamp
                )
            
            # Handle the error using base handler
            error_response = self.handle_error(error, base_context, log_error)
            
            # Enhance with chat-specific information
            if chat_context:
                error_response = self._enhance_chat_error_response(error_response, chat_context)
            
            # Add system health information
            error_response = self._add_system_health_info(error_response)
            
            return error_response
            
        except Exception as e:
            logger.error(f"Error in chat error handler: {e}")
            return self._create_fallback_chat_error_response()
    
    def _enhance_chat_error_response(
        self,
        error_response: ErrorResponse,
        chat_context: ChatErrorContext
    ) -> ErrorResponse:
        """Enhance error response with chat-specific information."""
        
        # Add chat context to details
        if not error_response.details:
            error_response.details = {}
        
        error_response.details.update({
            "session_id": chat_context.session_id,
            "model_name": chat_context.model_name,
            "repository_url": chat_context.repository_url,
            "branch": chat_context.branch,
            "user_tier": chat_context.user_tier,
            "conversion_stage": chat_context.conversion_stage
        })
        
        if chat_context.context_files:
            error_response.details["context_files_count"] = len(chat_context.context_files)
        
        # Enhance suggested actions based on chat context
        error_response.suggested_actions = self._get_enhanced_chat_actions(
            error_response,
            chat_context
        )
        
        return error_response
    
    def _get_enhanced_chat_actions(
        self,
        error_response: ErrorResponse,
        chat_context: ChatErrorContext
    ) -> List[SuggestedAction]:
        """Get enhanced suggested actions for chat errors."""
        
        actions = list(error_response.suggested_actions)  # Copy existing actions
        
        # Add chat-specific actions based on context
        if chat_context.session_id and error_response.category == ErrorCategory.VALIDATION:
            actions.append(SuggestedAction(
                action_type="retry",
                description="Try starting a new chat session if the problem persists.",
                action_url="/contribution/chat",
                action_data={"session_id": chat_context.session_id}
            ))
        
        if chat_context.model_name and error_response.category == ErrorCategory.MODEL:
            actions.append(SuggestedAction(
                action_type="check_settings",
                description="Try selecting a different AI model from the dropdown.",
                action_data={"current_model": chat_context.model_name}
            ))
        
        if chat_context.repository_url and error_response.category == ErrorCategory.REPOSITORY:
            actions.append(SuggestedAction(
                action_type="check_settings",
                description="Verify the repository URL and your access permissions.",
                action_data={"repository_url": chat_context.repository_url}
            ))
        
        if chat_context.user_tier == "free" and error_response.category == ErrorCategory.AUTHORIZATION:
            actions.append(SuggestedAction(
                action_type="upgrade_tier",
                description="Upgrade to Pro or Enterprise for access to advanced features.",
                action_url="/pricing"
            ))
        
        return actions
    
    def _add_system_health_info(self, error_response: ErrorResponse) -> ErrorResponse:
        """Add system health information to error response."""
        try:
            # Get system health asynchronously (this is a simplified version)
            # In a real implementation, you might want to cache this information
            if not error_response.details:
                error_response.details = {}
            
            # Add basic health status
            error_response.details["system_status"] = "checking"
            
            # You could add more detailed health information here
            # based on the degradation service status
            
        except Exception as e:
            logger.warning(f"Could not add system health info: {e}")
        
        return error_response
    
    def _create_fallback_chat_error_response(self) -> ErrorResponse:
        """Create a fallback error response for chat errors."""
        return ErrorResponse(
            error_code="CHAT_SYSTEM_ERROR",
            message="🤖 Chat System Error: An unexpected error occurred in the chat system. Please try again.",
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.HIGH,
            suggested_actions=[
                SuggestedAction(
                    action_type="retry",
                    description="Try starting a new chat session.",
                    action_url="/contribution/chat"
                ),
                SuggestedAction(
                    action_type="contact_support",
                    description="Contact support if the problem persists.",
                    action_url="/support"
                )
            ],
            correlation_id=self._generate_correlation_id()
        )
    
    def get_chat_error_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get error statistics specific to chat functionality."""
        base_stats = self.get_error_statistics()
        
        # Add chat-specific statistics
        chat_stats = {
            "chat_errors": {
                "session_errors": 0,
                "model_errors": 0,
                "repository_errors": 0,
                "conversion_errors": 0
            },
            "session_id": session_id
        }
        
        # Analyze error types for chat-specific patterns
        for error_type, count in base_stats.get("top_errors", []):
            if "session" in error_type.lower():
                chat_stats["chat_errors"]["session_errors"] += count
            elif "model" in error_type.lower():
                chat_stats["chat_errors"]["model_errors"] += count
            elif "repo" in error_type.lower():
                chat_stats["chat_errors"]["repository_errors"] += count
            elif "conversion" in error_type.lower():
                chat_stats["chat_errors"]["conversion_errors"] += count
        
        return {**base_stats, **chat_stats}


# Global cosmos error handler instance
cosmos_error_handler = None


def get_cosmos_error_handler(redis_client=None) -> CosmosErrorHandler:
    """Get or create the global cosmos error handler instance."""
    global cosmos_error_handler
    
    if cosmos_error_handler is None:
        cosmos_error_handler = CosmosErrorHandler(redis_client)
    
    return cosmos_error_handler


def handle_chat_error(
    error: Union[Exception, CosmosError],
    chat_context: Optional[ChatErrorContext] = None
) -> ErrorResponse:
    """
    Convenience function to handle chat errors using the global handler.
    
    Args:
        error: The error to handle
        chat_context: Chat-specific error context
        
    Returns:
        ErrorResponse with chat-specific information
    """
    handler = get_cosmos_error_handler()
    return handler.handle_chat_error(error, chat_context)