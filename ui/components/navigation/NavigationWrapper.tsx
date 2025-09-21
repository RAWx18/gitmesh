'use client';

import { Suspense } from 'react';
import { useHubNavigation } from '@/lib/hooks/useHubNavigation';

interface NavigationWrapperProps {
  children: (navigation: ReturnType<typeof useHubNavigation>) => React.ReactNode;
}

function NavigationContent({ children }: NavigationWrapperProps) {
  const navigation = useHubNavigation();
  return <>{children(navigation)}</>;
}

export function NavigationWrapper({ children }: NavigationWrapperProps) {
  return (
    <Suspense fallback={<div>Loading navigation...</div>}>
      <NavigationContent>{children}</NavigationContent>
    </Suspense>
  );
}