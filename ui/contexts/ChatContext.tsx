"use client";

import React, { createContext, useContext, useReducer, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { useRepository } from './RepositoryContext';
import ChatAPI, { ChatMessage, ChatSession } from '@/lib/chat-api';

// Types for chat state management
// ChatMessage and ChatSession are now imported from chat-api.ts

interface FileSystemItem {
  name: string;
  type: 'file' | 'folder';
  selected?: boolean;
  children?: FileSystemItem[];
  size?: number;
  path?: string;
  branch?: string;
  content?: string;
  contentHash?: string;
  lastFetched?: Date;
  error?: string;
}

interface MessageStatus {
  id: string;
  status: 'sending' | 'sent' | 'failed' | 'retrying';
  retryCount: number;
  error?: string;
}

// ChatSession is now imported from chat-api.ts

interface FileCache {
  [key: string]: {
    content: string;
    hash: string;
    timestamp: Date;
    error?: string;
  };
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  fileCache: FileCache;
  selectedFiles: Array<{branch: string, path: string, content: string, contentHash?: string}>;
  fileStructures: Record<string, FileSystemItem[]>;
  messageStatuses: Record<string, MessageStatus>;
  loadingStates: {
    files: Record<string, boolean>;
    chat: boolean;
    sessions: boolean;
  };
  errors: {
    files: Record<string, string>;
    chat: string | null;
    sessions: string | null;
  };
}

// Action types
type ChatAction =
  | { type: 'CREATE_SESSION'; payload: { session: ChatSession } }
  | { type: 'UPDATE_SESSION'; payload: { sessionId: string; updates: Partial<ChatSession> } }
  | { type: 'DELETE_SESSION'; payload: { sessionId: string } }
  | { type: 'SET_SESSIONS'; payload: { sessions: ChatSession[] } }
  | { type: 'SET_ACTIVE_SESSION'; payload: { sessionId: string } }
  | { type: 'ADD_MESSAGE'; payload: { sessionId: string; message: ChatMessage } }
  | { type: 'UPDATE_MESSAGE'; payload: { sessionId: string; messageId: string; updates: Partial<ChatMessage> } }
  | { type: 'SET_MESSAGE_STATUS'; payload: { messageId: string; status: MessageStatus } }
  | { type: 'UPDATE_MESSAGE_STATUS'; payload: { messageId: string; updates: Partial<MessageStatus> } }
  | { type: 'REMOVE_MESSAGE_STATUS'; payload: { messageId: string } }
  | { type: 'SET_SELECTED_FILES'; payload: { files: Array<{branch: string, path: string, content: string, contentHash?: string}> } }
  | { type: 'ADD_SELECTED_FILE'; payload: { file: {branch: string, path: string, content: string, contentHash?: string} } }
  | { type: 'REMOVE_SELECTED_FILE'; payload: { branch: string; path: string } }
  | { type: 'CACHE_FILE_CONTENT'; payload: { key: string; content: string; hash: string; error?: string } }
  | { type: 'SET_FILE_STRUCTURE'; payload: { branch: string; structure: FileSystemItem[] } }
  | { type: 'SET_LOADING_STATE'; payload: { type: 'files' | 'chat' | 'sessions'; key?: string; loading: boolean } }
  | { type: 'SET_ERROR'; payload: { type: 'files' | 'chat' | 'sessions'; key?: string; error: string | null } }
  | { type: 'CLEAR_ERRORS'; payload: { type: 'files' | 'chat' | 'sessions' } }
  | { type: 'RESET_STATE' };

// Initial state
const initialState: ChatState = {
  sessions: [],
  activeSessionId: null,
  fileCache: {},
  selectedFiles: [],
  fileStructures: {},
  messageStatuses: {},
  loadingStates: {
    files: {},
    chat: false,
    sessions: false
  },
  errors: {
    files: {},
    chat: null,
    sessions: null
  }
};

// Reducer function
function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'CREATE_SESSION':
      return {
        ...state,
        sessions: [action.payload.session, ...state.sessions],
        activeSessionId: action.payload.session.id
      };

    case 'UPDATE_SESSION':
      return {
        ...state,
        sessions: state.sessions.map(session =>
          session.id === action.payload.sessionId
            ? { ...session, ...action.payload.updates, updatedAt: new Date() }
            : session
        )
      };

    case 'DELETE_SESSION':
      return {
        ...state,
        sessions: state.sessions.filter(session => session.id !== action.payload.sessionId),
        activeSessionId: state.activeSessionId === action.payload.sessionId ? null : state.activeSessionId
      };

    case 'SET_SESSIONS':
      return {
        ...state,
        sessions: action.payload.sessions
      };

    case 'SET_ACTIVE_SESSION':
      return {
        ...state,
        activeSessionId: action.payload.sessionId
      };

    case 'ADD_MESSAGE':
      return {
        ...state,
        sessions: state.sessions.map(session =>
          session.id === action.payload.sessionId
            ? {
                ...session,
                messages: [...session.messages, action.payload.message],
                updatedAt: new Date()
              }
            : session
        )
      };

    case 'UPDATE_MESSAGE':
      return {
        ...state,
        sessions: state.sessions.map(session =>
          session.id === action.payload.sessionId
            ? {
                ...session,
                messages: session.messages.map(message =>
                  message.id === action.payload.messageId
                    ? { ...message, ...action.payload.updates }
                    : message
                )
              }
            : session
        )
      };

    case 'SET_MESSAGE_STATUS':
      return {
        ...state,
        messageStatuses: {
          ...state.messageStatuses,
          [action.payload.messageId]: action.payload.status
        }
      };

    case 'UPDATE_MESSAGE_STATUS':
      const currentStatus = state.messageStatuses[action.payload.messageId];
      return {
        ...state,
        messageStatuses: {
          ...state.messageStatuses,
          [action.payload.messageId]: {
            ...currentStatus,
            ...action.payload.updates
          }
        }
      };

    case 'REMOVE_MESSAGE_STATUS':
      const { [action.payload.messageId]: removed, ...remainingStatuses } = state.messageStatuses;
      return {
        ...state,
        messageStatuses: remainingStatuses
      };

    case 'SET_SELECTED_FILES':
      return {
        ...state,
        selectedFiles: action.payload.files
      };

    case 'ADD_SELECTED_FILE':
      // Check if file already exists to prevent duplicates
      const existingFileIndex = state.selectedFiles.findIndex(
        file => file.branch === action.payload.file.branch && file.path === action.payload.file.path
      );
      
      if (existingFileIndex !== -1) {
        console.log('File already exists in context, updating:', action.payload.file.path);
        // Update existing file instead of adding duplicate
        const updatedFiles = [...state.selectedFiles];
        updatedFiles[existingFileIndex] = action.payload.file;
        return {
          ...state,
          selectedFiles: updatedFiles
        };
      }
      
      console.log('Adding new file to context:', action.payload.file.path);
      return {
        ...state,
        selectedFiles: [...state.selectedFiles, action.payload.file]
      };

    case 'REMOVE_SELECTED_FILE':
      return {
        ...state,
        selectedFiles: state.selectedFiles.filter(
          file => !(file.branch === action.payload.branch && file.path === action.payload.path)
        )
      };

    case 'CACHE_FILE_CONTENT':
      return {
        ...state,
        fileCache: {
          ...state.fileCache,
          [action.payload.key]: {
            content: action.payload.content,
            hash: action.payload.hash,
            timestamp: new Date(),
            error: action.payload.error
          }
        }
      };

    case 'SET_FILE_STRUCTURE':
      return {
        ...state,
        fileStructures: {
          ...state.fileStructures,
          [action.payload.branch]: action.payload.structure
        }
      };

    case 'SET_LOADING_STATE':
      if (action.payload.type === 'files' && action.payload.key) {
        return {
          ...state,
          loadingStates: {
            ...state.loadingStates,
            files: {
              ...state.loadingStates.files,
              [action.payload.key]: action.payload.loading
            }
          }
        };
      }
      return {
        ...state,
        loadingStates: {
          ...state.loadingStates,
          [action.payload.type]: action.payload.loading
        }
      };

    case 'SET_ERROR':
      if (action.payload.type === 'files' && action.payload.key) {
        return {
          ...state,
          errors: {
            ...state.errors,
            files: {
              ...state.errors.files,
              [action.payload.key]: action.payload.error || ''
            }
          }
        };
      }
      return {
        ...state,
        errors: {
          ...state.errors,
          [action.payload.type]: action.payload.error
        }
      };

    case 'CLEAR_ERRORS':
      if (action.payload.type === 'files') {
        return {
          ...state,
          errors: {
            ...state.errors,
            files: {}
          }
        };
      }
      return {
        ...state,
        errors: {
          ...state.errors,
          [action.payload.type]: null
        }
      };

    case 'RESET_STATE':
      return initialState;

    default:
      return state;
  }
}

