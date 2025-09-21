"""
Database configuration and connection management.
Uses unified configuration system to eliminate hardcoded values.
"""

import logging
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from .simple_config import get_config

logger = logging.getLogger(__name__)

# Database base class
Base = declarative_base()

# Global database components
_engine = None
_session_factory = None
_database_manager = None


class DatabaseManager:
    """Database manager with unified configuration."""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.initialized = False
        self.config = get_config()
    
    async def initialize(self) -> bool:
        """Initialize database connection."""
        try:
            # Get database URL from unified config
            database_url = self.config.get_database_url()
            
            self.engine = create_async_engine(
                database_url,
                echo=self.config.db_echo,
                future=True,
                pool_size=self.config.db_pool_size,
                max_overflow=self.config.db_max_overflow
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
    """Get database settings from unified config."""
    config = get_config()
    return {
        "database_url": config.get_database_url(),
        "echo": config.db_echo,
        "pool_size": config.db_pool_size,
        "max_overflow": config.db_max_overflow
    }


async def close_database():
    """Close database connections."""
    db_manager = get_database_manager()
    await db_manager.close()