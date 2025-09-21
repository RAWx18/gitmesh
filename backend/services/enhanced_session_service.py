"""
Enhanced Session Management Service with Supabase Integration
Provides persistent session storage and automatic cleanup
"""

import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, status
import jwt

from config.settings import get_settings
from services.supabase_service import supabase_service, SessionRecord
from utils.error_handling import AuthenticationError

logger = logging.getLogger(__name__)
settings = get_settings()


class EnhancedSessionService:
    """Enhanced session service with Supabase persistence."""
    
    def __init__(self):
        self.jwt_secret = settings.JWT_SECRET
        self.jwt_algorithm = "HS256"
        self.session_duration = timedelta(days=7)  # Default 7 days
    
    async def create_session(
        self, 
        user_data: Dict[str, Any], 
        github_token: str,
        request: Request = None
    ) -> Dict[str, Any]:
        """Create a new user session with Supabase persistence."""
        try:
            # Generate session ID
            session_id = str(uuid.uuid4())
            user_id = str(user_data.get('id', user_data.get('login', 'unknown')))
            
            # Create session record
            session_record = SessionRecord(
                session_id=session_id,
                user_id=user_id,
                github_token=github_token,
                user_data=user_data,
                expires_at=datetime.utcnow() + self.session_duration
            )
            
            # Store in Supabase
            stored_session = await supabase_service.store_session(session_record)
            
            # Create JWT token
            jwt_payload = {
                'session_id': session_id,
                'user_id': user_id,
                'exp': int(stored_session.expires_at.timestamp()),
                'iat': int(datetime.utcnow().timestamp())
            }
            
            jwt_token = jwt.encode(jwt_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            
            # Record session creation event
            await supabase_service.record_user_event(
                user_id,
                'session_created',
                {
                    'session_id': session_id,
                    'expires_at': stored_session.expires_at.isoformat()
                },
                self._get_client_ip(request) if request else None,
                request.headers.get('user-agent') if request else None
            )
            
            logger.info(f"Created session for user {user_id}: {session_id}")
            
            return {
                'session_id': session_id,
                'jwt_token': jwt_token,
                'user_data': user_data,
                'expires_at': stored_session.expires_at.isoformat(),
                'github_token': github_token
            }
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create session"
            )
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data from Supabase."""
        try:
            session_record = await supabase_service.get_session(session_id)
            
            if not session_record:
                return None
            
            # Check if session is expired
            if session_record.expires_at <= datetime.utcnow():
                await self.delete_session(session_id)
                return None
            
            return {
                'session_id': session_record.session_id,
                'user_id': session_record.user_id,
                'user_data': session_record.user_data,
                'github_token': session_record.github_token,
                'expires_at': session_record.expires_at.isoformat(),
                'created_at': session_record.created_at.isoformat() if session_record.created_at else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    async def get_session_from_jwt(self, jwt_token: str) -> Optional[Dict[str, Any]]:
        """Get session data from JWT token."""
        try:
            # Decode JWT
            payload = jwt.decode(jwt_token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            session_id = payload.get('session_id')
            
            if not session_id:
                return None
            
            # Get session from Supabase
            return await self.get_session(session_id)
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get session from JWT: {e}")
            return None
    
    async def refresh_session(self, session_id: str, extend_hours: int = 24) -> Optional[Dict[str, Any]]:
        """Refresh session expiration time."""
        try:
            session_record = await supabase_service.get_session(session_id)
            
            if not session_record:
                return None
            
            # Extend expiration
            new_expires_at = datetime.utcnow() + timedelta(hours=extend_hours)
            
            # Update session
            session_record.expires_at = new_expires_at
            updated_session = await supabase_service.store_session(session_record)
            
            # Record refresh event
            await supabase_service.record_user_event(
                session_record.user_id,
                'session_refreshed',
                {
                    'session_id': session_id,
                    'new_expires_at': new_expires_at.isoformat()
                }
            )
            
            logger.info(f"Refreshed session {session_id} until {new_expires_at}")
            
            return {
                'session_id': updated_session.session_id,
                'user_id': updated_session.user_id,
                'user_data': updated_session.user_data,
                'github_token': updated_session.github_token,
                'expires_at': updated_session.expires_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh session {session_id}: {e}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            # Get session for logging
            session_record = await supabase_service.get_session(session_id)
            
            # Delete from Supabase
            await supabase_service.delete_session(session_id)
            
            # Record deletion event
            if session_record:
                await supabase_service.record_user_event(
                    session_record.user_id,
                    'session_deleted',
                    {'session_id': session_id}
                )
            
            logger.info(f"Deleted session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        try:
            deleted_count = await supabase_service.cleanup_expired_sessions()
            logger.info(f"Cleaned up {deleted_count} expired sessions")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all active sessions for a user."""
        try:
            # This would require a new method in supabase_service
            # For now, return empty list
            return []
            
        except Exception as e:
            logger.error(f"Failed to get user sessions for {user_id}: {e}")
            return []
    
    async def validate_session_middleware(self, request: Request) -> Optional[Dict[str, Any]]:
        """Middleware to validate session from request."""
        try:
            # Try to get JWT from Authorization header
            auth_header = request.headers.get('authorization', '')
            if auth_header.startswith('Bearer '):
                jwt_token = auth_header[7:]  # Remove 'Bearer ' prefix
                session_data = await self.get_session_from_jwt(jwt_token)
                
                if session_data:
                    # Add session data to request state
                    request.state.session = session_data
                    request.state.user = session_data['user_data']
                    request.state.user_id = session_data['user_id']
                    request.state.github_token = session_data['github_token']
                    
                    return session_data
            
            # Try to get session ID from cookies
            session_id = request.cookies.get('session_id')
            if session_id:
                session_data = await self.get_session(session_id)
                
                if session_data:
                    request.state.session = session_data
                    request.state.user = session_data['user_data']
                    request.state.user_id = session_data['user_id']
                    request.state.github_token = session_data['github_token']
                    
                    return session_data
            
            return None
            
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return None
    
    async def handle_rate_limit_signout(self, user_id: str, reason: str = "Rate limit exceeded"):
        """Handle automatic signout due to rate limiting."""
        try:
            # Get all user sessions (would need implementation)
            # For now, just record the event
            await supabase_service.record_user_event(
                user_id,
                'rate_limit_signout',
                {
                    'reason': reason,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
            logger.warning(f"Rate limit signout for user {user_id}: {reason}")
            
            # In a real implementation, you might want to:
            # 1. Delete all user sessions
            # 2. Add user to temporary block list
            # 3. Send notification to user
            
        except Exception as e:
            logger.error(f"Failed to handle rate limit signout for {user_id}: {e}")
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        return forwarded_for or (request.client.host if request.client else 'unknown')
    
    def _create_jwt_token(self, payload: Dict[str, Any]) -> str:
        """Create JWT token with payload."""
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def _decode_jwt_token(self, token: str) -> Dict[str, Any]:
        """Decode JWT token."""
        return jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])


# Global service instance
enhanced_session_service = EnhancedSessionService()