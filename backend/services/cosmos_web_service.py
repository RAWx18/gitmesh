"""
Cosmos Web Service Foundation
Provides web-compatible interface to Cosmos AI coding assistant functionality.
Updated to use OptimizedCosmosWrapper for enhanced performance and Redis-first architecture.
"""

import uuid
import json
import redis
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..config.key_manager import key_manager
    from ..config.cosmos_models import MODEL_ALIASES
    from ..services.conversion_tracking_service import conversion_tracking_service
    from ..services.performance_optimization_service import get_performance_service, cached_response
    from ..services.optimized_repo_cache import get_optimized_repo_cache
    from ..services.chat_analytics_service import chat_analytics_service
    from ..services.optimized_cosmos_wrapper import OptimizedCosmosWrapper
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from config.key_manager import key_manager
    from config.cosmos_models import MODEL_ALIASES
    from services.conversion_tracking_service import conversion_tracking_service
    from services.performance_optimization_service import get_performance_service, cached_response
    from services.optimized_repo_cache import get_optimized_repo_cache
    from services.chat_analytics_service import chat_analytics_service
    from services.optimized_cosmos_wrapper import OptimizedCosmosWrapper


class SessionStatus(str, Enum):
    """Chat session status enumeration."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class ContextFile:
    """Context file data model."""
    path: str
    name: str
    size: int
    language: str
    added_at: datetime
    is_modified: bool = False
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ChatSession:
    """Chat session data model."""
    id: str
    user_id: str
    title: str
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    model: str = "gemini"  # Default to Gemini as per requirements
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = None
    updated_at: datetime = None
    message_count: int = 0
    selected_files: List[str] = None
    context_files: List[ContextFile] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.selected_files is None:
            self.selected_files = []
        if self.context_files is None:
            self.context_files = []


@dataclass
class ChatMessage:
    """Chat message data model."""
    id: str
    session_id: str
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    context_files_used: List[str] = None
    shell_commands_converted: List[str] = None
    conversion_notes: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.context_files_used is None:
            self.context_files_used = []
        if self.shell_commands_converted is None:
            self.shell_commands_converted = []


@dataclass
class ModelInfo:
    """Model information data model."""
    name: str
    alias: str
    provider: str
    tier_required: str = "free"
    max_tokens: int = 4096
    supports_code: bool = True
    supports_reasoning: bool = False


class CosmosWebService:
    """
    Cosmos Web Service Foundation
    
    Provides session management and model validation for Cosmos AI integration.
    Uses Redis for storage and integrates with existing Cosmos MODEL_ALIASES.
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize the Cosmos Web Service with OptimizedCosmosWrapper integration."""
        self.settings = get_settings()
        self.key_manager = key_manager
        
        # Initialize performance optimization services
        self.performance_service = get_performance_service()
        self.repo_cache = get_optimized_repo_cache()
        
        # Initialize analytics service
        self.analytics_service = chat_analytics_service
        
        # Use provided Redis client or get optimized one from performance service
        self.redis_client = redis_client or self.performance_service.get_redis_client("cosmos_web")
        
        # Session configuration
        self.session_ttl = 86400  # 24 hours
        self.message_ttl = 604800  # 7 days
        
        # Key prefixes for Redis
        self.session_prefix = "cosmos:session:"
        self.message_prefix = "cosmos:message:"
        self.user_sessions_prefix = "cosmos:user_sessions:"
        
        # OptimizedCosmosWrapper instances cache
        self.wrapper_cache: Dict[str, OptimizedCosmosWrapper] = {}
        self.wrapper_cache_ttl = 3600  # 1 hour TTL for wrapper instances
        self.wrapper_last_used: Dict[str, datetime] = {}
        
        # Migration flags for backward compatibility
        self.use_optimized_wrapper = True  # Feature flag for new wrapper
        self.fallback_to_legacy = True    # Allow fallback to legacy behavior
    
    async def create_session(
        self, 
        user_id: str, 
        title: str = "New Chat",
        repository_url: Optional[str] = None, 
        branch: Optional[str] = None,
        model: str = "gemini"
    ) -> str:
        """
        Create a new chat session.
        
        Args:
            user_id: User identifier
            title: Session title
            repository_url: Optional repository URL
            branch: Optional branch name
            model: AI model to use (must be valid alias)
            
        Returns:
            Session ID
            
        Raises:
            ValueError: If model is invalid
        """
        # Validate model
        if not self.is_valid_model(model):
            raise ValueError(f"Invalid model: {model}. Must be one of: {list(MODEL_ALIASES.keys())}")
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Create session object
        session = ChatSession(
            id=session_id,
            user_id=user_id,
            title=title,
            repository_url=repository_url,
            branch=branch,
            model=model
        )
        
        # Store session in Redis
        session_key = f"{self.session_prefix}{session_id}"
        session_data = self._serialize_session(session)
        
        # Use pipeline for atomic operations
        pipe = self.redis_client.pipeline()
        pipe.hset(session_key, mapping=session_data)
        pipe.expire(session_key, self.session_ttl)
        
        # Add to user's session list
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        pipe.sadd(user_sessions_key, session_id)
        pipe.expire(user_sessions_key, self.session_ttl)
        
        pipe.execute()
        
        # Track session creation analytics
        try:
            await self.analytics_service.track_session_metrics(
                session_id=session_id,
                user_id=user_id,
                model_used=model,
                repository_url=repository_url,
                branch=branch,
                message_count=0,
                context_files_count=0,
                context_files_size=0,
                is_active=True
            )
            
            await self.analytics_service.track_user_engagement(
                user_id=user_id,
                session_id=session_id,
                activity_type="session_created",
                model=model,
                repository_url=repository_url
            )
        except Exception as e:
            logger.error(f"Error tracking session creation analytics: {e}")
        
        return session_id
    
    @cached_response(ttl=300)  # Cache for 5 minutes
    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Retrieve a chat session by ID with caching.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ChatSession object or None if not found
        """
        session_key = f"{self.session_prefix}{session_id}"
        session_data = self.redis_client.hgetall(session_key)
        
        if not session_data:
            return None
        
        return self._deserialize_session(session_data)
    
    async def update_session(self, session_id: str, **updates) -> bool:
        """
        Update session properties.
        
        Args:
            session_id: Session identifier
            **updates: Fields to update
            
        Returns:
            True if successful, False if session not found
        """
        session_key = f"{self.session_prefix}{session_id}"
        
        # Check if session exists
        if not self.redis_client.exists(session_key):
            return False
        
        # Validate model if being updated
        if 'model' in updates and not self.is_valid_model(updates['model']):
            raise ValueError(f"Invalid model: {updates['model']}")
        
        # Add updated timestamp
        updates['updated_at'] = datetime.now().isoformat()
        
        # Update session
        self.redis_client.hset(session_key, mapping=updates)
        
        return True
    
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """
        Delete a chat session and its messages.
        
        Args:
            session_id: Session identifier
            user_id: User identifier (for authorization)
            
        Returns:
            True if successful, False if session not found
        """
        session_key = f"{self.session_prefix}{session_id}"
        
        # Verify session exists and belongs to user
        session_data = self.redis_client.hgetall(session_key)
        if not session_data or session_data.get('user_id') != user_id:
            return False
        
        # Use pipeline for atomic operations
        pipe = self.redis_client.pipeline()
        
        # Delete session
        pipe.delete(session_key)
        
        # Remove from user's session list
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        pipe.srem(user_sessions_key, session_id)
        
        # Delete all messages for this session
        message_pattern = f"{self.message_prefix}{session_id}:*"
        message_keys = self.redis_client.keys(message_pattern)
        if message_keys:
            pipe.delete(*message_keys)
        
        pipe.execute()
        
        return True
    
    @cached_response(ttl=60)  # Cache for 1 minute
    async def get_user_sessions(self, user_id: str) -> List[ChatSession]:
        """
        Get all sessions for a user with caching and batch optimization.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of ChatSession objects
        """
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        session_ids = self.redis_client.smembers(user_sessions_key)
        
        if not session_ids:
            return []
        
        # Batch fetch sessions for better performance
        batch_operations = []
        for session_id in session_ids:
            session_key = f"{self.session_prefix}{session_id}"
            batch_operations.append({
                'method': 'hgetall',
                'args': [session_key]
            })
        
        try:
            # Use performance service for batch operations
            session_data_list = await self.performance_service.batch_redis_operations(batch_operations)
            
            sessions = []
            for session_data in session_data_list:
                if session_data:
                    try:
                        session = self._deserialize_session(session_data)
                        sessions.append(session)
                    except Exception as e:
                        logger.error(f"Error deserializing session: {e}")
                        continue
            
            # Sort by updated_at descending
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error in batch session fetch: {e}")
            # Fallback to individual fetches
            sessions = []
            for session_id in session_ids:
                session = await self.get_session(session_id)
                if session:
                    sessions.append(session)
            
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            return sessions
    
    async def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        context_files_used: Optional[List[str]] = None,
        shell_commands_converted: Optional[List[str]] = None,
        conversion_notes: Optional[str] = None
    ) -> str:
        """
        Add a message to a chat session.
        
        Args:
            session_id: Session identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            metadata: Optional metadata
            context_files_used: Files that were in context
            shell_commands_converted: Shell commands converted to web operations
            conversion_notes: Notes about CLI-to-web conversions
            
        Returns:
            Message ID
            
        Raises:
            ValueError: If session doesn't exist or role is invalid
        """
        # Validate session exists
        session_key = f"{self.session_prefix}{session_id}"
        if not self.redis_client.exists(session_key):
            raise ValueError(f"Session {session_id} not found")
        
        # Validate role
        if role not in ['user', 'assistant', 'system']:
            raise ValueError(f"Invalid role: {role}")
        
        # Generate message ID
        message_id = str(uuid.uuid4())
        
        # Create message object
        message = ChatMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
            context_files_used=context_files_used or [],
            shell_commands_converted=shell_commands_converted or [],
            conversion_notes=conversion_notes
        )
        
        # Store message in Redis
        message_key = f"{self.message_prefix}{session_id}:{message_id}"
        message_data = self._serialize_message(message)
        
        # Use pipeline for atomic operations
        pipe = self.redis_client.pipeline()
        pipe.hset(message_key, mapping=message_data)
        pipe.expire(message_key, self.message_ttl)
        
        # Update session message count and timestamp
        pipe.hincrby(session_key, 'message_count', 1)
        pipe.hset(session_key, 'updated_at', datetime.now().isoformat())
        
        pipe.execute()
        
        # Track message analytics
        try:
            # Get session data for analytics
            session_data = self.redis_client.hgetall(session_key)
            if session_data:
                await self.analytics_service.track_session_metrics(
                    session_id=session_id,
                    user_id=session_data.get("user_id", ""),
                    model_used=session_data.get("model", ""),
                    repository_url=session_data.get("repository_url"),
                    branch=session_data.get("branch"),
                    message_increment=1,
                    is_active=True
                )
                
                await self.analytics_service.track_user_engagement(
                    user_id=session_data.get("user_id", ""),
                    session_id=session_id,
                    activity_type="message",
                    model=session_data.get("model", ""),
                    repository_url=session_data.get("repository_url")
                )
                
                # Track conversion operations if any
                if shell_commands_converted:
                    for command in shell_commands_converted:
                        await self.analytics_service.track_conversion_operation(
                            session_id=session_id,
                            operation_type="shell_command",
                            original_command=command,
                            web_equivalent="web_safe_operation",
                            success=True,
                            conversion_time=0.1,  # Placeholder
                            complexity_score=5,
                            user_feedback=conversion_notes
                        )
        except Exception as e:
            logger.error(f"Error tracking message analytics: {e}")
        
        return message_id
    
    async def get_session_messages(
        self, 
        session_id: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[ChatMessage]:
        """
        Get messages for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            offset: Number of messages to skip
            
        Returns:
            List of ChatMessage objects
        """
        message_pattern = f"{self.message_prefix}{session_id}:*"
        message_keys = self.redis_client.keys(message_pattern)
        
        messages = []
        for message_key in message_keys:
            message_data = self.redis_client.hgetall(message_key)
            if message_data:
                message = self._deserialize_message(message_data)
                messages.append(message)
        
        # Sort by timestamp
        messages.sort(key=lambda m: m.timestamp)
        
        # Apply pagination
        start = offset
        end = offset + limit
        return messages[start:end]
    
    async def get_or_create_wrapper(
        self, 
        user_id: str, 
        session_id: str, 
        repository_url: Optional[str] = None,
        model: str = "gemini"
    ) -> Optional[OptimizedCosmosWrapper]:
        """
        Get or create an OptimizedCosmosWrapper instance for a user session.
        
        Args:
            user_id: User identifier
            session_id: Session identifier (used as project_id)
            repository_url: Repository URL for context
            model: AI model to use
            
        Returns:
            OptimizedCosmosWrapper instance or None if creation fails
        """
        if not self.use_optimized_wrapper:
            return None
        
        wrapper_key = f"{user_id}:{session_id}:{repository_url or 'no_repo'}"
        
        # Check if wrapper exists and is still valid
        if wrapper_key in self.wrapper_cache:
            last_used = self.wrapper_last_used.get(wrapper_key, datetime.now())
            if (datetime.now() - last_used).total_seconds() < self.wrapper_cache_ttl:
                # Update last used time
                self.wrapper_last_used[wrapper_key] = datetime.now()
                return self.wrapper_cache[wrapper_key]
            else:
                # Wrapper expired, clean it up
                await self._cleanup_wrapper(wrapper_key)
        
        # Create new wrapper
        try:
            wrapper = OptimizedCosmosWrapper(
                redis_client=self.redis_client,
                user_id=user_id,
                project_id=session_id,
                repository_url=repository_url,
                model=model
            )
            
            # Initialize wrapper
            if await wrapper.initialize():
                self.wrapper_cache[wrapper_key] = wrapper
                self.wrapper_last_used[wrapper_key] = datetime.now()
                logger.info(f"Created OptimizedCosmosWrapper for user {user_id}, session {session_id}")
                return wrapper
            else:
                logger.error(f"Failed to initialize OptimizedCosmosWrapper for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating OptimizedCosmosWrapper: {e}")
            return None
    
    async def _cleanup_wrapper(self, wrapper_key: str):
        """Clean up an expired wrapper instance."""
        try:
            if wrapper_key in self.wrapper_cache:
                wrapper = self.wrapper_cache[wrapper_key]
                wrapper.cleanup()
                del self.wrapper_cache[wrapper_key]
                
            if wrapper_key in self.wrapper_last_used:
                del self.wrapper_last_used[wrapper_key]
                
            logger.debug(f"Cleaned up wrapper: {wrapper_key}")
            
        except Exception as e:
            logger.error(f"Error cleaning up wrapper {wrapper_key}: {e}")
    
    async def process_chat_with_optimized_wrapper(
        self,
        session_id: str,
        user_id: str,
        message: str,
        context: Dict[str, Any] = None,
        selected_files: List[str] = None,
        model_name: str = None
    ) -> Dict[str, Any]:
        """
        Process chat message using OptimizedCosmosWrapper.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            message: User message
            context: Additional context
            selected_files: Selected file paths
            model_name: Override model name
            
        Returns:
            Chat response dictionary
        """
        try:
            # Get session to determine repository context
            session = await self.get_session(session_id)
            if not session:
                return {
                    "error": "Session not found",
                    "content": "I couldn't find your chat session. Please start a new conversation."
                }
            
            # Use session model if no override provided
            model = model_name or session.model
            
            # Get or create wrapper
            wrapper = await self.get_or_create_wrapper(
                user_id=user_id,
                session_id=session_id,
                repository_url=session.repository_url,
                model=model
            )
            
            if not wrapper:
                if self.fallback_to_legacy:
                    logger.warning("OptimizedCosmosWrapper not available, falling back to legacy behavior")
                    return await self._legacy_chat_processing(session_id, message, context, selected_files)
                else:
                    return {
                        "error": "Cosmos service unavailable",
                        "content": "I'm currently unable to process your request. Please try again later."
                    }
            
            # Get session history for context
            session_messages = await self.get_session_messages(session_id, limit=10)
            session_history = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in session_messages
            ]
            
            # Process message through optimized wrapper
            response = await wrapper.process_chat_message(
                message=message,
                context=context,
                session_history=session_history,
                selected_files=selected_files,
                model_name=model
            )
            
            # Add user message to session
            await self.add_message(
                session_id=session_id,
                role="user",
                content=message,
                context_files_used=selected_files,
                metadata={"model": model}
            )
            
            # Add assistant response to session
            await self.add_message(
                session_id=session_id,
                role="assistant",
                content=response.get("content", ""),
                context_files_used=response.get("context_files_used", []),
                shell_commands_converted=response.get("shell_commands_converted", []),
                conversion_notes=response.get("conversion_notes"),
                metadata=response.get("metadata", {})
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in optimized chat processing: {e}")
            
            # Fallback to legacy processing if enabled
            if self.fallback_to_legacy:
                logger.info("Falling back to legacy chat processing due to error")
                return await self._legacy_chat_processing(session_id, message, context, selected_files)
            else:
                return {
                    "error": str(e),
                    "content": "I encountered an error while processing your message. Please try again."
                }
    
    async def _legacy_chat_processing(
        self,
        session_id: str,
        message: str,
        context: Dict[str, Any] = None,
        selected_files: List[str] = None
    ) -> Dict[str, Any]:
        """
        Legacy chat processing fallback method.
        
        This method provides backward compatibility when OptimizedCosmosWrapper
        is not available or fails.
        """
        logger.info("Using legacy chat processing")
        
        # Simple fallback response
        return {
            "content": f"I received your message: {message}. However, I'm currently running in compatibility mode with limited functionality. Please try again later for full AI assistance.",
            "context_files_used": selected_files or [],
            "shell_commands_converted": [],
            "conversion_notes": "Running in legacy compatibility mode",
            "error": None,
            "metadata": {
                "model_used": "legacy",
                "response_time": 0.1,
                "legacy_mode": True
            },
            "confidence": 0.1,
            "sources": []
        }
    
    async def cleanup_expired_wrappers(self):
        """Clean up expired wrapper instances."""
        try:
            current_time = datetime.now()
            expired_keys = []
            
            for wrapper_key, last_used in self.wrapper_last_used.items():
                if (current_time - last_used).total_seconds() > self.wrapper_cache_ttl:
                    expired_keys.append(wrapper_key)
            
            for key in expired_keys:
                await self._cleanup_wrapper(key)
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired wrapper instances")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired wrappers: {e}")
    
    async def get_wrapper_performance_metrics(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Get performance metrics from a user's wrapper instance."""
        try:
            wrapper_key = f"{user_id}:{session_id}:*"  # Match any repository
            
            # Find matching wrapper
            for key, wrapper in self.wrapper_cache.items():
                if key.startswith(f"{user_id}:{session_id}:"):
                    return wrapper.get_detailed_performance_report()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting wrapper performance metrics: {e}")
            return None
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the service and its components."""
        try:
            health = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {}
            }
            
            # Check Redis connectivity
            try:
                self.redis_client.ping()
                health["components"]["redis"] = "healthy"
            except Exception as e:
                health["components"]["redis"] = f"unhealthy: {e}"
                health["status"] = "degraded"
            
            # Check wrapper cache status
            health["components"]["wrapper_cache"] = {
                "active_wrappers": len(self.wrapper_cache),
                "status": "healthy"
            }
            
            # Check performance service
            try:
                perf_health = self.performance_service.health_check()
                health["components"]["performance_service"] = perf_health
            except Exception as e:
                health["components"]["performance_service"] = f"unhealthy: {e}"
            
            return health
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def shutdown(self):
        """Gracefully shutdown the service and clean up resources."""
        try:
            logger.info("Shutting down CosmosWebService...")
            
            # Clean up all wrapper instances
            for wrapper_key in list(self.wrapper_cache.keys()):
                await self._cleanup_wrapper(wrapper_key)
            
            logger.info("CosmosWebService shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during CosmosWebService shutdown: {e}")
    
    def get_available_models(self) -> List[ModelInfo]:
        """
        Get list of available AI models from Cosmos configuration.
        
        Returns:
            List of ModelInfo objects
        """
        models = []
        
        # Create ModelInfo objects from MODEL_ALIASES
        for alias, canonical_name in MODEL_ALIASES.items():
            # Determine provider from canonical name
            provider = "unknown"
            if canonical_name.startswith("anthropic/"):
                provider = "anthropic"
            elif canonical_name.startswith("gpt-") or canonical_name.startswith("openai/"):
                provider = "openai"
            elif canonical_name.startswith("gemini/"):
                provider = "google"
            elif canonical_name.startswith("deepseek/"):
                provider = "deepseek"
            elif canonical_name.startswith("openrouter/"):
                provider = "openrouter"
            elif canonical_name.startswith("xai/"):
                provider = "xai"
            
            # Determine tier requirements (simplified for now)
            tier_required = "free"
            if "opus" in alias or "gpt-4" in canonical_name:
                tier_required = "pro"
            elif "enterprise" in alias:
                tier_required = "enterprise"
            
            model_info = ModelInfo(
                name=canonical_name,
                alias=alias,
                provider=provider,
                tier_required=tier_required,
                supports_reasoning="reasoning" in canonical_name or "r1" in alias
            )
            models.append(model_info)
        
        return models
    
    def is_valid_model(self, model: str) -> bool:
        """
        Validate if a model alias is supported.
        
        Args:
            model: Model alias to validate
            
        Returns:
            True if valid, False otherwise
        """
        return model in MODEL_ALIASES
    
    def get_canonical_model_name(self, alias: str) -> Optional[str]:
        """
        Get canonical model name from alias.
        
        Args:
            alias: Model alias
            
        Returns:
            Canonical model name or None if invalid
        """
        return MODEL_ALIASES.get(alias)
    
    def enable_optimized_wrapper(self, enable: bool = True):
        """
        Enable or disable the OptimizedCosmosWrapper.
        
        Args:
            enable: Whether to enable the optimized wrapper
        """
        self.use_optimized_wrapper = enable
        logger.info(f"OptimizedCosmosWrapper {'enabled' if enable else 'disabled'}")
    
    def enable_legacy_fallback(self, enable: bool = True):
        """
        Enable or disable fallback to legacy behavior.
        
        Args:
            enable: Whether to enable legacy fallback
        """
        self.fallback_to_legacy = enable
        logger.info(f"Legacy fallback {'enabled' if enable else 'disabled'}")
    
    async def migrate_session_to_optimized(self, session_id: str) -> bool:
        """
        Migrate an existing session to use OptimizedCosmosWrapper.
        
        Args:
            session_id: Session to migrate
            
        Returns:
            True if migration successful, False otherwise
        """
        try:
            session = await self.get_session(session_id)
            if not session:
                logger.error(f"Session {session_id} not found for migration")
                return False
            
            # Create wrapper for this session
            wrapper = await self.get_or_create_wrapper(
                user_id=session.user_id,
                session_id=session_id,
                repository_url=session.repository_url,
                model=session.model
            )
            
            if wrapper:
                logger.info(f"Successfully migrated session {session_id} to OptimizedCosmosWrapper")
                return True
            else:
                logger.error(f"Failed to create OptimizedCosmosWrapper for session {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error migrating session {session_id}: {e}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get current service status and configuration.
        
        Returns:
            Dictionary with service status information
        """
        return {
            "optimized_wrapper_enabled": self.use_optimized_wrapper,
            "legacy_fallback_enabled": self.fallback_to_legacy,
            "active_wrappers": len(self.wrapper_cache),
            "wrapper_cache_ttl": self.wrapper_cache_ttl,
            "session_ttl": self.session_ttl,
            "message_ttl": self.message_ttl,
            "redis_connected": self._check_redis_connection(),
            "performance_service_available": self.performance_service is not None,
            "analytics_service_available": self.analytics_service is not None
        }
    
    def _check_redis_connection(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False
    
    async def add_context_files(
        self, 
        session_id: str, 
        file_paths: List[str],
        repository_url: Optional[str] = None,
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add files to session context with validation and metadata.
        
        Args:
            session_id: Session identifier
            file_paths: List of file paths to add
            repository_url: Repository URL (optional, uses session default)
            branch: Branch name (optional, uses session default)
            
        Returns:
            Dictionary with operation results
            
        Raises:
            ValueError: If session doesn't exist or validation fails
        """
        # Get session
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Use session repository info if not provided
        repo_url = repository_url or session.repository_url
        repo_branch = branch or session.branch
        
        if not repo_url:
            raise ValueError("Repository URL is required for context file operations")
        
        # Initialize repository manager
        try:
            from .redis_repo_manager import RedisRepoManager
            repo_manager = RedisRepoManager(
                repo_url=repo_url,
                branch=repo_branch or "main",
                user_tier="free",  # TODO: Get from user context
                username=session.user_id
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize repository manager: {e}")
        
        # Validate and process files
        added_files = []
        failed_files = []
        existing_paths = {cf.path for cf in session.context_files}
        
        # Context file limits
        MAX_CONTEXT_FILES = 50
        MAX_FILE_SIZE = 1024 * 1024  # 1MB per file
        MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB total
        
        # Calculate current total size
        current_total_size = sum(cf.size for cf in session.context_files)
        
        for file_path in file_paths:
            try:
                # Skip if already in context
                if file_path in existing_paths:
                    failed_files.append({
                        "path": file_path,
                        "error": "File already in context"
                    })
                    continue
                
                # Check context file limit
                if len(session.context_files) + len(added_files) >= MAX_CONTEXT_FILES:
                    failed_files.append({
                        "path": file_path,
                        "error": f"Maximum context files limit reached ({MAX_CONTEXT_FILES})"
                    })
                    continue
                
                # Get file metadata
                file_metadata = repo_manager.get_file_metadata(file_path)
                if not file_metadata:
                    failed_files.append({
                        "path": file_path,
                        "error": "File not found in repository"
                    })
                    continue
                
                # Check file size limit
                if file_metadata.size > MAX_FILE_SIZE:
                    failed_files.append({
                        "path": file_path,
                        "error": f"File too large ({file_metadata.size} bytes, max {MAX_FILE_SIZE})"
                    })
                    continue
                
                # Check total size limit
                if current_total_size + file_metadata.size > MAX_TOTAL_SIZE:
                    failed_files.append({
                        "path": file_path,
                        "error": f"Total context size limit exceeded (max {MAX_TOTAL_SIZE} bytes)"
                    })
                    continue
                
                # Create context file
                context_file = ContextFile(
                    path=file_path,
                    name=file_metadata.name,
                    size=file_metadata.size,
                    language=file_metadata.language,
                    added_at=datetime.now(),
                    is_modified=False,
                    metadata={
                        "is_tracked": file_metadata.is_tracked,
                        "last_modified": file_metadata.last_modified
                    }
                )
                
                added_files.append(context_file)
                current_total_size += file_metadata.size
                
            except Exception as e:
                failed_files.append({
                    "path": file_path,
                    "error": f"Error processing file: {str(e)}"
                })
        
        # Update session with new context files
        if added_files:
            session.context_files.extend(added_files)
            
            # Serialize context files with datetime handling
            context_files_data = []
            for cf in session.context_files:
                cf_dict = asdict(cf)
                cf_dict['added_at'] = cf.added_at.isoformat()
                context_files_data.append(cf_dict)
            
            # Debounce context file updates to avoid excessive Redis writes
            await self.performance_service.debounce_cache_update(
                f"context_files:{session_id}",
                self._update_context_files_in_redis,
                delay=0.5,  # 500ms debounce
                session_id=session_id,
                context_files_data=context_files_data
            )
        
        return {
            "added_count": len(added_files),
            "failed_count": len(failed_files),
            "added_files": [
                {
                    "path": cf.path,
                    "name": cf.name,
                    "size": cf.size,
                    "language": cf.language,
                    "added_at": cf.added_at.isoformat()
                }
                for cf in added_files
            ],
            "failed_files": failed_files,
            "total_context_files": len(session.context_files),
            "total_context_size": sum(cf.size for cf in session.context_files)
        }
    
    async def remove_context_files(
        self, 
        session_id: str, 
        file_paths: List[str]
    ) -> Dict[str, Any]:
        """
        Remove files from session context.
        
        Args:
            session_id: Session identifier
            file_paths: List of file paths to remove
            
        Returns:
            Dictionary with operation results
            
        Raises:
            ValueError: If session doesn't exist
        """
        # Get session
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Track removed and not found files
        removed_files = []
        not_found_files = []
        
        # Create set for efficient lookup
        paths_to_remove = set(file_paths)
        
        # Filter out files to remove
        remaining_files = []
        for context_file in session.context_files:
            if context_file.path in paths_to_remove:
                removed_files.append({
                    "path": context_file.path,
                    "name": context_file.name,
                    "size": context_file.size
                })
                paths_to_remove.remove(context_file.path)
            else:
                remaining_files.append(context_file)
        
        # Track files that weren't found in context
        not_found_files = [{"path": path, "error": "File not in context"} for path in paths_to_remove]
        
        # Update session
        session.context_files = remaining_files
        
        # Serialize context files with datetime handling
        context_files_data = []
        for cf in session.context_files:
            cf_dict = asdict(cf)
            cf_dict['added_at'] = cf.added_at.isoformat()
            context_files_data.append(cf_dict)
        
        # Update session in Redis
        await self.update_session(session_id,
            context_files=json.dumps(context_files_data),
            updated_at=datetime.now().isoformat()
        )
        
        return {
            "removed_count": len(removed_files),
            "not_found_count": len(not_found_files),
            "removed_files": removed_files,
            "not_found_files": not_found_files,
            "total_context_files": len(session.context_files),
            "total_context_size": sum(cf.size for cf in session.context_files)
        }
    
    async def get_context_files(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get context files for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of context file information
            
        Raises:
            ValueError: If session doesn't exist
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        return [
            {
                "path": cf.path,
                "name": cf.name,
                "size": cf.size,
                "language": cf.language,
                "added_at": cf.added_at.isoformat(),
                "is_modified": cf.is_modified,
                "metadata": cf.metadata
            }
            for cf in session.context_files
        ]
    
    async def clear_context_files(self, session_id: str) -> Dict[str, Any]:
        """
        Clear all context files from a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with operation results
            
        Raises:
            ValueError: If session doesn't exist
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        cleared_count = len(session.context_files)
        session.context_files = []
        
        # Update session in Redis
        await self.update_session(session_id,
            context_files=json.dumps([]),
            updated_at=datetime.now().isoformat()
        )
        
        return {
            "cleared_count": cleared_count,
            "total_context_files": 0,
            "total_context_size": 0
        }
    
    async def _update_context_files_in_redis(
        self, 
        session_id: str, 
        context_files_data: List[Dict[str, Any]]
    ) -> None:
        """
        Helper method for debounced context file updates.
        
        Args:
            session_id: Session identifier
            context_files_data: Serialized context files data
        """
        try:
            await self.update_session(session_id,
                context_files=json.dumps(context_files_data),
                updated_at=datetime.now().isoformat()
            )
            logger.debug(f"Updated context files for session {session_id}")
        except Exception as e:
            logger.error(f"Error updating context files in Redis: {e}")
    
    async def get_conversion_progress(self, session_id: str) -> Dict[str, Any]:
        """
        Get conversion progress for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with conversion progress information
        """
        try:
            progress = await conversion_tracking_service.get_session_progress(session_id)
            return progress.dict()
        except Exception as e:
            logger.error(f"Error getting conversion progress: {e}")
            return {
                "total_operations": 0,
                "converted_operations": 0,
                "failed_operations": 0,
                "pending_operations": 0,
                "conversion_percentage": 0.0,
                "success_rate": 0.0,
                "error": str(e)
            }
    
    async def get_conversion_operations(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent conversion operations for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of operations to return
            
        Returns:
            List of operation dictionaries
        """
        try:
            operations = await conversion_tracking_service.get_session_operations(
                session_id, 
                limit=limit
            )
            return [op.dict() for op in operations]
        except Exception as e:
            logger.error(f"Error getting conversion operations: {e}")
            return []
    
    async def get_context_stats(self, session_id: str) -> Dict[str, Any]:
        """
        Get context statistics for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with context statistics
            
        Raises:
            ValueError: If session doesn't exist
        """
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if not session.context_files:
            return {
                "total_files": 0,
                "total_size": 0,
                "average_file_size": 0,
                "languages": {},
                "oldest_file": None,
                "newest_file": None
            }
        
        # Calculate statistics
        total_files = len(session.context_files)
        total_size = sum(cf.size for cf in session.context_files)
        average_file_size = total_size / total_files if total_files > 0 else 0
        
        # Language distribution
        languages = {}
        for cf in session.context_files:
            languages[cf.language] = languages.get(cf.language, 0) + 1
        
        # Oldest and newest files
        sorted_files = sorted(session.context_files, key=lambda cf: cf.added_at)
        oldest_file = {
            "path": sorted_files[0].path,
            "added_at": sorted_files[0].added_at.isoformat()
        }
        newest_file = {
            "path": sorted_files[-1].path,
            "added_at": sorted_files[-1].added_at.isoformat()
        }
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "average_file_size": round(average_file_size, 2),
            "languages": languages,
            "oldest_file": oldest_file,
            "newest_file": newest_file
        }

    def _serialize_session(self, session: ChatSession) -> Dict[str, str]:
        """Serialize session object for Redis storage."""
        data = asdict(session)
        # Convert datetime objects to ISO strings
        data['created_at'] = session.created_at.isoformat()
        data['updated_at'] = session.updated_at.isoformat()
        # Convert list to JSON string
        data['selected_files'] = json.dumps(session.selected_files)
        # Convert context files to JSON string with datetime handling
        context_files_data = []
        for cf in session.context_files:
            cf_dict = asdict(cf)
            cf_dict['added_at'] = cf.added_at.isoformat()
            context_files_data.append(cf_dict)
        data['context_files'] = json.dumps(context_files_data)
        # Convert enum to string value
        data['status'] = session.status.value
        return {k: str(v) for k, v in data.items()}
    
    def _deserialize_session(self, data: Dict[str, str]) -> ChatSession:
        """Deserialize session data from Redis."""
        # Convert string values back to appropriate types
        session_data = dict(data)
        session_data['created_at'] = datetime.fromisoformat(data['created_at'])
        session_data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        session_data['message_count'] = int(data.get('message_count', 0))
        session_data['selected_files'] = json.loads(data.get('selected_files', '[]'))
        
        # Deserialize context files
        context_files_data = json.loads(data.get('context_files', '[]'))
        context_files = []
        for cf_data in context_files_data:
            # Convert datetime string back to datetime object
            cf_data['added_at'] = datetime.fromisoformat(cf_data['added_at'])
            context_files.append(ContextFile(**cf_data))
        session_data['context_files'] = context_files
        
        # Convert string back to enum
        status_value = data.get('status', SessionStatus.ACTIVE.value)
        session_data['status'] = SessionStatus(status_value)
        
        return ChatSession(**session_data)
    
    def _serialize_message(self, message: ChatMessage) -> Dict[str, str]:
        """Serialize message object for Redis storage."""
        data = asdict(message)
        # Convert datetime to ISO string
        data['timestamp'] = message.timestamp.isoformat()
        # Convert lists and dicts to JSON strings
        data['metadata'] = json.dumps(message.metadata) if message.metadata else '{}'
        data['context_files_used'] = json.dumps(message.context_files_used)
        data['shell_commands_converted'] = json.dumps(message.shell_commands_converted)
        return {k: str(v) if v is not None else '' for k, v in data.items()}
    
    def _deserialize_message(self, data: Dict[str, str]) -> ChatMessage:
        """Deserialize message data from Redis."""
        message_data = dict(data)
        message_data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        message_data['metadata'] = json.loads(data.get('metadata', '{}')) or None
        message_data['context_files_used'] = json.loads(data.get('context_files_used', '[]'))
        message_data['shell_commands_converted'] = json.loads(data.get('shell_commands_converted', '[]'))
        
        # Handle empty strings as None
        for key in ['conversion_notes']:
            if message_data.get(key) == '':
                message_data[key] = None
        
        return ChatMessage(**message_data)