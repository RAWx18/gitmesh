'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Clock, RefreshCw, Home } from 'lucide-react';

interface RateLimitInfo {
  errorData: any;
  retryAfter: number;
  resetTime: Date;
}

interface RateLimitHandlerProps {
  children: React.ReactNode;
}

const RateLimitHandler: React.FC<RateLimitHandlerProps> = ({ children }) => {
  const [rateLimitInfo, setRateLimitInfo] = useState<RateLimitInfo | null>(null);
  const [timeUntilReset, setTimeUntilReset] = useState<number>(0);
  const [isVisible, setIsVisible] = useState(false);
  const router = useRouter();

  // Check for existing rate limit on mount
  useEffect(() => {
    checkExistingRateLimit();
  }, []);

  // Listen for rate limit events
  useEffect(() => {
    const handleRateLimitExceeded = (event: CustomEvent) => {
      const { errorData, retryAfter, resetTime } = event.detail;
      setRateLimitInfo({
        errorData,
        retryAfter,
        resetTime: new Date(resetTime)
      });
      setIsVisible(true);
    };

    window.addEventListener('github-rate-limit-exceeded', handleRateLimitExceeded as EventListener);

    return () => {
      window.removeEventListener('github-rate-limit-exceeded', handleRateLimitExceeded as EventListener);
    };
  }, []);

  // Update countdown timer
  useEffect(() => {
    if (!rateLimitInfo) return;

    const updateTimer = () => {
      const now = Date.now();
      const timeLeft = Math.max(0, rateLimitInfo.resetTime.getTime() - now);
      setTimeUntilReset(timeLeft);

      if (timeLeft === 0) {
        handleRateLimitReset();
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);

    return () => clearInterval(interval);
  }, [rateLimitInfo]);

  const checkExistingRateLimit = useCallback(() => {
    try {
      const rateLimitData = localStorage.getItem('github_rate_limit');
      if (rateLimitData) {
        const info = JSON.parse(rateLimitData);
        const resetTime = new Date(info.resetTime);
        
        if (Date.now() < resetTime.getTime()) {
          setRateLimitInfo({
            errorData: info.errorData,
            retryAfter: info.retryAfter,
            resetTime
          });
          setIsVisible(true);
        } else {
          // Rate limit has expired, clear it
          localStorage.removeItem('github_rate_limit');
        }
      }
    } catch (e) {
      console.warn('Failed to check existing rate limit:', e);
    }
  }, []);

  const handleRateLimitReset = useCallback(() => {
    setRateLimitInfo(null);
    setIsVisible(false);
    localStorage.removeItem('github_rate_limit');
    
    // Show success notification
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('Rate Limit Reset', {
        body: 'GitHub API rate limit has been reset. You can now continue using the application.',
        icon: '/favicon.ico'
      });
    }
  }, []);

  const handleGoToLanding = useCallback(() => {
    router.push('/');
  }, [router]);

  const handleRetry = useCallback(() => {
    if (timeUntilReset === 0) {
      handleRateLimitReset();
      window.location.reload();
    }
  }, [timeUntilReset, handleRateLimitReset]);

  const handleDismiss = useCallback(() => {
    setIsVisible(false);
  }, []);

  const formatTime = useCallback((milliseconds: number): string => {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  }, []);

  const getErrorMessage = useCallback(() => {
    if (!rateLimitInfo?.errorData) return 'Rate limit exceeded';
    
    const error = rateLimitInfo.errorData.error || rateLimitInfo.errorData;
    return error.message || 'GitHub API rate limit exceeded';
  }, [rateLimitInfo]);

  const getErrorDetails = useCallback(() => {
    if (!rateLimitInfo?.errorData?.error?.details) return null;
    
    const details = rateLimitInfo.errorData.error.details;
    return {
      maxRequests: details.max_requests || 60,
      currentCount: details.current_count || 0,
      limitType: details.limit_type || 'requests_per_minute'
    };
  }, [rateLimitInfo]);

  if (!isVisible || !rateLimitInfo) {
    return <>{children}</>;
  }

  const errorDetails = getErrorDetails();
  const isResetTime = timeUntilReset === 0;

  return (
    <>
      {children}
      
      {/* Rate Limit Overlay */}
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
          {/* Header */}
          <div className="flex items-center mb-4">
            <AlertTriangle className="h-6 w-6 text-red-500 mr-3" />
            <h2 className="text-lg font-semibold text-gray-900">
              Rate Limit Exceeded
            </h2>
          </div>

          {/* Error Message */}
          <div className="mb-4">
            <p className="text-gray-700 mb-2">
              {getErrorMessage()}
            </p>
            
            {errorDetails && (
              <div className="bg-gray-50 rounded p-3 text-sm">
                <p><strong>Limit:</strong> {errorDetails.maxRequests} {errorDetails.limitType.replace('_', ' ')}</p>
                <p><strong>Current:</strong> {errorDetails.currentCount} requests</p>
              </div>
            )}
          </div>

          {/* Countdown Timer */}
          <div className="mb-6">
            <div className="flex items-center justify-center bg-blue-50 rounded-lg p-4">
              <Clock className="h-5 w-5 text-blue-500 mr-2" />
              <div className="text-center">
                <p className="text-sm text-gray-600">
                  {isResetTime ? 'Rate limit has been reset!' : 'Time until reset:'}
                </p>
                <p className="text-xl font-mono font-bold text-blue-600">
                  {isResetTime ? '00:00' : formatTime(timeUntilReset)}
                </p>
              </div>
            </div>
          </div>

          {/* Suggestions */}
          <div className="mb-6">
            <h3 className="text-sm font-medium text-gray-900 mb-2">What you can do:</h3>
            <ul className="text-sm text-gray-600 space-y-1">
              <li>• Wait for the rate limit to reset automatically</li>
              <li>• Reduce the frequency of your requests</li>
              <li>• Consider upgrading to a higher tier for increased limits</li>
              <li>• Use the demo mode to explore the application</li>
            </ul>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={handleGoToLanding}
              className="flex items-center justify-center px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
            >
              <Home className="h-4 w-4 mr-2" />
              Go to Landing Page
            </button>
            
            <button
              onClick={isResetTime ? handleRetry : handleDismiss}
              className={`flex items-center justify-center px-4 py-2 rounded-md transition-colors ${
                isResetTime
                  ? 'bg-green-600 text-white hover:bg-green-700'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              {isResetTime ? 'Retry Now' : 'Dismiss'}
            </button>
          </div>

          {/* Auto-redirect notice */}
          {!isResetTime && (
            <p className="text-xs text-gray-500 text-center mt-4">
              You will be automatically redirected to the landing page in a few seconds to prevent a dead end.
            </p>
          )}
        </div>
      </div>
    </>
  );
};

export default RateLimitHandler;