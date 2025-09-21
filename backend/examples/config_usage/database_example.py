"""
Example: Using unified config for database operations
"""
from config.unified_config import get_config
from sqlalchemy.ext.asyncio import create_async_engine

def create_database_engine():
    config = get_config()
    
    # Instead of hardcoded URL
    # engine = create_async_engine("postgresql://...")
    
    # Use unified config
    engine = create_async_engine(
        config.get_database_url(),
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        echo=config.database.echo
    )
    return engine
