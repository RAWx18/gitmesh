/**
 * Chat Session Manager
 * Handles session persistence and cleanup for the chat interface
 */

class ChatSessionManager {
    constructor(apiBaseUrl = '/api/v1/chat') {
        this.apiBaseUrl = apiBaseUrl;
        this.currentSessionId = null;
        this.heartbeatInterval = null;
        this.heartbeatIntervalMs = 30000; // 30 seconds
        this.isActive = false;
    }

    /**
     * Start session management for a chat session
     */
    startSession(sessionId) {
        this.currentSessionId = sessionId;
        this.isActive = true;
        this.startHeartbeat();
        
        // Listen for page visibility changes
        document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
        
        // Listen for beforeunload to cleanup
        window.addEventListener('beforeunload', this.handleBeforeUnload.bind(this));
        
        console.log(`Chat session ${sessionId} started with heartbeat`);
    }

    /**
     * Stop session management
     */
    stopSession() {
        this.isActive = false;
        this.stopHeartbeat();
        
        // Remove event listeners
        document.removeEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
        window.removeEventListener('beforeunload', this.handleBeforeUnload.bind(this));
        
        console.log(`Chat session ${this.currentSessionId} stopped`);
        this.currentSessionId = null;
    }

    /**
     * Start heartbeat to keep session alive
     */
    startHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }

        this.heartbeatInterval = setInterval(async () => {
            if (this.isActive && this.currentSessionId) {
                try {
                    await this.sendHeartbeat();
                } catch (error) {
                    console.warn('Heartbeat failed:', error);
                }
            }
        }, this.heartbeatIntervalMs);
    }

    /**
     * Stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    /**
     * Send heartbeat to server
     */
    async sendHeartbeat() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`${this.apiBaseUrl}/sessions/${this.currentSessionId}/heartbeat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error(`Heartbeat failed: ${response.status}`);
            }

            const data = await response.json();
            console.debug('Heartbeat sent:', data);
        } catch (error) {
            console.error('Error sending heartbeat:', error);
        }
    }

    /**
     * Clean up sessions when navigating away
     */
    async cleanupSessions(type = 'inactive') {
        try {
            const response = await fetch(`${this.apiBaseUrl}/sessions/cleanup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ type })
            });

            if (!response.ok) {
                throw new Error(`Cleanup failed: ${response.status}`);
            }

            const data = await response.json();
            console.log('Sessions cleaned up:', data);
            return data;
        } catch (error) {
            console.error('Error cleaning up sessions:', error);
            throw error;
        }
    }

    /**
     * Handle page visibility changes
     */
    handleVisibilityChange() {
        if (document.hidden) {
            // Page is hidden, pause heartbeat
            this.stopHeartbeat();
            console.log('Page hidden, heartbeat paused');
        } else {
            // Page is visible, resume heartbeat
            if (this.isActive && this.currentSessionId) {
                this.startHeartbeat();
                console.log('Page visible, heartbeat resumed');
            }
        }
    }

    /**
     * Handle before page unload
     */
    handleBeforeUnload() {
        // Clean up inactive sessions when leaving
        if (this.isActive) {
            // Use sendBeacon for reliable cleanup on page unload
            const cleanupData = JSON.stringify({ type: 'inactive' });
            
            if (navigator.sendBeacon) {
                navigator.sendBeacon(
                    `${this.apiBaseUrl}/sessions/cleanup`,
                    cleanupData
                );
            }
        }
    }

    /**
     * Navigate to hub and cleanup sessions
     */
    async navigateToHub() {
        try {
            // Clean up all sessions when going to hub
            await this.cleanupSessions('all');
            this.stopSession();
            
            // Navigate to hub
            window.location.href = '/hub';
        } catch (error) {
            console.error('Error during hub navigation:', error);
            // Navigate anyway
            window.location.href = '/hub';
        }
    }

    /**
     * Check if session is active
     */
    isSessionActive() {
        return this.isActive && this.currentSessionId !== null;
    }

    /**
     * Get current session ID
     */
    getCurrentSessionId() {
        return this.currentSessionId;
    }
}

// Export for use in other modules
export default ChatSessionManager;

// Also make it available globally for direct script usage
if (typeof window !== 'undefined') {
    window.ChatSessionManager = ChatSessionManager;
}