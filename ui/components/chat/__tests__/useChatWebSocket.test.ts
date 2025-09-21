/**
 * Tests for useChatWebSocket hook
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { useChatWebSocket } from '../../../hooks/useChatWebSocket';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Simulate connection opening
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
    }, 10);
  }

  send(data: string) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
    // Store sent data for testing
    (this as any).lastSentData = data;
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: code || 1000, reason }));
    }
  }

  // Helper method to simulate receiving messages
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { 
        data: JSON.stringify(data) 
      }));
    }
  }

  // Helper method to simulate errors
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

// Mock global WebSocket
(global as any).WebSocket = MockWebSocket;

// Mock window.location
Object.defineProperty(window, 'location', {
  value: {
    protocol: 'http:',
    host: 'localhost:3000'
  },
  writable: true
});

describe('useChatWebSocket', () => {
  const defaultOptions = {
    sessionId: 'test-session-123',
    token: 'test-token',
    userId: 'test-user'
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('should initialize with correct default state', () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    expect(result.current.isConnected).toBe(false);
    expect(result.current.connectionStatus.status).toBe('disconnected');
    expect(result.current.isReconnecting).toBe(false);
    expect(result.current.streamingResponse).toBe('');
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.isTyping).toBe(false);
  });

  it('should connect to WebSocket on mount', async () => {
    const onConnectionChange = jest.fn();
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, onConnectionChange })
    );

    // Fast-forward to allow connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    expect(onConnectionChange).toHaveBeenCalledWith({
      status: 'connected',
      connected_at: expect.any(String)
    });
  });

  it('should handle connection established message', async () => {
    const onMessage = jest.fn();
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, onMessage })
    );

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    // Simulate connection established message
    const mockWs = (global as any).WebSocket.mock.instances[0];
    act(() => {
      mockWs.simulateMessage({
        type: 'connection_established',
        session_id: 'test-session-123',
        user_id: 'test-user',
        timestamp: new Date().toISOString()
      });
    });

    expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'connection_established',
        session_id: 'test-session-123'
      })
    );
  });

  it('should send user messages', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    // Send message
    act(() => {
      result.current.sendMessage('Hello, AI!');
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];
    const sentData = JSON.parse(mockWs.lastSentData);
    
    expect(sentData.type).toBe('user_message');
    expect(sentData.content).toBe('Hello, AI!');
    expect(sentData.message_id).toBeDefined();
    expect(sentData.timestamp).toBeDefined();
  });

  it('should handle streaming AI responses', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Simulate streaming response chunks
    act(() => {
      mockWs.simulateMessage({
        type: 'ai_response_chunk',
        response_id: 'resp-123',
        chunk: 'Hello',
        chunk_index: 0,
        is_final: false,
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.streamingResponse).toBe('Hello');

    act(() => {
      mockWs.simulateMessage({
        type: 'ai_response_chunk',
        response_id: 'resp-123',
        chunk: ' there!',
        chunk_index: 1,
        is_final: true,
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.streamingResponse).toBe('Hello there!');

    // Simulate response complete
    act(() => {
      mockWs.simulateMessage({
        type: 'ai_response_complete',
        response_id: 'resp-123',
        content: 'Hello there!',
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.streamingResponse).toBe('');
    expect(result.current.isProcessing).toBe(false);
  });

  it('should handle processing indicators', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Simulate processing start
    act(() => {
      mockWs.simulateMessage({
        type: 'processing_start',
        message_id: 'msg-123',
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.isProcessing).toBe(true);

    // Simulate processing stop
    act(() => {
      mockWs.simulateMessage({
        type: 'processing_stop',
        message_id: 'msg-123',
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.isProcessing).toBe(false);
  });

  it('should handle typing indicators', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Simulate typing start
    act(() => {
      mockWs.simulateMessage({
        type: 'typing_start',
        session_id: 'test-session-123',
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.isTyping).toBe(true);

    // Simulate typing stop
    act(() => {
      mockWs.simulateMessage({
        type: 'typing_stop',
        session_id: 'test-session-123',
        timestamp: new Date().toISOString()
      });
    });

    expect(result.current.isTyping).toBe(false);
  });

  it('should send typing indicators', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Send typing start
    act(() => {
      result.current.sendTypingStart();
    });

    let sentData = JSON.parse(mockWs.lastSentData);
    expect(sentData.type).toBe('typing_start');

    // Send typing stop
    act(() => {
      result.current.sendTypingStop();
    });

    sentData = JSON.parse(mockWs.lastSentData);
    expect(sentData.type).toBe('typing_stop');
  });

  it('should handle errors', async () => {
    const onError = jest.fn();
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, onError })
    );

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Simulate error message
    act(() => {
      mockWs.simulateMessage({
        type: 'error',
        error: 'Something went wrong',
        message: 'Error details',
        timestamp: new Date().toISOString()
      });
    });

    expect(onError).toHaveBeenCalledWith('Something went wrong');
  });

  it('should handle connection errors and reconnect', async () => {
    const onError = jest.fn();
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, onError, autoReconnect: true })
    );

    // Wait for initial connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Simulate connection error
    act(() => {
      mockWs.simulateError();
    });

    expect(onError).toHaveBeenCalledWith('WebSocket connection error');

    // Simulate connection close with error code
    act(() => {
      mockWs.close(1006, 'Connection lost');
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.isReconnecting).toBe(true);

    // Fast-forward to trigger reconnection
    act(() => {
      jest.advanceTimersByTime(2000);
    });

    // Should attempt to reconnect
    expect((global as any).WebSocket).toHaveBeenCalledTimes(2);
  });

  it('should send heartbeat messages', async () => {
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, heartbeatInterval: 1000 })
    );

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];

    // Fast-forward to trigger heartbeat
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    const sentData = JSON.parse(mockWs.lastSentData);
    expect(sentData.type).toBe('heartbeat');
  });

  it('should not send messages when disconnected', async () => {
    const onError = jest.fn();
    const { result } = renderHook(() => 
      useChatWebSocket({ ...defaultOptions, onError })
    );

    // Try to send message before connection
    act(() => {
      result.current.sendMessage('Hello');
    });

    expect(onError).toHaveBeenCalledWith('Failed to send message - not connected');
  });

  it('should ignore empty messages', async () => {
    const { result } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];
    const initialLastSentData = mockWs.lastSentData;

    // Try to send empty message
    act(() => {
      result.current.sendMessage('   ');
    });

    // Should not send anything
    expect(mockWs.lastSentData).toBe(initialLastSentData);
  });

  it('should disconnect properly on unmount', async () => {
    const { result, unmount } = renderHook(() => useChatWebSocket(defaultOptions));

    // Wait for connection
    act(() => {
      jest.advanceTimersByTime(20);
    });

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    const mockWs = (global as any).WebSocket.mock.instances[0];
    const closeSpy = jest.spyOn(mockWs, 'close');

    // Unmount component
    unmount();

    expect(closeSpy).toHaveBeenCalledWith(1000, 'User disconnected');
  });
});