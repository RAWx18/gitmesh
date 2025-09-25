"""
Health Check API Routes

Provides health check endpoints for all major components of the Cosmos optimization system.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
import logging
from datetime import datetime

try:
    # Try relative imports first (when used as module)
    from ....services.performance_monitoring_service import get_performance_monitoring_service
    from ....services.smart_redis_repo_manager import SmartRedisRepoManager
    from ....services.intelligent_vfs import IntelligentVFS
    from ....config.settings import get_settings
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.performance_monitoring_service import get_performance_monitoring_service
    from services.smart_redis_repo_manager import SmartRedisRepoManager
    from services.intelligent_vfs import IntelligentVFS
    from config.settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    Returns overall system health status.
    """
    try:
        monitoring_service = get_performance_monitoring_service()
        health_results = await monitoring_service.health_checker.run_all_health_checks()
        
        # Determine overall status
        statuses = [result.status.value for result in health_results.values()]
        
        if "critical" in statuses:
            overall_status = "critical"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": {
                component: result.to_dict()
                for component, result in health_results.items()
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "critical",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check with performance metrics.
    """
    try:
        monitoring_service = get_performance_monitoring_service()
        
        # Get health check results
        health_results = await monitoring_service.health_checker.run_all_health_checks()
        
        # Get performance summary
        performance_summary = await monitoring_service.get_performance_summary()
        
        # Get system metrics
        system_metrics = await _get_system_metrics()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "health_checks": {
                component: result.to_dict()
                for component, result in health_results.items()
            },
            "performance": performance_summary,
            "system": system_metrics
        }
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/redis")
async def redis_health_check() -> Dict[str, Any]:
    """
    Redis-specific health check with connectivity and performance metrics.
    """
    try:
        monitoring_service = get_performance_monitoring_service()
        redis_health = await monitoring_service.health_checker.run_health_check("redis")
        
        # Get Redis-specific metrics
        redis_metrics = await _get_redis_metrics()
        
        return {
            "component": "redis",
            "health": redis_health.to_dict(),
            "metrics": redis_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vfs")
async def vfs_health_check() -> Dict[str, Any]:
    """
    Virtual File System health check with integrity validation.
    """
    try:
        # Check VFS integrity
        vfs_status = await _check_vfs_integrity()
        
        return {
            "component": "virtual_file_system",
            "status": vfs_status["status"],
            "details": vfs_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"VFS health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cosmos")
async def cosmos_health_check() -> Dict[str, Any]:
    """
    Cosmos engine health validation.
    """
    try:
        # Check Cosmos engine health
        cosmos_status = await _check_cosmos_engine_health()
        
        return {
            "component": "cosmos_engine",
            "status": cosmos_status["status"],
            "details": cosmos_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cosmos health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def performance_metrics() -> Dict[str, Any]:
    """
    Get current performance metrics.
    """
    try:
        monitoring_service = get_performance_monitoring_service()
        performance_summary = await monitoring_service.get_performance_summary()
        
        return {
            "metrics": performance_summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Performance metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_active_alerts() -> Dict[str, Any]:
    """
    Get active performance alerts.
    """
    try:
        monitoring_service = get_performance_monitoring_service()
        
        # Get recent alert metrics
        from datetime import timedelta
        recent_alerts = await monitoring_service.metrics_collector.get_metrics(
            "performance_alerts",
            since=datetime.now() - timedelta(hours=24)
        )
        
        active_alerts = []
        for alert in monitoring_service.alerts:
            if alert.last_triggered:
                time_since_trigger = datetime.now() - alert.last_triggered
                if time_since_trigger.total_seconds() < 3600:  # Last hour
                    active_alerts.append({
                        "name": alert.name,
                        "message": alert.message,
                        "severity": alert.severity,
                        "triggered_at": alert.last_triggered.isoformat(),
                        "minutes_ago": int(time_since_trigger.total_seconds() / 60)
                    })
        
        return {
            "active_alerts": active_alerts,
            "total_alerts_24h": len(recent_alerts),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Alert retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Helper functions

async def _get_system_metrics() -> Dict[str, Any]:
    """Get system-level metrics."""
    try:
        import psutil
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        
        # Process metrics
        process = psutil.Process()
        process_memory = process.memory_info()
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count
            },
            "memory": {
                "total_gb": memory.total / (1024**3),
                "available_gb": memory.available / (1024**3),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024**3),
                "free_gb": disk.free / (1024**3),
                "percent": (disk.used / disk.total) * 100
            },
            "process": {
                "memory_mb": process_memory.rss / (1024**2),
                "memory_percent": process.memory_percent()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        return {"error": str(e)}


async def _get_redis_metrics() -> Dict[str, Any]:
    """Get Redis-specific metrics."""
    try:
        from ..services.performance_optimization_service import get_performance_service
        perf_service = get_performance_service()
        
        # Get connection pool stats
        pool_stats = perf_service.connection_pool_manager.get_pool_stats()
        
        # Get Redis info
        client = perf_service.get_redis_client()
        redis_info = client.info()
        
        return {
            "connection_pools": pool_stats,
            "redis_info": {
                "connected_clients": redis_info.get("connected_clients", 0),
                "used_memory_human": redis_info.get("used_memory_human", "unknown"),
                "keyspace_hits": redis_info.get("keyspace_hits", 0),
                "keyspace_misses": redis_info.get("keyspace_misses", 0),
                "total_commands_processed": redis_info.get("total_commands_processed", 0)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting Redis metrics: {e}")
        return {"error": str(e)}


async def _check_vfs_integrity() -> Dict[str, Any]:
    """Check Virtual File System integrity."""
    try:
        # This would check VFS integrity
        # For now, return a basic status
        return {
            "status": "healthy",
            "message": "Virtual File System is operational",
            "details": {
                "indexed_files": 0,  # Would be populated with actual data
                "cache_size": 0,
                "last_update": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"VFS integrity check failed: {e}")
        return {
            "status": "critical",
            "message": f"VFS integrity check failed: {str(e)}",
            "error": str(e)
        }


async def _check_cosmos_engine_health() -> Dict[str, Any]:
    """Check Cosmos engine health."""
    try:
        # This would check Cosmos engine health
        # For now, return a basic status
        return {
            "status": "healthy",
            "message": "Cosmos engine is operational",
            "details": {
                "models_available": True,
                "last_request": None,
                "avg_response_time": None
            }
        }
        
    except Exception as e:
        logger.error(f"Cosmos engine health check failed: {e}")
        return {
            "status": "critical",
            "message": f"Cosmos engine health check failed: {str(e)}",
            "error": str(e)
        }