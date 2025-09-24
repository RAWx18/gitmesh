# Chat Session Management Integration

This document explains how to integrate the chat session management system to ensure sessions persist while users are on the chat page and are cleaned up when they navigate to the hub.

## Backend Changes

### 1. Redis-based Session Storage
- Sessions are now stored in Redis with TTL (24 hours by default)
- Automatic cleanup of expired sessions
- Persistent storage across server restarts

### 2. New API Endpoints

#### Session Heartbeat
```
POST /api/v1/chat/sessions/{session_id}/heartbeat
```
Keeps the session alive and extends TTL.

#### Session Cleanup
```
POST /api/v1/chat/sessions/cleanup
```
Cleans up user sessions with different strategies:
- `type: "all"` - Delete all user sessions
- `type: "inactive"` - Delete sessions older than 1 hour
- `type: "specific"` - Delete specific session IDs

## Frontend Integration

### 1. Using the React Hook (Recommended)

```jsx
import { useChatSession } from '../hooks/useChatSession';

function ChatPage() {
    const { 
        startSession, 
        stopSession, 
        navigateToHub, 
        isSessionActive 
    } = useChatSession();

    useEffect(() => {
        // Start session when component mounts
        const sessionId = 'your-session-id';
        startSession(sessionId);

        // Cleanup when component unmounts
        return () => {
            stopSession();
        };
    }, [startSession, stopSession]);

    const handleGoToHub = () => {
        // This will cleanup sessions and navigate
        navigateToHub();
    };

    return (
        <div>
            <button onClick={handleGoToHub}>
                Go to Hub
            </button>
            {/* Your chat interface */}
        </div>
    );
}
```

### 2. Using the Session Manager Directly

```javascript
import ChatSessionManager from '../utils/chatSessionManager';

const sessionManager = new ChatSessionManager();

// Start session
sessionManager.startSession('session-id-123');

// Navigate to hub with cleanup
sessionManager.navigateToHub();

// Manual cleanup
sessionManager.cleanupSessions('all');
```

### 3. Integration in Existing Chat Component

Update your existing chat component (`ui/app/contribution/chat/page.tsx`):

```tsx
'use client';

import { useEffect } from 'react';
import { useChatSession } from '../../../hooks/useChatSession';
import ChatInterface from '../../../components/chat/ChatInterface';

export default function ChatPage() {
    const { startSession, stopSession, navigateToHub } = useChatSession();

    useEffect(() => {
        // Get or create session ID
        const sessionId = getOrCreateSessionId(); // Your session creation logic
        startSession(sessionId);

        return () => {
            stopSession();
        };
    }, [startSession, stopSession]);

    const handleBackToHub = () => {
        navigateToHub(); // This will cleanup and navigate
    };

    return (
        <div className="chat-page">
            <header>
                <button onClick={handleBackToHub}>
                    ← Back to Hub
                </button>
            </header>
            <ChatInterface />
        </div>
    );
}
```

## How It Works

### Session Lifecycle

1. **Session Start**: When user enters chat page
   - Session is created/retrieved
   - Heartbeat starts (every 30 seconds)
   - Session TTL is set to 24 hours

2. **Session Active**: While user is on chat page
   - Heartbeat keeps session alive
   - TTL is refreshed on each heartbeat
   - Session pauses when page is hidden

3. **Session End**: When user navigates away
   - Sessions are cleaned up based on strategy
   - Heartbeat stops
   - Resources are freed

### Cleanup Strategies

- **Navigate to Hub**: Clean up ALL sessions
- **Page Refresh**: Keep current session, clean inactive ones
- **Browser Close**: Clean up inactive sessions (via sendBeacon)

### Automatic Features

- **Page Visibility**: Pauses heartbeat when tab is hidden
- **Before Unload**: Cleans up sessions when leaving site
- **Error Handling**: Graceful degradation if cleanup fails
- **Fallback Storage**: Uses in-memory storage if Redis unavailable

## Configuration

### Backend Configuration

```python
# Session TTL (hours)
SESSION_TTL_HOURS = 24

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL = 30

# Inactive session threshold (seconds)
INACTIVE_THRESHOLD = 3600  # 1 hour
```

### Frontend Configuration

```javascript
const sessionManager = new ChatSessionManager('/api/v1/chat');
sessionManager.heartbeatIntervalMs = 30000; // 30 seconds
```

## Testing

### Test Session Persistence
1. Start chat session
2. Refresh page
3. Verify session continues

### Test Cleanup
1. Start chat session
2. Navigate to hub
3. Verify session is cleaned up
4. Return to chat
5. Verify new session is created

### Test Heartbeat
1. Start chat session
2. Monitor network tab
3. Verify heartbeat requests every 30 seconds
4. Hide tab, verify heartbeat stops
5. Show tab, verify heartbeat resumes

## Troubleshooting

### Sessions Not Persisting
- Check Redis connection
- Verify TTL settings
- Check for JavaScript errors

### Cleanup Not Working
- Verify API endpoints are accessible
- Check browser console for errors
- Test with different cleanup strategies

### Performance Issues
- Adjust heartbeat interval
- Monitor Redis memory usage
- Consider session data size

## Migration from In-Memory Storage

If you're currently using in-memory session storage:

1. Update imports to use new session management
2. Replace direct session access with API calls
3. Add session cleanup to navigation handlers
4. Test thoroughly in development environment

The system automatically falls back to in-memory storage if Redis is unavailable, ensuring compatibility during migration.