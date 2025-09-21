"""
Supabase integration service for GitMesh
Handles rate limiting data, session persistence, and user analytics
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import asyncpg
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RateLimitRecord:
    """Rate limit record for Supabase storage."""
    user_id: str
    endpoint: str
    request_count: int
    window_start: datetime
    window_end: datetime
    is_blocked: bool = False
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class SessionRecord:
    """Session record for Supabase storage."""
    session_id: str
    user_id: str
    github_token: str
    user_data: Dict[str, Any]
    expires_at: datetime
    created_at: datetime = None
    updated_at: datetime = None


class SupabaseService:
    """Supabase service for GitMesh data persistence."""
    
    def __init__(self):
        self.database_url = settings.SUPABASE_URL
        self.connection_pool = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the Supabase connection pool."""
        if self._initialized:
            return
        
        try:
            self.connection_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                command_timeout=30
            )
            
            # Create tables if they don't exist
            await self._create_tables()
            self._initialized = True
            logger.info("Supabase service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase service: {e}")
            raise
    
    async def _create_tables(self):
        """Create necessary tables for GitMesh."""
        async with self.connection_pool.acquire() as conn:
            # Rate limiting table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    endpoint VARCHAR(500) NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
                    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
                    is_blocked BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(user_id, endpoint, window_start)
                );
            """)
            
            # Sessions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    github_token TEXT,
                    user_data JSONB,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # User analytics table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_analytics (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    event_data JSONB,
                    ip_address INET,
                    user_agent TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # GitHub API usage tracking
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS github_api_usage (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    endpoint VARCHAR(500) NOT NULL,
                    method VARCHAR(10) NOT NULL,
                    status_code INTEGER,
                    response_time_ms INTEGER,
                    rate_limit_remaining INTEGER,
                    rate_limit_reset TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Create indexes for better performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_user_endpoint 
                ON rate_limits(user_id, endpoint);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_window 
                ON rate_limits(window_start, window_end);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id 
                ON user_sessions(user_id);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_expires 
                ON user_sessions(expires_at);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_analytics_user_event 
                ON user_analytics(user_id, event_type);
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_github_usage_user_endpoint 
                ON github_api_usage(user_id, endpoint);
            """)
    
    async def close(self):
        """Close the connection pool."""
        if self.connection_pool:
            await self.connection_pool.close()
            self._initialized = False
    
    # Rate Limiting Methods
    
    async def record_rate_limit(self, user_id: str, endpoint: str, window_minutes: int = 60) -> RateLimitRecord:
        """Record a rate limit entry for a user and endpoint."""
        if not self._initialized:
            await self.initialize()
        
        now = datetime.utcnow()
        window_start = now.replace(minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(minutes=window_minutes)
        
        async with self.connection_pool.acquire() as conn:
            # Try to update existing record
            result = await conn.fetchrow("""
                UPDATE rate_limits 
                SET request_count = request_count + 1, updated_at = NOW()
                WHERE user_id = $1 AND endpoint = $2 AND window_start = $3
                RETURNING *;
            """, user_id, endpoint, window_start)
            
            if result:
                return RateLimitRecord(
                    user_id=result['user_id'],
                    endpoint=result['endpoint'],
                    request_count=result['request_count'],
                    window_start=result['window_start'],
                    window_end=result['window_end'],
                    is_blocked=result['is_blocked'],
                    created_at=result['created_at'],
                    updated_at=result['updated_at']
                )
            
            # Create new record
            result = await conn.fetchrow("""
                INSERT INTO rate_limits (user_id, endpoint, request_count, window_start, window_end)
                VALUES ($1, $2, 1, $3, $4)
                RETURNING *;
            """, user_id, endpoint, window_start, window_end)
            
            return RateLimitRecord(
                user_id=result['user_id'],
                endpoint=result['endpoint'],
                request_count=result['request_count'],
                window_start=result['window_start'],
                window_end=result['window_end'],
                is_blocked=result['is_blocked'],
                created_at=result['created_at'],
                updated_at=result['updated_at']
            )
    
    async def get_rate_limit_status(self, user_id: str, endpoint: str) -> Optional[RateLimitRecord]:
        """Get current rate limit status for user and endpoint."""
        if not self._initialized:
            await self.initialize()
        
        now = datetime.utcnow()
        window_start = now.replace(minute=0, second=0, microsecond=0)
        
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM rate_limits 
                WHERE user_id = $1 AND endpoint = $2 AND window_start = $3;
            """, user_id, endpoint, window_start)
            
            if result:
                return RateLimitRecord(
                    user_id=result['user_id'],
                    endpoint=result['endpoint'],
                    request_count=result['request_count'],
                    window_start=result['window_start'],
                    window_end=result['window_end'],
                    is_blocked=result['is_blocked'],
                    created_at=result['created_at'],
                    updated_at=result['updated_at']
                )
            
            return None
    
    async def block_user_endpoint(self, user_id: str, endpoint: str, duration_minutes: int = 60):
        """Block a user from accessing an endpoint."""
        if not self._initialized:
            await self.initialize()
        
        now = datetime.utcnow()
        window_start = now.replace(minute=0, second=0, microsecond=0)
        
        async with self.connection_pool.acquire() as conn:
            await conn.execute("""
                UPDATE rate_limits 
                SET is_blocked = TRUE, updated_at = NOW()
                WHERE user_id = $1 AND endpoint = $2 AND window_start = $3;
            """, user_id, endpoint, window_start)
    
    async def cleanup_old_rate_limits(self, days_old: int = 7):
        """Clean up old rate limit records."""
        if not self._initialized:
            await self.initialize()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        async with self.connection_pool.acquire() as conn:
            deleted_count = await conn.fetchval("""
                DELETE FROM rate_limits 
                WHERE created_at < $1;
            """, cutoff_date)
            
            logger.info(f"Cleaned up {deleted_count} old rate limit records")
            return deleted_count
    
    # Session Management Methods
    
    async def store_session(self, session_record: SessionRecord) -> SessionRecord:
        """Store a user session."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO user_sessions (session_id, user_id, github_token, user_data, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (session_id) 
                DO UPDATE SET 
                    github_token = EXCLUDED.github_token,
                    user_data = EXCLUDED.user_data,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                RETURNING *;
            """, 
            session_record.session_id,
            session_record.user_id,
            session_record.github_token,
            json.dumps(session_record.user_data),
            session_record.expires_at
            )
            
            return SessionRecord(
                session_id=result['session_id'],
                user_id=result['user_id'],
                github_token=result['github_token'],
                user_data=json.loads(result['user_data']) if result['user_data'] else {},
                expires_at=result['expires_at'],
                created_at=result['created_at'],
                updated_at=result['updated_at']
            )
    
    async def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Get a user session by ID."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM user_sessions 
                WHERE session_id = $1 AND expires_at > NOW();
            """, session_id)
            
            if result:
                return SessionRecord(
                    session_id=result['session_id'],
                    user_id=result['user_id'],
                    github_token=result['github_token'],
                    user_data=json.loads(result['user_data']) if result['user_data'] else {},
                    expires_at=result['expires_at'],
                    created_at=result['created_at'],
                    updated_at=result['updated_at']
                )
            
            return None
    
    async def delete_session(self, session_id: str):
        """Delete a user session."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM user_sessions WHERE session_id = $1;
            """, session_id)
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            deleted_count = await conn.fetchval("""
                DELETE FROM user_sessions WHERE expires_at <= NOW();
            """)
            
            logger.info(f"Cleaned up {deleted_count} expired sessions")
            return deleted_count
    
    # Analytics Methods
    
    async def record_user_event(
        self, 
        user_id: str, 
        event_type: str, 
        event_data: Dict[str, Any] = None,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Record a user analytics event."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_analytics (user_id, event_type, event_data, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5);
            """, 
            user_id, 
            event_type, 
            json.dumps(event_data) if event_data else None,
            ip_address,
            user_agent
            )
    
    async def record_github_api_usage(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int,
        rate_limit_remaining: int = None,
        rate_limit_reset: datetime = None
    ):
        """Record GitHub API usage for analytics."""
        if not self._initialized:
            await self.initialize()
        
        async with self.connection_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO github_api_usage 
                (user_id, endpoint, method, status_code, response_time_ms, rate_limit_remaining, rate_limit_reset)
                VALUES ($1, $2, $3, $4, $5, $6, $7);
            """, 
            user_id, endpoint, method, status_code, response_time_ms, 
            rate_limit_remaining, rate_limit_reset
            )
    
    async def get_user_analytics(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get user analytics for the specified period."""
        if not self._initialized:
            await self.initialize()
        
        since_date = datetime.utcnow() - timedelta(days=days)
        
        async with self.connection_pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT event_type, COUNT(*) as count, 
                       DATE_TRUNC('day', created_at) as date
                FROM user_analytics 
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY event_type, DATE_TRUNC('day', created_at)
                ORDER BY date DESC;
            """, user_id, since_date)
            
            return [dict(row) for row in results]
    
    async def get_github_api_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get GitHub API usage statistics for a user."""
        if not self._initialized:
            await self.initialize()
        
        since_date = datetime.utcnow() - timedelta(days=days)
        
        async with self.connection_pool.acquire() as conn:
            # Total requests
            total_requests = await conn.fetchval("""
                SELECT COUNT(*) FROM github_api_usage 
                WHERE user_id = $1 AND created_at >= $2;
            """, user_id, since_date)
            
            # Average response time
            avg_response_time = await conn.fetchval("""
                SELECT AVG(response_time_ms) FROM github_api_usage 
                WHERE user_id = $1 AND created_at >= $2;
            """, user_id, since_date)
            
            # Error rate
            error_count = await conn.fetchval("""
                SELECT COUNT(*) FROM github_api_usage 
                WHERE user_id = $1 AND created_at >= $2 AND status_code >= 400;
            """, user_id, since_date)
            
            # Most used endpoints
            top_endpoints = await conn.fetch("""
                SELECT endpoint, COUNT(*) as count 
                FROM github_api_usage 
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY endpoint 
                ORDER BY count DESC 
                LIMIT 10;
            """, user_id, since_date)
            
            return {
                'total_requests': total_requests or 0,
                'average_response_time_ms': float(avg_response_time) if avg_response_time else 0,
                'error_rate': (error_count / total_requests * 100) if total_requests > 0 else 0,
                'top_endpoints': [dict(row) for row in top_endpoints]
            }


# Global instance
supabase_service = SupabaseService()