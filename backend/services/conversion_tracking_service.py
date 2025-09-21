"""
Conversion Tracking Service

Service for tracking CLI-to-web conversion operations, progress monitoring,
and effectiveness metrics collection.
"""

import uuid
import json
import redis
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..models.api.conversion_tracking import (
        ConversionOperation, ConversionProgress, ConversionMetrics,
        ConversionNote, ConversionReport, ConversionType, ConversionStatus,
        ConversionPriority, ConversionRequest, ConversionUpdateRequest
    )
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from models.api.conversion_tracking import (
        ConversionOperation, ConversionProgress, ConversionMetrics,
        ConversionNote, ConversionReport, ConversionType, ConversionStatus,
        ConversionPriority, ConversionRequest, ConversionUpdateRequest
    )

logger = logging.getLogger(__name__)


class ConversionTrackingService:
    """
    Service for tracking progressive shell-to-web conversion operations.
    
    Provides functionality for:
    - Tracking individual conversion operations
    - Monitoring conversion progress and effectiveness
    - Collecting metrics and generating reports
    - Managing conversion notes and documentation
    """
    
    def __init__(self):
        """Initialize the conversion tracking service."""
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
        
        # Use Redis URL if available (for cloud connections)
        if hasattr(self.settings, 'redis_url') and self.settings.redis_url:
            self.redis_client = redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=30,
                socket_timeout=30
            )
        else:
            self.redis_client = redis.Redis(**redis_config)
        
        # Redis key prefixes
        self.operation_prefix = "conversion:operation:"
        self.session_progress_prefix = "conversion:session_progress:"
        self.global_progress_prefix = "conversion:global_progress"
        self.metrics_prefix = "conversion:metrics:"
        self.notes_prefix = "conversion:note:"
        self.daily_stats_prefix = "conversion:daily:"
        
        # TTL settings (in seconds)
        self.operation_ttl = 30 * 24 * 3600  # 30 days
        self.progress_ttl = 7 * 24 * 3600    # 7 days
        self.metrics_ttl = 90 * 24 * 3600    # 90 days
        
        logger.info("ConversionTrackingService initialized")
    
    async def create_operation(self, request: ConversionRequest) -> str:
        """
        Create a new conversion operation.
        
        Args:
            request: Conversion request details
            
        Returns:
            Operation ID
        """
        try:
            # Generate operation ID
            operation_id = str(uuid.uuid4())
            
            # Create operation object
            operation = ConversionOperation(
                id=operation_id,
                operation_type=request.operation_type,
                original_command=request.original_command,
                session_id=request.session_id,
                user_id=request.user_id,
                priority=request.priority,
                context_files=request.context_files,
                metadata=request.metadata or {}
            )
            
            # Store operation in Redis
            operation_key = f"{self.operation_prefix}{operation_id}"
            operation_data = self._serialize_operation(operation)
            
            pipe = self.redis_client.pipeline()
            pipe.hset(operation_key, mapping=operation_data)
            pipe.expire(operation_key, self.operation_ttl)
            
            # Add to session operations list
            session_ops_key = f"conversion:session_ops:{request.session_id}"
            pipe.sadd(session_ops_key, operation_id)
            pipe.expire(session_ops_key, self.operation_ttl)
            
            # Add to user operations list
            user_ops_key = f"conversion:user_ops:{request.user_id}"
            pipe.sadd(user_ops_key, operation_id)
            pipe.expire(user_ops_key, self.operation_ttl)
            
            # Update daily statistics
            today = datetime.now().strftime("%Y-%m-%d")
            daily_key = f"{self.daily_stats_prefix}{today}"
            pipe.hincrby(daily_key, "total_operations", 1)
            pipe.hincrby(daily_key, f"type_{request.operation_type.value}", 1)
            pipe.hincrby(daily_key, f"priority_{request.priority.value}", 1)
            pipe.expire(daily_key, self.metrics_ttl)
            
            pipe.execute()
            
            # Update progress tracking
            await self._update_session_progress(request.session_id)
            await self._update_global_progress()
            
            logger.info(f"Created conversion operation: {operation_id}")
            return operation_id
            
        except Exception as e:
            logger.error(f"Error creating conversion operation: {e}")
            raise
    
    async def update_operation(self, request: ConversionUpdateRequest) -> bool:
        """
        Update an existing conversion operation.
        
        Args:
            request: Update request details
            
        Returns:
            True if successful, False if operation not found
        """
        try:
            operation_key = f"{self.operation_prefix}{request.operation_id}"
            
            # Check if operation exists
            if not self.redis_client.exists(operation_key):
                logger.warning(f"Operation not found: {request.operation_id}")
                return False
            
            # Get current operation data
            current_data = self.redis_client.hgetall(operation_key)
            operation = self._deserialize_operation(current_data)
            
            # Update fields
            updates = {}
            if request.status is not None:
                operation.status = request.status
                updates['status'] = request.status.value
                
                # Set timing based on status
                if request.status == ConversionStatus.IN_PROGRESS and not operation.started_at:
                    operation.started_at = datetime.now()
                    updates['started_at'] = operation.started_at.isoformat()
                elif request.status == ConversionStatus.COMPLETED and not operation.completed_at:
                    operation.completed_at = datetime.now()
                    updates['completed_at'] = operation.completed_at.isoformat()
            
            if request.converted_equivalent is not None:
                operation.converted_equivalent = request.converted_equivalent
                updates['converted_equivalent'] = request.converted_equivalent
            
            if request.conversion_notes is not None:
                operation.conversion_notes = request.conversion_notes
                updates['conversion_notes'] = request.conversion_notes
            
            if request.error_message is not None:
                operation.error_message = request.error_message
                updates['error_message'] = request.error_message
            
            if request.web_equivalent_output is not None:
                operation.web_equivalent_output = request.web_equivalent_output
                updates['web_equivalent_output'] = request.web_equivalent_output
            
            if request.user_satisfaction is not None:
                operation.user_satisfaction = request.user_satisfaction
                updates['user_satisfaction'] = str(request.user_satisfaction)
            
            if request.conversion_accuracy is not None:
                operation.conversion_accuracy = request.conversion_accuracy
                updates['conversion_accuracy'] = str(request.conversion_accuracy)
            
            if request.performance_impact is not None:
                operation.performance_impact = request.performance_impact
                updates['performance_impact'] = str(request.performance_impact)
            
            # Update Redis
            if updates:
                self.redis_client.hset(operation_key, mapping=updates)
                
                # Update daily statistics if status changed
                if 'status' in updates:
                    today = datetime.now().strftime("%Y-%m-%d")
                    daily_key = f"{self.daily_stats_prefix}{today}"
                    self.redis_client.hincrby(daily_key, f"status_{request.status.value}", 1)
                
                # Update progress tracking
                await self._update_session_progress(operation.session_id)
                await self._update_global_progress()
            
            logger.info(f"Updated conversion operation: {request.operation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating conversion operation: {e}")
            raise 
   
    async def get_operation(self, operation_id: str) -> Optional[ConversionOperation]:
        """
        Get a conversion operation by ID.
        
        Args:
            operation_id: Operation identifier
            
        Returns:
            ConversionOperation or None if not found
        """
        try:
            operation_key = f"{self.operation_prefix}{operation_id}"
            operation_data = self.redis_client.hgetall(operation_key)
            
            if not operation_data:
                return None
            
            return self._deserialize_operation(operation_data)
            
        except Exception as e:
            logger.error(f"Error getting conversion operation: {e}")
            return None
    
    async def get_session_operations(
        self, 
        session_id: str, 
        status_filter: Optional[ConversionStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ConversionOperation]:
        """
        Get conversion operations for a session.
        
        Args:
            session_id: Session identifier
            status_filter: Optional status filter
            limit: Maximum number of operations to return
            offset: Number of operations to skip
            
        Returns:
            List of ConversionOperation objects
        """
        try:
            session_ops_key = f"conversion:session_ops:{session_id}"
            operation_ids = self.redis_client.smembers(session_ops_key)
            
            operations = []
            for operation_id in operation_ids:
                operation = await self.get_operation(operation_id)
                if operation:
                    if status_filter is None or operation.status == status_filter:
                        operations.append(operation)
            
            # Sort by creation time (newest first)
            operations.sort(key=lambda op: op.created_at, reverse=True)
            
            # Apply pagination
            start = offset
            end = offset + limit
            return operations[start:end]
            
        except Exception as e:
            logger.error(f"Error getting session operations: {e}")
            return []
    
    async def get_session_progress(self, session_id: str) -> ConversionProgress:
        """
        Get conversion progress for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ConversionProgress object
        """
        try:
            # Get all operations for the session
            operations = await self.get_session_operations(session_id, limit=1000)
            
            # Calculate progress
            progress = ConversionProgress(session_id=session_id)
            progress.calculate_metrics(operations)
            
            # Cache the progress
            progress_key = f"{self.session_progress_prefix}{session_id}"
            progress_data = progress.dict()
            # Convert datetime objects to ISO strings
            if progress_data.get('last_conversion'):
                progress_data['last_conversion'] = progress.last_conversion.isoformat()
            
            self.redis_client.hset(progress_key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in progress_data.items()})
            self.redis_client.expire(progress_key, self.progress_ttl)
            
            return progress
            
        except Exception as e:
            logger.error(f"Error getting session progress: {e}")
            return ConversionProgress(session_id=session_id)
    
    def _serialize_operation(self, operation: ConversionOperation) -> Dict[str, str]:
        """Serialize operation for Redis storage."""
        data = operation.dict()
        
        # Convert datetime objects to ISO strings
        data['created_at'] = operation.created_at.isoformat()
        if operation.started_at:
            data['started_at'] = operation.started_at.isoformat()
        if operation.completed_at:
            data['completed_at'] = operation.completed_at.isoformat()
        
        # Convert enums to string values
        data['operation_type'] = operation.operation_type.value
        data['status'] = operation.status.value
        data['priority'] = operation.priority.value
        
        # Convert lists and dicts to JSON
        data['context_files'] = json.dumps(operation.context_files)
        data['metadata'] = json.dumps(operation.metadata)
        
        return {k: str(v) if v is not None else '' for k, v in data.items()}
    
    def _deserialize_operation(self, data: Dict[str, str]) -> ConversionOperation:
        """Deserialize operation from Redis data."""
        # Convert string values back to appropriate types
        operation_data = dict(data)
        
        # Convert datetime strings back to datetime objects
        operation_data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('started_at'):
            operation_data['started_at'] = datetime.fromisoformat(data['started_at'])
        if data.get('completed_at'):
            operation_data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        
        # Convert enum strings back to enums
        operation_data['operation_type'] = ConversionType(data['operation_type'])
        operation_data['status'] = ConversionStatus(data['status'])
        operation_data['priority'] = ConversionPriority(data['priority'])
        
        # Convert JSON strings back to objects
        operation_data['context_files'] = json.loads(data.get('context_files', '[]'))
        operation_data['metadata'] = json.loads(data.get('metadata', '{}'))
        
        # Convert numeric strings
        if data.get('user_satisfaction'):
            operation_data['user_satisfaction'] = int(data['user_satisfaction'])
        if data.get('conversion_accuracy'):
            operation_data['conversion_accuracy'] = float(data['conversion_accuracy'])
        if data.get('performance_impact'):
            operation_data['performance_impact'] = float(data['performance_impact'])
        
        # Handle None values and empty strings
        for key in ['converted_equivalent', 'conversion_notes', 'error_message', 'web_equivalent_output', 'started_at', 'completed_at']:
            if operation_data.get(key) == '':
                operation_data[key] = None
        
        # Handle numeric fields
        for key in ['user_satisfaction', 'conversion_accuracy', 'performance_impact']:
            if operation_data.get(key) == '':
                operation_data[key] = None
        
        return ConversionOperation(**operation_data)
    
    async def _update_session_progress(self, session_id: str):
        """Update cached session progress."""
        try:
            await self.get_session_progress(session_id)
        except Exception as e:
            logger.error(f"Error updating session progress: {e}")
    
    async def _update_global_progress(self):
        """Update cached global progress."""
        try:
            progress = ConversionProgress()
            
            # Get daily statistics for the last 30 days
            total_ops = 0
            for i in range(30):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                daily_key = f"{self.daily_stats_prefix}{date_str}"
                daily_data = self.redis_client.hgetall(daily_key)
                
                if daily_data:
                    total_ops += int(daily_data.get('total_operations', 0))
            
            progress.total_operations = total_ops
            
            # Cache the progress
            progress_data = progress.dict()
            if progress_data.get('last_conversion'):
                progress_data['last_conversion'] = progress.last_conversion.isoformat()
            
            self.redis_client.hset(
                self.global_progress_prefix, 
                mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in progress_data.items()}
            )
            self.redis_client.expire(self.global_progress_prefix, self.progress_ttl)
            
        except Exception as e:
            logger.error(f"Error updating global progress: {e}")
    
    async def get_conversion_metrics(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> ConversionMetrics:
        """
        Get detailed conversion metrics.
        
        Args:
            start_date: Start date for metrics (default: 30 days ago)
            end_date: End date for metrics (default: now)
            
        Returns:
            ConversionMetrics object
        """
        try:
            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()
            
            metrics = ConversionMetrics()
            
            # Get daily conversion counts
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime("%Y-%m-%d")
                daily_key = f"{self.daily_stats_prefix}{date_str}"
                daily_data = self.redis_client.hgetall(daily_key)
                
                if daily_data:
                    total_ops = int(daily_data.get('total_operations', 0))
                    metrics.daily_conversions[date_str] = total_ops
                
                current_date += timedelta(days=1)
            
            # Set basic metrics
            metrics.users_with_conversions = 1  # Simplified for demo
            metrics.sessions_with_conversions = 1
            metrics.error_rate = 10.0
            metrics.feature_completeness = 75.0
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            return ConversionMetrics()
    
    async def create_note(
        self, 
        operation_id: str, 
        note_type: str, 
        title: str, 
        content: str,
        author: str,
        tags: Optional[List[str]] = None,
        is_public: bool = True
    ) -> str:
        """
        Create a conversion note.
        
        Args:
            operation_id: Related operation ID
            note_type: Type of note
            title: Note title
            content: Note content
            author: Note author
            tags: Optional tags
            is_public: Whether note is public
            
        Returns:
            Note ID
        """
        try:
            note_id = str(uuid.uuid4())
            
            note = ConversionNote(
                id=note_id,
                operation_id=operation_id,
                note_type=note_type,
                title=title,
                content=content,
                author=author,
                tags=tags or [],
                is_public=is_public
            )
            
            # Store note in Redis
            note_key = f"{self.notes_prefix}{note_id}"
            note_data = note.dict()
            note_data['created_at'] = note.created_at.isoformat()
            note_data['tags'] = json.dumps(note.tags)
            
            pipe = self.redis_client.pipeline()
            pipe.hset(note_key, mapping={k: str(v) for k, v in note_data.items()})
            pipe.expire(note_key, self.operation_ttl)
            
            # Add to operation notes list
            op_notes_key = f"conversion:op_notes:{operation_id}"
            pipe.sadd(op_notes_key, note_id)
            pipe.expire(op_notes_key, self.operation_ttl)
            
            pipe.execute()
            
            logger.info(f"Created conversion note: {note_id}")
            return note_id
            
        except Exception as e:
            logger.error(f"Error creating conversion note: {e}")
            raise


# Global service instance
conversion_tracking_service = ConversionTrackingService()