"use client";

import { useEffect, useRef, Suspense } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import VSCodeInterface from '@/components/VSCodeInterface';
import ClientProviders from '@/components/ClientProviders';
import "./globals.css";
import { KnowledgeBaseProvider } from '@/contexts/KnowledgeBaseContext';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { BranchProvider } from '@/contexts/BranchContext';
import { toast } from 'sonner';

export const dynamic = 'force-dynamic'

function ContributionLayoutContent({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { setRepository, repository, isRepositoryLoaded } = useRepository();
  const repoProcessedRef = useRef(false);
  const router = useRouter();
  const { isAuthenticated, token } = useAuth();

  // Repository data will be handled by parent components or context

  // Set up demo repository if in demo mode and no repository is set
  useEffect(() => {
    // Only set demo repository if:
    // 1. User is authenticated with demo token
    // 2. No repository is currently set
    // 3. Repository hasn't been processed from URL params
    // 4. Repository context has finished loading (to avoid overriding restored repository)
    if (isAuthenticated && token === 'demo-token' && !repository && !repoProcessedRef.current && isRepositoryLoaded) {
      const demoRepository = {
        name: 'GitMesh-app',
        full_name: 'demo-user/GitMesh-app',
        description: 'A demo repository for testing GitMesh features',
        owner: {
          login: 'demo-user',
          avatar_url: 'https://github.com/github.png',
          type: 'User'
        },
        language: 'TypeScript',
        stargazers_count: 42,
        forks_count: 8,
        html_url: 'https://github.com/demo-user/GitMesh-app',
        clone_url: 'https://github.com/demo-user/GitMesh-app.git',
        default_branch: '',
        created_at: '2023-01-01T00:00:00Z',
        updated_at: new Date().toISOString(),
        private: false,
        type: 'owned' as const
      };
      setRepository(demoRepository);
      repoProcessedRef.current = true;
    }
  }, [isAuthenticated, token, repository, isRepositoryLoaded, setRepository]);

  return (
    <ClientProviders>
      <KnowledgeBaseProvider>
        <BranchProvider>
          <div className="h-screen overflow-hidden">
            <VSCodeInterface>
              {children}
            </VSCodeInterface>
          </div>
        </BranchProvider>
      </KnowledgeBaseProvider>
    </ClientProviders>
  );
}

export default function ContributionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
      </div>
    }>
      <ContributionLayoutContent>{children}</ContributionLayoutContent>
    </Suspense>
  );
}