// Context interface
interface ChatContextType {
  state: ChatState;
  // Session management
  createSession: (title?: string) => string | Promise<string>;
  updateSession: (sessionId: string, updates: Partial<ChatSession>) => void;
  deleteSession: (sessionId: string) => void;
  setActiveSession: (sessionId: string) => void;
  getActiveSession: () => ChatSession | null;
  getSession: (sessionId: string) => ChatSession | null;
  
  // Message management
  addMessage: (sessionId: string, message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  sendMessage: (sessionId: string, message: string) => Promise<ChatMessage>;
  sendMessageWithRetry: (sessionId: string, message: string, maxRetries?: number, options? : { model?: string; context?: any }) => Promise<ChatMessage>;
  updateMessage: (sessionId: string, messageId: string, updates: Partial<ChatMessage>) => void;
  setMessageStatus: (messageId: string, status: MessageStatus) => void;
  updateMessageStatus: (messageId: string, updates: Partial<MessageStatus>) => void;
  getMessageStatus: (messageId: string) => MessageStatus | null;
  
  // File management
  setSelectedFiles: (files: Array<{branch: string, path: string, content: string, contentHash?: string}>) => void;
  addSelectedFile: (file: {branch: string, path: string, content: string, contentHash?: string}) => void;
  removeSelectedFile: (branch: string, path: string) => void;
  getCachedFileContent: (key: string) => { content: string; hash: string; timestamp: Date; error?: string } | null;
  cacheFileContent: (key: string, content: string, hash: string, error?: string) => void;
  setFileStructure: (branch: string, structure: FileSystemItem[]) => void;
  
  // Loading and error states
  setLoadingState: (type: 'files' | 'chat' | 'sessions', key?: string, loading?: boolean) => void;
  setError: (type: 'files' | 'chat' | 'sessions', key?: string, error?: string | null) => void;
  clearErrors: (type: 'files' | 'chat' | 'sessions') => void;
  
  // Utility functions
  generateSessionId: () => string;
  generateMessageId: () => string;
  getFileCacheKey: (branch: string, path: string) => string;
  getFileHash: (content: string) => string;
}

// Create context
const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Provider component
export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const { token, user, githubApi } = useAuth();
  const { repository } = useRepository();
  
