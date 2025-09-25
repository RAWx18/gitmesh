/**
 * Navigation Cache Hook for managing cache cleanup during page transitions
 * 
 * This hook handles automatic cache cleanup when users navigate between
 * different sections of the application, particularly from /contribution to /hub.
 */

import { useEffect, useCallback, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

interface NavigationCacheConfig {
  enableAutoCleanup?: boolean;
  cleanupDelay?: number; // ms to wait before cleanup
  showNotifications?: boolean;
}

interface CacheCleanupResult {
  repository_cache_cleared: boolean;
  session_cache_cleared: boolean;
  context_cache_cleared: boolean;
  entries_cleaned: number;
  memory_freed_mb: number;
  cleanup_time_ms: number;
}

const DEFAULT_CONFIG: NavigationCacheConfig = {
  enableAutoCleanup: true,
  cleanupDelay: 1000, // 1 second delay
  showNotifications: false
};

export function useNavigationCache(config: NavigationCacheConfig = {}) {
  const pathname = usePathname();
  const { user } = useAuth();
  const previousPathRef = useRef<string | null>(null);
  const cleanupTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  const finalConfig = { ...DEFAULT_CONFIG, ...config };

  /**
   * Call the backend API to handle navigation-based cache cleanup
   */
  const triggerCacheCleanup = useCallback(async (
    fromPage: string, 
    toPage: string
  ): Promise<CacheCleanupResult | null> => {
    if (!user?.id) {
      console.warn('No user ID available for cache cleanup');
      return null;
    }

    try {
      const response = await fetch('/api/v1/chat/navigation-cleanup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from_page: fromPage,
          to_page: toPage,
          user_id: user.id
        })
      });

      if (!response.ok) {
        throw new Error(`Cache cleanup failed: ${response.status}`);
      }

      const result: CacheCleanupResult = await response.json();
      
      if (finalConfig.showNotifications && result.entries_cleaned > 0) {
        toast.success(
          `Cache cleaned: ${result.entries_cleaned} entries, ${result.memory_freed_mb.toFixed(1)}MB freed`
        );
      }

      console.log('Navigation cache cleanup completed:', result);
      return result;

    } catch (error) {
      console.error('Cache cleanup error:', error);
      
      if (finalConfig.showNotifications) {
        toast.error('Cache cleanup failed');
      }
      
      return null;
    }
  }, [user?.id, finalConfig.showNotifications]);

  /**
   * Manual cache cleanup function
   */
  const manualCleanup = useCallback(async (): Promise<CacheCleanupResult | null> => {
    return triggerCacheCleanup(pathname, pathname);
  }, [pathname, triggerCacheCleanup]);

  /**
   * Clear all user cache
   */
  const clearAllCache = useCallback(async (): Promise<boolean> => {
    if (!user?.id) {
      return false;
    }

    try {
      const response = await fetch('/api/v1/chat/clear-cache', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user.id
        })
      });

      if (!response.ok) {
        throw new Error(`Clear cache failed: ${response.status}`);
      }

      const result = await response.json();
      
      if (finalConfig.showNotifications) {
        toast.success('All cache cleared successfully');
      }

      console.log('All cache cleared:', result);
      return true;

    } catch (error) {
      console.error('Clear all cache error:', error);
      
      if (finalConfig.showNotifications) {
        toast.error('Failed to clear cache');
      }
      
      return false;
    }
  }, [user?.id, finalConfig.showNotifications]);

  /**
   * Get cache statistics
   */
  const getCacheStats = useCallback(async () => {
    if (!user?.id) {
      return null;
    }

    try {
      const response = await fetch(`/api/v1/chat/cache-stats?user_id=${user.id}`);
      
      if (!response.ok) {
        throw new Error(`Get cache stats failed: ${response.status}`);
      }

      return await response.json();

    } catch (error) {
      console.error('Get cache stats error:', error);
      return null;
    }
  }, [user?.id]);

  /**
   * Check if navigation should trigger cleanup
   */
  const shouldCleanupOnNavigation = useCallback((fromPath: string, toPath: string): boolean => {
    // Clear repository cache when leaving /contribution for /hub
    if (fromPath.startsWith('/contribution') && toPath.startsWith('/hub')) {
      return true;
    }

    // Clear session cache when leaving chat
    if (fromPath.startsWith('/contribution/chat') && !toPath.startsWith('/contribution/chat')) {
      return true;
    }

    // Clear context when switching between major sections
    if (fromPath.startsWith('/hub') && toPath.startsWith('/contribution')) {
      return true;
    }

    return false;
  }, []);

  /**
   * Handle navigation changes with automatic cleanup
   */
  useEffect(() => {
    if (!finalConfig.enableAutoCleanup || !user?.id) {
      previousPathRef.current = pathname;
      return;
    }

    const previousPath = previousPathRef.current;
    
    if (previousPath && previousPath !== pathname) {
      const shouldCleanup = shouldCleanupOnNavigation(previousPath, pathname);
      
      if (shouldCleanup) {
        console.log(`Navigation detected: ${previousPath} -> ${pathname}, scheduling cleanup`);
        
        // Clear any existing timeout
        if (cleanupTimeoutRef.current) {
          clearTimeout(cleanupTimeoutRef.current);
        }

        // Schedule cleanup with delay to avoid race conditions
        cleanupTimeoutRef.current = setTimeout(() => {
          triggerCacheCleanup(previousPath, pathname);
        }, finalConfig.cleanupDelay);
      }
    }

    previousPathRef.current = pathname;

    // Cleanup timeout on unmount
    return () => {
      if (cleanupTimeoutRef.current) {
        clearTimeout(cleanupTimeoutRef.current);
      }
    };
  }, [pathname, user?.id, finalConfig.enableAutoCleanup, finalConfig.cleanupDelay, shouldCleanupOnNavigation, triggerCacheCleanup]);

  /**
   * Cleanup on component unmount (page unload)
   */
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Trigger immediate cleanup when leaving the page
      if (pathname.startsWith('/contribution') && user?.id) {
        // Use sendBeacon for reliable cleanup on page unload
        const data = JSON.stringify({
          from_page: pathname,
          to_page: 'external',
          user_id: user.id
        });

        if (navigator.sendBeacon) {
          navigator.sendBeacon('/api/v1/chat/navigation-cleanup', data);
        }
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [pathname, user?.id]);

  return {
    // Manual cleanup functions
    triggerCacheCleanup,
    manualCleanup,
    clearAllCache,
    getCacheStats,
    
    // Current state
    currentPath: pathname,
    previousPath: previousPathRef.current,
    
    // Configuration
    config: finalConfig
  };
}

/**
 * Hook for monitoring cache health and performance
 */
export function useCacheHealth() {
  const { user } = useAuth();

  const getCacheHealth = useCallback(async () => {
    if (!user?.id) {
      return null;
    }

    try {
      const response = await fetch(`/api/v1/chat/cache-health?user_id=${user.id}`);
      
      if (!response.ok) {
        throw new Error(`Get cache health failed: ${response.status}`);
      }

      return await response.json();

    } catch (error) {
      console.error('Get cache health error:', error);
      return null;
    }
  }, [user?.id]);

  const optimizeCache = useCallback(async () => {
    if (!user?.id) {
      return null;
    }

    try {
      const response = await fetch('/api/v1/chat/optimize-cache', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user.id
        })
      });

      if (!response.ok) {
        throw new Error(`Cache optimization failed: ${response.status}`);
      }

      return await response.json();

    } catch (error) {
      console.error('Cache optimization error:', error);
      return null;
    }
  }, [user?.id]);

  return {
    getCacheHealth,
    optimizeCache
  };
}