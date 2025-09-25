/**
 * Hook for repository context detection and management
 */

import { useState, useEffect, useCallback } from 'react';
import { useRepository } from '@/contexts/RepositoryContext';
import { useBranch } from '@/contexts/BranchContext';
import { useAuth } from '@/contexts/AuthContext';

export interface RepositoryContext {
  url: string;
  branch: string;
  name: string;
  owner: string;
  is_private: boolean;
  size_mb?: number;
  file_count?: number;
  validation_status: 'unknown' | 'valid' | 'invalid' | 'too_large' | 'error';
  error_message?: string;
  cached: boolean;
}

export interface SuggestedFile {
  path: string;
  name: string;
  relevance_score: number;
  language?: string;
  size_bytes?: number;
  show_plus_icon: boolean;
}

interface UseRepositoryContextReturn {
  repositoryContext: RepositoryContext | null;
  suggestedFiles: SuggestedFile[];
  isLoading: boolean;
  error: string | null;
  detectContext: () => Promise<void>;
  getSuggestedFiles: () => Promise<void>;
  clearCache: (cleanupAll?: boolean) => Promise<void>;
}

export const useRepositoryContext = (): UseRepositoryContextReturn => {
  const { repository } = useRepository();
  const { selectedBranch } = useBranch();
  const { token } = useAuth();
  
  const [repositoryContext, setRepositoryContext] = useState<RepositoryContext | null>(null);
  const [suggestedFiles, setSuggestedFiles] = useState<SuggestedFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detectContext = useCallback(async () => {
    if (!repository || !token) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Build page context from current repository state
      const pageContext = {
        repository_id: repository.full_name,
        repository_url: repository.html_url,
        branch: selectedBranch || repository.default_branch || 'main',
        owner: repository.owner.login,
        repo: repository.name,
        current_url: window.location.pathname,
        is_private: repository.private
      };

      const response = await fetch('/api/v1/chat/repository/context', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          page_context: pageContext
        })
      });

      const data = await response.json();

      if (data.success && data.repository_context) {
        setRepositoryContext(data.repository_context);
        
        // If repository is valid and cached, get suggested files
        if (data.repository_context.validation_status === 'valid' && data.repository_context.cached) {
          await getSuggestedFiles();
        }
      } else {
        setError(data.error || 'Failed to detect repository context');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      setError(errorMessage);
      console.error('Error detecting repository context:', err);
    } finally {
      setIsLoading(false);
    }
  }, [repository, selectedBranch, token]);

  const getSuggestedFiles = useCallback(async () => {
    if (!repository || !token || !repositoryContext) {
      return;
    }

    try {
      const params = new URLSearchParams({
        repository_url: repositoryContext.url,
        branch: repositoryContext.branch,
        limit: '10'
      });

      const response = await fetch(`/api/v1/chat/repository/suggested-files?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();

      if (data.success) {
        setSuggestedFiles(data.suggested_files || []);
      } else {
        console.error('Failed to get suggested files:', data.error);
        setSuggestedFiles([]);
      }
    } catch (err) {
      console.error('Error getting suggested files:', err);
      setSuggestedFiles([]);
    }
  }, [repository, token, repositoryContext]);

  const clearCache = useCallback(async (cleanupAll: boolean = false) => {
    if (!repository || !token || !repositoryContext) {
      return;
    }

    try {
      const params = new URLSearchParams({
        repository_url: repositoryContext.url,
        branch: repositoryContext.branch
      });

      if (cleanupAll) {
        params.append('cleanup_all', 'true');
      }

      const response = await fetch(`/api/v1/chat/repository/cache?${params}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();

      if (data.success) {
        console.log('Repository cache cleared:', data.message);
        
        // Clear local state
        if (cleanupAll) {
          setRepositoryContext(null);
          setSuggestedFiles([]);
        }
      } else {
        console.error('Failed to clear cache:', data.error);
      }
    } catch (err) {
      console.error('Error clearing repository cache:', err);
    }
  }, [repository, token, repositoryContext]);

  // Auto-detect context when repository or branch changes
  useEffect(() => {
    if (repository && token) {
      detectContext();
    }
  }, [repository, selectedBranch, token, detectContext]);

  // Clear cache when navigating away from /contribution
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (repositoryContext && window.location.pathname.includes('/contribution')) {
        // Only clear cache if we're leaving the contribution section
        const newPath = window.location.pathname;
        if (!newPath.includes('/contribution')) {
          clearCache(true);
        }
      }
    };

    // Listen for navigation changes
    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [repositoryContext, clearCache]);

  return {
    repositoryContext,
    suggestedFiles,
    isLoading,
    error,
    detectContext,
    getSuggestedFiles,
    clearCache
  };
};

export default useRepositoryContext;