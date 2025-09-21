#!/usr/bin/env python3
"""
Backend Restart Script for Rate Limit Recovery
Monitors rate limit status and restarts services when needed
"""

import os
import sys
import time
import signal
import logging
import asyncio
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.supabase_service import supabase_service
from utils.github_utils import GitHubAPIClient
from config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimitMonitor:
    """Monitor and handle GitHub API rate limits."""
    
    def __init__(self):
        self.github_client = GitHubAPIClient()
        self.monitoring = False
        self.restart_threshold = 5  # Restart after 5 consecutive rate limit hits
        self.consecutive_rate_limits = 0
        self.last_restart = None
        self.min_restart_interval = timedelta(minutes=30)  # Minimum 30 minutes between restarts
    
    async def start_monitoring(self):
        """Start monitoring rate limits."""
        logger.info("Starting rate limit monitoring...")
        self.monitoring = True
        
        try:
            await supabase_service.initialize()
            
            while self.monitoring:
                await self.check_rate_limits()
                await asyncio.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
        finally:
            await supabase_service.close()
    
    async def check_rate_limits(self):
        """Check current rate limit status."""
        try:
            # Check GitHub API rate limits
            rate_limit_status = await self.check_github_rate_limits()
            
            if rate_limit_status and rate_limit_status.get('is_rate_limited'):
                self.consecutive_rate_limits += 1
                logger.warning(f"Rate limit detected ({self.consecutive_rate_limits}/{self.restart_threshold})")
                
                # Check if we should restart
                if self.consecutive_rate_limits >= self.restart_threshold:
                    await self.handle_rate_limit_restart()
            else:
                # Reset counter on successful check
                if self.consecutive_rate_limits > 0:
                    logger.info("Rate limits cleared, resetting counter")
                    self.consecutive_rate_limits = 0
            
            # Check Supabase rate limit records
            await self.check_supabase_rate_limits()
            
        except Exception as e:
            logger.error(f"Error checking rate limits: {e}")
    
    async def check_github_rate_limits(self) -> Optional[Dict[str, Any]]:
        """Check GitHub API rate limits."""
        try:
            # Try to make a simple API call to check rate limits
            response, headers = await self.github_client._make_request('GET', '/rate_limit')
            
            if 'rate' in response:
                rate_info = response['rate']
                return {
                    'limit': rate_info.get('limit', 5000),
                    'remaining': rate_info.get('remaining', 5000),
                    'reset': rate_info.get('reset', 0),
                    'is_rate_limited': rate_info.get('remaining', 5000) <= 10,
                    'is_near_limit': rate_info.get('remaining', 5000) <= (rate_info.get('limit', 5000) * 0.1)
                }
            
            return None
            
        except Exception as e:
            if "rate limit" in str(e).lower():
                return {'is_rate_limited': True, 'error': str(e)}
            logger.error(f"Error checking GitHub rate limits: {e}")
            return None
    
    async def check_supabase_rate_limits(self):
        """Check rate limits stored in Supabase."""
        try:
            # This would check for blocked users or high rate limit violations
            # For now, just log that we're checking
            logger.debug("Checking Supabase rate limit records...")
            
        except Exception as e:
            logger.error(f"Error checking Supabase rate limits: {e}")
    
    async def handle_rate_limit_restart(self):
        """Handle backend restart due to rate limits."""
        try:
            # Check if enough time has passed since last restart
            if self.last_restart:
                time_since_restart = datetime.now() - self.last_restart
                if time_since_restart < self.min_restart_interval:
                    logger.warning(f"Skipping restart, only {time_since_restart} since last restart")
                    return
            
            logger.warning("Rate limit threshold reached, initiating backend restart...")
            
            # Record restart event in Supabase
            await supabase_service.record_user_event(
                'system',
                'backend_restart',
                {
                    'reason': 'rate_limit_exceeded',
                    'consecutive_hits': self.consecutive_rate_limits,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
            
            # Perform restart
            await self.restart_backend()
            
            # Update restart time and reset counter
            self.last_restart = datetime.now()
            self.consecutive_rate_limits = 0
            
            logger.info("Backend restart completed")
            
        except Exception as e:
            logger.error(f"Error during restart: {e}")
    
    async def restart_backend(self):
        """Restart the backend services."""
        try:
            # Method 1: Graceful restart using systemctl (if running as service)
            if await self.try_systemctl_restart():
                return
            
            # Method 2: Docker restart (if running in Docker)
            if await self.try_docker_restart():
                return
            
            # Method 3: Process restart (if running as standalone process)
            if await self.try_process_restart():
                return
            
            logger.warning("No suitable restart method found")
            
        except Exception as e:
            logger.error(f"Error restarting backend: {e}")
    
    async def try_systemctl_restart(self) -> bool:
        """Try to restart using systemctl."""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'gitmesh-backend'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Restarting backend using systemctl...")
                subprocess.run(['systemctl', 'restart', 'gitmesh-backend'], check=True)
                return True
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        return False
    
    async def try_docker_restart(self) -> bool:
        """Try to restart using Docker."""
        try:
            # Check if running in Docker
            result = subprocess.run(
                ['docker', 'ps', '--filter', 'name=gitmesh-backend', '--format', '{{.Names}}'],
                capture_output=True,
                text=True
            )
            
            if 'gitmesh-backend' in result.stdout:
                logger.info("Restarting backend using Docker...")
                subprocess.run(['docker', 'restart', 'gitmesh-backend'], check=True)
                return True
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        return False
    
    async def try_process_restart(self) -> bool:
        """Try to restart by killing and restarting the process."""
        try:
            # This is more complex and depends on how the backend is started
            # For now, just log that we would restart
            logger.info("Would restart backend process (not implemented)")
            return False
            
        except Exception:
            pass
        
        return False
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self.monitoring = False


class BackendHealthChecker:
    """Check backend health and restart if needed."""
    
    def __init__(self):
        self.health_check_url = f"{settings.PYTHON_SERVER}/health"
        self.max_failures = 3
        self.consecutive_failures = 0
    
    async def check_health(self) -> bool:
        """Check if backend is healthy."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.health_check_url, timeout=10) as response:
                    if response.status == 200:
                        self.consecutive_failures = 0
                        return True
                    else:
                        self.consecutive_failures += 1
                        return False
                        
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.consecutive_failures += 1
            return False
    
    async def monitor_health(self):
        """Monitor backend health."""
        while True:
            try:
                is_healthy = await self.check_health()
                
                if not is_healthy:
                    logger.warning(f"Backend health check failed ({self.consecutive_failures}/{self.max_failures})")
                    
                    if self.consecutive_failures >= self.max_failures:
                        logger.error("Backend appears to be down, attempting restart...")
                        # Here you could trigger a restart
                        
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(30)


async def main():
    """Main monitoring function."""
    monitor = RateLimitMonitor()
    health_checker = BackendHealthChecker()
    
    # Set up signal handlers
    def signal_handler(signum, frame):
        logger.info("Received signal, stopping monitoring...")
        monitor.stop_monitoring()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start monitoring tasks
    tasks = [
        asyncio.create_task(monitor.start_monitoring()),
        asyncio.create_task(health_checker.monitor_health())
    ]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped")
    finally:
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()


if __name__ == "__main__":
    asyncio.run(main())