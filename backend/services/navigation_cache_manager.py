"""
Navigation Cache Manager for handling page transitions and cache cleanup.

This service manages cache lifecycle based on user navigation patterns,
automatically cleaning up repository and session data when users navigate
between different sections of the application.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from enum import Enum
from .cache_management_service import CacheManagementService, create_cache_management_service

logger = logging.getLogger(__name__)


class PageType(Enum):
    """Enumeration of page types for navigation tracking."""
    CONTRIBUTION = "contribution"
    CONTRIBUTION_CHAT = "contribution_chat"
    HUB = "hub"
    HUB_OVERVIEW = "hub_overview"
    HUB_PROJECTS = "hub_projects"
    HUB_ANALYTICS = "hub_analytics"
    HUB_SETTINGS = "hub_settings"
    OTHER = "other"


@dataclass
class NavigationEvent:
    """Navigation event data class."""
    user_id: str
    from_page: str
    to_page: str
    from_page_type: PageType
    to_page_type: PageType
    timestamp: datetime
    session_id: Optional[str] = None
    repository_url: Optional[str] = None


@dataclass
class CacheCleanupResult:
    """Cache cleanup result data class."""
    repository_cache_cleared: bool
    session_cache_cleared: bool
    context_cache_cleared: bool
    entries_cleaned: int
    memory_freed_mb: float
    cleanup_time_ms: float


class NavigationCacheManager:
    """
    Manager for handling cache cleanup based on user navigation patterns.
    
    Automatically cleans up repository data when users leave /contribution pages
    and manages session data lifecycle based on page transitions.
    """
    
    def __init__(self, user_id: str):
        """
        Initialize navigation cache manager.
        
        Args:
            user_id: User identifier
        """
        self.user_id = user_id
        self.cache_service = create_cache_management_service(user_id)
        
        # Navigation tracking
        self.current_page: Optional[str] = None
        self.current_page_type: Optional[PageType] = None
        self.navigation_history: List[NavigationEvent] = []
        self.session_start_time = datetime.now()
        
        # Cache cleanup rules - Fixed for better memory management
        self.cleanup_rules = {
            # Clear repository cache when leaving contribution pages for hub
            (PageType.CONTRIBUTION, PageType.HUB): ['repository', 'context'],
            (PageType.CONTRIBUTION, PageType.HUB_OVERVIEW): ['repository', 'context'],
            (PageType.CONTRIBUTION, PageType.HUB_PROJECTS): ['repository', 'context'],
            (PageType.CONTRIBUTION, PageType.HUB_ANALYTICS): ['repository', 'context'],
            (PageType.CONTRIBUTION, PageType.HUB_SETTINGS): ['repository', 'context'],
            
            # Clear all caches when leaving chat for hub
            (PageType.CONTRIBUTION_CHAT, PageType.HUB): ['repository', 'session', 'context'],
            (PageType.CONTRIBUTION_CHAT, PageType.HUB_OVERVIEW): ['repository', 'session', 'context'],
            (PageType.CONTRIBUTION_CHAT, PageType.HUB_PROJECTS): ['repository', 'session', 'context'],
            (PageType.CONTRIBUTION_CHAT, PageType.HUB_ANALYTICS): ['repository', 'session', 'context'],
            (PageType.CONTRIBUTION_CHAT, PageType.HUB_SETTINGS): ['repository', 'session', 'context'],
            
            # Clear session cache when leaving chat for other contribution pages
            (PageType.CONTRIBUTION_CHAT, PageType.CONTRIBUTION): ['session'],
            
            # Clear session and context when leaving chat for external pages
            (PageType.CONTRIBUTION_CHAT, PageType.OTHER): ['session', 'context'],
            
            # Clear context when switching between major sections
            (PageType.HUB, PageType.CONTRIBUTION): ['context'],
            (PageType.HUB_OVERVIEW, PageType.CONTRIBUTION): ['context'],
            (PageType.HUB_PROJECTS, PageType.CONTRIBUTION): ['context'],
            (PageType.HUB_ANALYTICS, PageType.CONTRIBUTION): ['context'],
            (PageType.HUB_SETTINGS, PageType.CONTRIBUTION): ['context'],
            
            # Clear context when switching between hub sections (optional)
            (PageType.HUB, PageType.HUB_OVERVIEW): [],
            (PageType.HUB, PageType.HUB_PROJECTS): [],
            (PageType.HUB, PageType.HUB_ANALYTICS): [],
            (PageType.HUB, PageType.HUB_SETTINGS): [],
        }
        
        logger.info(f"NavigationCacheManager initialized for user: {user_id}")
    
    def _classify_page_type(self, page_path: str) -> PageType:
        """
        Classify page type based on path.
        
        Args:
            page_path: Page path/URL
            
        Returns:
            PageType enum value
        """
        page_lower = page_path.lower()
        
        if page_lower.startswith('/contribution/chat'):
            return PageType.CONTRIBUTION_CHAT
        elif page_lower.startswith('/contribution'):
            return PageType.CONTRIBUTION
        elif page_lower.startswith('/hub/overview'):
            return PageType.HUB_OVERVIEW
        elif page_lower.startswith('/hub/projects'):
            return PageType.HUB_PROJECTS
        elif page_lower.startswith('/hub/analytics'):
            return PageType.HUB_ANALYTICS
        elif page_lower.startswith('/hub/settings'):
            return PageType.HUB_SETTINGS
        elif page_lower.startswith('/hub'):
            return PageType.HUB
        else:
            return PageType.OTHER
    
    def on_enter_contribution_page(self, user_id: str, repo_context: Dict[str, Any]) -> None:
        """
        Handle user entering contribution page.
        
        Args:
            user_id: User identifier
            repo_context: Repository context information
        """
        try:
            logger.info(f"User {user_id} entering contribution page with repo: {repo_context.get('url', 'unknown')}")
            
            # Update current page tracking
            self.current_page = "/contribution"
            self.current_page_type = PageType.CONTRIBUTION
            
            # Cache repository context if provided
            if repo_context and repo_context.get('url'):
                self.cache_service.cache_repository_data(
                    repo_context['url'],
                    repo_context,
                    ttl=3600  # 1 hour TTL for contribution page context
                )
            
            # Record navigation event
            nav_event = NavigationEvent(
                user_id=user_id,
                from_page=self.navigation_history[-1].to_page if self.navigation_history else "unknown",
                to_page="/contribution",
                from_page_type=self.navigation_history[-1].to_page_type if self.navigation_history else PageType.OTHER,
                to_page_type=PageType.CONTRIBUTION,
                timestamp=datetime.now(),
                repository_url=repo_context.get('url')
            )
            
            self.navigation_history.append(nav_event)
            
        except Exception as e:
            logger.error(f"Error handling contribution page entry: {e}")
    
    def on_leave_contribution_page(self, user_id: str) -> CacheCleanupResult:
        """
        Handle user leaving contribution page.
        
        Args:
            user_id: User identifier
            
        Returns:
            CacheCleanupResult with cleanup details
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"User {user_id} leaving contribution page, performing cache cleanup")
            
            # Get initial cache stats
            initial_stats = self.cache_service.get_cache_stats()
            initial_memory = initial_stats.memory_usage_mb
            
            # Clear repository cache
            repo_cleared = self.cache_service.clear_user_repository_cache(user_id)
            
            # Clear session cache if coming from chat
            session_cleared = False
            if (self.current_page_type == PageType.CONTRIBUTION_CHAT or 
                any(event.from_page_type == PageType.CONTRIBUTION_CHAT 
                    for event in self.navigation_history[-3:])):  # Check last 3 events
                session_cleared = self.cache_service.clear_user_session_cache(user_id)
            
            # Cleanup expired entries
            entries_cleaned = self.cache_service.cleanup_expired_caches()
            
            # Get final stats
            final_stats = self.cache_service.get_cache_stats()
            final_memory = final_stats.memory_usage_mb
            memory_freed = max(0, initial_memory - final_memory)
            
            cleanup_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = CacheCleanupResult(
                repository_cache_cleared=repo_cleared,
                session_cache_cleared=session_cleared,
                context_cache_cleared=True,  # Always clear context
                entries_cleaned=entries_cleaned,
                memory_freed_mb=memory_freed,
                cleanup_time_ms=cleanup_time
            )
            
            logger.info(f"Contribution page cleanup completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error during contribution page cleanup: {e}")
            cleanup_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return CacheCleanupResult(
                repository_cache_cleared=False,
                session_cache_cleared=False,
                context_cache_cleared=False,
                entries_cleaned=0,
                memory_freed_mb=0.0,
                cleanup_time_ms=cleanup_time
            )
    
    def on_enter_hub_page(self, user_id: str) -> None:
        """
        Handle user entering hub page.
        
        Args:
            user_id: User identifier
        """
        try:
            logger.info(f"User {user_id} entering hub page")
            
            # Update current page tracking
            self.current_page = "/hub"
            self.current_page_type = PageType.HUB
            
            # If coming from contribution, trigger cleanup
            if (self.navigation_history and 
                self.navigation_history[-1].from_page_type in [PageType.CONTRIBUTION, PageType.CONTRIBUTION_CHAT]):
                
                logger.info("Triggering cache cleanup due to contribution -> hub navigation")
                self.on_leave_contribution_page(user_id)
            
            # Record navigation event
            nav_event = NavigationEvent(
                user_id=user_id,
                from_page=self.navigation_history[-1].to_page if self.navigation_history else "unknown",
                to_page="/hub",
                from_page_type=self.navigation_history[-1].to_page_type if self.navigation_history else PageType.OTHER,
                to_page_type=PageType.HUB,
                timestamp=datetime.now()
            )
            
            self.navigation_history.append(nav_event)
            
        except Exception as e:
            logger.error(f"Error handling hub page entry: {e}")
    
    def handle_navigation(self, from_page: str, to_page: str, 
                         session_id: Optional[str] = None,
                         repository_url: Optional[str] = None) -> CacheCleanupResult:
        """
        Handle navigation between pages with automatic cache cleanup.
        
        Args:
            from_page: Page user is leaving
            to_page: Page user is navigating to
            session_id: Optional session identifier
            repository_url: Optional repository URL
            
        Returns:
            CacheCleanupResult with cleanup details
        """
        start_time = datetime.now()
        
        try:
            from_page_type = self._classify_page_type(from_page)
            to_page_type = self._classify_page_type(to_page)
            
            logger.info(f"Navigation: {from_page} ({from_page_type.value}) -> {to_page} ({to_page_type.value})")
            
            # Record navigation event
            nav_event = NavigationEvent(
                user_id=self.user_id,
                from_page=from_page,
                to_page=to_page,
                from_page_type=from_page_type,
                to_page_type=to_page_type,
                timestamp=datetime.now(),
                session_id=session_id,
                repository_url=repository_url
            )
            
            self.navigation_history.append(nav_event)
            
            # Update current page tracking
            self.current_page = to_page
            self.current_page_type = to_page_type
            
            # Check cleanup rules
            cleanup_key = (from_page_type, to_page_type)
            cleanup_types = self.cleanup_rules.get(cleanup_key, [])
            
            if not cleanup_types:
                # No cleanup needed
                return CacheCleanupResult(
                    repository_cache_cleared=False,
                    session_cache_cleared=False,
                    context_cache_cleared=False,
                    entries_cleaned=0,
                    memory_freed_mb=0.0,
                    cleanup_time_ms=0.0
                )
            
            # Get initial stats
            initial_stats = self.cache_service.get_cache_stats()
            initial_memory = initial_stats.memory_usage_mb
            
            # Perform cleanup based on rules
            repo_cleared = False
            session_cleared = False
            context_cleared = False
            
            if 'repository' in cleanup_types:
                repo_cleared = self.cache_service.clear_user_repository_cache()
                logger.info("Repository cache cleared due to navigation rule")
            
            if 'session' in cleanup_types:
                session_cleared = self.cache_service.clear_user_session_cache()
                logger.info("Session cache cleared due to navigation rule")
            
            if 'context' in cleanup_types:
                context_cleared = True
                logger.info("Context cache cleared due to navigation rule")
            
            # Cleanup expired entries
            entries_cleaned = self.cache_service.cleanup_expired_caches()
            
            # Get final stats
            final_stats = self.cache_service.get_cache_stats()
            final_memory = final_stats.memory_usage_mb
            memory_freed = max(0, initial_memory - final_memory)
            
            cleanup_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = CacheCleanupResult(
                repository_cache_cleared=repo_cleared,
                session_cache_cleared=session_cleared,
                context_cache_cleared=context_cleared,
                entries_cleaned=entries_cleaned,
                memory_freed_mb=memory_freed,
                cleanup_time_ms=cleanup_time
            )
            
            logger.info(f"Navigation cleanup completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error during navigation handling: {e}")
            cleanup_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return CacheCleanupResult(
                repository_cache_cleared=False,
                session_cache_cleared=False,
                context_cache_cleared=False,
                entries_cleaned=0,
                memory_freed_mb=0.0,
                cleanup_time_ms=cleanup_time
            )
    
    def cleanup_expired_caches(self) -> int:
        """
        Cleanup expired cache entries.
        
        Returns:
            Number of entries cleaned up
        """
        try:
            cleaned_count = self.cache_service.cleanup_expired_caches()
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired cache entries")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return 0
    
    def get_navigation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent navigation history.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of navigation events
        """
        try:
            recent_events = self.navigation_history[-limit:] if self.navigation_history else []
            
            return [
                {
                    'from_page': event.from_page,
                    'to_page': event.to_page,
                    'from_page_type': event.from_page_type.value,
                    'to_page_type': event.to_page_type.value,
                    'timestamp': event.timestamp.isoformat(),
                    'session_id': event.session_id,
                    'repository_url': event.repository_url
                }
                for event in recent_events
            ]
            
        except Exception as e:
            logger.error(f"Error getting navigation history: {e}")
            return []
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        try:
            session_duration = (datetime.now() - self.session_start_time).total_seconds()
            
            # Count page types visited
            page_type_counts = {}
            for event in self.navigation_history:
                page_type = event.to_page_type.value
                page_type_counts[page_type] = page_type_counts.get(page_type, 0) + 1
            
            # Get cache stats
            cache_stats = self.cache_service.get_cache_stats()
            
            return {
                'session_duration_seconds': session_duration,
                'navigation_events': len(self.navigation_history),
                'current_page': self.current_page,
                'current_page_type': self.current_page_type.value if self.current_page_type else None,
                'page_type_visits': page_type_counts,
                'cache_stats': {
                    'total_keys': cache_stats.total_keys,
                    'memory_usage_mb': cache_stats.memory_usage_mb,
                    'hit_rate': cache_stats.hit_rate,
                    'repository_cache_count': cache_stats.repository_cache_count,
                    'session_cache_count': cache_stats.session_cache_count
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {
                'error': str(e),
                'session_duration_seconds': 0,
                'navigation_events': 0
            }


def create_navigation_cache_manager(user_id: str) -> NavigationCacheManager:
    """
    Create a navigation cache manager instance.
    
    Args:
        user_id: User identifier
        
    Returns:
        NavigationCacheManager instance
    """
    return NavigationCacheManager(user_id)