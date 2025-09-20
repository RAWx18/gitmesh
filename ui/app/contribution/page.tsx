"use client";

import { useState, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAnimateIn } from '@/lib/animations';
import { BranchWhat } from '@/components/branch-content/BranchWhat';
import AnimatedTransition from '@/components/AnimatedTransition';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

export default function ContributionPage() {
  const [authProcessed, setAuthProcessed] = useState(false);
  const showContent = useAnimateIn(false, 300);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setUserFromCallback, isAuthenticated } = useAuth();

  // Handle authentication parameters from OAuth callback
  useEffect(() => {
    const handleAuth = async () => {
      const authToken = searchParams.get('auth_token');
      const authUser = searchParams.get('auth_user');
      const authError = searchParams.get('auth_error');
      const authMessage = searchParams.get('auth_message');

      // Handle OAuth errors
      if (authError && authMessage) {
        console.error('OAuth error received:', authError, authMessage);
        
        // Clean up URL parameters
        const newUrl = window.location.pathname;
        window.history.replaceState({}, document.title, newUrl);
        
        // Show error toast
        toast.error(decodeURIComponent(authMessage), {
          description: "Redirecting to homepage",
          duration: 5000,
        });
        
        // Redirect to landing page on OAuth error
        router.push('/');
        return;
      }

      if (authToken && authUser && !authProcessed) {
        try {
          console.log('Processing authentication from URL params...');
          const userData = JSON.parse(decodeURIComponent(authUser));
          setUserFromCallback(userData, authToken);
          setAuthProcessed(true);
          
          // Clean up URL parameters
          const newUrl = window.location.pathname;
          window.history.replaceState({}, document.title, newUrl);
          
          console.log('Authentication successful, user logged in');
        } catch (error) {
          console.error('Error processing authentication:', error);
          // Redirect to landing page on error
          router.push('/');
        }
      }
    };

    handleAuth();
  }, [searchParams, setUserFromCallback, authProcessed, router]);

  // Redirect to landing page if not authenticated and no auth params
  useEffect(() => {
    const authToken = searchParams.get('auth_token');
    const authUser = searchParams.get('auth_user');
    
    // If no auth params and not authenticated, redirect to home
    if (!authToken && !authUser && !isAuthenticated) {
      console.log('Not authenticated, redirecting to landing page');
      router.push('/');
      return;
    }
    
    // If auth processing is complete and still not authenticated, redirect
    if (authProcessed && !isAuthenticated && !authToken) {
      console.log('Authentication processing complete but not authenticated, redirecting to landing page');
      router.push('/');
    }
  }, [isAuthenticated, searchParams, authProcessed, router]);

  return (
    <div className="w-full h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <AnimatedTransition show={showContent} animation="fade" duration={800}>
          <BranchWhat />
        </AnimatedTransition>
      </div>
    </div>
  );
}