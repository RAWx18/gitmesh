"use client";

import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect, Suspense } from 'react';
import { HubNavigation } from '@/components/hub/HubNavigation';

export const dynamic = 'force-dynamic'

function HubLayoutContent({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, loading, setUserFromCallback } = useAuth();
  const router = useRouter();

  // Redirect to landing page if not authenticated
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, loading, router]);

  // Show loading while checking authentication
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500"></div>
      </div>
    );
  }

  // Don't render if not authenticated (will redirect)
  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <HubNavigation />
      <main className="pt-16">
        {children}
      </main>
    </div>
  );
}

export default function HubLayout({
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
      <HubLayoutContent>{children}</HubLayoutContent>
    </Suspense>
  );
}