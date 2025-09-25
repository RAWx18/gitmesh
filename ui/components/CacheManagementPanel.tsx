/**
 * Cache Management Panel Component
 * 
 * Provides UI for monitoring cache health, viewing statistics,
 * and performing manual cache cleanup operations.
 */

"use client";

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigationCache, useCacheHealth } from '@/hooks/useNavigationCache';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { 
  Trash2, 
  RefreshCw, 
  Activity, 
  Database, 
  Clock,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  MemoryStick,
  Zap
} from 'lucide-react';
import { toast } from 'sonner';

interface CacheStats {
  total_keys: number;
  memory_usage_mb: number;
  hit_rate: number;
  miss_rate: number;
  expired_keys: number;
  user_cache_count: number;
  repository_cache_count: number;
  session_cache_count: number;
  last_cleanup: string | null;
}

interface CacheHealth {
  is_healthy: boolean;
  connection_status: string;
  memory_usage_percent: number;
  response_time_ms: number;
  error_count: number;
  last_error: string | null;
  uptime_seconds: number;
}

interface CacheManagementPanelProps {
  className?: string;
  showAdvanced?: boolean;
}

export const CacheManagementPanel: React.FC<CacheManagementPanelProps> = ({
  className,
  showAdvanced = false
}) => {
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [cacheHealth, setCacheHealth] = useState<CacheHealth | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const { 
    manualCleanup, 
    clearAllCache, 
    getCacheStats 
  } = useNavigationCache();
  
  const { 
    getCacheHealth, 
    optimizeCache 
  } = useCacheHealth();

  /**
   * Load cache statistics and health data
   */
  const loadCacheData = async () => {
    setIsLoading(true);
    
    try {
      const [statsResult, healthResult] = await Promise.all([
        getCacheStats(),
        getCacheHealth()
      ]);

      if (statsResult?.success) {
        setCacheStats(statsResult.cache_stats);
      }

      if (healthResult?.success) {
        setCacheHealth(healthResult.health_status);
      }

      setLastRefresh(new Date());
    } catch (error) {
      console.error('Error loading cache data:', error);
      toast.error('Failed to load cache data');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle manual cache cleanup
   */
  const handleManualCleanup = async () => {
    setIsLoading(true);
    
    try {
      const result = await manualCleanup();
      
      if (result) {
        toast.success(
          `Cleanup completed: ${result.entries_cleaned} entries, ${result.memory_freed_mb.toFixed(1)}MB freed`
        );
        
        // Refresh data after cleanup
        await loadCacheData();
      } else {
        toast.error('Cleanup failed');
      }
    } catch (error) {
      console.error('Manual cleanup error:', error);
      toast.error('Cleanup failed');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle clear all cache
   */
  const handleClearAllCache = async () => {
    if (!confirm('Are you sure you want to clear all cache? This will remove all cached repository data and sessions.')) {
      return;
    }

    setIsLoading(true);
    
    try {
      const success = await clearAllCache();
      
      if (success) {
        toast.success('All cache cleared successfully');
        
        // Refresh data after clearing
        await loadCacheData();
      } else {
        toast.error('Failed to clear cache');
      }
    } catch (error) {
      console.error('Clear all cache error:', error);
      toast.error('Failed to clear cache');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle cache optimization
   */
  const handleOptimizeCache = async () => {
    setIsLoading(true);
    
    try {
      const result = await optimizeCache();
      
      if (result?.success) {
        const optimizationResults = result.optimization_results;
        toast.success(
          `Cache optimized: ${optimizationResults.cleaned_entries} entries cleaned, ${optimizationResults.memory_saved_mb?.toFixed(1) || 0}MB saved`
        );
        
        // Refresh data after optimization
        await loadCacheData();
      } else {
        toast.error('Cache optimization failed');
      }
    } catch (error) {
      console.error('Cache optimization error:', error);
      toast.error('Cache optimization failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Load data on component mount
  useEffect(() => {
    loadCacheData();
  }, []);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(loadCacheData, 30000);
    return () => clearInterval(interval);
  }, []);

  const getHealthStatusColor = (isHealthy: boolean) => {
    return isHealthy ? 'text-green-600' : 'text-red-600';
  };

  const getHealthStatusIcon = (isHealthy: boolean) => {
    return isHealthy ? <CheckCircle size={16} /> : <AlertTriangle size={16} />;
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database size={20} className="text-primary" />
          <h3 className="text-lg font-semibold">Cache Management</h3>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadCacheData}
            disabled={isLoading}
          >
            <RefreshCw size={14} className={cn("mr-1", isLoading && "animate-spin")} />
            Refresh
          </Button>
          
          {lastRefresh && (
            <span className="text-xs text-muted-foreground">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* Cache Health Status */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity size={16} />
            Cache Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          {cacheHealth ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={getHealthStatusColor(cacheHealth.is_healthy)}>
                    {getHealthStatusIcon(cacheHealth.is_healthy)}
                  </span>
                  <span className="font-medium">
                    {cacheHealth.is_healthy ? 'Healthy' : 'Unhealthy'}
                  </span>
                </div>
                <Badge variant={cacheHealth.is_healthy ? 'default' : 'destructive'}>
                  {cacheHealth.connection_status}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Response Time:</span>
                  <div className="font-mono">
                    {cacheHealth.response_time_ms.toFixed(1)}ms
                  </div>
                </div>
                <div>
                  <span className="text-muted-foreground">Memory Usage:</span>
                  <div className="font-mono">
                    {cacheHealth.memory_usage_percent.toFixed(1)}%
                  </div>
                </div>
              </div>

              {cacheHealth.memory_usage_percent > 0 && (
                <Progress 
                  value={cacheHealth.memory_usage_percent} 
                  className="h-2"
                />
              )}

              {cacheHealth.error_count > 0 && (
                <div className="text-sm text-red-600">
                  <span className="font-medium">Errors:</span> {cacheHealth.error_count}
                  {cacheHealth.last_error && (
                    <div className="text-xs mt-1 font-mono bg-red-50 p-1 rounded">
                      {cacheHealth.last_error}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              {isLoading ? 'Loading health data...' : 'Health data unavailable'}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cache Statistics */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp size={16} />
            Cache Statistics
          </CardTitle>
        </CardHeader>
        <CardContent>
          {cacheStats ? (
            <div className="space-y-4">
              {/* Key Metrics */}
              <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-3 bg-muted/50 rounded-lg">
                  <div className="text-2xl font-bold text-primary">
                    {cacheStats.total_keys}
                  </div>
                  <div className="text-xs text-muted-foreground">Total Keys</div>
                </div>
                <div className="text-center p-3 bg-muted/50 rounded-lg">
                  <div className="text-2xl font-bold text-primary">
                    {cacheStats.memory_usage_mb.toFixed(1)}MB
                  </div>
                  <div className="text-xs text-muted-foreground">Memory Usage</div>
                </div>
              </div>

              {/* Hit/Miss Rates */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Hit Rate:</span>
                  <span className="font-mono">{cacheStats.hit_rate.toFixed(1)}%</span>
                </div>
                <Progress value={cacheStats.hit_rate} className="h-2" />
              </div>

              {/* Cache Breakdown */}
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span>Repository Cache:</span>
                  <Badge variant="outline">{cacheStats.repository_cache_count}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Session Cache:</span>
                  <Badge variant="outline">{cacheStats.session_cache_count}</Badge>
                </div>
                <div className="flex justify-between">
                  <span>User Cache:</span>
                  <Badge variant="outline">{cacheStats.user_cache_count}</Badge>
                </div>
              </div>

              {/* Last Cleanup */}
              {cacheStats.last_cleanup && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock size={14} />
                  <span>
                    Last cleanup: {new Date(cacheStats.last_cleanup).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              {isLoading ? 'Loading statistics...' : 'Statistics unavailable'}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cache Actions */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Zap size={16} />
            Cache Actions
          </CardTitle>
          <CardDescription>
            Manage cache data and optimize performance
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <Button
              variant="outline"
              onClick={handleManualCleanup}
              disabled={isLoading}
              className="w-full justify-start"
            >
              <RefreshCw size={14} className="mr-2" />
              Clean Expired Entries
            </Button>

            <Button
              variant="outline"
              onClick={handleOptimizeCache}
              disabled={isLoading}
              className="w-full justify-start"
            >
              <MemoryStick size={14} className="mr-2" />
              Optimize Memory Usage
            </Button>

            <Separator />

            <Button
              variant="destructive"
              onClick={handleClearAllCache}
              disabled={isLoading}
              className="w-full justify-start"
            >
              <Trash2 size={14} className="mr-2" />
              Clear All Cache
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Advanced Information */}
      {showAdvanced && cacheStats && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Advanced Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm font-mono">
              <div className="flex justify-between">
                <span>Expired Keys:</span>
                <span>{cacheStats.expired_keys}</span>
              </div>
              <div className="flex justify-between">
                <span>Miss Rate:</span>
                <span>{cacheStats.miss_rate.toFixed(1)}%</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default CacheManagementPanel;