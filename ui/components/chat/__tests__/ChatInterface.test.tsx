import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatInterface } from '../ChatInterface';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { useChat } from '@/contexts/ChatContext';
import { useBranch } from '@/contexts/BranchContext';

// Mock the contexts
jest.mock('@/contexts/AuthContext');
jest.mock('@/contexts/RepositoryContext');
jest.mock('@/contexts/ChatContext');
jest.mock('@/contexts/BranchContext');

// Mock the child components
jest.mock('../ModelSelector', () => ({
  ModelSelector: ({ selectedModel, onModelChange }: any) => (
    <div data-testid="model-selector">
      <span>Model: {selectedModel}</span>
      <button onClick={() => onModelChange('test-model')}>Change Model</button>
    </div>
  )
}));

jest.mock('../RepositorySelector', () => ({
  RepositorySelector: () => <div data-testid="repository-selector">Repository Selector</div>
}));

jest.mock('../ContextPanel', () => ({
  ContextPanel: () => <div data-testid="context-panel">Context Panel</div>
}));

// Mock react-markdown
jest.mock('react-markdown', () => {
  return function ReactMarkdown({ children }: { children: string }) {
    return <div data-testid="markdown-content">{children}</div>;
  };
});

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRepository = useRepository as jest.MockedFunction<typeof useRepository>;
const mockUseChat = useChat as jest.MockedFunction<typeof useChat>;
const mockUseBranch = useBranch as jest.MockedFunction<typeof useBranch>;

