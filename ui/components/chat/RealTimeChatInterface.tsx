/**
 * Real-time Chat Interface Component
 * 
 * Provides real-time chat communication with WebSocket support,
 * message streaming, typing indicators, and connection status.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Wifi, WifiOff, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Alert, AlertDescription } from '../ui/alert';
import { useChatWebSocket, ChatMessage, ConnectionStatus } from '../../hooks/useChatWebSocket';

interface RealTimeChatInterfaceProps {
  sessionId: string;
  token?: string;
  userId?: string;
  className?: string;
  onMessageSent?: (message: string) => void;
  onMessageReceived?: (message: ChatMessage) => void;
}

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  isError?: boolean;
  metadata?: any;
}

export const RealTimeChatInterface: React.FC<RealTimeChatInterfaceProps> = ({
  sessionId,
  token,
  userId,
  className = '',
  onMessageSent,
  onMessageReceived
}) => {
  // State
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTypingInput, setIsTypingInput] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState<{ [key: string]: 'sending' | 'delivered' | 'failed' }>({});

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // WebSocket hook
  const {
    isConnected,
    connectionStatus,
    isReconnecting,
    sendMessage,
    sendTypingStart,
    sendTypingStop,
    connect,
    disconnect,
    streamingResponse,
    isProcessing,
    isTyping
  } = useChatWebSocket({
    sessionId,
    token,
    userId,
    autoReconnect: true,
    onMessage: handleWebSocketMessage,
    onConnectionChange: handleConnectionChange,
    onError: handleWebSocketError
  });

  // Handle WebSocket messages
  function handleWebSocketMessage(message: ChatMessage) {
    onMessageReceived?.(message);

    switch (message.type) {
      case 'user_message':
        // User message echo (shouldn't happen normally)
        break;

      case 'ai_response_chunk':
        // Handle streaming response
        if (message.chunk_index === 0) {
          // Start new streaming message
          const streamingMessage: DisplayMessage = {
            id: message.response_id || message.id,
            role: 'assistant',
            content: message.chunk || '',
            timestamp: message.timestamp,
            isStreaming: true
          };
          setMessages(prev => [...prev, streamingMessage]);
        } else {
          // Update streaming message
          setMessages(prev => prev.map(msg => 
            msg.id === message.response_id && msg.isStreaming
              ? { ...msg, content: msg.content + (message.chunk || '') }
              : msg
          ));
        }
        break;

      case 'ai_response_complete':
        // Complete streaming message
        setMessages(prev => prev.map(msg => 
          msg.id === message.response_id && msg.isStreaming
            ? { 
                ...msg, 
                content: message.content || msg.content,
                isStreaming: false,
                metadata: message.metadata
              }
            : msg
        ));
        break;

      case 'message_delivered':
        // Update delivery status
        if (message.message_id) {
          setDeliveryStatus(prev => ({
            ...prev,
            [message.message_id!]: 'delivered'
          }));
        }
        break;

      case 'message_failed':
        // Handle message failure
        if (message.message_id) {
          setDeliveryStatus(prev => ({
            ...prev,
            [message.message_id!]: 'failed'
          }));
        }
        
        // Add fallback response if provided
        if (message.fallback_response) {
          const errorMessage: DisplayMessage = {
            id: `error_${Date.now()}`,
            role: 'assistant',
            content: message.fallback_response,
            timestamp: new Date().toISOString(),
            isError: true
          };
          setMessages(prev => [...prev, errorMessage]);
        }
        break;

      case 'error':
      case 'validation_error':
        setError(message.error || message.message || 'Unknown error occurred');
        setTimeout(() => setError(null), 5000);
        break;
    }
  }

  // Handle connection status changes
  function handleConnectionChange(status: ConnectionStatus) {
    if (status.status === 'connected') {
      setError(null);
    }
  }

  // Handle WebSocket errors
  function handleWebSocketError(error: string) {
    setError(error);
    setTimeout(() => setError(null), 5000);
  }

  // Handle input change with typing indicators
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);

    // Send typing indicators
    if (value.trim() && !isTypingInput) {
      setIsTypingInput(true);
      sendTypingStart();
    }

    // Clear existing timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }

    // Set timeout to stop typing indicator
    typingTimeoutRef.current = setTimeout(() => {
      if (isTypingInput) {
        setIsTypingInput(false);
        sendTypingStop();
      }
    }, 1000);
  }, [isTypingInput, sendTypingStart, sendTypingStop]);

  // Handle form submission
  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputValue.trim() || !isConnected) {
      return;
    }

    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const content = inputValue.trim();

    // Add user message to display
    const userMessage: DisplayMessage = {
      id: messageId,
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);

    // Set delivery status
    setDeliveryStatus(prev => ({
      ...prev,
      [messageId]: 'sending'
    }));

    // Send message via WebSocket
    sendMessage(content);

    // Clear input and stop typing indicator
    setInputValue('');
    if (isTypingInput) {
      setIsTypingInput(false);
      sendTypingStop();
    }

    // Clear typing timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }

    // Callback
    onMessageSent?.(content);
  }, [inputValue, isConnected, sendMessage, isTypingInput, sendTypingStop, onMessageSent]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingResponse]);

  // Cleanup typing timeout
  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
    };
  }, []);

  // Connection status indicator
  const getConnectionStatusBadge = () => {
    if (isReconnecting) {
      return (
        <Badge variant="outline" className="flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          Reconnecting...
        </Badge>
      );
    }

    if (isConnected) {
      return (
        <Badge variant="default" className="flex items-center gap-1 bg-green-500">
          <Wifi className="h-3 w-3" />
          Connected
        </Badge>
      );
    }

    return (
      <Badge variant="destructive" className="flex items-center gap-1">
        <WifiOff className="h-3 w-3" />
        Disconnected
      </Badge>
    );
  };

  // Message delivery status icon
  const getDeliveryStatusIcon = (messageId: string) => {
    const status = deliveryStatus[messageId];
    
    switch (status) {
      case 'sending':
        return <Loader2 className="h-3 w-3 animate-spin text-gray-400" />;
      case 'delivered':
        return <CheckCircle className="h-3 w-3 text-green-500" />;
      case 'failed':
        return <AlertCircle className="h-3 w-3 text-red-500" />;
      default:
        return null;
    }
  };

  return (
    <Card className={`flex flex-col h-full ${className}`}>
      <CardHeader className="flex-shrink-0 pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">AI Assistant</CardTitle>
          <div className="flex items-center gap-2">
            {getConnectionStatusBadge()}
            {isProcessing && (
              <Badge variant="outline" className="flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                Processing...
              </Badge>
            )}
          </div>
        </div>
        
        {error && (
          <Alert variant="destructive" className="mt-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardHeader>

      <CardContent className="flex-1 flex flex-col min-h-0">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 ${
                  message.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : message.isError
                    ? 'bg-red-50 text-red-800 border border-red-200'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                <div className="whitespace-pre-wrap break-words">
                  {message.content}
                  {message.isStreaming && (
                    <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                  )}
                </div>
                
                <div className="flex items-center justify-between mt-1 text-xs opacity-70">
                  <span>
                    {new Date(message.timestamp).toLocaleTimeString()}
                  </span>
                  {message.role === 'user' && (
                    <div className="ml-2">
                      {getDeliveryStatusIcon(message.id)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Streaming response */}
          {streamingResponse && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg px-3 py-2 bg-gray-100 text-gray-800">
                <div className="whitespace-pre-wrap break-words">
                  {streamingResponse}
                  <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                </div>
              </div>
            </div>
          )}

          {/* Typing indicator */}
          {isTyping && (
            <div className="flex justify-start">
              <div className="rounded-lg px-3 py-2 bg-gray-100 text-gray-500 text-sm">
                <div className="flex items-center gap-1">
                  <span>AI is typing</span>
                  <div className="flex gap-1">
                    <div className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            ref={inputRef}
            value={inputValue}
            onChange={handleInputChange}
            placeholder={
              isConnected 
                ? "Type your message..." 
                : "Connecting..."
            }
            disabled={!isConnected || isProcessing}
            className="flex-1"
            autoComplete="off"
          />
          <Button
            type="submit"
            disabled={!isConnected || !inputValue.trim() || isProcessing}
            size="icon"
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>

        {/* Connection controls */}
        {!isConnected && !isReconnecting && (
          <div className="mt-2 text-center">
            <Button
              variant="outline"
              size="sm"
              onClick={connect}
              className="text-xs"
            >
              Reconnect
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};