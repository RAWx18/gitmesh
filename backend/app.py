"""
Gitmesh FastAPI Application
Main entry point for the system.
"""
import sys
import os

# Add the parent directory to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

load_dotenv()

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict, Any
import structlog
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import core components
from config.settings import get_settings
from utils.tracing import trace

# Import API routes
from api.v1.routes import health
from api.v1.routes.auth import router as auth_router
from api.v1.routes.github import router as github_router
from api.v1.routes.analytics import router as analytics_router
from api.v1.routes.projects import router as projects_router
from api.v1.routes.webhooks import router as webhooks_router
from api.v1.routes.aggregated import router as aggregated_router
from api.v1.routes.websocket import router as websocket_router
from api.v1.routes.file_upload import router as file_upload_router
from api.v1.routes.static import router as static_router
from api.v1.routes.hub import router as hub_router

logger = structlog.get_logger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    
    # Startup
    logger.info("🚀 Starting Gitmesh System...")
    
    try:
        # Initialize database first
        from config.database import get_database_manager
        db_manager = get_database_manager()
        db_success = await db_manager.initialize()
        if not db_success:
            logger.error("❌ Failed to initialize database")
            raise RuntimeError("Database initialization failed")
        app.state.db_manager = db_manager
        
        logger.info("✅ Database initialized successfully")
        
        logger.info("✅ Gitmesh System started successfully")
        trace("app_started", {"status": "success"})
        
    except Exception as e:
        logger.error("❌ Failed to start Gitmesh System", error=str(e))
        trace("app_started", {"status": "failed", "error": str(e)})
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Gitmesh System...")
    try:
        # Shutdown database connections
        from config.database import close_database
        await close_database()
        logger.info("✅ Database connections closed")
        
        trace("app_shutdown", {"status": "success"})
    except Exception as e:
        logger.error("❌ Error during shutdown", error=str(e))
        trace("app_shutdown", {"status": "failed", "error": str(e)})


# Create FastAPI app
app = FastAPI(
    title="Gitmesh System",
    description="Git collaboration system",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(github_router, prefix="/api/v1/github", tags=["github"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(aggregated_router, prefix="/api/v1/aggregated", tags=["aggregated"])

# Include routes for JS backend compatibility
app.include_router(websocket_router, prefix="/api/v1", tags=["websocket"])
app.include_router(file_upload_router, prefix="/api/v1", tags=["file_upload"])
app.include_router(static_router, tags=["static_files"])
app.include_router(hub_router, prefix="/api/v1/hub", tags=["hub"])

# Include AI import routes (Cosmos integration)
try:
    from api.v1.routes.ai_import import router as ai_import_router
    app.include_router(ai_import_router, prefix="/api/ai", tags=["ai_import"])
    logger.info("✅ AI Import routes (Cosmos) loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ AI Import routes not available: {e}")
except Exception as e:
    logger.error(f"❌ Error loading AI Import routes: {e}")

# Include Chat routes (Cosmos AI integration)
try:
    from api.v1.routes.chat import router as chat_router
    app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
    logger.info("✅ Chat routes (Cosmos AI) loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ Chat routes not available: {e}")
except Exception as e:
    logger.error(f"❌ Error loading Chat routes: {e}")

# Add a test endpoint to verify the connection
@app.get("/test")
async def test_connection():
    """Test endpoint to verify the system is running."""
    return {
        "status": "ok",
        "message": "Gitmesh System is running",
        "version": "2.0.0",
        "websocket_support": "enabled",
        "file_upload_support": "enabled", 
        "static_file_support": "enabled",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/test/quick")
async def quick_test():
    """Quick test endpoint for fast response."""
    return {
        "status": "ok",
        "message": "Quick response test",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint."""
    try:
        return {
            "status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "components": {
                "database": True
            }
        }
    
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": asyncio.get_event_loop().time()
        }

# API documentation customization
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Gitmesh System",
        "version": "2.0.0",
        "description": "Git collaboration system",
        "features": [
            "GitHub OAuth authentication",
            "GitHub API integration",
            "Advanced analytics",
            "Webhook processing"
        ],
        "endpoints": {
            "health": "/health",
            "test": "/test", 
            "auth": "/api/v1/auth",
            "github": "/api/v1/github",
            "analytics": "/api/v1/analytics",
            "projects": "/api/v1/projects",
            "websocket": "/api/v1/chat/ws",
            "file_upload": "/api/v1/import",
            "static_files": "/public/* and /static/*",
            "webhooks": "/api/v1/webhooks",
            "aggregated": "/api/v1/aggregated",
            "docs": "/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # Development server configuration
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
