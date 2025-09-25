"""
Cache Cleanup Scheduler Service

Provides scheduled cleanup jobs for cache management, including:
- Periodic expired cache cleanup
- Memory usage optimization
- Health monitoring and alerting
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

from .cache_management_service import create_cache_management_service
from .navigation_cache_manager import create_navigation_cache_manager

logger = logging.getLogger(__name__)


@dataclass
class CleanupJobResult:
    """Result of a cleanup job execution."""
    job_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    entries_cleaned: int
    memory_freed_mb: float
    error_message: Optional[str] = None


@dataclass
class SchedulerConfig:
    """Configuration for the cache cleanup scheduler."""
    # Cleanup intervals (in seconds)
    expired_cleanup_interval: int = 300  # 5 minutes
    memory_optimization_interval: int = 1800  # 30 minutes
    health_check_interval: int = 60  # 1 minute
    
    # Memory thresholds
    memory_warning_threshold_mb: float = 80.0  # 80MB
    memory_critical_threshold_mb: float = 100.0  # 100MB
    
    # Cleanup limits
    max_cleanup_duration_seconds: int = 30  # Max 30 seconds per cleanup
    max_concurrent_cleanups: int = 2
    
    # Health monitoring
    enable_health_monitoring: bool = True
    enable_memory_alerts: bool = True
    
    # Logging
    log_cleanup_results: bool = True
    log_health_status: bool = False


class CacheCleanupScheduler:
    """
    Scheduler for automated cache cleanup and maintenance tasks.
    
    Runs background jobs to:
    - Clean up expired cache entries
    - Optimize memory usage
    - Monitor cache health
    - Alert on issues
    """
    
    def __init__(self, config: SchedulerConfig = None):
        """
        Initialize the cache cleanup scheduler.
        
        Args:
            config: Scheduler configuration
        """
        self.config = config or SchedulerConfig()
        self.is_running = False
        self.jobs_running = set()
        self.job_history: List[CleanupJobResult] = []
        self.last_health_check: Optional[datetime] = None
        self.health_alerts_sent = set()
        
        # Thread pool for cleanup jobs
        self.executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent_cleanups,
            thread_name_prefix="cache-cleanup"
        )
        
        # Background task handles
        self.cleanup_task: Optional[asyncio.Task] = None
        self.optimization_task: Optional[asyncio.Task] = None
        self.health_task: Optional[asyncio.Task] = None
        
        logger.info(f"CacheCleanupScheduler initialized with config: {self.config}")
    
    async def start(self):
        """Start the scheduler and all background tasks."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.is_running = True
        logger.info("Starting cache cleanup scheduler")
        
        # Start background tasks
        self.cleanup_task = asyncio.create_task(self._expired_cleanup_loop())
        self.optimization_task = asyncio.create_task(self._memory_optimization_loop())
        
        if self.config.enable_health_monitoring:
            self.health_task = asyncio.create_task(self._health_monitoring_loop())
        
        logger.info("Cache cleanup scheduler started successfully")
    
    async def stop(self):
        """Stop the scheduler and all background tasks."""
        if not self.is_running:
            return
        
        logger.info("Stopping cache cleanup scheduler")
        self.is_running = False
        
        # Cancel background tasks
        tasks = [self.cleanup_task, self.optimization_task, self.health_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Shutdown thread pool
        self.executor.shutdown(wait=True)
        
        logger.info("Cache cleanup scheduler stopped")
    
    async def _expired_cleanup_loop(self):
        """Background loop for cleaning up expired cache entries."""
        while self.is_running:
            try:
                await self._run_expired_cleanup_job()
                await asyncio.sleep(self.config.expired_cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in expired cleanup loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _memory_optimization_loop(self):
        """Background loop for memory optimization."""
        while self.is_running:
            try:
                await self._run_memory_optimization_job()
                await asyncio.sleep(self.config.memory_optimization_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory optimization loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _health_monitoring_loop(self):
        """Background loop for health monitoring."""
        while self.is_running:
            try:
                await self._run_health_check_job()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def _run_expired_cleanup_job(self):
        """Run expired cache cleanup job."""
        job_name = "expired_cleanup"
        
        if job_name in self.jobs_running:
            logger.debug(f"Job {job_name} already running, skipping")
            return
        
        self.jobs_running.add(job_name)
        start_time = datetime.now()
        
        try:
            # Run cleanup in thread pool to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._execute_expired_cleanup
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            job_result = CleanupJobResult(
                job_name=job_name,
                success=True,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                entries_cleaned=result.get('total_cleaned', 0),
                memory_freed_mb=result.get('total_memory_freed', 0.0)
            )
            
            self._record_job_result(job_result)
            
            if self.config.log_cleanup_results and result.get('total_cleaned', 0) > 0:
                logger.info(f"Expired cleanup completed: {result}")
                
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            job_result = CleanupJobResult(
                job_name=job_name,
                success=False,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                entries_cleaned=0,
                memory_freed_mb=0.0,
                error_message=str(e)
            )
            
            self._record_job_result(job_result)
            logger.error(f"Expired cleanup job failed: {e}")
            
        finally:
            self.jobs_running.discard(job_name)
    
    def _execute_expired_cleanup(self) -> Dict[str, Any]:
        """Execute expired cleanup for all users (thread-safe)."""
        total_cleaned = 0
        total_memory_freed = 0.0
        users_processed = 0
        
        # For now, we'll create a generic cache service to clean system-wide expired entries
        # In a production system, you might want to track active users and clean their caches
        try:
            # Create a system-wide cache service
            cache_service = create_cache_management_service("system")
            
            # Get initial memory usage
            initial_memory = cache_service._get_memory_usage_mb()
            
            # Clean expired caches
            cleaned_count = cache_service.cleanup_expired_caches()
            total_cleaned += cleaned_count
            
            # Get final memory usage
            final_memory = cache_service._get_memory_usage_mb()
            memory_freed = max(0, initial_memory - final_memory)
            total_memory_freed += memory_freed
            
            users_processed += 1
            
        except Exception as e:
            logger.error(f"Error cleaning expired caches: {e}")
        
        return {
            'total_cleaned': total_cleaned,
            'total_memory_freed': total_memory_freed,
            'users_processed': users_processed
        }
    
    async def _run_memory_optimization_job(self):
        """Run memory optimization job."""
        job_name = "memory_optimization"
        
        if job_name in self.jobs_running:
            logger.debug(f"Job {job_name} already running, skipping")
            return
        
        self.jobs_running.add(job_name)
        start_time = datetime.now()
        
        try:
            # Run optimization in thread pool
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._execute_memory_optimization
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            job_result = CleanupJobResult(
                job_name=job_name,
                success=True,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                entries_cleaned=result.get('total_cleaned', 0),
                memory_freed_mb=result.get('total_memory_freed', 0.0)
            )
            
            self._record_job_result(job_result)
            
            if self.config.log_cleanup_results:
                logger.info(f"Memory optimization completed: {result}")
                
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            job_result = CleanupJobResult(
                job_name=job_name,
                success=False,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                entries_cleaned=0,
                memory_freed_mb=0.0,
                error_message=str(e)
            )
            
            self._record_job_result(job_result)
            logger.error(f"Memory optimization job failed: {e}")
            
        finally:
            self.jobs_running.discard(job_name)
    
    def _execute_memory_optimization(self) -> Dict[str, Any]:
        """Execute memory optimization (thread-safe)."""
        try:
            cache_service = create_cache_management_service("system")
            optimization_results = cache_service.optimize_memory_usage()
            
            return {
                'total_cleaned': optimization_results.get('cleaned_entries', 0),
                'total_memory_freed': optimization_results.get('memory_saved_mb', 0.0),
                'optimization_results': optimization_results
            }
            
        except Exception as e:
            logger.error(f"Error during memory optimization: {e}")
            return {
                'total_cleaned': 0,
                'total_memory_freed': 0.0,
                'error': str(e)
            }
    
    async def _run_health_check_job(self):
        """Run health check job."""
        try:
            cache_service = create_cache_management_service("system")
            health_status = cache_service.health_check()
            cache_stats = cache_service.get_cache_stats()
            
            self.last_health_check = datetime.now()
            
            # Check for health issues
            if not health_status.is_healthy:
                await self._handle_health_alert("unhealthy", {
                    'connection_status': health_status.connection_status,
                    'error_count': health_status.error_count,
                    'last_error': health_status.last_error
                })
            
            # Check memory usage
            if (self.config.enable_memory_alerts and 
                cache_stats.memory_usage_mb > self.config.memory_warning_threshold_mb):
                
                alert_level = "critical" if cache_stats.memory_usage_mb > self.config.memory_critical_threshold_mb else "warning"
                
                await self._handle_memory_alert(alert_level, {
                    'memory_usage_mb': cache_stats.memory_usage_mb,
                    'total_keys': cache_stats.total_keys,
                    'threshold_mb': self.config.memory_critical_threshold_mb if alert_level == "critical" else self.config.memory_warning_threshold_mb
                })
            
            if self.config.log_health_status:
                logger.debug(f"Health check: healthy={health_status.is_healthy}, memory={cache_stats.memory_usage_mb:.1f}MB")
                
        except Exception as e:
            logger.error(f"Health check job failed: {e}")
    
    async def _handle_health_alert(self, alert_type: str, details: Dict[str, Any]):
        """Handle health alert."""
        alert_key = f"health_{alert_type}"
        
        if alert_key not in self.health_alerts_sent:
            logger.warning(f"Cache health alert ({alert_type}): {details}")
            self.health_alerts_sent.add(alert_key)
            
            # In a production system, you might want to send notifications here
            # e.g., email, Slack, PagerDuty, etc.
    
    async def _handle_memory_alert(self, alert_level: str, details: Dict[str, Any]):
        """Handle memory usage alert."""
        alert_key = f"memory_{alert_level}"
        
        # Only send alert once per hour for the same level
        now = datetime.now()
        last_alert_time = getattr(self, f'last_{alert_key}_alert', None)
        
        if not last_alert_time or (now - last_alert_time).total_seconds() > 3600:
            logger.warning(f"Cache memory alert ({alert_level}): {details}")
            setattr(self, f'last_{alert_key}_alert', now)
            
            # Trigger immediate cleanup if critical
            if alert_level == "critical":
                logger.info("Triggering immediate cleanup due to critical memory usage")
                await self._run_memory_optimization_job()
    
    def _record_job_result(self, result: CleanupJobResult):
        """Record job result in history."""
        self.job_history.append(result)
        
        # Keep only last 100 results
        if len(self.job_history) > 100:
            self.job_history = self.job_history[-100:]
    
    def get_job_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent job history."""
        recent_jobs = self.job_history[-limit:] if self.job_history else []
        
        return [
            {
                'job_name': job.job_name,
                'success': job.success,
                'start_time': job.start_time.isoformat(),
                'end_time': job.end_time.isoformat(),
                'duration_seconds': job.duration_seconds,
                'entries_cleaned': job.entries_cleaned,
                'memory_freed_mb': job.memory_freed_mb,
                'error_message': job.error_message
            }
            for job in reversed(recent_jobs)
        ]
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        now = datetime.now()
        
        # Calculate success rates
        recent_jobs = self.job_history[-50:] if self.job_history else []
        total_jobs = len(recent_jobs)
        successful_jobs = sum(1 for job in recent_jobs if job.success)
        success_rate = (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
        
        # Calculate total cleanup stats
        total_entries_cleaned = sum(job.entries_cleaned for job in recent_jobs)
        total_memory_freed = sum(job.memory_freed_mb for job in recent_jobs)
        
        return {
            'is_running': self.is_running,
            'jobs_running': list(self.jobs_running),
            'total_jobs_executed': len(self.job_history),
            'recent_success_rate': success_rate,
            'total_entries_cleaned': total_entries_cleaned,
            'total_memory_freed_mb': total_memory_freed,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'config': {
                'expired_cleanup_interval': self.config.expired_cleanup_interval,
                'memory_optimization_interval': self.config.memory_optimization_interval,
                'health_check_interval': self.config.health_check_interval,
                'memory_warning_threshold_mb': self.config.memory_warning_threshold_mb,
                'memory_critical_threshold_mb': self.config.memory_critical_threshold_mb
            }
        }


# Global scheduler instance
_scheduler_instance: Optional[CacheCleanupScheduler] = None
_scheduler_lock = threading.Lock()


def get_cache_cleanup_scheduler(config: SchedulerConfig = None) -> CacheCleanupScheduler:
    """
    Get the global cache cleanup scheduler instance.
    
    Args:
        config: Scheduler configuration (only used on first call)
        
    Returns:
        CacheCleanupScheduler instance
    """
    global _scheduler_instance
    
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = CacheCleanupScheduler(config)
        
        return _scheduler_instance


async def start_cache_cleanup_scheduler(config: SchedulerConfig = None):
    """Start the global cache cleanup scheduler."""
    scheduler = get_cache_cleanup_scheduler(config)
    await scheduler.start()


async def stop_cache_cleanup_scheduler():
    """Stop the global cache cleanup scheduler."""
    global _scheduler_instance
    
    if _scheduler_instance:
        await _scheduler_instance.stop()