"use client";

import React, { createContext, useContext, useState, ReactNode, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { apiService } from '@/lib/api';

interface RepositoryData {
  name: string;
  full_name: string;
  description: string;
  owner: any;
  language: string;
  stargazers_count: number;
  forks_count: number;
  html_url: string;
  clone_url: string;
  default_branch: string;
  created_at: string;
  updated_at: string;
  private: boolean;
  type: "starred" | "owned";
}

interface RepositoryContextType {
  repository: RepositoryData | null;
  setRepository: (repo: RepositoryData | null) => void;
  isRepositoryLoaded: boolean;
}

const RepositoryContext = createContext<RepositoryContextType | undefined>(undefined);

export const useRepository = () => {
  const context = useContext(RepositoryContext);
  if (context === undefined) {
    throw new Error('useRepository must be used within a RepositoryProvider');
  }
  return context;
};

interface RepositoryProviderProps {
  children: ReactNode;
}

const REPOSITORY_STORAGE_KEY = 'GitMesh-selected-repository';

export const RepositoryProvider: React.FC<RepositoryProviderProps> = ({ children }) => {
  const [repository, setRepository] = useState<RepositoryData | null>(null);
  const [isRepositoryLoaded, setIsRepositoryLoaded] = useState(false);
  const prevRepositoryRef = useRef<RepositoryData | null>(null);
  const searchParams = useSearchParams();

  useEffect(() => {
    const repoParam = searchParams.get('repo');
    const ownerName = searchParams.get('owner');

    const fetchRepository = async (owner: string, repo: string) => {
      setIsRepositoryLoaded(false);
      const { data, error } = await apiService.getRepositoryDetails(owner, repo);
      if (data) {
        handleSetRepository(data.repository);
      } else {
        console.error("Failed to fetch repository details:", error);
        // Fallback to session storage or clear if invalid
        loadFromSession();
      }
      setIsRepositoryLoaded(true);
    };

    const loadFromSession = () => {
      if (typeof window !== 'undefined') {
        try {
          const storedRepo = sessionStorage.getItem(REPOSITORY_STORAGE_KEY);
          if (storedRepo) {
            const parsedRepo = JSON.parse(storedRepo);
            setRepository(parsedRepo);
            prevRepositoryRef.current = parsedRepo;
          }
        } catch (error) {
          console.error('Error loading repository from storage:', error);
          sessionStorage.removeItem(REPOSITORY_STORAGE_KEY);
        }
      }
    };

    // Handle encoded repository object from projects page
    if (repoParam && !ownerName) {
      try {
        const decodedRepo = JSON.parse(decodeURIComponent(repoParam));
        console.log('Setting repository from URL parameter:', decodedRepo);
        handleSetRepository(decodedRepo);
        setIsRepositoryLoaded(true);
        
        // Clean up URL parameter after processing
        if (typeof window !== 'undefined') {
          const url = new URL(window.location.href);
          url.searchParams.delete('repo');
          window.history.replaceState({}, document.title, url.toString());
        }
        return;
      } catch (error) {
        console.error('Error parsing repository from URL parameter:', error);
      }
    }

    // Handle separate owner and repo parameters (legacy format)
    if (ownerName && repoParam) {
      fetchRepository(ownerName, repoParam);
    } else {
      loadFromSession();
      setIsRepositoryLoaded(true);
    }
  }, [searchParams]);

  const handleSetRepository = useCallback((repo: RepositoryData | null) => {
    const prevKey = prevRepositoryRef.current ? `${prevRepositoryRef.current.owner.login}/${prevRepositoryRef.current.name}` : null;
    const newKey = repo ? `${repo.owner.login}/${repo.name}` : null;
    
    if (prevKey !== newKey) {
      prevRepositoryRef.current = repo;
      setRepository(repo);
      
      if (typeof window !== 'undefined') {
        try {
          if (repo) {
            sessionStorage.setItem(REPOSITORY_STORAGE_KEY, JSON.stringify(repo));
          } else {
            sessionStorage.removeItem(REPOSITORY_STORAGE_KEY);
          }
        } catch (error) {
          console.error('Error saving repository to storage:', error);
        }
      }
    }
  }, []);

  return (
    <RepositoryContext.Provider value={{ 
      repository, 
      setRepository: handleSetRepository, 
      isRepositoryLoaded 
    }}>
      {children}
    </RepositoryContext.Provider>
  );
}; 