"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { useChat } from '@/contexts/ChatContext';
import { useBranch } from '@/contexts/BranchContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Send,
  Bot,
  User,
  Loader2,
  AlertCircle,
  CheckCircle,
  Copy,
  Clock,
  FileText,
} from 'lucide-react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { ModelSelector } from './ModelSelector';
import { RepositorySelector } from './RepositorySelector';
import { ContextPanel } from './ContextPanel';
import { RepositorySizeErrorDialog } from './RepositorySizeErrorDialog';
import { ChatMessage } from '@/lib/chat-api';

interface ChatInterfaceProps {
  className?: string;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ className }) => {
  const { user, isAuthenticated } = useAuth();
  const { repository } = useRepository();
  const { selectedBranch } = useBranch();
  const {
    state,
    getActiveSession,
    sendMessageWithRetry,
    createSession,
    getMessageStatus,
    setRepositorySizeError
  } = useChat();

  // Local state
  const [message, setMessage] = useState('');
  const [selectedModel, setSelectedModel] = useState('gemini');
  const [isExpanded, setIsExpanded] = useState(false);
  const [showContextPanel, setShowContextPanel] = useState(true);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Get active session
  const activeSession = getActiveSession();

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.messages, scrollToBottom]);

  // Auto-resize textarea
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [message, adjustTextareaHeight]);

  // Handle message submission
  const handleSendMessage = useCallback(async () => {
    if (!message.trim() || !activeSession || state.loadingStates.chat) {
      return;
    }

    if (!isAuthenticated) {
      toast.error('Please sign in to send messages');
      return;
    }

    const messageText = message.trim();
    setMessage('');

    try {
      await sendMessageWithRetry(activeSession.id, messageText, 3, {
        model: selectedModel,
        context: {
          files: state.selectedFiles
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      toast.error('Failed to send message. Please try again.');
    }
  }, [message, activeSession, state.loadingStates.chat, state.selectedFiles, isAuthenticated, sendMessageWithRetry, selectedModel]);

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage]);

  // Copy message content
  const handleCopyMessage = useCallback((content: string) => {
    navigator.clipboard.writeText(content);
    toast.success('Message copied to clipboard');
  }, []);

  // Create initial session if none exists
  useEffect(() => {
    if (!activeSession && repository && isAuthenticated && !state.loadingStates.sessions) {
      createSession(`Chat with ${repository.name}`);
    }
  }, [activeSession, repository, isAuthenticated, state.loadingStates.sessions, createSession]);

  if (!isAuthenticated) {
    return (
      <div className={cn("flex items-center justify-center h-full", className)}>
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto">
            <Bot size={24} className="text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-2">Sign in to start chatting</h3>
            <p className="text-muted-foreground">
              Connect your GitHub account to chat with your repositories
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className={cn("flex items-center justify-center h-full", className)}>
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto">
            <FileText size={24} className="text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-2">Select a repository</h3>
            <p className="text-muted-foreground">
              Choose a repository to start chatting with your codebase
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex h-full bg-background", className)}>
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat Header */}
        <div className="flex items-center justify-between p-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Bot size={20} className="text-primary" />
              <h2 className="font-semibold">
                {activeSession?.title || 'New Chat'}
              </h2>
            </div>
            {activeSession && activeSession.messages && (
              <Badge variant="outline" className="text-xs">
                {activeSession.messages.length} messages
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Model Selector */}
            <ModelSelector
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
            />

            {/* Repository Selector */}
            <RepositorySelector />

            <Separator orientation="vertical" className="h-6" />
            {/* Context Panel Toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowContextPanel(!showContextPanel)}
              className="flex items-center gap-2"
            >
              {showContextPanel ? (
                <span className="text-lg font-bold">&gt;</span>
              ) : (
                <span className="text-lg font-bold">&lt;</span>
              )}
            </Button>
          </div>
        </div>

        {/* Messages Area */}
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-6 max-w-4xl mx-auto">
            {!activeSession?.messages || activeSession.messages.length === 0 ? (
              <div className="text-center py-12">
                <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Bot size={24} className="text-primary" />
                </div>
                <h3 className="text-lg font-semibold mb-2">Start a conversation</h3>
                <p className="text-muted-foreground mb-4">
                  Ask questions about your code, request explanations, or get help with development tasks.
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMessage("Explain the main functionality of this repository")}
                  >
                    Explain this repo
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMessage("What are the main components and their relationships?")}
                  >
                    Show architecture
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMessage("Help me understand the codebase structure")}
                  >
                    Code structure
                  </Button>
                </div>
              </div>
            ) : (
              <AnimatePresence>
                {activeSession.messages.map((msg) => (
                  <ChatMessageComponent
                    key={msg.id}
                    message={msg}
                    onCopy={handleCopyMessage}
                    messageStatus={getMessageStatus(msg.id)}
                  />
                ))}
              </AnimatePresence>
            )}

            {/* Loading indicator */}
            {state.loadingStates.chat && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-3"
              >
                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                  <Bot size={16} />
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Thinking...</span>
                </div>
              </motion.div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Message Input */}
        <div className="p-4 border-t border-border bg-card/50">
          <div className="max-w-4xl mx-auto">
            {/* Context Files Preview */}
            {state.selectedFiles.length > 0 && (
              <div className="mb-3 p-2 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <FileText size={14} />
                  <span>Context files ({state.selectedFiles.length})</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {state.selectedFiles.slice(0, 3).map((file, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {file.path.split('/').pop()}
                    </Badge>
                  ))}
                  {state.selectedFiles.length > 3 && (
                    <Badge variant="secondary" className="text-xs">
                      +{state.selectedFiles.length - 3} more
                    </Badge>
                  )}
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <div className="flex-1 relative">
                <Textarea
                  ref={textareaRef}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    state.selectedFiles.length > 0
                      ? "Ask about your selected files..."
                      : "Ask about your repository..."
                  }
                  className="min-h-[44px] max-h-[120px] resize-none pr-12"
                  disabled={state.loadingStates.chat}
                />
                <div className="absolute right-2 bottom-2 text-xs text-muted-foreground">
                  {message.length}/4000
                </div>
              </div>
              <Button
                onClick={handleSendMessage}
                disabled={!message.trim() || state.loadingStates.chat}
                size="sm"
                className="h-[44px] px-4"
              >
                {state.loadingStates.chat ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Send size={16} />
                )}
              </Button>
            </div>

            <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-4">
                <span>Press Enter to send, Shift+Enter for new line</span>
                {selectedModel && (
                  <span>Model: {selectedModel}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {repository && (
                  <span>{repository.name}/{selectedBranch}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Context Panel */}
      {showContextPanel && (
        <div className="w-80 border-l border-border bg-card/30">
          <ContextPanel />
        </div>
      )}

      {/* Repository Size Error Dialog */}
      <RepositorySizeErrorDialog
        isOpen={!!state.repositorySizeError}
        onClose={() => setRepositorySizeError(null)}
        repositoryName={state.repositorySizeError?.repositoryName}
        repositorySize={state.repositorySizeError?.repositorySize}
        maxSize={state.repositorySizeError?.maxSize}
        onUpgrade={() => {
          // Handle upgrade logic here
          window.open('/pricing', '_blank');
        }}
      />
    </div>
  );
};

// Chat Message Component
interface ChatMessageComponentProps {
  message: ChatMessage;
  onCopy: (content: string) => void;
  messageStatus?: {
    id: string;
    status: 'sending' | 'sent' | 'failed' | 'retrying';
    retryCount: number;
    error?: string;
  } | null;
}

const ChatMessageComponent: React.FC<ChatMessageComponentProps> = ({
  message,
  onCopy,
  messageStatus
}) => {
  const isUser = message.type === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "flex gap-4",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      <div className={cn(
        "flex gap-3 max-w-[80%]",
        isUser && "flex-row-reverse"
      )}>
        {/* Avatar */}
        <div className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        )}>
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        {/* Message Content */}
        <div className={cn(
          "rounded-lg p-4 relative group",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        )}>
          {/* Message Header */}
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {isUser ? 'You' : 'Assistant'}
              </span>
              {message.model && (
                <Badge
                  variant={isUser ? "secondary" : "outline"}
                  className="text-xs px-1 py-0 h-4"
                >
                  {message.model}
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-2 text-xs opacity-70">
              <Clock size={12} />
              <span>
                {new Date(message.timestamp).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </span>

              {/* Message Status */}
              {messageStatus && (
                <MessageStatusIndicator {...messageStatus} />
              )}

              {/* Copy Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onCopy(message.content)}
                className="opacity-0 group-hover:opacity-100 transition-opacity h-6 w-6 p-0"
              >
                <Copy size={12} />
              </Button>
            </div>
          </div>

          {/* Message Content */}
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                h1: ({ children }) => <h1 className="text-xl font-bold mb-2">{children}</h1>,
                h2: ({ children }) => <h2 className="text-lg font-semibold mb-2">{children}</h2>,
                h3: ({ children }) => <h3 className="text-base font-medium mb-1">{children}</h3>,
                p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
                ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
                code: ({ children, className }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="bg-muted px-1 py-0.5 rounded text-sm font-mono">
                      {children}
                    </code>
                  ) : (
                    <code className={className}>{children}</code>
                  );
                },
                pre: ({ children }) => (
                  <pre className="bg-muted p-3 rounded-lg overflow-x-auto text-sm">
                    {children}
                  </pre>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>

          {/* Files Referenced */}
          {message.files && message.files.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border/20">
              <div className="text-xs text-muted-foreground mb-1">
                Referenced files:
              </div>
              <div className="flex flex-wrap gap-1">
                {message.files.map((file, index) => (
                  <Badge key={index} variant="outline" className="text-xs">
                    {file.split('/').pop()}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

// Message Status Indicator Component
const MessageStatusIndicator: React.FC<{
  status: 'sending' | 'sent' | 'failed' | 'retrying';
  retryCount?: number;
  error?: string;
}> = ({ status, retryCount = 0, error }) => {
  switch (status) {
    case 'sending':
      return (
        <div className="flex items-center gap-1 text-xs">
          <Loader2 size={10} className="animate-spin" />
          <span>Sending...</span>
        </div>
      );
    case 'retrying':
      return (
        <div className="flex items-center gap-1 text-xs text-amber-600">
          <Loader2 size={10} className="animate-spin" />
          <span>Retrying ({retryCount}/3)...</span>
        </div>
      );
    case 'failed':
      return (
        <div className="flex items-center gap-1 text-xs text-red-500" title={error}>
          <AlertCircle size={10} />
          <span>Failed</span>
        </div>
      );
    case 'sent':
      return (
        <div className="flex items-center gap-1 text-xs text-green-600">
          <CheckCircle size={10} />
          <span>Sent</span>
        </div>
      );
    default:
      return null;
  }
};