"""
Cosmos Web Service Foundation
Provides web-compatible interface to Cosmos AI coding assistant functionality.
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
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from config.key_manager import key_manager
    from config.cosmos_models import MODEL_ALIASES
    from services.conversion_tracking_service import conversion_tracking_service
    from services.performance_optimization_service import get_performance_service, cached_response
    from services.optimized_repo_cache import get_optimized_repo_cache
    from services.chat_analytics_service import chat_analytics_service


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
    
    def __init__(self):
        """Initialize the Cosmos Web Service."""
        self.settings = get_settings()
        self.key_manager = key_manager
        
        # Initialize performance optimization services
        self.performance_service = get_performance_service()
        self.repo_cache = get_optimized_repo_cache()
        
        # Initialize analytics service
        self.analytics_service = chat_analytics_service
        
        # Use optimized Redis client from performance service
        self.redis_client = self.performance_service.get_redis_client("cosmos_web")
        
        # Session configuration
        self.session_ttl = 86400  # 24 hours
        self.message_ttl = 604800  # 7 days
        
        # Key prefixes for Redis
        self.session_prefix = "cosmos:session:"
        self.message_prefix = "cosmos:message:"
        self.user_sessions_prefix = "cosmos:user_sessions:"
    
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