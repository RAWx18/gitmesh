/**
 * Repository Cache Manager Component
 * 
 * Automatically manages repository caching when users navigate to/from contribution pages.
 * Shows caching status and provides manual cache controls.
 */

import React, { useEffect, useState } from 'react';
import { useRepository } from '@/contexts/RepositoryContext';
import { useRepositoryCache } from '@/hooks/useRepositoryCache';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Database, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  Loader2,
  Trash2
} from 'lucide-react';
import { toast } from 'sonner';

interface CacheStatus {
  cached: boolean;
  repository_name?: string;
  file_count?: number;
  ready_for_chat?: boolean;
  message?: string;
}

export const RepositoryCacheManager: React.FC = () => {
  const { repository } = useRepository();
  const { getCacheStatus, cacheRepository, clearCache } = useRepositoryCache();
  
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  /**
   * Check cache status for current repository
   */
  const checkCacheStatus = async () => {
    if (!repository) return;

    try {
      setIsLoading(true);
      const repoKey = `${repository.owner.login}/${repository.name}`;
      const status = await getCacheStatus(repoKey, repository.default_branch || 'main');
      setCacheStatus(status);
    } catch (error) {
      console.error('Error checking cache status:', error);
      toast.error('Failed to check cache status');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Manually trigger repository caching
   */
  const handleCacheRepository = async () => {
    if (!repository) return;

    try {
      setIsRefreshing(true);
      const repoUrl = repository.clone_url || repository.html_url;
      
      const result = await cacheRepository(
        repoUrl,
        repository.default_branch || 'main',
        'free' // Default tier
      );

      if (result) {
        toast.success(`Started caching ${result.repository_name}`);
        // Check status again after a short delay
        setTimeout(checkCacheStatus, 2000);
      } else {
        toast.error('Failed to start repository caching');
      }
    } catch (error) {
      console.error('Error caching repository:', error);
      toast.error('Failed to cache repository');
    } finally {
      setIsRefreshing(false);
    }
  };

  /**
   * Manually clear repository cache
   */
  const handleClearCache = async () => {
    if (!repository) return;

    try {
      setIsRefreshing(true);
      const repoUrl = repository.clone_url || repository.html_url;
      
      const success = await clearCache(repoUrl);

      if (success) {
        toast.success('Repository cache cleared');
        setCacheStatus(null);
        setTimeout(checkCacheStatus, 1000);
      } else {
        toast.error('Failed to clear repository cache');
      }
    } catch (error) {
      console.error('Error clearing cache:', error);
      toast.error('Failed to clear cache');
    } finally {
      setIsRefreshing(false);
    }
  };

  /**
   * Check cache status when repository changes
   */
  useEffect(() => {
    if (repository) {
      checkCacheStatus();
    } else {
      setCacheStatus(null);
    }
  }, [repository]);

  // Don't render if no repository is selected
  if (!repository) {
    return null;
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Database size={20} className="text-primary" />
          <CardTitle className="text-lg">Repository Cache</CardTitle>
        </div>
        <CardDescription>
          Redis Cloud caching status for faster chat responses
        </CardDescription>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Repository Info */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-sm">{repository.full_name}</p>
            <p className="text-xs text-muted-foreground">
              Branch: {repository.default_branch || 'main'}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={checkCacheStatus}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
          </Button>
        </div>

        {/* Cache Status */}
        {cacheStatus && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              {cacheStatus.cached ? (
                <>
                  <CheckCircle size={16} className="text-green-500" />
                  <Badge variant="default" className="bg-green-100 text-green-800">
                    Cached
                  </Badge>
                </>
              ) : (
                <>
                  <AlertCircle size={16} className="text-orange-500" />
                  <Badge variant="secondary">
                    Not Cached
                  </Badge>
                </>
              )}
            </div>

            {cacheStatus.cached && (
              <div className="text-sm space-y-1">
                {cacheStatus.file_count !== undefined && (
                  <p className="text-muted-foreground">
                    Files: {cacheStatus.file_count.toLocaleString()}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Chat Ready:</span>
                  {cacheStatus.ready_for_chat ? (
                    <Badge variant="default" className="bg-green-100 text-green-800 text-xs">
                      Ready
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-xs">
                      Processing
                    </Badge>
                  )}
                </div>
              </div>
            )}

            {cacheStatus.message && (
              <p className="text-xs text-muted-foreground">
                {cacheStatus.message}
              </p>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-2">
          {!cacheStatus?.cached ? (
            <Button
              onClick={handleCacheRepository}
              disabled={isRefreshing}
              size="sm"
              className="flex-1"
            >
              {isRefreshing ? (
                <>
                  <Loader2 size={14} className="mr-2 animate-spin" />
                  Caching...
                </>
              ) : (
                <>
                  <Database size={14} className="mr-2" />
                  Cache Repository
                </>
              )}
            </Button>
          ) : (
            <Button
              onClick={handleClearCache}
              disabled={isRefreshing}
              variant="outline"
              size="sm"
              className="flex-1"
            >
              {isRefreshing ? (
                <>
                  <Loader2 size={14} className="mr-2 animate-spin" />
                  Clearing...
                </>
              ) : (
                <>
                  <Trash2 size={14} className="mr-2" />
                  Clear Cache
                </>
              )}
            </Button>
          )}
        </div>

        {/* Auto-caching Notice */}
        <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
          <p>
            💡 Repositories are automatically cached when you visit the contribution page 
            and cleared when you return to the hub.
          </p>
        </div>
      </CardContent>
    </Card>
  );
};