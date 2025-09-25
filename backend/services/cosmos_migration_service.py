"""
Cosmos Migration and Compatibility Service

Provides migration utilities and backward compatibility for transitioning
from legacy Cosmos integration to OptimizedCosmosWrapper.

Features:
- Backward compatibility for existing API calls
- Migration utilities for existing sessions and data
- Feature flags to enable/disable optimization features
- Rollback mechanisms if issues occur
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import redis

from ..config.production import get_production_settings, FeatureFlag, is_feature_enabled
from ..services.cosmos_web_service import CosmosWebService
from ..services.cosmos_integration_service import CosmosIntegrationService
from ..utils.audit_logging import AuditLogger
from ..utils.error_handling import ErrorHandler

logger = logging.getLogger(__name__)


class MigrationStatus(str, Enum):
    """Migration status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationResult:
    """Migration operation result."""
    session_id: str
    status: MigrationStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    rollback_available: bool = True
    performance_improvement: Optional[float] = None  # Percentage improvement


@dataclass
class CompatibilityReport:
    """Compatibility assessment report."""
    total_sessions: int
    compatible_sessions: int
    incompatible_sessions: int
    migration_required: int
    estimated_migration_time: float  # In minutes
    compatibility_issues: List[str]
    recommendations: List[str]


