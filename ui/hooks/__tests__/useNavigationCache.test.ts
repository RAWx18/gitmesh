/**
 * Tests for useNavigationCache hook
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigationCache, useCacheHealth } from '../useNavigationCache';
import { toast } from 'sonner';

// Mock dependencies
jest.mock('next/navigation');
jest.mock('@/contexts/AuthContext');
jest.mock('sonner');

// Mock fetch
global.fetch = jest.fn();

const mockUsePathname = usePathname as jest.MockedFunction<typeof usePathname>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockToast = toast as jest.Mocked<typeof toast>;

describe('useNavigationCache', () => {
  const mockUser = { id: 'test-user-123' };
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: mockUser } as any);
    mockUsePathname.mockReturnValue('/contribution/chat');
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        repository_cache_cleared: true,
        session_cache_cleared: true,
        context_cache_cleared: true,
        entries_cleaned: 5,
        memory_freed_mb: 2.5,
        cleanup_time_ms: 150
      })
    });
  });

  describe('Navigation Detection', () => {
    it('should detect navigation from contribution to hub', async () => {
      const { result, rerender } = renderHook(() => useNavigationCache());
      
      // Initial render on /contribution/chat
      expect(result.current.currentPath).toBe('/contribution/chat');
      
      // Navigate to hub
      mockUsePathname.mockReturnValue('/hub/overview');
      rerender();
      
      // Wait for cleanup to be triggered
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/navigation-cleanup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_page: '/contribution/chat',
            to_page: '/hub/overview',
            user_id: 'test-user-123'
          })
        });
      });
    });

    it('should not trigger cleanup for navigation within same section', async () => {
      const { result, rerender } = renderHook(() => useNavigationCache());
      
      // Initial render on /hub/overview
      mockUsePathname.mockReturnValue('/hub/overview');
      rerender();
      
      // Navigate within hub
      mockUsePathname.mockReturnValue('/hub/projects');
      rerender();
      
      // Should not trigger cleanup
      await new Promise(resolve => setTimeout(resolve, 1100)); // Wait longer than cleanup delay
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should handle navigation without user', () => {
      mockUseAuth.mockReturnValue({ user: null } as any);
      
      const { result } = renderHook(() => useNavigationCache());
      
      expect(result.current.currentPath).toBe('/contribution/chat');
      // Should not crash or make API calls without user
    });
  });

  describe('Manual Cleanup', () => {
    it('should perform manual cleanup', async () => {
      const { result } = renderHook(() => useNavigationCache());
      
      await act(async () => {
        const cleanupResult = await result.current.manualCleanup();
        expect(cleanupResult).toEqual({
          repository_cache_cleared: true,
          session_cache_cleared: true,
          context_cache_cleared: true,
          entries_cleaned: 5,
          memory_freed_mb: 2.5,
          cleanup_time_ms: 150
        });
      });
      
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/navigation-cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_page: '/contribution/chat',
          to_page: '/contribution/chat',
          user_id: 'test-user-123'
        })
      });
    });

    it('should handle cleanup failure', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 500
      });
      
      const { result } = renderHook(() => useNavigationCache());
      
      await act(async () => {
        const cleanupResult = await result.current.manualCleanup();
        expect(cleanupResult).toBeNull();
      });
    });
  });

  describe('Clear All Cache', () => {
    it('should clear all cache', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true })
      });
      
      const { result } = renderHook(() => useNavigationCache());
      
      await act(async () => {
        const success = await result.current.clearAllCache();
        expect(success).toBe(true);
      });
      
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/clear-cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'test-user-123'
        })
      });
    });
  });

  describe('Cache Statistics', () => {
    it('should get cache statistics', async () => {
      const mockStats = {
        success: true,
        cache_stats: {
          total_keys: 100,
          memory_usage_mb: 25.5,
          hit_rate: 85.2,
          repository_cache_count: 5
        }
      };
      
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockStats)
      });
      
      const { result } = renderHook(() => useNavigationCache());
      
      await act(async () => {
        const stats = await result.current.getCacheStats();
        expect(stats).toEqual(mockStats);
      });
      
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/cache-stats?user_id=test-user-123');
    });
  });

  describe('Configuration', () => {
    it('should use custom configuration', () => {
      const customConfig = {
        enableAutoCleanup: false,
        cleanupDelay: 2000,
        showNotifications: true
      };
      
      const { result } = renderHook(() => useNavigationCache(customConfig));
      
      expect(result.current.config).toEqual(customConfig);
    });

    it('should merge with default configuration', () => {
      const partialConfig = {
        showNotifications: true
      };
      
      const { result } = renderHook(() => useNavigationCache(partialConfig));
      
      expect(result.current.config).toEqual({
        enableAutoCleanup: true,
        cleanupDelay: 1000,
        showNotifications: true
      });
    });
  });

  describe('Notifications', () => {
    it('should show notifications when enabled', async () => {
      const { result } = renderHook(() => useNavigationCache({ showNotifications: true }));
      
      await act(async () => {
        await result.current.manualCleanup();
      });
      
      expect(mockToast.success).toHaveBeenCalledWith(
        'Cache cleaned: 5 entries, 2.5MB freed'
      );
    });

    it('should not show notifications when disabled', async () => {
      const { result } = renderHook(() => useNavigationCache({ showNotifications: false }));
      
      await act(async () => {
        await result.current.manualCleanup();
      });
      
      expect(mockToast.success).not.toHaveBeenCalled();
    });
  });

  describe('Page Unload Cleanup', () => {
    it('should setup beforeunload listener', () => {
      const addEventListenerSpy = jest.spyOn(window, 'addEventListener');
      const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
      
      const { unmount } = renderHook(() => useNavigationCache());
      
      expect(addEventListenerSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));
      
      unmount();
      
      expect(removeEventListenerSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));
      
      addEventListenerSpy.mockRestore();
      removeEventListenerSpy.mockRestore();
    });

    it('should use sendBeacon on page unload', () => {
      const mockSendBeacon = jest.fn().mockReturnValue(true);
      Object.defineProperty(navigator, 'sendBeacon', {
        value: mockSendBeacon,
        writable: true
      });
      
      renderHook(() => useNavigationCache());
      
      // Simulate beforeunload event
      const beforeUnloadEvent = new Event('beforeunload');
      window.dispatchEvent(beforeUnloadEvent);
      
      expect(mockSendBeacon).toHaveBeenCalledWith(
        '/api/v1/chat/navigation-cleanup',
        JSON.stringify({
          from_page: '/contribution/chat',
          to_page: 'external',
          user_id: 'test-user-123'
        })
      );
    });
  });
});

describe('useCacheHealth', () => {
  const mockUser = { id: 'test-user-123' };
  
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: mockUser } as any);
  });

  describe('Cache Health', () => {
    it('should get cache health status', async () => {
      const mockHealth = {
        success: true,
        health_status: {
          is_healthy: true,
          connection_status: 'connected',
          memory_usage_percent: 45.2,
          response_time_ms: 12.5,
          error_count: 0
        }
      };
      
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockHealth)
      });
      
      const { result } = renderHook(() => useCacheHealth());
      
      await act(async () => {
        const health = await result.current.getCacheHealth();
        expect(health).toEqual(mockHealth);
      });
      
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/cache-health?user_id=test-user-123');
    });

    it('should optimize cache', async () => {
      const mockOptimization = {
        success: true,
        optimization_results: {
          cleaned_entries: 15,
          memory_saved_mb: 5.2,
          optimization_time: '2023-12-01T10:30:00Z'
        }
      };
      
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockOptimization)
      });
      
      const { result } = renderHook(() => useCacheHealth());
      
      await act(async () => {
        const optimization = await result.current.optimizeCache();
        expect(optimization).toEqual(mockOptimization);
      });
      
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/chat/optimize-cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'test-user-123'
        })
      });
    });

    it('should handle health check failure', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));
      
      const { result } = renderHook(() => useCacheHealth());
      
      await act(async () => {
        const health = await result.current.getCacheHealth();
        expect(health).toBeNull();
      });
    });
  });
});