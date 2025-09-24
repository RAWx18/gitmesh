/**
 * Repository Cache Management Hook
 * 
 * Manages automatic repository caching when users navigate to/from contribution pages.
 * Handles the asyncio event loop issue by using proper API calls.
 */

import { useCallback, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { apiService } from '@/lib/api';

interface CacheStatus {
  cached: boolean;
  repository_name?: string;
  branch?: string;
  file_count?: number;
  ready_for_chat?: boolean;
  message?: string;
}

interface CacheResponse {
  success: boolean;
  message: string;
  repository_name: string;
  cached_at: string;
  file_count?: number;
}

export const useRepositoryCache = () => {
  const { token } = useAuth();
  const { repository } = useRepository();
  const router = useRouter();
  const cacheRequestRef = useRef<AbortController | null>(null);
  const currentRepoRef = useRef<string | null>(null);

  /**
   * Cache a repository for immediate access
   */
  const cacheRepository = useCallback(async (
    repoUrl: string,
    branch: string = 'main',
    userTier: string = 'free'
  ): Promise<CacheResponse | null> => {
    if (!token) {
      console.warn('No authentication token available for repository caching');
      return null;
    }

    try {
      // Cancel any existing cache request
      if (cacheRequestRef.current) {
        cacheRequestRef.current.abort();
      }

      // Create new abort controller
      cacheRequestRef.current = new AbortController();

      console.log(`Starting repository cache for: ${repoUrl}`);

      const response = await fetch('/api/v1/repository-cache/cache', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          repo_url: repoUrl,
          branch,
          user_tier: userTier,
        }),
        signal: cacheRequestRef.current.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const data: CacheResponse = await response.json();
      console.log(`Repository caching started: ${data.repository_name}`);
      
      return data;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Repository cache request was cancelled');
        return null;
      }
      
      console.error('Error caching repository:', error);
      return null;
    }
  }, [token]);

  /**
   * Check the cache status of a repository
   */
  const getCacheStatus = useCallback(async (
    repoName: string,
    branch: string = 'main'
  ): Promise<CacheStatus | null> => {
    if (!token) {
      return null;
    }

    try {
      const response = await fetch(`/api/v1/repository-cache/status/${encodeURIComponent(repoName)}?branch=${branch}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: CacheStatus = await response.json();
      return data;
    } catch (error) {
      console.error('Error getting cache status:', error);
      return null;
    }
  }, [token]);

  /**
   * Clear repository cache
   */
  const clearCache = useCallback(async (repoUrl?: string): Promise<boolean> => {
    if (!token) {
      return false;
    }

    try {
      const response = await fetch('/api/v1/repository-cache/clear', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          repo_url: repoUrl,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`Cache cleared: ${data.message}`);
      
      return data.success;
    } catch (error) {
      console.error('Error clearing cache:', error);
      return false;
    }
  }, [token]);

  /**
   * Auto-cache repository when navigating to contribution page
   */
  const autoCacheOnContribution = useCallback(async () => {
    if (!repository || !token) {
      return;
    }

    const repoKey = `${repository.owner.login}/${repository.name}`;
    
    // Avoid duplicate caching requests
    if (currentRepoRef.current === repoKey) {
      return;
    }

    currentRepoRef.current = repoKey;

    try {
      // Check if already cached
      const status = await getCacheStatus(repoKey, repository.default_branch || 'main');
      
      if (status?.cached && status.ready_for_chat) {
        console.log(`Repository ${repoKey} is already cached and ready`);
        return;
      }

      // Start caching
      const repoUrl = repository.clone_url || repository.html_url;
      await cacheRepository(
        repoUrl,
        repository.default_branch || 'main',
        'free' // Default tier, could be dynamic based on user
      );
    } catch (error) {
      console.error('Error in auto-cache:', error);
    }
  }, [repository, token, getCacheStatus, cacheRepository]);

  /**
   * Auto-clear cache when navigating away from contribution page
   */
  const autoClearOnLeave = useCallback(async () => {
    if (!repository || !token) {
      return;
    }

    try {
      const repoUrl = repository.clone_url || repository.html_url;
      await clearCache(repoUrl);
      currentRepoRef.current = null;
    } catch (error) {
      console.error('Error in auto-clear:', error);
    }
  }, [repository, token, clearCache]);

  /**
   * Effect to handle route changes and auto-cache/clear
   */
  useEffect(() => {
    const handleRouteChange = () => {
      const currentPath = window.location.pathname;
      
      if (currentPath.startsWith('/contribution')) {
        // User navigated to contribution page - start caching
        autoCacheOnContribution();
      } else if (currentPath.startsWith('/hub') && currentRepoRef.current) {
        // User navigated to hub from contribution - clear cache
        autoClearOnLeave();
      }
    };

    // Handle initial page load
    handleRouteChange();

    // Listen for route changes using Next.js router events would be better,
    // but for now we'll use the history API approach
    const originalPushState = window.history.pushState;
    const originalReplaceState = window.history.replaceState;

    window.history.pushState = function(...args) {
      originalPushState.apply(window.history, args);
      setTimeout(handleRouteChange, 100); // Small delay to ensure route change is processed
    };

    window.history.replaceState = function(...args) {
      originalReplaceState.apply(window.history, args);
      setTimeout(handleRouteChange, 100);
    };

    window.addEventListener('popstate', handleRouteChange);

    return () => {
      // Cleanup
      if (cacheRequestRef.current) {
        cacheRequestRef.current.abort();
      }
      
      window.history.pushState = originalPushState;
      window.history.replaceState = originalReplaceState;
      window.removeEventListener('popstate', handleRouteChange);
    };
  }, [autoCacheOnContribution, autoClearOnLeave]);

  return {
    cacheRepository,
    getCacheStatus,
    clearCache,
    autoCacheOnContribution,
    autoClearOnLeave,
  };
};