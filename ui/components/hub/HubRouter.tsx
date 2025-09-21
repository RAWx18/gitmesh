'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { useBranch } from '@/contexts/BranchContext';
import { HubView, HubState } from '@/types/hub';
import { ContributionNavigation } from '../contribution/ContributionNavigation';
import { HubNavigation } from './HubNavigation';
import { OverviewDashboard } from './overview/OverviewDashboard';
import AnimatedTransition from '@/components/AnimatedTransition';
import { NavigationWrapper } from '@/components/navigation/NavigationWrapper';
import { Loader2 } from 'lucide-react';

interface HubRouterProps {
  className?: string;
  onError?: (error: Error) => void;
  onLoading?: (isLoading: boolean) => void;
  isContribution?: boolean;
  children: React.ReactNode;
}

function HubRouterContent({
  className = '',
  onError,
  onLoading,
  isContribution = false,
  children,
}: HubRouterProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, user } = useAuth();
  const { repository, isRepositoryLoaded } = useRepository();
  const { selectedBranch } = useBranch();
  
  return (
    <NavigationWrapper>
      {({ navigationState, navigateToView, updateFilters }) => (
        <HubRouterInner
          className={className}
          onError={onError}
          onLoading={onLoading}
          isContribution={isContribution}
          router={router}
          pathname={pathname}
          isAuthenticated={isAuthenticated}
          user={user}
          repository={repository}
          isRepositoryLoaded={isRepositoryLoaded}
          selectedBranch={selectedBranch}
          navigationState={navigationState}
          navigateToView={navigateToView}
          updateFilters={updateFilters}
        >
          {children}
        </HubRouterInner>
      )}
    </NavigationWrapper>
  );
}

interface HubRouterInnerProps extends HubRouterProps {
  router: any;
  pathname: string;
  isAuthenticated: boolean;
  user: any;
  repository: any;
  isRepositoryLoaded: boolean;
  selectedBranch: string;
  navigationState: any;
  navigateToView: any;
  updateFilters: any;
}

function HubRouterInner({
  className = '',
  onError,
  onLoading,
  isContribution = false,
  children,
  router,
  pathname,
  isAuthenticated,
  user,
  repository,
  isRepositoryLoaded,
  selectedBranch,
  navigationState,
  navigateToView,
  updateFilters,
}: HubRouterInnerProps) {

  // Hub state management
  const [hubState, setHubState] = useState<HubState>({
    currentView: navigationState.currentView,
    repository: undefined,
    user: undefined,
    filters: {
      projects: {},
      activity: {},
      insights: {}
    },
    loading: {},
    errors: {}
  });

  // Update hub state when context or navigation changes
  useEffect(() => {
    setHubState(prev => ({
      ...prev,
      currentView: navigationState.currentView,
      repository: repository || undefined,
      user: user || undefined
    }));
  }, [repository, user, navigationState.currentView]);

  // Handle view changes with enhanced navigation
  const handleViewChange = useCallback(async (view: HubView) => {
    if (view === hubState.currentView) return;

    onLoading?.(true);

    try {
      // Update state immediately for responsive UI
      setHubState(prev => ({
        ...prev,
        currentView: view,
        loading: {
          ...prev.loading,
          [view]: true
        }
      }));

      // Use enhanced navigation
      await navigateToView(view, { 
        preserveFilters: true, 
        transition: true 
      });

    } catch (error) {
      console.error('Navigation error:', error);
      onError?.(error as Error);
    } finally {
      onLoading?.(false);
      
      // Clear loading state for the view
      setHubState(prev => ({
        ...prev,
        loading: {
          ...prev.loading,
          [view]: false
        }
      }));
    }
  }, [hubState.currentView, navigateToView, onError, onLoading]);

  // Handle navigation state changes
  useEffect(() => {
    if (navigationState.currentView !== hubState.currentView) {
      handleViewChange(navigationState.currentView);
    }
  }, [navigationState.currentView, hubState.currentView, handleViewChange]);

  // Update filters using the navigation hook
  const updateUrlWithFilters = useCallback(() => {
    updateFilters(hubState.filters);
  }, [hubState.filters, updateFilters]);

  // Handle errors from child components
  const handleError = useCallback((error: Error) => {
    console.error('Hub router error:', error);
    
    setHubState(prev => ({
      ...prev,
      errors: {
        ...prev.errors,
        [hubState.currentView]: error.message
      }
    }));
    
    onError?.(error);
  }, [hubState.currentView, onError]);

  // Handle loading states from child components
  const handleLoadingChange = useCallback((view: AllViews, isLoading: boolean) => {
    setHubState(prev => ({
      ...prev,
      loading: {
        ...prev.loading,
        [view]: isLoading
      }
    }));
    
    onLoading?.(isLoading);
  }, [onLoading]);

  // Clear errors when view changes
  useEffect(() => {
    setHubState(prev => ({
      ...prev,
      errors: {
        ...prev.errors,
        [hubState.currentView]: undefined
      }
    }));
  }, [hubState.currentView]);

  // Show loading state while contexts are initializing
  if (!isRepositoryLoaded || navigationState.isTransitioning) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex items-center space-x-2">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span>Loading hub...</span>
        </div>
      </div>
    );
  }

  // Redirect if not authenticated
  if (!isAuthenticated) {
    router.push('/');
    return null;
  }

  // Redirect if no repository selected
  if (!repository) {
    router.push('/contribution');
    return null;
  }

  return (
    <div className={`min-h-screen bg-background ${className}`}>
      {/* Navigation */}
      {isContribution ? (
        <ContributionNavigation
          currentView={hubState.currentView}
          onViewChange={handleViewChange}
          repository={repository}
          user={user}
        />
      ) : (
        <HubNavigation
          currentView={hubState.currentView}
          onViewChange={handleViewChange}
          repository={repository}
          user={user}
        />
      )}

      {/* Main Content Area */}
      <main className="container mx-auto px-4 py-8">
        <AnimatedTransition 
          show={!navigationState.isTransitioning} 
          animation="fade" 
          duration={300}
        >
          {children}
        </AnimatedTransition>
      </main>

      {/* Global Error Display */}
      {hubState.errors[hubState.currentView] && (
        <div className="fixed bottom-4 right-4 max-w-md">
          <div className="bg-destructive text-destructive-foreground p-4 rounded-lg shadow-lg">
            <h4 className="font-semibold mb-2">Error</h4>
            <p className="text-sm">{hubState.errors[hubState.currentView]}</p>
            <button
              onClick={() => setHubState(prev => ({
                ...prev,
                errors: { ...prev.errors, [hubState.currentView]: undefined }
              }))}
              className="mt-2 text-xs underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {hubState.loading[hubState.currentView] && (
        <div className="fixed inset-0 bg-background/50 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-background border rounded-lg p-6 shadow-lg">
            <div className="flex items-center space-x-3">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Loading {hubState.currentView}...</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export const HubRouter: React.FC<HubRouterProps> = (props) => {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex items-center space-x-2">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span>Loading navigation...</span>
        </div>
      </div>
    }>
      <HubRouterContent {...props} />
    </Suspense>
  );
};

export default HubRouter;