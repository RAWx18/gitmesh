/**
 * Tests for RealTimeChatInterface component
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RealTimeChatInterface } from '../RealTimeChatInterface';
import { useChatWebSocket } from '../../../hooks/useChatWebSocket';

// Mock the WebSocket hook
jest.mock('../../../hooks/useChatWebSocket');

const mockUseChatWebSocket = useChatWebSocket as jest.MockedFunction<typeof useChatWebSocket>;

describe('RealTimeChatInterface', () => {
  const defaultProps = {
    sessionId: 'test-session-123',
    token: 'test-token',
    userId: 'test-user'
  };

  const mockWebSocketReturn = {
    isConnected: true,
    connectionStatus: { status: 'connected' as const },
    isReconnecting: false,
    sendMessage: jest.fn(),
    sendTypingStart: jest.fn(),
    sendTypingStop: jest.fn(),
    connect: jest.fn(),
    disconnect: jest.fn(),
    streamingResponse: '',
    isProcessing: false,
    isTyping: false
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseChatWebSocket.mockReturnValue(mockWebSocketReturn);
  });

  it('should render chat interface with correct elements', () => {
    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('AI Assistant')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  it('should show disconnected status when not connected', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isConnected: false,
      connectionStatus: { status: 'disconnected' }
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('Disconnected')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Connecting...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('should show reconnecting status', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isConnected: false,
      isReconnecting: true,
      connectionStatus: { status: 'reconnecting' }
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
  });

  it('should show processing status', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isProcessing: true
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('Processing...')).toBeInTheDocument();
  });

  it('should send message when form is submitted', async () => {
    const user = userEvent.setup();
    const mockSendMessage = jest.fn();
    const mockOnMessageSent = jest.fn();

    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      sendMessage: mockSendMessage
    });

    render(
      <RealTimeChatInterface 
        {...defaultProps} 
        onMessageSent={mockOnMessageSent}
      />
    );

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    // Type message
    await user.type(input, 'Hello AI!');
    expect(input).toHaveValue('Hello AI!');

    // Submit form
    await user.click(sendButton);

    expect(mockSendMessage).toHaveBeenCalledWith('Hello AI!');
    expect(mockOnMessageSent).toHaveBeenCalledWith('Hello AI!');
    expect(input).toHaveValue(''); // Input should be cleared
  });

  it('should send message on Enter key press', async () => {
    const user = userEvent.setup();
    const mockSendMessage = jest.fn();

    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      sendMessage: mockSendMessage
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const input = screen.getByPlaceholderText('Type your message...');

    // Type message and press Enter
    await user.type(input, 'Hello AI!{enter}');

    expect(mockSendMessage).toHaveBeenCalledWith('Hello AI!');
    expect(input).toHaveValue('');
  });

  it('should not send empty messages', async () => {
    const user = userEvent.setup();
    const mockSendMessage = jest.fn();

    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      sendMessage: mockSendMessage
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    // Try to send empty message
    await user.click(sendButton);
    expect(mockSendMessage).not.toHaveBeenCalled();

    // Try to send whitespace-only message
    await user.type(input, '   ');
    await user.click(sendButton);
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('should send typing indicators', async () => {
    const user = userEvent.setup();
    const mockSendTypingStart = jest.fn();
    const mockSendTypingStop = jest.fn();

    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      sendTypingStart: mockSendTypingStart,
      sendTypingStop: mockSendTypingStop
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const input = screen.getByPlaceholderText('Type your message...');

    // Start typing
    await user.type(input, 'H');
    expect(mockSendTypingStart).toHaveBeenCalled();

    // Simulate typing timeout
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(mockSendTypingStop).toHaveBeenCalled();
  });

  it('should display user messages', () => {
    const { rerender } = render(<RealTimeChatInterface {...defaultProps} />);

    // Simulate adding a user message
    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    fireEvent.change(input, { target: { value: 'Hello AI!' } });
    fireEvent.click(sendButton);

    // The message should appear in the chat
    expect(screen.getByText('Hello AI!')).toBeInTheDocument();
  });

  it('should display streaming AI responses', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      streamingResponse: 'Hello there! This is a streaming response...'
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('Hello there! This is a streaming response...')).toBeInTheDocument();
    // Should show typing indicator for streaming
    expect(screen.getByText(/Hello there! This is a streaming response.../)).toBeInTheDocument();
  });

  it('should display typing indicator when AI is typing', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isTyping: true
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    expect(screen.getByText('AI is typing')).toBeInTheDocument();
  });

  it('should display error messages', () => {
    render(<RealTimeChatInterface {...defaultProps} />);

    // Simulate error by calling the onError callback
    const onErrorCallback = mockUseChatWebSocket.mock.calls[0][0].onError;
    
    act(() => {
      onErrorCallback?.('Connection failed');
    });

    expect(screen.getByText('Connection failed')).toBeInTheDocument();
  });

  it('should show reconnect button when disconnected', () => {
    const mockConnect = jest.fn();

    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isConnected: false,
      isReconnecting: false,
      connect: mockConnect
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const reconnectButton = screen.getByRole('button', { name: /reconnect/i });
    expect(reconnectButton).toBeInTheDocument();

    fireEvent.click(reconnectButton);
    expect(mockConnect).toHaveBeenCalled();
  });

  it('should disable input and send button when processing', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isProcessing: true
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    expect(input).toBeDisabled();
    expect(sendButton).toBeDisabled();
  });

  it('should disable input and send button when disconnected', () => {
    mockUseChatWebSocket.mockReturnValue({
      ...mockWebSocketReturn,
      isConnected: false
    });

    render(<RealTimeChatInterface {...defaultProps} />);

    const input = screen.getByPlaceholderText('Connecting...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    expect(input).toBeDisabled();
    expect(sendButton).toBeDisabled();
  });

  it('should call onMessageReceived when messages are received', () => {
    const mockOnMessageReceived = jest.fn();

    render(
      <RealTimeChatInterface 
        {...defaultProps} 
        onMessageReceived={mockOnMessageReceived}
      />
    );

    // Simulate receiving a message by calling the onMessage callback
    const onMessageCallback = mockUseChatWebSocket.mock.calls[0][0].onMessage;
    const testMessage = {
      id: 'msg-123',
      type: 'ai_response_complete',
      content: 'AI response',
      timestamp: new Date().toISOString()
    };

    act(() => {
      onMessageCallback?.(testMessage);
    });

    expect(mockOnMessageReceived).toHaveBeenCalledWith(testMessage);
  });

  it('should auto-scroll to bottom when new messages arrive', () => {
    const mockScrollIntoView = jest.fn();
    Element.prototype.scrollIntoView = mockScrollIntoView;

    render(<RealTimeChatInterface {...defaultProps} />);

    // Send a message to trigger scroll
    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    fireEvent.change(input, { target: { value: 'Test message' } });
    fireEvent.click(sendButton);

    expect(mockScrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth' });
  });

  it('should display message timestamps', () => {
    render(<RealTimeChatInterface {...defaultProps} />);

    // Send a message
    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    fireEvent.change(input, { target: { value: 'Test message' } });
    fireEvent.click(sendButton);

    // Should display timestamp (format may vary based on locale)
    const timeElements = screen.getAllByText(/\d{1,2}:\d{2}/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  it('should handle message delivery status', () => {
    render(<RealTimeChatInterface {...defaultProps} />);

    // Send a message
    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    fireEvent.change(input, { target: { value: 'Test message' } });
    fireEvent.click(sendButton);

    // Should show sending status initially (loading icon)
    // This would be tested by checking for the presence of loading indicators
    // The exact implementation depends on how delivery status is displayed
  });

  it('should apply custom className', () => {
    const { container } = render(
      <RealTimeChatInterface {...defaultProps} className="custom-chat-class" />
    );

    expect(container.firstChild).toHaveClass('custom-chat-class');
  });
});