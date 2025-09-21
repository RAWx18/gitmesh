/**
 * Custom hook for managing WebSocket connection for real-time chat
 */

import { useEffect, useRef, useState, useCallback } from 'react';

export interface ChatMessage {
  id: string;
  type: string;
  content?: string;
  timestamp: string;
  message_id?: string;
  response_id?: string;
  chunk?: string;
  chunk_index?: number;
  is_final?: boolean;
  metadata?: any;
  error?: string;
  is_error?: boolean;
}

export interface ConnectionStatus {
  status: 'connected' | 'disconnected' | 'reconnecting' | 'error';
  connected_at?: string;
  last_heartbeat?: string;
  message_count?: number;
}

export interface UseChatWebSocketOptions {
  sessionId: string;
  token?: string;
  userId?: string;
  autoReconnect?: boolean;
  heartbeatInterval?: number;
  onMessage?: (message: ChatMessage) => void;
  onConnectionChange?: (status: ConnectionStatus) => void;
  onError?: (error: string) => void;
}

export interface UseChatWebSocketReturn {
  // Connection state
  isConnected: boolean;
  connectionStatus: ConnectionStatus;
  isReconnecting: boolean;
  
  // Message handling
  sendMessage: (content: string) => void;
  sendTypingStart: () => void;
  sendTypingStop: () => void;
  
  // Connection management
  connect: () => void;
  disconnect: () => void;
  
  // Message streaming
  streamingResponse: string;
  isProcessing: boolean;
  isTyping: boolean;
}

export const useChatWebSocket = (options: UseChatWebSocketOptions): UseChatWebSocketReturn => {
  const {
    sessionId,
    token,
    userId,
    autoReconnect = true,
    heartbeatInterval = 30000,
    onMessage,
    onConnectionChange,
    onError
  } = options;

  // WebSocket reference
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;

  // State
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    status: 'disconnected'
  });
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [streamingResponse, setStreamingResponse] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isTyping, setIsTyping] = useState(false);

  // Build WebSocket URL
  const getWebSocketUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const params = new URLSearchParams({
      session_id: sessionId,
      ...(token && { token }),
      ...(userId && { user_id: userId })
    });
    return `${protocol}//${host}/api/v1/chat/ws?${params.toString()}`;
  }, [sessionId, token, userId]);

  // Send message to WebSocket
  const sendWebSocketMessage = useCallback((message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        ...message,
        message_id: message.message_id || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toISOString()
      }));
      return true;
    }
    return false;
  }, []);

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: ChatMessage = JSON.parse(event.data);
      
      // Handle different message types
      switch (message.type) {
        case 'connection_established':
          setIsConnected(true);
          setIsReconnecting(false);
          reconnectAttemptsRef.current = 0;
          setConnectionStatus({
            status: 'connected',
            connected_at: message.timestamp
          });
          onConnectionChange?.({
            status: 'connected',
            connected_at: message.timestamp
          });
          break;

        case 'heartbeat':
          setConnectionStatus(prev => ({
            ...prev,
            last_heartbeat: message.timestamp
          }));
          break;

        case 'ai_response_chunk':
          if (message.chunk_index === 0) {
            setStreamingResponse(message.chunk || '');
          } else {
            setStreamingResponse(prev => prev + (message.chunk || ''));
          }
          break;

        case 'ai_response_complete':
          setStreamingResponse('');
          setIsProcessing(false);
          break;

        case 'processing_start':
          setIsProcessing(true);
          setStreamingResponse('');
          break;

        case 'processing_stop':
          setIsProcessing(false);
          break;

        case 'typing_start':
          setIsTyping(true);
          break;

        case 'typing_stop':
          setIsTyping(false);
          break;

        case 'error':
        case 'validation_error':
        case 'message_failed':
          onError?.(message.error || message.message || 'Unknown error');
          setIsProcessing(false);
          break;

        case 'message_delivered':
          // Message was successfully delivered
          break;

        default:
          // Pass through other messages to the callback
          onMessage?.(message);
          break;
      }

      // Always call the message callback
      onMessage?.(message);

    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      onError?.('Failed to parse message from server');
    }
  }, [onMessage, onConnectionChange, onError]);

  // Handle connection open
  const handleOpen = useCallback(() => {
    console.log('WebSocket connected');
    setIsConnected(true);
    setIsReconnecting(false);
    reconnectAttemptsRef.current = 0;

    // Start heartbeat
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
    }
    heartbeatIntervalRef.current = setInterval(() => {
      sendWebSocketMessage({ type: 'heartbeat' });
    }, heartbeatInterval);

  }, [sendWebSocketMessage, heartbeatInterval]);

  // Handle connection close
  const handleClose = useCallback((event: CloseEvent) => {
    console.log('WebSocket disconnected:', event.code, event.reason);
    setIsConnected(false);
    setIsProcessing(false);
    setStreamingResponse('');
    
    // Clear heartbeat
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }

    const newStatus: ConnectionStatus = {
      status: event.code === 1000 ? 'disconnected' : 'error'
    };
    setConnectionStatus(newStatus);
    onConnectionChange?.(newStatus);

    // Auto-reconnect if enabled and not a normal closure
    if (autoReconnect && event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
      setIsReconnecting(true);
      
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectAttemptsRef.current++;
        connect();
      }, delay);
    }
  }, [autoReconnect, onConnectionChange]);

  // Handle connection error
  const handleError = useCallback((event: Event) => {
    console.error('WebSocket error:', event);
    onError?.('WebSocket connection error');
    setConnectionStatus({ status: 'error' });
    onConnectionChange?.({ status: 'error' });
  }, [onError, onConnectionChange]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    try {
      const url = getWebSocketUrl();
      wsRef.current = new WebSocket(url);
      
      wsRef.current.onopen = handleOpen;
      wsRef.current.onmessage = handleMessage;
      wsRef.current.onclose = handleClose;
      wsRef.current.onerror = handleError;

    } catch (error) {
      console.error('Error creating WebSocket connection:', error);
      onError?.('Failed to create WebSocket connection');
    }
  }, [getWebSocketUrl, handleOpen, handleMessage, handleClose, handleError, onError]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    setIsProcessing(false);
    setStreamingResponse('');
  }, []);

  // Send user message
  const sendMessage = useCallback((content: string) => {
    if (!content.trim()) return;

    const success = sendWebSocketMessage({
      type: 'user_message',
      content: content.trim()
    });

    if (!success) {
      onError?.('Failed to send message - not connected');
    }
  }, [sendWebSocketMessage, onError]);

  // Send typing indicators
  const sendTypingStart = useCallback(() => {
    sendWebSocketMessage({ type: 'typing_start' });
  }, [sendWebSocketMessage]);

  const sendTypingStop = useCallback(() => {
    sendWebSocketMessage({ type: 'typing_stop' });
  }, [sendWebSocketMessage]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    // Connection state
    isConnected,
    connectionStatus,
    isReconnecting,
    
    // Message handling
    sendMessage,
    sendTypingStart,
    sendTypingStop,
    
    // Connection management
    connect,
    disconnect,
    
    // Message streaming
    streamingResponse,
    isProcessing,
    isTyping
  };
};