describe('ChatInterface', () => {
  const mockSendMessageWithRetry = jest.fn();
  const mockCreateSession = jest.fn();
  const mockGetMessageStatus = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();

    mockUseAuth.mockReturnValue({
      user: { id: 1, login: 'testuser' },
      isAuthenticated: true,
    } as any);

    mockUseRepository.mockReturnValue({
      repository: {
        id: 1,
        name: 'test-repo',
        full_name: 'testuser/test-repo',
        owner: { login: 'testuser' },
        default_branch: 'main'
      }
    } as any);

    mockUseBranch.mockReturnValue({
      selectedBranch: 'main',
      branchList: ['main', 'develop']
    } as any);

    mockUseChat.mockReturnValue({
      state: {
        selectedFiles: [],
        loadingStates: { chat: false, files: {}, sessions: false },
        errors: { chat: null, files: {}, sessions: null }
      },
      getActiveSession: () => ({
        id: 'session-1',
        title: 'Test Chat',
        messages: [],
        selectedFiles: [],
        createdAt: new Date(),
        updatedAt: new Date()
      }),
      sendMessageWithRetry: mockSendMessageWithRetry,
      createSession: mockCreateSession,
      getMessageStatus: mockGetMessageStatus
    } as any);
  });

  it('renders chat interface when authenticated with repository', () => {
    render(<ChatInterface />);
    
    expect(screen.getByText('Test Chat')).toBeInTheDocument();
    expect(screen.getByTestId('model-selector')).toBeInTheDocument();
    expect(screen.getByTestId('repository-selector')).toBeInTheDocument();
    expect(screen.getByTestId('context-panel')).toBeInTheDocument();
  });

  it('shows sign in message when not authenticated', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
    } as any);

    render(<ChatInterface />);
    
    expect(screen.getByText('Sign in to start chatting')).toBeInTheDocument();
    expect(screen.getByText('Connect your GitHub account to chat with your repositories')).toBeInTheDocument();
  });

  it('shows repository selection message when no repository selected', () => {
    mockUseRepository.mockReturnValue({
      repository: null
    } as any);

    render(<ChatInterface />);
    
    expect(screen.getByText('Select a repository')).toBeInTheDocument();
    expect(screen.getByText('Choose a repository to start chatting with your codebase')).toBeInTheDocument();
  });

  it('displays welcome message when no messages exist', () => {
    render(<ChatInterface />);
    
    expect(screen.getByText('Start a conversation')).toBeInTheDocument();
    expect(screen.getByText('Ask questions about your code, request explanations, or get help with development tasks.')).toBeInTheDocument();
  });

  it('handles message input and submission', async () => {
    render(<ChatInterface />);
    
    const textarea = screen.getByPlaceholderText('Ask about your repository...');
    const sendButton = screen.getByRole('button', { name: /send/i });
    
    // Type a message
    fireEvent.change(textarea, { target: { value: 'Test message' } });
    expect(textarea).toHaveValue('Test message');
    
    // Click send button
    fireEvent.click(sendButton);
    
    await waitFor(() => {
      expect(mockSendMessageWithRetry).toHaveBeenCalledWith(
        'session-1',
        'Test message',
        3,
        expect.objectContaining({
          model: 'gemini',
          context: { files: [] }
        })
      );
    });
  });

  it('handles Enter key to send message', async () => {
    render(<ChatInterface />);
    
    const textarea = screen.getByPlaceholderText('Ask about your repository...');
    
    // Type a message
    fireEvent.change(textarea, { target: { value: 'Test message' } });
    
    // Press Enter
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });
    
    await waitFor(() => {
      expect(mockSendMessageWithRetry).toHaveBeenCalled();
    });
  });

  it('handles Shift+Enter for new line', () => {
    render(<ChatInterface />);
    
    const textarea = screen.getByPlaceholderText('Ask about your repository...');
    
    // Type a message
    fireEvent.change(textarea, { target: { value: 'Test message' } });
    
    // Press Shift+Enter (should not send)
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: true });
    
    expect(mockSendMessageWithRetry).not.toHaveBeenCalled();
  });

  it('disables send button when loading', () => {
    mockUseChat.mockReturnValue({
      state: {
        selectedFiles: [],
        loadingStates: { chat: true, files: {}, sessions: false },
        errors: { chat: null, files: {}, sessions: null }
      },
      getActiveSession: () => ({
        id: 'session-1',
        title: 'Test Chat',
        messages: [],
        selectedFiles: [],
        createdAt: new Date(),
        updatedAt: new Date()
      }),
      sendMessageWithRetry: mockSendMessageWithRetry,
      createSession: mockCreateSession,
      getMessageStatus: mockGetMessageStatus
    } as any);

    render(<ChatInterface />);
    
    const sendButton = screen.getByRole('button', { name: /send/i });
    expect(sendButton).toBeDisabled();
  });

  it('shows context files preview when files are selected', () => {
    mockUseChat.mockReturnValue({
      state: {
        selectedFiles: [
          { branch: 'main', path: 'src/test.ts', content: 'test content' },
          { branch: 'main', path: 'src/utils.ts', content: 'utils content' }
        ],
        loadingStates: { chat: false, files: {}, sessions: false },
        errors: { chat: null, files: {}, sessions: null }
      },
      getActiveSession: () => ({
        id: 'session-1',
        title: 'Test Chat',
        messages: [],
        selectedFiles: [],
        createdAt: new Date(),
        updatedAt: new Date()
      }),
      sendMessageWithRetry: mockSendMessageWithRetry,
      createSession: mockCreateSession,
      getMessageStatus: mockGetMessageStatus
    } as any);

    render(<ChatInterface />);
    
    expect(screen.getByText('Context files (2)')).toBeInTheDocument();
    expect(screen.getByText('test.ts')).toBeInTheDocument();
    expect(screen.getByText('utils.ts')).toBeInTheDocument();
  });

  it('toggles context panel visibility', () => {
    render(<ChatInterface />);
    
    const contextToggle = screen.getByRole('button', { name: /context/i });
    
    // Context panel should be visible initially
    expect(screen.getByTestId('context-panel')).toBeInTheDocument();
    
    // Click to hide
    fireEvent.click(contextToggle);
    
    // Context panel should be hidden
    expect(screen.queryByTestId('context-panel')).not.toBeInTheDocument();
  });

  it('creates initial session when none exists', () => {
    mockUseChat.mockReturnValue({
      state: {
        selectedFiles: [],
        loadingStates: { chat: false, files: {}, sessions: false },
        errors: { chat: null, files: {}, sessions: null }
      },
      getActiveSession: () => null, // No active session
      sendMessageWithRetry: mockSendMessageWithRetry,
      createSession: mockCreateSession,
      getMessageStatus: mockGetMessageStatus
    } as any);

    render(<ChatInterface />);
    
    expect(mockCreateSession).toHaveBeenCalledWith('Chat with test-repo');
  });
});