"""
Session Persistence and Recovery Service
Provides enhanced session persistence, recovery, history, and sharing functionality.
"""

import json
import uuid
import gzip
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import redis
import logging

try:
    from ..config.settings import get_settings
    from ..services.cosmos_web_service import ChatSession, ChatMessage, ContextFile
except ImportError:
    from config.settings import get_settings
    from services.cosmos_web_service import ChatSession, ChatMessage, ContextFile

logger = logging.getLogger(__name__)


class SessionBackupStatus(str, Enum):
    """Session backup status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionShareType(str, Enum):
    """Session sharing type enumeration."""
    READ_ONLY = "read_only"
    COLLABORATIVE = "collaborative"
    PUBLIC = "public"


@dataclass
class SessionBackup:
    """Session backup data model."""
    backup_id: str
    session_id: str
    user_id: str
    backup_type: str  # 'manual', 'auto', 'export'
    status: SessionBackupStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    size_bytes: int = 0
    compressed_size_bytes: int = 0
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


@dataclass
class SessionShare:
    """Session sharing data model."""
    share_id: str
    session_id: str
    owner_id: str
    share_type: SessionShareType
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    allowed_users: List[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.allowed_users is None:
            self.allowed_users = []


@dataclass
class SessionExport:
    """Session export data model."""
    export_id: str
    session_id: str
    user_id: str
    export_format: str  # 'json', 'markdown', 'html', 'pdf'
    created_at: datetime
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class SessionPersistenceService:
    """
    Enhanced session persistence and recovery service.
    
    Provides:
    - Automatic session backups and recovery
    - Session history management
    - Session export functionality
    - Session sharing and collaboration
    - Connection recovery mechanisms
    """
    
    def __init__(self):
        """Initialize the session persistence service."""
        self.settings = get_settings()
        
        # Initialize Redis client
        redis_config = {
            'host': self.settings.redis_host,
            'port': self.settings.redis_port,
            'db': self.settings.redis_db,
            'decode_responses': True,
            'username': self.settings.redis_username,
            'password': self.settings.redis_password,
            'socket_timeout': 30,
            'socket_connect_timeout': 30,
        }
        
        if self.settings.redis_ssl:
            redis_config.update({
                'ssl': True,
                'ssl_cert_reqs': None,
                'ssl_check_hostname': False,
                'ssl_ca_certs': None,
            })
        
        if hasattr(self.settings, 'redis_url') and self.settings.redis_url:
            self.redis_client = redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=30,
                socket_timeout=30
            )
        else:
            self.redis_client = redis.Redis(**redis_config)
        
        # Configuration
        self.backup_ttl = 2592000  # 30 days
        self.share_ttl = 604800    # 7 days default
        self.export_ttl = 86400    # 1 day
        self.auto_backup_interval = 3600  # 1 hour
        
        # Key prefixes
        self.backup_prefix = "cosmos:backup:"
        self.share_prefix = "cosmos:share:"
        self.export_prefix = "cosmos:export:"
        self.history_prefix = "cosmos:history:"
        self.recovery_prefix = "cosmos:recovery:"
        
    async def create_session_backup(
        self,
        session_id: str,
        user_id: str,
        backup_type: str = "manual",
        include_messages: bool = True,
        include_context: bool = True
    ) -> str:
        """
        Create a backup of a chat session.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            backup_type: Type of backup ('manual', 'auto', 'export')
            include_messages: Whether to include messages in backup
            include_context: Whether to include context files in backup
            
        Returns:
            Backup ID
            
        Raises:
            ValueError: If session doesn't exist or backup fails
        """
        try:
            # Import here to avoid circular imports
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            # Get session data
            session = await cosmos_service.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            
            # Verify user ownership
            if session.user_id != user_id:
                raise ValueError("Unauthorized: User does not own this session")
            
            # Generate backup ID
            backup_id = str(uuid.uuid4())
            
            # Create backup record
            backup = SessionBackup(
                backup_id=backup_id,
                session_id=session_id,
                user_id=user_id,
                backup_type=backup_type,
                status=SessionBackupStatus.PENDING,
                created_at=datetime.now()
            )
            
            # Store backup record
            backup_key = f"{self.backup_prefix}{backup_id}"
            backup_data = self._serialize_backup(backup)
            self.redis_client.hset(backup_key, mapping=backup_data)
            self.redis_client.expire(backup_key, self.backup_ttl)
            
            # Add to user's backup list
            user_backups_key = f"{self.backup_prefix}user:{user_id}"
            self.redis_client.sadd(user_backups_key, backup_id)
            self.redis_client.expire(user_backups_key, self.backup_ttl)
            
            # Start backup process
            await self._perform_backup(backup_id, session, include_messages, include_context)
            
            return backup_id
            
        except Exception as e:
            logger.error(f"Error creating session backup: {e}")
            raise ValueError(f"Failed to create backup: {str(e)}")
    
    async def _perform_backup(
        self,
        backup_id: str,
        session: ChatSession,
        include_messages: bool,
        include_context: bool
    ) -> None:
        """
        Perform the actual backup process.
        
        Args:
            backup_id: Backup identifier
            session: Session to backup
            include_messages: Whether to include messages
            include_context: Whether to include context files
        """
        try:
            # Update backup status
            backup_key = f"{self.backup_prefix}{backup_id}"
            self.redis_client.hset(backup_key, "status", SessionBackupStatus.IN_PROGRESS.value)
            
            # Prepare backup data
            backup_data = {
                "session": asdict(session),
                "messages": [],
                "context_files": [],
                "metadata": {
                    "backup_id": backup_id,
                    "created_at": datetime.now().isoformat(),
                    "include_messages": include_messages,
                    "include_context": include_context
                }
            }
            
            # Handle datetime serialization
            backup_data["session"]["created_at"] = session.created_at.isoformat()
            backup_data["session"]["updated_at"] = session.updated_at.isoformat()
            
            # Serialize context files
            if session.context_files:
                for cf in session.context_files:
                    cf_dict = asdict(cf)
                    cf_dict["added_at"] = cf.added_at.isoformat()
                    backup_data["session"]["context_files"] = backup_data["session"].get("context_files", [])
                    backup_data["session"]["context_files"].append(cf_dict)
            
            # Include messages if requested
            if include_messages:
                from .cosmos_web_service import CosmosWebService
                cosmos_service = CosmosWebService()
                messages = await cosmos_service.get_session_messages(session.id, limit=1000)
                
                for message in messages:
                    msg_dict = asdict(message)
                    msg_dict["timestamp"] = message.timestamp.isoformat()
                    backup_data["messages"].append(msg_dict)
            
            # Include context file content if requested
            if include_context and session.context_files:
                try:
                    from .redis_repo_manager import RedisRepoManager
                    if session.repository_url:
                        repo_manager = RedisRepoManager(
                            repo_url=session.repository_url,
                            branch=session.branch or "main",
                            user_tier="free",  # TODO: Get from user context
                            username=session.user_id
                        )
                        
                        for cf in session.context_files:
                            try:
                                content = repo_manager.get_file_content(cf.path)
                                backup_data["context_files"].append({
                                    "path": cf.path,
                                    "content": content,
                                    "metadata": asdict(cf)
                                })
                            except Exception as e:
                                logger.warning(f"Could not backup context file {cf.path}: {e}")
                except Exception as e:
                    logger.warning(f"Could not backup context files: {e}")
            
            # Serialize and compress backup data
            json_data = json.dumps(backup_data, indent=2)
            original_size = len(json_data.encode('utf-8'))
            
            # Compress the data
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            compressed_size = len(compressed_data)
            
            # Encode for storage
            encoded_data = base64.b64encode(compressed_data).decode('utf-8')
            
            # Store compressed backup
            backup_data_key = f"{self.backup_prefix}data:{backup_id}"
            self.redis_client.set(backup_data_key, encoded_data)
            self.redis_client.expire(backup_data_key, self.backup_ttl)
            
            # Update backup record
            updates = {
                "status": SessionBackupStatus.COMPLETED.value,
                "completed_at": datetime.now().isoformat(),
                "size_bytes": str(original_size),
                "compressed_size_bytes": str(compressed_size)
            }
            self.redis_client.hset(backup_key, mapping=updates)
            
            logger.info(f"Backup {backup_id} completed successfully. Size: {original_size} -> {compressed_size} bytes")
            
        except Exception as e:
            logger.error(f"Error performing backup {backup_id}: {e}")
            
            # Update backup status to failed
            self.redis_client.hset(backup_key, mapping={
                "status": SessionBackupStatus.FAILED.value,
                "error_message": str(e)
            })
            raise
    
    async def restore_session_from_backup(
        self,
        backup_id: str,
        user_id: str,
        new_session_id: Optional[str] = None
    ) -> str:
        """
        Restore a session from backup.
        
        Args:
            backup_id: Backup identifier
            user_id: User identifier
            new_session_id: Optional new session ID (generates if not provided)
            
        Returns:
            New session ID
            
        Raises:
            ValueError: If backup doesn't exist or restore fails
        """
        try:
            # Get backup record
            backup = await self.get_backup(backup_id)
            if not backup:
                raise ValueError(f"Backup {backup_id} not found")
            
            # Verify user ownership
            if backup.user_id != user_id:
                raise ValueError("Unauthorized: User does not own this backup")
            
            # Check backup status
            if backup.status != SessionBackupStatus.COMPLETED:
                raise ValueError(f"Backup is not completed (status: {backup.status})")
            
            # Get backup data
            backup_data_key = f"{self.backup_prefix}data:{backup_id}"
            encoded_data = self.redis_client.get(backup_data_key)
            if not encoded_data:
                raise ValueError("Backup data not found")
            
            # Decode and decompress
            compressed_data = base64.b64decode(encoded_data.encode('utf-8'))
            json_data = gzip.decompress(compressed_data).decode('utf-8')
            backup_data = json.loads(json_data)
            
            # Generate new session ID if not provided
            if not new_session_id:
                new_session_id = str(uuid.uuid4())
            
            # Restore session
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            # Create new session with restored data
            session_data = backup_data["session"]
            session_data["id"] = new_session_id
            session_data["created_at"] = datetime.now().isoformat()
            session_data["updated_at"] = datetime.now().isoformat()
            
            # Create session
            restored_session_id = await cosmos_service.create_session(
                user_id=user_id,
                title=f"Restored: {session_data.get('title', 'Untitled')}",
                repository_url=session_data.get('repository_url'),
                branch=session_data.get('branch'),
                model=session_data.get('model', 'gemini')
            )
            
            # Restore messages if available
            if backup_data.get("messages"):
                for msg_data in backup_data["messages"]:
                    await cosmos_service.add_message(
                        session_id=restored_session_id,
                        role=msg_data["role"],
                        content=msg_data["content"],
                        metadata=msg_data.get("metadata"),
                        context_files_used=msg_data.get("context_files_used", []),
                        shell_commands_converted=msg_data.get("shell_commands_converted", []),
                        conversion_notes=msg_data.get("conversion_notes")
                    )
            
            # Restore context files if available
            if backup_data.get("context_files"):
                context_file_paths = [cf["path"] for cf in backup_data["context_files"]]
                if context_file_paths:
                    try:
                        await cosmos_service.add_context_files(
                            session_id=restored_session_id,
                            file_paths=context_file_paths,
                            repository_url=session_data.get('repository_url'),
                            branch=session_data.get('branch')
                        )
                    except Exception as e:
                        logger.warning(f"Could not restore context files: {e}")
            
            logger.info(f"Session restored from backup {backup_id} as {restored_session_id}")
            return restored_session_id
            
        except Exception as e:
            logger.error(f"Error restoring session from backup {backup_id}: {e}")
            raise ValueError(f"Failed to restore session: {str(e)}")
    
    async def get_backup(self, backup_id: str) -> Optional[SessionBackup]:
        """
        Get backup information.
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            SessionBackup object or None if not found
        """
        backup_key = f"{self.backup_prefix}{backup_id}"
        backup_data = self.redis_client.hgetall(backup_key)
        
        if not backup_data:
            return None
        
        return self._deserialize_backup(backup_data)
    
    async def get_user_backups(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionBackup]:
        """
        Get backups for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of backups to return
            offset: Number of backups to skip
            
        Returns:
            List of SessionBackup objects
        """
        user_backups_key = f"{self.backup_prefix}user:{user_id}"
        backup_ids = self.redis_client.smembers(user_backups_key)
        
        backups = []
        for backup_id in backup_ids:
            backup = await self.get_backup(backup_id)
            if backup:
                backups.append(backup)
        
        # Sort by created_at descending
        backups.sort(key=lambda b: b.created_at, reverse=True)
        
        # Apply pagination
        start = offset
        end = offset + limit
        return backups[start:end]
    
    async def delete_backup(self, backup_id: str, user_id: str) -> bool:
        """
        Delete a backup.
        
        Args:
            backup_id: Backup identifier
            user_id: User identifier
            
        Returns:
            True if successful, False if backup not found
        """
        # Get backup to verify ownership
        backup = await self.get_backup(backup_id)
        if not backup or backup.user_id != user_id:
            return False
        
        # Delete backup data and record
        pipe = self.redis_client.pipeline()
        
        backup_key = f"{self.backup_prefix}{backup_id}"
        backup_data_key = f"{self.backup_prefix}data:{backup_id}"
        user_backups_key = f"{self.backup_prefix}user:{user_id}"
        
        pipe.delete(backup_key)
        pipe.delete(backup_data_key)
        pipe.srem(user_backups_key, backup_id)
        
        pipe.execute()
        
        return True
    
    def _serialize_backup(self, backup: SessionBackup) -> Dict[str, str]:
        """Serialize backup object for Redis storage."""
        data = asdict(backup)
        data['created_at'] = backup.created_at.isoformat()
        if backup.completed_at:
            data['completed_at'] = backup.completed_at.isoformat()
        if backup.metadata:
            data['metadata'] = json.dumps(backup.metadata)
        return {k: str(v) for k, v in data.items()}
    
    def _deserialize_backup(self, data: Dict[str, str]) -> SessionBackup:
        """Deserialize backup data from Redis."""
        backup_data = dict(data)
        
        # Convert string values back to appropriate types
        backup_data['status'] = SessionBackupStatus(backup_data['status'])
        backup_data['created_at'] = datetime.fromisoformat(backup_data['created_at'])
        
        if backup_data.get('completed_at'):
            backup_data['completed_at'] = datetime.fromisoformat(backup_data['completed_at'])
        else:
            backup_data['completed_at'] = None
        
        backup_data['size_bytes'] = int(backup_data.get('size_bytes', 0))
        backup_data['compressed_size_bytes'] = int(backup_data.get('compressed_size_bytes', 0))
        
        if backup_data.get('metadata'):
            backup_data['metadata'] = json.loads(backup_data['metadata'])
        else:
            backup_data['metadata'] = None
        
        return SessionBackup(**backup_data)
    
    async def create_session_share(
        self,
        session_id: str,
        owner_id: str,
        share_type: SessionShareType = SessionShareType.READ_ONLY,
        expires_in_hours: Optional[int] = None,
        allowed_users: Optional[List[str]] = None
    ) -> str:
        """
        Create a shareable link for a session.
        
        Args:
            session_id: Session identifier
            owner_id: Owner user identifier
            share_type: Type of sharing (read_only, collaborative, public)
            expires_in_hours: Hours until expiration (None for no expiration)
            allowed_users: List of allowed user IDs (for collaborative sharing)
            
        Returns:
            Share ID
            
        Raises:
            ValueError: If session doesn't exist or sharing fails
        """
        try:
            # Verify session exists and user owns it
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            session = await cosmos_service.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            
            if session.user_id != owner_id:
                raise ValueError("Unauthorized: User does not own this session")
            
            # Generate share ID
            share_id = str(uuid.uuid4())
            
            # Calculate expiration
            expires_at = None
            if expires_in_hours:
                expires_at = datetime.now() + timedelta(hours=expires_in_hours)
            
            # Create share record
            share = SessionShare(
                share_id=share_id,
                session_id=session_id,
                owner_id=owner_id,
                share_type=share_type,
                created_at=datetime.now(),
                expires_at=expires_at,
                allowed_users=allowed_users or []
            )
            
            # Store share record
            share_key = f"{self.share_prefix}{share_id}"
            share_data = self._serialize_share(share)
            self.redis_client.hset(share_key, mapping=share_data)
            
            # Set expiration if specified
            if expires_at:
                ttl = int((expires_at - datetime.now()).total_seconds())
                self.redis_client.expire(share_key, ttl)
            else:
                self.redis_client.expire(share_key, self.share_ttl)
            
            # Add to session's share list
            session_shares_key = f"{self.share_prefix}session:{session_id}"
            self.redis_client.sadd(session_shares_key, share_id)
            self.redis_client.expire(session_shares_key, self.share_ttl)
            
            # Add to owner's share list
            owner_shares_key = f"{self.share_prefix}owner:{owner_id}"
            self.redis_client.sadd(owner_shares_key, share_id)
            self.redis_client.expire(owner_shares_key, self.share_ttl)
            
            logger.info(f"Created share {share_id} for session {session_id}")
            return share_id
            
        except Exception as e:
            logger.error(f"Error creating session share: {e}")
            raise ValueError(f"Failed to create share: {str(e)}")
    
    async def get_shared_session(
        self,
        share_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a shared session by share ID.
        
        Args:
            share_id: Share identifier
            user_id: Requesting user identifier
            
        Returns:
            Session data if accessible, None otherwise
        """
        try:
            # Get share record
            share = await self.get_share(share_id)
            if not share:
                return None
            
            # Check expiration
            if share.expires_at and datetime.now() > share.expires_at:
                return None
            
            # Check access permissions
            if not self._check_share_access(share, user_id):
                return None
            
            # Update access tracking
            await self._update_share_access(share_id)
            
            # Get session data
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            session = await cosmos_service.get_session(share.session_id)
            if not session:
                return None
            
            # Get messages (limited for shared sessions)
            messages = await cosmos_service.get_session_messages(
                share.session_id, 
                limit=100  # Limit messages for shared sessions
            )
            
            # Prepare response based on share type
            response = {
                "share_id": share_id,
                "share_type": share.share_type.value,
                "session": {
                    "id": session.id,
                    "title": session.title,
                    "repository_url": session.repository_url,
                    "branch": session.branch,
                    "model": session.model,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "message_count": session.message_count
                },
                "messages": [
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                        "context_files_used": msg.context_files_used
                    }
                    for msg in messages
                ],
                "context_files": [
                    {
                        "path": cf.path,
                        "name": cf.name,
                        "size": cf.size,
                        "language": cf.language,
                        "added_at": cf.added_at.isoformat()
                    }
                    for cf in session.context_files
                ],
                "permissions": {
                    "can_read": True,
                    "can_write": share.share_type == SessionShareType.COLLABORATIVE,
                    "can_export": share.share_type != SessionShareType.READ_ONLY
                }
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting shared session {share_id}: {e}")
            return None
    
    async def get_share(self, share_id: str) -> Optional[SessionShare]:
        """
        Get share information.
        
        Args:
            share_id: Share identifier
            
        Returns:
            SessionShare object or None if not found
        """
        share_key = f"{self.share_prefix}{share_id}"
        share_data = self.redis_client.hgetall(share_key)
        
        if not share_data:
            return None
        
        return self._deserialize_share(share_data)
    
    async def revoke_share(self, share_id: str, owner_id: str) -> bool:
        """
        Revoke a session share.
        
        Args:
            share_id: Share identifier
            owner_id: Owner user identifier
            
        Returns:
            True if successful, False if share not found
        """
        # Get share to verify ownership
        share = await self.get_share(share_id)
        if not share or share.owner_id != owner_id:
            return False
        
        # Delete share record and references
        pipe = self.redis_client.pipeline()
        
        share_key = f"{self.share_prefix}{share_id}"
        session_shares_key = f"{self.share_prefix}session:{share.session_id}"
        owner_shares_key = f"{self.share_prefix}owner:{owner_id}"
        
        pipe.delete(share_key)
        pipe.srem(session_shares_key, share_id)
        pipe.srem(owner_shares_key, share_id)
        
        pipe.execute()
        
        return True
    
    def _check_share_access(self, share: SessionShare, user_id: str) -> bool:
        """Check if user has access to shared session."""
        # Owner always has access
        if share.owner_id == user_id:
            return True
        
        # Public shares are accessible to everyone
        if share.share_type == SessionShareType.PUBLIC:
            return True
        
        # Check allowed users list
        if share.allowed_users and user_id in share.allowed_users:
            return True
        
        return False
    
    async def _update_share_access(self, share_id: str) -> None:
        """Update share access tracking."""
        share_key = f"{self.share_prefix}{share_id}"
        pipe = self.redis_client.pipeline()
        pipe.hincrby(share_key, "access_count", 1)
        pipe.hset(share_key, "last_accessed", datetime.now().isoformat())
        pipe.execute()
    
    async def export_session(
        self,
        session_id: str,
        user_id: str,
        export_format: str = "json",
        include_context: bool = True
    ) -> str:
        """
        Export a session to various formats.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            export_format: Export format ('json', 'markdown', 'html')
            include_context: Whether to include context files
            
        Returns:
            Export ID
            
        Raises:
            ValueError: If session doesn't exist or export fails
        """
        try:
            # Verify session access
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            session = await cosmos_service.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            
            # Check if user has access (owner or shared access)
            has_access = session.user_id == user_id
            if not has_access:
                # Check if user has shared access
                session_shares_key = f"{self.share_prefix}session:{session_id}"
                share_ids = self.redis_client.smembers(session_shares_key)
                
                for share_id in share_ids:
                    share = await self.get_share(share_id)
                    if share and self._check_share_access(share, user_id):
                        has_access = True
                        break
            
            if not has_access:
                raise ValueError("Unauthorized: User does not have access to this session")
            
            # Generate export ID
            export_id = str(uuid.uuid4())
            
            # Create export record
            export_record = SessionExport(
                export_id=export_id,
                session_id=session_id,
                user_id=user_id,
                export_format=export_format,
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=self.export_ttl)
            )
            
            # Store export record
            export_key = f"{self.export_prefix}{export_id}"
            export_data = self._serialize_export(export_record)
            self.redis_client.hset(export_key, mapping=export_data)
            self.redis_client.expire(export_key, self.export_ttl)
            
            # Generate export content
            export_content = await self._generate_export_content(
                session, export_format, include_context
            )
            
            # Store export content
            export_content_key = f"{self.export_prefix}content:{export_id}"
            self.redis_client.set(export_content_key, export_content)
            self.redis_client.expire(export_content_key, self.export_ttl)
            
            logger.info(f"Created export {export_id} for session {session_id}")
            return export_id
            
        except Exception as e:
            logger.error(f"Error exporting session: {e}")
            raise ValueError(f"Failed to export session: {str(e)}")
    
    async def get_export_content(self, export_id: str, user_id: str) -> Optional[str]:
        """
        Get export content.
        
        Args:
            export_id: Export identifier
            user_id: User identifier
            
        Returns:
            Export content or None if not found/unauthorized
        """
        try:
            # Get export record
            export_record = await self.get_export(export_id)
            if not export_record or export_record.user_id != user_id:
                return None
            
            # Check expiration
            if export_record.expires_at and datetime.now() > export_record.expires_at:
                return None
            
            # Get export content
            export_content_key = f"{self.export_prefix}content:{export_id}"
            content = self.redis_client.get(export_content_key)
            
            return content
            
        except Exception as e:
            logger.error(f"Error getting export content {export_id}: {e}")
            return None
    
    async def get_export(self, export_id: str) -> Optional[SessionExport]:
        """
        Get export information.
        
        Args:
            export_id: Export identifier
            
        Returns:
            SessionExport object or None if not found
        """
        export_key = f"{self.export_prefix}{export_id}"
        export_data = self.redis_client.hgetall(export_key)
        
        if not export_data:
            return None
        
        return self._deserialize_export(export_data)
    
    async def _generate_export_content(
        self,
        session: ChatSession,
        export_format: str,
        include_context: bool
    ) -> str:
        """
        Generate export content in the specified format.
        
        Args:
            session: Session to export
            export_format: Format to export to
            include_context: Whether to include context files
            
        Returns:
            Export content as string
        """
        try:
            from .cosmos_web_service import CosmosWebService
            cosmos_service = CosmosWebService()
            
            # Get session messages
            messages = await cosmos_service.get_session_messages(session.id, limit=1000)
            
            if export_format == "json":
                return await self._generate_json_export(session, messages, include_context)
            elif export_format == "markdown":
                return await self._generate_markdown_export(session, messages, include_context)
            elif export_format == "html":
                return await self._generate_html_export(session, messages, include_context)
            else:
                raise ValueError(f"Unsupported export format: {export_format}")
                
        except Exception as e:
            logger.error(f"Error generating export content: {e}")
            raise
    
    async def _generate_json_export(
        self,
        session: ChatSession,
        messages: List[ChatMessage],
        include_context: bool
    ) -> str:
        """Generate JSON export."""
        export_data = {
            "session": {
                "id": session.id,
                "title": session.title,
                "repository_url": session.repository_url,
                "branch": session.branch,
                "model": session.model,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": session.message_count
            },
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "context_files_used": msg.context_files_used,
                    "shell_commands_converted": msg.shell_commands_converted,
                    "conversion_notes": msg.conversion_notes,
                    "metadata": msg.metadata
                }
                for msg in messages
            ],
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "format": "json",
                "include_context": include_context
            }
        }
        
        if include_context and session.context_files:
            export_data["context_files"] = [
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
        
        return json.dumps(export_data, indent=2)
    
    async def _generate_markdown_export(
        self,
        session: ChatSession,
        messages: List[ChatMessage],
        include_context: bool
    ) -> str:
        """Generate Markdown export."""
        lines = [
            f"# {session.title}",
            "",
            f"**Session ID:** {session.id}",
            f"**Repository:** {session.repository_url or 'None'}",
            f"**Branch:** {session.branch or 'None'}",
            f"**Model:** {session.model}",
            f"**Created:** {session.created_at.isoformat()}",
            f"**Messages:** {len(messages)}",
            ""
        ]
        
        if include_context and session.context_files:
            lines.extend([
                "## Context Files",
                ""
            ])
            for cf in session.context_files:
                lines.append(f"- `{cf.path}` ({cf.language}, {cf.size} bytes)")
            lines.append("")
        
        lines.extend([
            "## Conversation",
            ""
        ])
        
        for msg in messages:
            role_emoji = "🧑" if msg.role == "user" else "🤖"
            lines.extend([
                f"### {role_emoji} {msg.role.title()} - {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                msg.content,
                ""
            ])
            
            if msg.context_files_used:
                lines.extend([
                    "**Context files used:**",
                    ""
                ])
                for file_path in msg.context_files_used:
                    lines.append(f"- `{file_path}`")
                lines.append("")
        
        lines.extend([
            "---",
            f"*Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        ])
        
        return "\n".join(lines)
    
    async def _generate_html_export(
        self,
        session: ChatSession,
        messages: List[ChatMessage],
        include_context: bool
    ) -> str:
        """Generate HTML export."""
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            f"<title>{session.title}</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 40px; }",
            ".header { border-bottom: 2px solid #ccc; padding-bottom: 20px; margin-bottom: 30px; }",
            ".message { margin: 20px 0; padding: 15px; border-radius: 8px; }",
            ".user { background-color: #e3f2fd; }",
            ".assistant { background-color: #f3e5f5; }",
            ".timestamp { font-size: 0.9em; color: #666; }",
            ".context-files { background-color: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 4px; }",
            "pre { background-color: #f8f8f8; padding: 10px; border-radius: 4px; overflow-x: auto; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='header'>",
            f"<h1>{session.title}</h1>",
            f"<p><strong>Session ID:</strong> {session.id}</p>",
            f"<p><strong>Repository:</strong> {session.repository_url or 'None'}</p>",
            f"<p><strong>Branch:</strong> {session.branch or 'None'}</p>",
            f"<p><strong>Model:</strong> {session.model}</p>",
            f"<p><strong>Created:</strong> {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>",
            f"<p><strong>Messages:</strong> {len(messages)}</p>",
            "</div>"
        ]
        
        if include_context and session.context_files:
            html_parts.extend([
                "<h2>Context Files</h2>",
                "<div class='context-files'>",
                "<ul>"
            ])
            for cf in session.context_files:
                html_parts.append(f"<li><code>{cf.path}</code> ({cf.language}, {cf.size} bytes)</li>")
            html_parts.extend([
                "</ul>",
                "</div>"
            ])
        
        html_parts.append("<h2>Conversation</h2>")
        
        for msg in messages:
            role_class = msg.role
            role_emoji = "🧑" if msg.role == "user" else "🤖"
            
            html_parts.extend([
                f"<div class='message {role_class}'>",
                f"<h3>{role_emoji} {msg.role.title()}</h3>",
                f"<div class='timestamp'>{msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</div>",
                f"<div>{msg.content.replace(chr(10), '<br>')}</div>"
            ])
            
            if msg.context_files_used:
                html_parts.extend([
                    "<div class='context-files'>",
                    "<strong>Context files used:</strong>",
                    "<ul>"
                ])
                for file_path in msg.context_files_used:
                    html_parts.append(f"<li><code>{file_path}</code></li>")
                html_parts.extend([
                    "</ul>",
                    "</div>"
                ])
            
            html_parts.append("</div>")
        
        html_parts.extend([
            "<hr>",
            f"<p><em>Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>",
            "</body>",
            "</html>"
        ])
        
        return "\n".join(html_parts)
    
    def _serialize_share(self, share: SessionShare) -> Dict[str, str]:
        """Serialize share object for Redis storage."""
        data = asdict(share)
        data['created_at'] = share.created_at.isoformat()
        if share.expires_at:
            data['expires_at'] = share.expires_at.isoformat()
        if share.last_accessed:
            data['last_accessed'] = share.last_accessed.isoformat()
        if share.allowed_users:
            data['allowed_users'] = json.dumps(share.allowed_users)
        if share.metadata:
            data['metadata'] = json.dumps(share.metadata)
        return {k: str(v) for k, v in data.items()}
    
    def _deserialize_share(self, data: Dict[str, str]) -> SessionShare:
        """Deserialize share data from Redis."""
        share_data = dict(data)
        
        share_data['share_type'] = SessionShareType(share_data['share_type'])
        share_data['created_at'] = datetime.fromisoformat(share_data['created_at'])
        
        if share_data.get('expires_at'):
            share_data['expires_at'] = datetime.fromisoformat(share_data['expires_at'])
        else:
            share_data['expires_at'] = None
        
        if share_data.get('last_accessed'):
            share_data['last_accessed'] = datetime.fromisoformat(share_data['last_accessed'])
        else:
            share_data['last_accessed'] = None
        
        share_data['access_count'] = int(share_data.get('access_count', 0))
        
        if share_data.get('allowed_users'):
            share_data['allowed_users'] = json.loads(share_data['allowed_users'])
        else:
            share_data['allowed_users'] = []
        
        if share_data.get('metadata'):
            share_data['metadata'] = json.loads(share_data['metadata'])
        else:
            share_data['metadata'] = None
        
        return SessionShare(**share_data)
    
    def _serialize_export(self, export: SessionExport) -> Dict[str, str]:
        """Serialize export object for Redis storage."""
        data = asdict(export)
        data['created_at'] = export.created_at.isoformat()
        if export.expires_at:
            data['expires_at'] = export.expires_at.isoformat()
        if export.metadata:
            data['metadata'] = json.dumps(export.metadata)
        return {k: str(v) for k, v in data.items()}
    
    def _deserialize_export(self, data: Dict[str, str]) -> SessionExport:
        """Deserialize export data from Redis."""
        export_data = dict(data)
        
        export_data['created_at'] = datetime.fromisoformat(export_data['created_at'])
        
        if export_data.get('expires_at'):
            export_data['expires_at'] = datetime.fromisoformat(export_data['expires_at'])
        else:
            export_data['expires_at'] = None
        
        if export_data.get('metadata'):
            export_data['metadata'] = json.loads(export_data['metadata'])
        else:
            export_data['metadata'] = None
        
        return SessionExport(**export_data)

# Global service instance
session_persistence_service = SessionPersistenceService()