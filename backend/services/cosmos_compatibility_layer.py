"""
Cosmos Compatibility Layer

Provides backward compatibility for existing API calls while transitioning
to OptimizedCosmosWrapper. This layer ensures that existing frontend components
continue to work without modification during the migration period.

Features:
- API compatibility for existing endpoints
- Automatic routing between legacy and optimized implementations
- Graceful degradation when optimization is unavailable
- Request/response format compatibility
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import asdict

from ..config.production import FeatureFlag, is_feature_enabled
from ..services.cosmos_web_service import CosmosWebService
from ..services.cosmos_integration_service import CosmosIntegrationService
from ..services.cosmos_migration_service import get_migration_service
from ..utils.audit_logging import AuditLogger

logger = logging.getLogger(__name__)


class CosmosCompatibilityLayer:
    """
    Compatibility layer that provides backward-compatible API while
    routing requests to optimized or legacy implementations.
    """
    
    def __init__(
        self,
        cosmos_web_service: CosmosWebService,
        integration_service: CosmosIntegrationService,
        redis_client
    ):
        """Initialize the compatibility layer."""
        self.cosmos_web_service = cosmos_web_service
        self.integration_service = integration_service
        self.redis_client = redis_client
        
        # Migration service for handling transitions
        self.migration_service = get_migration_service(redis_client)
        self.migration_service.set_services(cosmos_web_service, integration_service)
        
        # Audit logging
        self.audit_logger = AuditLogger(redis_client)
        
        # Compatibility settings
        self.auto_migrate_sessions = True  # Automatically migrate compatible sessions
        self.fallback_on_error = True     # Fallback to legacy on optimization errors
        
        logger.info("CosmosCompatibilityLayer initialized")
    
    async def create_session(
        self,
        user_id: str,
        title: str = "New Chat",
        repository_url: Optional[str] = None,
        branch: Optional[str] = None,
        model: str = "gemini"
    ) -> str:
        """
        Create a new chat session with compatibility handling.
        
        This method maintains the same API as the original create_session
        but routes to optimized implementation when available.
        """
        try:
            # Use the standard web service method
            session_id = await self.cosmos_web_service.create_session(
                user_id=user_id,
                title=title,
                repository_url=repository_url,
                branch=branch,
                model=model
            )
            
            # If optimization is enabled and session has repository, try to migrate
            if (is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION) and 
                repository_url and self.auto_migrate_sessions):
                
                try:
                    await self.migration_service.migrate_session(session_id)
                    logger.info(f"Auto-migrated new session {session_id} to optimized wrapper")
                except Exception as e:
                    logger.warning(f"Auto-migration failed for session {session_id}: {e}")
                    # Continue with legacy session - no error to user
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise
    
    async def send_message(
        self,
        session_id: str,
        user_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        selected_files: Optional[List[str]] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message with compatibility handling.
        
        Routes to optimized or legacy implementation based on session state
        and feature flags. Maintains backward compatibility with existing API.
        """
        try:
            # Check if optimization is enabled
            if is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION):
                # Try optimized processing first
                try:
                    response = await self.cosmos_web_service.process_chat_with_optimized_wrapper(
                        session_id=session_id,
                        user_id=user_id,
                        message=message,
                        context=context,
                        selected_files=selected_files,
                        model_name=model_name
                    )
                    
                    # Mark response as optimized for monitoring
                    if response and "metadata" in response:
                        response["metadata"]["processing_type"] = "optimized"
                    
                    return response
                    
                except Exception as e:
                    logger.warning(f"Optimized processing failed for session {session_id}: {e}")
                    
                    if self.fallback_on_error:
                        logger.info(f"Falling back to legacy processing for session {session_id}")
                        return await self._legacy_send_message(
                            session_id, user_id, message, context, selected_files, model_name
                        )
                    else:
                        raise
            else:
                # Use legacy processing
                return await self._legacy_send_message(
                    session_id, user_id, message, context, selected_files, model_name
                )
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
            # Return error response in expected format
            return {
                "content": "I apologize, but I encountered an error while processing your message. Please try again.",
                "error": str(e),
                "context_files_used": selected_files or [],
                "shell_commands_converted": [],
                "conversion_notes": None,
                "metadata": {
                    "processing_type": "error",
                    "error_occurred": True,
                    "response_time": 0.1
                },
                "confidence": 0.0,
                "sources": []
            }
    
    async def _legacy_send_message(
        self,
        session_id: str,
        user_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        selected_files: Optional[List[str]] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Legacy message processing for backward compatibility."""
        try:
            # Use the legacy processing method
            response = await self.cosmos_web_service._legacy_chat_processing(
                session_id=session_id,
                message=message,
                context=context,
                selected_files=selected_files
            )
            
            # Ensure response has expected format
            if response and "metadata" in response:
                response["metadata"]["processing_type"] = "legacy"
            
            return response
            
        except Exception as e:
            logger.error(f"Legacy processing failed: {e}")
            raise
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session with compatibility handling.
        
        Returns session data in the expected format, regardless of
        whether it's using optimized or legacy processing.
        """
        try:
            session = await self.cosmos_web_service.get_session(session_id)
            if not session:
                return None
            
            # Convert to dictionary format for API compatibility
            session_dict = asdict(session)
            
            # Add compatibility fields
            session_dict["created_at"] = session.created_at.isoformat()
            session_dict["updated_at"] = session.updated_at.isoformat()
            session_dict["status"] = session.status.value
            
            # Add optimization status
            migration_status = await self.migration_service.get_migration_status(session_id)
            session_dict["optimization_status"] = {
                "migrated": migration_status is not None,
                "migration_status": migration_status.get("status") if migration_status else None,
                "can_optimize": is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION) and session.repository_url is not None
            }
            
            return session_dict
            
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user sessions with compatibility handling."""
        try:
            sessions = await self.cosmos_web_service.get_user_sessions(user_id)
            
            # Convert to dictionary format for API compatibility
            session_dicts = []
            for session in sessions:
                session_dict = asdict(session)
                session_dict["created_at"] = session.created_at.isoformat()
                session_dict["updated_at"] = session.updated_at.isoformat()
                session_dict["status"] = session.status.value
                
                # Add optimization status
                migration_status = await self.migration_service.get_migration_status(session.id)
                session_dict["optimization_status"] = {
                    "migrated": migration_status is not None,
                    "migration_status": migration_status.get("status") if migration_status else None,
                    "can_optimize": is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION) and session.repository_url is not None
                }
                
                session_dicts.append(session_dict)
            
            return session_dicts
            
        except Exception as e:
            logger.error(f"Error getting user sessions for {user_id}: {e}")
            return []
    
    async def add_context_files(
        self,
        session_id: str,
        file_paths: List[str],
        repository_url: Optional[str] = None,
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add context files with compatibility handling."""
        try:
            return await self.cosmos_web_service.add_context_files(
                session_id=session_id,
                file_paths=file_paths,
                repository_url=repository_url,
                branch=branch
            )
        except Exception as e:
            logger.error(f"Error adding context files: {e}")
            return {
                "added_count": 0,
                "failed_count": len(file_paths),
                "added_files": [],
                "failed_files": [{"path": path, "error": str(e)} for path in file_paths],
                "total_context_files": 0,
                "total_context_size": 0
            }
    
    async def remove_context_files(
        self,
        session_id: str,
        file_paths: List[str]
    ) -> Dict[str, Any]:
        """Remove context files with compatibility handling."""
        try:
            return await self.cosmos_web_service.remove_context_files(
                session_id=session_id,
                file_paths=file_paths
            )
        except Exception as e:
            logger.error(f"Error removing context files: {e}")
            return {
                "removed_count": 0,
                "not_found_count": len(file_paths),
                "removed_files": [],
                "not_found_files": [{"path": path, "error": str(e)} for path in file_paths],
                "total_context_files": 0,
                "total_context_size": 0
            }
    
    async def get_context_files(self, session_id: str) -> List[Dict[str, Any]]:
        """Get context files with compatibility handling."""
        try:
            return await self.cosmos_web_service.get_context_files(session_id)
        except Exception as e:
            logger.error(f"Error getting context files: {e}")
            return []
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models with compatibility handling."""
        try:
            models = self.cosmos_web_service.get_available_models()
            
            # Convert to dictionary format for API compatibility
            return [asdict(model) for model in models]
            
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []
    
    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete session with compatibility handling."""
        try:
            # Clean up any optimization data first
            try:
                await self.migration_service.rollback_session(session_id)
            except Exception as e:
                logger.warning(f"Error during optimization cleanup for session {session_id}: {e}")
            
            # Delete the session
            return await self.cosmos_web_service.delete_session(session_id, user_id)
            
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get session messages with compatibility handling."""
        try:
            messages = await self.cosmos_web_service.get_session_messages(
                session_id=session_id,
                limit=limit,
                offset=offset
            )
            
            # Convert to dictionary format for API compatibility
            message_dicts = []
            for message in messages:
                message_dict = asdict(message)
                message_dict["timestamp"] = message.timestamp.isoformat()
                message_dicts.append(message_dict)
            
            return message_dicts
            
        except Exception as e:
            logger.error(f"Error getting session messages: {e}")
            return []
    
    # Migration and optimization management methods
    
    async def migrate_session_to_optimized(self, session_id: str, force: bool = False) -> Dict[str, Any]:
        """Migrate a session to optimized processing."""
        try:
            result = await self.migration_service.migrate_session(session_id, force)
            
            return {
                "success": result.status.value == "completed",
                "status": result.status.value,
                "session_id": result.session_id,
                "started_at": result.started_at.isoformat(),
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "error_message": result.error_message,
                "rollback_available": result.rollback_available
            }
            
        except Exception as e:
            logger.error(f"Error migrating session {session_id}: {e}")
            return {
                "success": False,
                "status": "failed",
                "session_id": session_id,
                "error_message": str(e),
                "rollback_available": False
            }
    
    async def rollback_session(self, session_id: str) -> Dict[str, Any]:
        """Rollback a session from optimized to legacy processing."""
        try:
            success = await self.migration_service.rollback_session(session_id)
            
            return {
                "success": success,
                "session_id": session_id,
                "message": "Session rolled back successfully" if success else "Rollback failed"
            }
            
        except Exception as e:
            logger.error(f"Error rolling back session {session_id}: {e}")
            return {
                "success": False,
                "session_id": session_id,
                "message": f"Rollback error: {str(e)}"
            }
    
    async def get_optimization_status(self, session_id: str) -> Dict[str, Any]:
        """Get optimization status for a session."""
        try:
            migration_status = await self.migration_service.get_migration_status(session_id)
            
            return {
                "session_id": session_id,
                "optimization_enabled": is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION),
                "migrated": migration_status is not None,
                "migration_status": migration_status.get("status") if migration_status else None,
                "migration_details": migration_status
            }
            
        except Exception as e:
            logger.error(f"Error getting optimization status for {session_id}: {e}")
            return {
                "session_id": session_id,
                "optimization_enabled": False,
                "migrated": False,
                "error": str(e)
            }
    
    async def get_compatibility_report(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get compatibility assessment report."""
        try:
            report = await self.migration_service.assess_compatibility(user_id)
            
            return {
                "user_id": user_id,
                "total_sessions": report.total_sessions,
                "compatible_sessions": report.compatible_sessions,
                "incompatible_sessions": report.incompatible_sessions,
                "migration_required": report.migration_required,
                "estimated_migration_time": report.estimated_migration_time,
                "compatibility_issues": report.compatibility_issues,
                "recommendations": report.recommendations,
                "assessment_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting compatibility report: {e}")
            return {
                "user_id": user_id,
                "error": str(e),
                "assessment_timestamp": datetime.now().isoformat()
            }
    
    async def get_migration_statistics(self) -> Dict[str, Any]:
        """Get overall migration statistics."""
        try:
            stats = await self.migration_service.get_migration_statistics()
            stats["timestamp"] = datetime.now().isoformat()
            return stats
            
        except Exception as e:
            logger.error(f"Error getting migration statistics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def configure_compatibility(
        self,
        auto_migrate_sessions: bool = True,
        fallback_on_error: bool = True
    ):
        """Configure compatibility layer behavior."""
        self.auto_migrate_sessions = auto_migrate_sessions
        self.fallback_on_error = fallback_on_error
        
        logger.info(f"Compatibility layer configured: auto_migrate={auto_migrate_sessions}, fallback={fallback_on_error}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on compatibility layer."""
        try:
            health = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {}
            }
            
            # Check web service
            web_health = await self.cosmos_web_service.health_check()
            health["components"]["web_service"] = web_health
            
            # Check integration service
            integration_health = await self.integration_service.get_health_status()
            health["components"]["integration_service"] = integration_health
            
            # Check migration service
            migration_stats = await self.migration_service.get_migration_statistics()
            health["components"]["migration_service"] = {
                "status": "healthy",
                "active_migrations": migration_stats.get("in_progress", 0)
            }
            
            # Check feature flags
            health["feature_flags"] = {
                "cosmos_optimization": is_feature_enabled(FeatureFlag.COSMOS_OPTIMIZATION),
                "cosmos_chat_enabled": is_feature_enabled(FeatureFlag.COSMOS_CHAT_ENABLED)
            }
            
            # Configuration
            health["configuration"] = {
                "auto_migrate_sessions": self.auto_migrate_sessions,
                "fallback_on_error": self.fallback_on_error
            }
            
            return health
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


# Global compatibility layer instance
compatibility_layer: Optional[CosmosCompatibilityLayer] = None


def get_compatibility_layer(
    cosmos_web_service: CosmosWebService,
    integration_service: CosmosIntegrationService,
    redis_client
) -> CosmosCompatibilityLayer:
    """Get or create the global compatibility layer instance."""
    global compatibility_layer
    
    if compatibility_layer is None:
        compatibility_layer = CosmosCompatibilityLayer(
            cosmos_web_service, integration_service, redis_client
        )
    
    return compatibility_layer