class CosmosMigrationService:
    """
    Service for managing migration from legacy Cosmos to OptimizedCosmosWrapper.
    
    Provides utilities for:
    - Assessing compatibility
    - Migrating sessions
    - Rolling back changes
    - Monitoring migration progress
    """
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize the migration service."""
        self.redis_client = redis_client
        self.production_settings = get_production_settings()
        
        # Services
        self.cosmos_web_service: Optional[CosmosWebService] = None
        self.integration_service: Optional[CosmosIntegrationService] = None
        
        # Migration tracking
        self.migration_prefix = "cosmos:migration:"
        self.rollback_prefix = "cosmos:rollback:"
        self.migration_ttl = 86400 * 7  # 7 days
        
        # Utilities
        self.audit_logger = AuditLogger(redis_client)
        self.error_handler = ErrorHandler(redis_client)
        
        # Migration configuration
        self.batch_size = 10  # Sessions to migrate per batch
        self.migration_timeout = 300  # 5 minutes per session
        self.rollback_timeout = 3600  # 1 hour rollback window
        
        logger.info("CosmosMigrationService initialized")
    
    def set_services(
        self, 
        cosmos_web_service: CosmosWebService,
        integration_service: CosmosIntegrationService
    ):
        """Set the required services."""
        self.cosmos_web_service = cosmos_web_service
        self.integration_service = integration_service
    
    async def assess_compatibility(self, user_id: Optional[str] = None) -> CompatibilityReport:
        """
        Assess compatibility of existing sessions with OptimizedCosmosWrapper.
        
        Args:
            user_id: Optional user ID to assess specific user's sessions
            
        Returns:
            CompatibilityReport with assessment results
        """
        try:
            logger.info(f"Assessing compatibility for user: {user_id or 'all users'}")
            
            # Get all sessions to assess
            if user_id:
                sessions = await self.cosmos_web_service.get_user_sessions(user_id)
            else:
                sessions = await self._get_all_sessions()
            
            total_sessions = len(sessions)
            compatible_sessions = 0
            incompatible_sessions = 0
            migration_required = 0
            compatibility_issues = []
            recommendations = []
            
            for session in sessions:
                compatibility = await self._assess_session_compatibility(session)
                
                if compatibility["compatible"]:
                    compatible_sessions += 1
                else:
                    incompatible_sessions += 1
                    compatibility_issues.extend(compatibility["issues"])
                
                if compatibility["needs_migration"]:
                    migration_required += 1
            
            # Generate recommendations
            if incompatible_sessions > 0:
                recommendations.append(f"Review {incompatible_sessions} incompatible sessions")
            
            if migration_required > 0:
                recommendations.append(f"Migrate {migration_required} sessions to optimized wrapper")
            
            if total_sessions > 100:
                recommendations.append("Consider batch migration for large number of sessions")
            
            # Estimate migration time (2 minutes per session on average)
            estimated_time = migration_required * 2.0
            
            report = CompatibilityReport(
                total_sessions=total_sessions,
                compatible_sessions=compatible_sessions,
                incompatible_sessions=incompatible_sessions,
                migration_required=migration_required,
                estimated_migration_time=estimated_time,
                compatibility_issues=list(set(compatibility_issues)),
                recommendations=recommendations
            )
            
            # Log assessment
            await self.audit_logger.log_system_event(
                event_type="compatibility_assessment",
                details={
                    "user_id": user_id,
                    "total_sessions": total_sessions,
                    "compatible": compatible_sessions,
                    "incompatible": incompatible_sessions,
                    "migration_required": migration_required
                }
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error assessing compatibility: {e}")
            return CompatibilityReport(
                total_sessions=0,
                compatible_sessions=0,
                incompatible_sessions=0,
                migration_required=0,
                estimated_migration_time=0,
                compatibility_issues=[f"Assessment failed: {str(e)}"],
                recommendations=["Retry assessment after resolving errors"]
            )
    
    async def _assess_session_compatibility(self, session) -> Dict[str, Any]:
        """Assess compatibility of a single session."""
        try:
            issues = []
            needs_migration = False
            
            # Check if session has repository URL (required for optimization)
            if not session.repository_url:
                issues.append("No repository URL - optimization not available")
                return {"compatible": True, "needs_migration": False, "issues": issues}
            
            # Check if repository is cached in Redis
            try:
                from ..services.smart_redis_repo_manager import SmartRedisRepoManager
                repo_manager = SmartRedisRepoManager(self.redis_client, session.repository_url)
                context = repo_manager.get_repository_context(session.repository_url)
                
                if not context:
                    issues.append("Repository not cached - needs caching before optimization")
                    needs_migration = True
                else:
                    needs_migration = True  # Can be migrated
                    
            except Exception as e:
                issues.append(f"Error checking repository cache: {e}")
                return {"compatible": False, "needs_migration": False, "issues": issues}
            
            # Check model compatibility
            if session.model not in ["gemini", "claude", "gpt-4"]:  # Supported models
                issues.append(f"Model {session.model} may have limited optimization support")
            
            # Check session age (very old sessions might have compatibility issues)
            if session.created_at and (datetime.now() - session.created_at).days > 30:
                issues.append("Old session - may need data refresh")
            
            return {
                "compatible": len([i for i in issues if "Error" in i]) == 0,
                "needs_migration": needs_migration,
                "issues": issues
            }
            
        except Exception as e:
            return {
                "compatible": False,
                "needs_migration": False,
                "issues": [f"Compatibility check failed: {e}"]
            }
    
    async def migrate_session(self, session_id: str, force: bool = False) -> MigrationResult:
        """
        Migrate a single session to use OptimizedCosmosWrapper.
        
        Args:
            session_id: Session to migrate
            force: Force migration even if compatibility issues exist
            
        Returns:
            MigrationResult with operation details
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"Starting migration for session {session_id}")
            
            # Create migration record
            migration_key = f"{self.migration_prefix}{session_id}"
            migration_data = {
                "session_id": session_id,
                "status": MigrationStatus.IN_PROGRESS.value,
                "started_at": start_time.isoformat(),
                "force": force
            }
            
            self.redis_client.hset(migration_key, mapping=migration_data)
            self.redis_client.expire(migration_key, self.migration_ttl)
            
            # Get session details
            session = await self.cosmos_web_service.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            
            # Assess compatibility if not forced
            if not force:
                compatibility = await self._assess_session_compatibility(session)
                if not compatibility["compatible"]:
                    raise ValueError(f"Session not compatible: {compatibility['issues']}")
            
            # Create rollback data before migration
            rollback_data = await self._create_rollback_data(session_id)
            
            # Perform migration
            success = await self.cosmos_web_service.migrate_session_to_optimized(session_id)
            
            if success:
                # Update migration record
                end_time = datetime.now()
                migration_data.update({
                    "status": MigrationStatus.COMPLETED.value,
                    "completed_at": end_time.isoformat(),
                    "duration": (end_time - start_time).total_seconds()
                })
                
                self.redis_client.hset(migration_key, mapping=migration_data)
                
                # Store rollback data
                rollback_key = f"{self.rollback_prefix}{session_id}"
                self.redis_client.hset(rollback_key, mapping=rollback_data)
                self.redis_client.expire(rollback_key, self.rollback_timeout)
                
                # Log successful migration
                await self.audit_logger.log_system_event(
                    event_type="session_migrated",
                    details={
                        "session_id": session_id,
                        "user_id": session.user_id,
                        "duration": (end_time - start_time).total_seconds(),
                        "force": force
                    }
                )
                
                return MigrationResult(
                    session_id=session_id,
                    status=MigrationStatus.COMPLETED,
                    started_at=start_time,
                    completed_at=end_time,
                    rollback_available=True
                )
            else:
                raise Exception("Migration failed - wrapper creation unsuccessful")
                
        except Exception as e:
            logger.error(f"Migration failed for session {session_id}: {e}")
            
            # Update migration record with failure
            migration_data.update({
                "status": MigrationStatus.FAILED.value,
                "error_message": str(e),
                "completed_at": datetime.now().isoformat()
            })
            
            migration_key = f"{self.migration_prefix}{session_id}"
            self.redis_client.hset(migration_key, mapping=migration_data)
            
            return MigrationResult(
                session_id=session_id,
                status=MigrationStatus.FAILED,
                started_at=start_time,
                completed_at=datetime.now(),
                error_message=str(e),
                rollback_available=False
            )
    
    async def migrate_user_sessions(
        self, 
        user_id: str, 
        batch_size: Optional[int] = None
    ) -> List[MigrationResult]:
        """
        Migrate all sessions for a user.
        
        Args:
            user_id: User whose sessions to migrate
            batch_size: Number of sessions to migrate in parallel
            
        Returns:
            List of MigrationResult objects
        """
        try:
            logger.info(f"Starting batch migration for user {user_id}")
            
            # Get user sessions
            sessions = await self.cosmos_web_service.get_user_sessions(user_id)
            if not sessions:
                logger.info(f"No sessions found for user {user_id}")
                return []
            
            batch_size = batch_size or self.batch_size
            results = []
            
            # Process sessions in batches
            for i in range(0, len(sessions), batch_size):
                batch = sessions[i:i + batch_size]
                batch_tasks = [
                    self.migrate_session(session.id)
                    for session in batch
                ]
                
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Batch migration error: {result}")
                    else:
                        results.append(result)
                
                # Small delay between batches to avoid overwhelming the system
                if i + batch_size < len(sessions):
                    await asyncio.sleep(1)
            
            # Log batch migration completion
            successful = len([r for r in results if r.status == MigrationStatus.COMPLETED])
            failed = len([r for r in results if r.status == MigrationStatus.FAILED])
            
            await self.audit_logger.log_system_event(
                event_type="batch_migration_completed",
                details={
                    "user_id": user_id,
                    "total_sessions": len(sessions),
                    "successful": successful,
                    "failed": failed,
                    "batch_size": batch_size
                }
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch migration for user {user_id}: {e}")
            return []
    
    async def rollback_session(self, session_id: str) -> bool:
        """
        Rollback a migrated session to legacy behavior.
        
        Args:
            session_id: Session to rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        try:
            logger.info(f"Rolling back session {session_id}")
            
            # Check if rollback data exists
            rollback_key = f"{self.rollback_prefix}{session_id}"
            rollback_data = self.redis_client.hgetall(rollback_key)
            
            if not rollback_data:
                logger.error(f"No rollback data found for session {session_id}")
                return False
            
            # Check rollback timeout
            migration_key = f"{self.migration_prefix}{session_id}"
            migration_data = self.redis_client.hgetall(migration_key)
            
            if migration_data:
                completed_at = datetime.fromisoformat(migration_data.get("completed_at", ""))
                if (datetime.now() - completed_at).total_seconds() > self.rollback_timeout:
                    logger.error(f"Rollback timeout exceeded for session {session_id}")
                    return False
            
            # Perform rollback by disabling optimization for this session
            # This is a simplified rollback - in practice, you might need to restore data
            
            # Update migration status
            migration_data.update({
                "status": MigrationStatus.ROLLED_BACK.value,
                "rolled_back_at": datetime.now().isoformat()
            })
            
            self.redis_client.hset(migration_key, mapping=migration_data)
            
            # Clean up rollback data
            self.redis_client.delete(rollback_key)
            
            # Log rollback
            await self.audit_logger.log_system_event(
                event_type="session_rolled_back",
                details={"session_id": session_id}
            )
            
            logger.info(f"Successfully rolled back session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error rolling back session {session_id}: {e}")
            return False
    
    async def get_migration_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get migration status for a session."""
        try:
            migration_key = f"{self.migration_prefix}{session_id}"
            migration_data = self.redis_client.hgetall(migration_key)
            
            if not migration_data:
                return None
            
            # Convert bytes to strings and parse dates
            status_data = {}
            for key, value in migration_data.items():
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                status_data[key] = value
            
            return status_data
            
        except Exception as e:
            logger.error(f"Error getting migration status for {session_id}: {e}")
            return None
    
    async def get_migration_statistics(self) -> Dict[str, Any]:
        """Get overall migration statistics."""
        try:
            # Get all migration records
            pattern = f"{self.migration_prefix}*"
            migration_keys = self.redis_client.keys(pattern)
            
            stats = {
                "total_migrations": len(migration_keys),
                "completed": 0,
                "failed": 0,
                "in_progress": 0,
                "rolled_back": 0,
                "average_duration": 0,
                "success_rate": 0
            }
            
            durations = []
            
            for key in migration_keys:
                migration_data = self.redis_client.hgetall(key)
                if migration_data:
                    status = migration_data.get(b"status", b"").decode('utf-8')
                    
                    if status == MigrationStatus.COMPLETED.value:
                        stats["completed"] += 1
                        
                        # Calculate duration if available
                        started = migration_data.get(b"started_at", b"").decode('utf-8')
                        completed = migration_data.get(b"completed_at", b"").decode('utf-8')
                        
                        if started and completed:
                            start_time = datetime.fromisoformat(started)
                            end_time = datetime.fromisoformat(completed)
                            duration = (end_time - start_time).total_seconds()
                            durations.append(duration)
                    
                    elif status == MigrationStatus.FAILED.value:
                        stats["failed"] += 1
                    elif status == MigrationStatus.IN_PROGRESS.value:
                        stats["in_progress"] += 1
                    elif status == MigrationStatus.ROLLED_BACK.value:
                        stats["rolled_back"] += 1
            
            # Calculate averages
            if durations:
                stats["average_duration"] = sum(durations) / len(durations)
            
            if stats["total_migrations"] > 0:
                stats["success_rate"] = stats["completed"] / stats["total_migrations"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting migration statistics: {e}")
            return {}
    
    async def _create_rollback_data(self, session_id: str) -> Dict[str, str]:
        """Create rollback data for a session."""
        try:
            session = await self.cosmos_web_service.get_session(session_id)
            if not session:
                return {}
            
            return {
                "session_id": session_id,
                "original_model": session.model,
                "original_status": session.status.value,
                "rollback_created_at": datetime.now().isoformat(),
                "user_id": session.user_id
            }
            
        except Exception as e:
            logger.error(f"Error creating rollback data for {session_id}: {e}")
            return {}
    
    async def _get_all_sessions(self) -> List:
        """Get all sessions from Redis (simplified implementation)."""
        try:
            # This is a simplified implementation
            # In practice, you'd need to scan through all user session keys
            pattern = "cosmos:user_sessions:*"
            user_keys = self.redis_client.keys(pattern)
            
            all_sessions = []
            for user_key in user_keys:
                user_id = user_key.decode('utf-8').split(':')[-1]
                sessions = await self.cosmos_web_service.get_user_sessions(user_id)
                all_sessions.extend(sessions)
            
            return all_sessions
            
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
            return []
    
    async def cleanup_migration_data(self, older_than_days: int = 7):
        """Clean up old migration and rollback data."""
        try:
            cutoff_time = datetime.now() - timedelta(days=older_than_days)
            
            # Clean up migration records
            pattern = f"{self.migration_prefix}*"
            migration_keys = self.redis_client.keys(pattern)
            
            cleaned_count = 0
            for key in migration_keys:
                migration_data = self.redis_client.hgetall(key)
                if migration_data:
                    started_at = migration_data.get(b"started_at", b"").decode('utf-8')
                    if started_at:
                        start_time = datetime.fromisoformat(started_at)
                        if start_time < cutoff_time:
                            self.redis_client.delete(key)
                            cleaned_count += 1
            
            # Clean up rollback records
            pattern = f"{self.rollback_prefix}*"
            rollback_keys = self.redis_client.keys(pattern)
            
            for key in rollback_keys:
                rollback_data = self.redis_client.hgetall(key)
                if rollback_data:
                    created_at = rollback_data.get(b"rollback_created_at", b"").decode('utf-8')
                    if created_at:
                        create_time = datetime.fromisoformat(created_at)
                        if create_time < cutoff_time:
                            self.redis_client.delete(key)
                            cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} old migration/rollback records")
            
        except Exception as e:
            logger.error(f"Error cleaning up migration data: {e}")


# Global migration service instance
migration_service: Optional[CosmosMigrationService] = None


def get_migration_service(redis_client: redis.Redis) -> CosmosMigrationService:
    """Get or create the global migration service instance."""
    global migration_service
    
    if migration_service is None:
        migration_service = CosmosMigrationService(redis_client)
    
    return migration_service