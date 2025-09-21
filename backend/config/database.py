"""
Database configuration and connection management.
This is a minimal implementation to get the server running.
"""

import logging
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Database base class
Base = declarative_base()

# Global database components
_engine = None
_session_factory = None
_database_manager = None


class DatabaseManager:
    """Simple database manager."""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.initialized = False
    
    async def initialize(self) -> bool:
        """Initialize database connection."""
        try:
            # Use PostgreSQL
            database_url = "postgresql+asyncpg://postgres.rrqdwjnlcfxacrnmnohi:GitMeshlfdt2025@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
            
            self.engine = create_async_engine(
                database_url,
                echo=False,
                future=True,
                pool_size=10,
                max_overflow=20
            )
            
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables if they don't exist
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            self.initialized = True
            logger.info("Database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False
    
    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            self.initialized = False
            logger.info("Database connections closed")


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    db_manager = get_database_manager()
    if not db_manager.initialized:
        await db_manager.initialize()
    
    async with db_manager.session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_async_db_session() -> AsyncSession:
    """Get async database session."""
    db_manager = get_database_manager()
    if not db_manager.initialized:
        await db_manager.initialize()
    
    return db_manager.session_factory()


def get_database_settings():
    """Get database settings."""
    return {
        "database_url": "postgresql+asyncpg://postgres.rrqdwjnlcfxacrnmnohi:GitMeshlfdt2025@aws-1-ap-south-1.pooler.supabase.com:5432/postgres",
        "echo": False
    }


async def close_database():
    """Close database connections."""
    db_manager = get_database_manager()
    await db_manager.close()