  console.log('ChatContext: Auth token available:', token ? 'Yes' : 'No');
  console.log('ChatContext: User available:', user ? 'Yes' : 'No');
  
  // Use real token if available, don't fall back to demo token for public repos
  const effectiveToken = token;
  console.log('ChatContext: Using token:', effectiveToken ? 'Real token' : 'No token (will use unauthenticated requests for public repos)');
  
  const chatAPI = useMemo(() => effectiveToken ? new ChatAPI(effectiveToken) : null, [effectiveToken]);

  // Generate unique IDs
  const generateSessionId = useCallback(() => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  const generateMessageId = useCallback(() => {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  // File cache key generation
  const getFileCacheKey = useCallback((branch: string, path: string) => {
    return `${branch}:${path}`;
  }, []);

  // Simple hash function for file content
  const getFileHash = useCallback((content: string) => {
    let hash = 0;
    for (let i = 0; i < content.length; i++) {
      const char = content.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return hash.toString(36);
  }, []);

  // Session management
  const createSession = useCallback((title?: string) => {
    if (!chatAPI) {
      // For demo mode or when no API is available, create a local session
      const sessionId = generateSessionId();
      const session: ChatSession = {
        id: sessionId,
        title: title || 'New Chat',
        messages: [],
        selectedFiles: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        repositoryId: repository?.full_name,
        branch: repository?.default_branch
      };
      
      dispatch({ type: 'CREATE_SESSION', payload: { session } });
      dispatch({ type: 'SET_ACTIVE_SESSION', payload: { sessionId } });
      return sessionId;
    }

    // If API is available, use it
    dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'sessions', loading: true } });
    
    return chatAPI.createSession({
      title: title || 'New Chat',
      repositoryId: repository?.full_name,
      branch: repository?.default_branch
    }).then(response => {
      if (response.success) {
        const session = response.session;
        dispatch({ type: 'CREATE_SESSION', payload: { session } });
        dispatch({ type: 'SET_ACTIVE_SESSION', payload: { sessionId: session.id } });
        return session.id;
      } else {
        throw new Error('Failed to create session');
      }
    }).catch(error => {
      dispatch({ type: 'SET_ERROR', payload: { type: 'sessions', error: error instanceof Error ? error.message : 'Failed to create session' } });
      throw error;
    }).finally(() => {
      dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'sessions', loading: false } });
    });
  }, [chatAPI, repository, generateSessionId]);

  const updateSession = useCallback((sessionId: string, updates: Partial<ChatSession>) => {
    if (!chatAPI) {
      dispatch({ type: 'UPDATE_SESSION', payload: { sessionId, updates } });
      return;
    }

    chatAPI.updateSession(sessionId, updates).then(response => {
      if (response.success) {
        dispatch({ type: 'UPDATE_SESSION', payload: { sessionId, updates: response.session } });
      }
    }).catch(error => {
      dispatch({ type: 'SET_ERROR', payload: { type: 'sessions', error: error instanceof Error ? error.message : 'Failed to update session' } });
    });
  }, [chatAPI]);

  const deleteSession = useCallback((sessionId: string) => {
    if (!chatAPI) {
      dispatch({ type: 'DELETE_SESSION', payload: { sessionId } });
      return;
    }

    chatAPI.deleteSession(sessionId).then(response => {
      if (response.success) {
        dispatch({ type: 'DELETE_SESSION', payload: { sessionId } });
      }
    }).catch(error => {
      dispatch({ type: 'SET_ERROR', payload: { type: 'sessions', error: error instanceof Error ? error.message : 'Failed to delete session' } });
    });
  }, [chatAPI]);

  const setActiveSession = useCallback((sessionId: string) => {
    dispatch({ type: 'SET_ACTIVE_SESSION', payload: { sessionId } });
  }, []);

  const getActiveSession = useCallback(() => {
    if (!state.activeSessionId) return null;
    return state.sessions.find(session => session.id === state.activeSessionId) || null;
  }, [state.activeSessionId, state.sessions]);

  const getSession = useCallback((sessionId: string) => {
    return state.sessions.find(session => session.id === sessionId) || null;
  }, [state.sessions]);

  // Message management
  const addMessage = useCallback((sessionId: string, message: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const fullMessage: ChatMessage = {
      ...message,
      id: generateMessageId(),
      timestamp: new Date()
    };
    dispatch({ type: 'ADD_MESSAGE', payload: { sessionId, message: fullMessage } });
  }, [generateMessageId]);

  const sendMessage = useCallback(async (sessionId: string, message: string) => {
    if (!chatAPI) {
      throw new Error('No authentication token available');
    }

    console.log('ChatContext: Sending message to session:', sessionId);
    console.log('ChatContext: Message:', message);

    try {
      dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'chat', loading: true } });
      
      console.log('ChatContext sendMessage - selectedFiles:', state.selectedFiles);
      console.log('ChatContext sendMessage - selectedFiles count:', state.selectedFiles?.length || 0);
      state.selectedFiles?.forEach((file, index) => {
        console.log(`  File ${index + 1}: ${file.path} - content length: ${file.content?.length || 0}`);
        console.log(`  Content preview: ${file.content?.substring(0, 200) || 'NO CONTENT'}...`);
      });
      
      // Prepare files with repository information
      const filesWithRepo = state.selectedFiles.map(file => {
        // Ensure content is always a string
        let fileContent = file.content;
        if (typeof fileContent !== 'string') {
          console.warn('ChatContext: File content is not a string, converting:', typeof fileContent);
          fileContent = String(fileContent || '');
        }
        
        return {
          path: file.path,
          content: fileContent,
          branch: file.branch,
          repository_id: repository?.full_name || 'default',
          owner: repository?.owner?.login || 'unknown',
          repo: repository?.name || 'repo',
          url: repository ? `https://github.com/${repository.owner.login}/${repository.name}/blob/${file.branch}/${file.path}` : undefined,
          raw_url: repository ? `https://raw.githubusercontent.com/${repository.owner.login}/${repository.name}/${file.branch}/${file.path}` : undefined
        };
      });
      
      console.log('ChatContext sendMessage - filesWithRepo:', filesWithRepo);
      console.log('ChatContext sendMessage - payload:', {
        message,
        context: {
          files: filesWithRepo
        },
        repository_id: repository?.full_name || 'default'
      });
      
      const response = await chatAPI.sendMessage(sessionId, {
        message,
        context: {
          files: filesWithRepo
        },
        repository_id: repository?.full_name || 'default'
      });
      
      if (response.success) {
        // Add both user and assistant messages
        dispatch({ type: 'ADD_MESSAGE', payload: { sessionId, message: response.userMessage } });
        dispatch({ type: 'ADD_MESSAGE', payload: { sessionId, message: response.assistantMessage } });
        return response.assistantMessage;
      } else {
        throw new Error('Failed to send message');
      }
    } catch (error) {
      dispatch({ type: 'SET_ERROR', payload: { type: 'chat', error: error instanceof Error ? error.message : 'Failed to send message' } });
      throw error;
    } finally {
      dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'chat', loading: false } });
    }
  }, [chatAPI, state.selectedFiles, repository]);

  const updateMessage = useCallback((sessionId: string, messageId: string, updates: Partial<ChatMessage>) => {
    dispatch({ type: 'UPDATE_MESSAGE', payload: { sessionId, messageId, updates } });
  }, []);

  // Message status management
  const setMessageStatus = useCallback((messageId: string, status: MessageStatus) => {
    dispatch({ type: 'SET_MESSAGE_STATUS', payload: { messageId, status } });
  }, []);

  const updateMessageStatus = useCallback((messageId: string, updates: Partial<MessageStatus>) => {
    dispatch({ type: 'UPDATE_MESSAGE_STATUS', payload: { messageId, updates } });
  }, []);

  const getMessageStatus = useCallback((messageId: string): MessageStatus | null => {
    return state.messageStatuses[messageId] || null;
  }, [state.messageStatuses]);

  // Enhanced sendMessage with retry logic
  const sendMessageWithRetry = useCallback(async (sessionId: string, message: string, maxRetries: number = 3, options?: { model?: string; context?: any }): Promise<ChatMessage> => {
    if (!chatAPI) {
      throw new Error('No authentication token available');
    }

    const messageId = generateMessageId();
    
    // Set initial status
    setMessageStatus(messageId, {
      id: messageId,
      status: 'sending',
      retryCount: 0
    });

    let lastError: Error | null = null;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          updateMessageStatus(messageId, { 
            status: 'retrying', 
            retryCount: attempt 
          });
          
          // Exponential backoff: wait 2^attempt seconds
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }

        dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'chat', loading: true } });
        
        console.log(`ChatContext sendMessageWithRetry - Attempt ${attempt + 1}/${maxRetries + 1}`);
        console.log('ChatContext sendMessage - selectedFiles:', state.selectedFiles);
        console.log('ChatContext sendMessage - selectedFiles count:', state.selectedFiles?.length || 0);
        
        // Prepare files with repository information
        const filesWithRepo = state.selectedFiles.map(file => ({
          path: file.path,
          content: file.content,
          branch: file.branch,
          repository_id: repository?.full_name || 'default',
          owner: repository?.owner?.login || 'unknown',
          repo: repository?.name || 'repo',
          url: repository ? `https://github.com/${repository.owner.login}/${repository.name}/blob/${file.branch}/${file.path}` : undefined,
          raw_url: repository ? `https://raw.githubusercontent.com/${repository.owner.login}/${repository.name}/${file.branch}/${file.path}` : undefined
        }));
        
        const response = await chatAPI.sendMessage(sessionId, {
          message,
          model: options?.model || 'gpt-4o-mini', // Use model from options or default
          context: {
            files: filesWithRepo
          },
          repository_id: repository?.full_name || 'default'
        });
        
        if (response.success) {
          // Update status to success and remove it after a delay
          updateMessageStatus(messageId, { status: 'sent' });
          setTimeout(() => {
            dispatch({ type: 'REMOVE_MESSAGE_STATUS', payload: { messageId } });
          }, 3000);
          
          // Add both user and assistant messages
          dispatch({ type: 'ADD_MESSAGE', payload: { sessionId, message: response.userMessage } });
          dispatch({ type: 'ADD_MESSAGE', payload: { sessionId, message: response.assistantMessage } });
          return response.assistantMessage;
        } else {
          throw new Error('Failed to send message');
        }
      } catch (error) {
        console.error(`Attempt ${attempt + 1} failed:`, error);
        lastError = error instanceof Error ? error : new Error('Unknown error');
        
        if (attempt === maxRetries) {
          // Final failure
          updateMessageStatus(messageId, { 
            status: 'failed', 
            error: lastError.message 
          });
          dispatch({ type: 'SET_ERROR', payload: { 
            type: 'chat', 
            error: `Failed to send message after ${maxRetries + 1} attempts: ${lastError.message}` 
          }});
          throw lastError;
        }
      } finally {
        dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'chat', loading: false } });
      }
    }
    
    // This should never be reached, but TypeScript requires it
    throw lastError || new Error('Unknown error occurred');
  }, [chatAPI, state.selectedFiles, repository, generateMessageId, setMessageStatus, updateMessageStatus]);

  // File management
  const setSelectedFiles = useCallback((files: Array<{branch: string, path: string, content: string, contentHash?: string}>) => {
    dispatch({ type: 'SET_SELECTED_FILES', payload: { files } });
  }, []);

  const addSelectedFile = useCallback((file: {branch: string, path: string, content: string, contentHash?: string}) => {
    dispatch({ type: 'ADD_SELECTED_FILE', payload: { file } });
  }, []);

  const removeSelectedFile = useCallback((branch: string, path: string) => {
    dispatch({ type: 'REMOVE_SELECTED_FILE', payload: { branch, path } });
  }, []);

  const getCachedFileContent = useCallback((key: string) => {
    return state.fileCache[key] || null;
  }, [state.fileCache]);

  const cacheFileContent = useCallback((key: string, content: string, hash: string, error?: string) => {
    dispatch({ type: 'CACHE_FILE_CONTENT', payload: { key, content, hash, error } });
  }, []);

  const setFileStructure = useCallback((branch: string, structure: FileSystemItem[]) => {
    dispatch({ type: 'SET_FILE_STRUCTURE', payload: { branch, structure } });
  }, []);

  // Loading and error states
  const setLoadingState = useCallback((type: 'files' | 'chat' | 'sessions', key?: string, loading: boolean = true) => {
    dispatch({ type: 'SET_LOADING_STATE', payload: { type, key, loading } });
  }, []);

  const setError = useCallback((type: 'files' | 'chat' | 'sessions', key?: string, error?: string | null) => {
    dispatch({ type: 'SET_ERROR', payload: { type, key, error: error || null } });
  }, []);

  const clearErrors = useCallback((type: 'files' | 'chat' | 'sessions') => {
    dispatch({ type: 'CLEAR_ERRORS', payload: { type } });
  }, []);

  // Load sessions on mount
  useEffect(() => {
    if (chatAPI && user) {
      dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'sessions', loading: true } });
      chatAPI.getUserSessions(user.id.toString()).then(response => {
        if (response.success) {
          dispatch({ type: 'SET_SESSIONS', payload: { sessions: response.sessions } });
        }
      }).catch(error => {
        dispatch({ type: 'SET_ERROR', payload: { type: 'sessions', error: error instanceof Error ? error.message : 'Failed to load sessions' } });
      }).finally(() => {
        dispatch({ type: 'SET_LOADING_STATE', payload: { type: 'sessions', loading: false } });
      });
    }
  }, [chatAPI, user]);

  // Create initial session if none exists
  useEffect(() => {
    if (state.sessions.length === 0 && repository && !state.loadingStates.sessions) {
      createSession('New Chat');
    }
  }, [state.sessions.length, repository, state.loadingStates.sessions, createSession]);



  const contextValue: ChatContextType = {
    state,
    createSession,
    updateSession,
    deleteSession,
    setActiveSession,
    getActiveSession,
    getSession,
    addMessage,
    sendMessage,
    sendMessageWithRetry,
    updateMessage,
    setMessageStatus,
    updateMessageStatus,
    getMessageStatus,
    setSelectedFiles,
    addSelectedFile,
    removeSelectedFile,
    getCachedFileContent,
    cacheFileContent,
    setFileStructure,
    setLoadingState,
    setError,
    clearErrors,
    generateSessionId,
    generateMessageId,
    getFileCacheKey,
    getFileHash,
  };

  return (
    <ChatContext.Provider value={contextValue}>
      {children}
    </ChatContext.Provider>
  );
};

// Hook to use the chat context
export const useChat = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
