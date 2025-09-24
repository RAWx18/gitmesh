/**
 * React hook for chat session management
 */

import { useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ChatSessionManager from '../utils/chatSessionManager';

export function useChatSession() {
    const sessionManagerRef = useRef(null);
    const router = useRouter();

    // Initialize session manager
    useEffect(() => {
        if (!sessionManagerRef.current) {
            sessionManagerRef.current = new ChatSessionManager();
        }

        return () => {
            if (sessionManagerRef.current) {
                sessionManagerRef.current.stopSession();
            }
        };
    }, []);

    // Start session
    const startSession = useCallback((sessionId) => {
        if (sessionManagerRef.current) {
            sessionManagerRef.current.startSession(sessionId);
        }
    }, []);

    // Stop session
    const stopSession = useCallback(() => {
        if (sessionManagerRef.current) {
            sessionManagerRef.current.stopSession();
        }
    }, []);

    // Navigate to hub with cleanup
    const navigateToHub = useCallback(async () => {
        if (sessionManagerRef.current) {
            try {
                await sessionManagerRef.current.cleanupSessions('all');
                sessionManagerRef.current.stopSession();
            } catch (error) {
                console.error('Error cleaning up sessions:', error);
            }
        }
        router.push('/hub');
    }, [router]);

    // Clean up sessions
    const cleanupSessions = useCallback(async (type = 'inactive') => {
        if (sessionManagerRef.current) {
            return await sessionManagerRef.current.cleanupSessions(type);
        }
    }, []);

    // Check if session is active
    const isSessionActive = useCallback(() => {
        return sessionManagerRef.current ? sessionManagerRef.current.isSessionActive() : false;
    }, []);

    // Get current session ID
    const getCurrentSessionId = useCallback(() => {
        return sessionManagerRef.current ? sessionManagerRef.current.getCurrentSessionId() : null;
    }, []);

    return {
        startSession,
        stopSession,
        navigateToHub,
        cleanupSessions,
        isSessionActive,
        getCurrentSessionId
    };
}

export default useChatSession;