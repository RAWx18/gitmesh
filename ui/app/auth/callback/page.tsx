"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

export const dynamic = 'force-dynamic'

function AuthCallbackContent() {
  const router = useRouter();
  const { setUserFromCallback } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState<string>("");

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const authToken = urlParams.get("auth_token");
    const authUser = urlParams.get("auth_user");

    console.log("AuthCallback: Processing callback");
    console.log("Auth token:", authToken ? "Present" : "Missing");
    console.log("Auth user:", authUser);
    console.log("Full URL:", window.location.href);

    setDebug(`Token: ${authToken ? "Present" : "Missing"}, User: ${authUser || "Missing"}`);

    if (authToken && authUser) {
      try {
        console.log("Setting user from callback...");
        
        // For now, we'll just log the user data.
        // In a real app, you'd fetch the full user profile here.
        const user = {
          login: authUser,
          id: 0,
          name: "",
          email: "",
          avatar_url: "",
          bio: "",
          location: "",
          company: "",
          blog: "",
          twitter_username: "",
          public_repos: 0,
          followers: 0,
          following: 0,
          created_at: "",
          lastLogin: ""
        };
        
        setUserFromCallback(user, authToken);
        console.log("User set, redirecting to overview...");
        
        // Add a small delay to ensure state is updated
        setTimeout(() => {
          router.push("/hub/overview");
        }, 100);
        
      } catch (err) {
        console.error("Error processing auth callback:", err);
        setError(`Error processing authentication: ${err}`);
      }
    } else {
      console.error("Missing auth parameters");
      setError("Missing authentication parameters. Please try logging in again.");
      
      // Redirect to home after 3 seconds
      setTimeout(() => {
        router.push("/");
      }, 3000);
    }
  }, [router, setUserFromCallback]);

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
          <div className="text-center">
            <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
              <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.314 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h3 className="mt-2 text-sm font-medium text-gray-900">Authentication Error</h3>
            <p className="mt-1 text-sm text-gray-500">{error}</p>
            <p className="mt-2 text-xs text-gray-400">Debug: {debug}</p>
            <div className="mt-6">
              <button
                onClick={() => router.push("/")}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
              >
                Return to Home
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600 mx-auto"></div>
        <h2 className="mt-4 text-xl font-semibold text-gray-900">Authenticating...</h2>
        <p className="mt-2 text-sm text-gray-500">Please wait while we complete your login.</p>
        <p className="mt-2 text-xs text-gray-400">Debug: {debug}</p>
      </div>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600 mx-auto"></div>
          <h2 className="mt-4 text-xl font-semibold text-gray-900">Loading...</h2>
        </div>
      </div>
    }>
      <AuthCallbackContent />
    </Suspense>
  );
}