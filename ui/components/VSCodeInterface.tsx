"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { useChat } from '@/contexts/ChatContext';
import { useBranch } from '@/contexts/BranchContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip';
import { 
  FileText, 
  Database, 
  Globe, 
  Upload, 
  Type, 
  GitBranch, 
  ChevronRight, 
  ChevronDown, 
  Folder, 
  File, 
  X, 
  Check, 
  Search, 
  Filter, 
  Settings, 
  Info, 
  AlertCircle,
  Activity,
  Clock,
  Code2,
  MessageSquare,
  Plus,
  Trash2,
  Copy,
  RefreshCw,
  Loader2,
  CheckSquare,
  Square,
  ChevronUp,
  Bot,
  Send,
  User,
  Bot as BotIcon,
  FileCode,
  Hash,
  Clock as ClockIcon,
  Copy as CopyIcon,
  ChevronLeft,
  Maximize2,
  Minimize2,
  Settings as SettingsIcon,
  Filter as FilterIcon,
  List,
  Plus as PlusIcon,
  Menu,
  Sidebar,
  MoreHorizontal,
  Star,
  Users,
  Calendar,
  Target,
  Zap,
  TrendingUp,
  BarChart3,
  GitCommit,
  GitPullRequest,
  Bug,
  Shield,
  Eye,
  Award,
  Flame,
  Home,
  FolderOpen,
  Brain,
  Github,
  Moon,
  Sun,
  LogOut,
  HelpCircle
} from 'lucide-react';
import { toast } from 'sonner';
import { useTheme } from 'next-themes';
import { useRouter, usePathname } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import FileChatInterface from './FileChatInterface';
import CosmosFeaturesPanelRN from './CosmosFeaturesPanelRN';
import { ChatSessionManager } from './ChatSessionManager';
import { ChatInterface } from './chat';

// Tab interface for chat sessions
interface ChatTab {
  id: string;
  title: string;
  isActive: boolean;
  hasUnsavedChanges?: boolean;
  type: 'chat' | 'import' | 'settings' | 'cosmos';
}

// Stats interface for metrics display
interface MetricsData {
  latency: number;
  tokensUsed: number;
  contextSize: number;
  filesLoaded: number;
  messagesCount: number;
  sessionDuration: number;
}

// Navigation item interface
interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  path?: string;
  active: boolean;
  badge?: string | number;
}

// Import source interface
interface ImportSource {
  id: string;
  name: string;
  type: string;
  icon: string;
  description: string;
}

const importSources: ImportSource[] = [
  {
    id: 'csv',
    name: 'CSV File',
    type: 'csv',
    icon: 'FileText',
    description: 'Import structured data from CSV files'
  },
  {
    id: 'control-panel',
    name: 'Control Panel Data',
    type: 'control-panel',
    icon: 'Database',
    description: 'Import data from Manage page controls'
  },
  {
    id: 'url',
    name: 'Web URL',
    type: 'url',
    icon: 'Globe',
    description: 'Import content from websites and articles'
  },
  {
    id: 'file',
    name: 'Document Upload',
    type: 'file',
    icon: 'Upload',
    description: 'Upload documents, PDFs, and other files'
  },
  {
    id: 'text',
    name: 'Text Input',
    type: 'text',
    icon: 'Type',
    description: 'Directly input or paste text content'
  },
  {
    id: 'branch',
    name: 'Branch Import',
    type: 'branch',
    icon: 'GitBranch',
    description: 'Import context from other branches'
  }
];

interface VSCodeInterfaceProps {
  children?: React.ReactNode;
}

export const VSCodeInterface: React.FC<VSCodeInterfaceProps> = ({ children }) => {
  const router = useRouter();
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { user, isAuthenticated, logout } = useAuth();
  const { repository } = useRepository();
  const { state, getActiveSession, createSession } = useChat();
  const { selectedBranch, branchList, setSelectedBranch } = useBranch();

  // State management
  const [tabs, setTabs] = useState<ChatTab[]>([
    { id: 'main', title: 'Chat', isActive: true, type: 'chat' }
  ]);
  const [activeTab, setActiveTab] = useState('main');
  const [activeNavItem, setActiveNavItem] = useState('chat');
  const [activeSection, setActiveSection] = useState('chat');
  const [showImportPanel, setShowImportPanel] = useState(false);
  const [showSessionManager, setShowSessionManager] = useState(false);
  const [metrics, setMetrics] = useState<MetricsData>({
    latency: 0,
    tokensUsed: 0,
    contextSize: 0,
    filesLoaded: 0,
    messagesCount: 0,
    sessionDuration: 0
  });

  // Get active session
  const activeSession = getActiveSession();

  // Update metrics based on current session
  useEffect(() => {
    if (activeSession) {
      setMetrics({
        latency: 120, // Simulated
        tokensUsed: activeSession.messages.length * 50, // Estimated
        contextSize: state.selectedFiles.reduce((acc, file) => acc + (file.content?.length || 0), 0),
        filesLoaded: state.selectedFiles.length,
        messagesCount: activeSession.messages.length,
        sessionDuration: Math.floor((Date.now() - new Date(activeSession.createdAt).getTime()) / 1000 / 60)
      });
    }
  }, [activeSession, state.selectedFiles]);

  // Set active navigation item based on current pathname
  useEffect(() => {
    const pathToNavMap: Record<string, string> = {
      '/contribution': 'about',
      '/contribution/chat': 'chat',
      '/contribution/why': 'why',
      '/contribution/how': 'how',
      '/contribution/contribute': 'contribute',
      '/contribution/manage': 'manage'
    };
    
    const navItem = pathToNavMap[pathname] || 'about';
    setActiveNavItem(navItem);
  }, [pathname]);

  // Navigation items
  const navigationItems = [
    {
      id: 'about',
      name: 'About',
      icon: <Info size={16} />,
      description: 'Learn about repository',
      route: '/contribution'
    },
    {
      id: 'why',
      name: 'Why',
      icon: <Target size={16} />,
      description: 'Why use',
      route: '/contribution/why'
    },
    {
      id: 'how',
      name: 'How',
      icon: <HelpCircle size={16} />,
      description: 'How to use',
      route: '/contribution/how'
    },
    {
      id: 'contribute',
      name: 'Contribute',
      icon: <Users size={16} />,
      description: 'Contribute',
      route: '/contribution/contribute'
    },
    {
      id: 'manage',
      name: 'Manage',
      icon: <Settings size={16} />,
      description: 'Manage your repositories',
      route: '/contribution/manage'
    },
    {
      id: 'chat',
      name: 'Chat',
      icon: <MessageSquare size={16} />,
      description: 'Chat with your repository files',
      route: '/contribution/chat'
    },
    {
      id: 'cosmos',
      name: 'Cosmos AI',
      icon: <Brain size={16} />,
      description: 'Cosmos AI features and capabilities',
      route: '/contribution/chat?tab=cosmos'
    },
  ];

  // Tab management
  const handleTabClick = (tabId: string) => {
    setTabs(tabs.map(tab => ({ ...tab, isActive: tab.id === tabId })));
    setActiveTab(tabId);
  };

  const handleTabClose = (tabId: string) => {
    if (tabs.length > 1) {
      const tabIndex = tabs.findIndex(tab => tab.id === tabId);
      const newTabs = tabs.filter(tab => tab.id !== tabId);
      
      if (tabId === activeTab) {
        const newActiveTab = newTabs[Math.min(tabIndex, newTabs.length - 1)];
        setActiveTab(newActiveTab.id);
        setTabs(newTabs.map(tab => ({ ...tab, isActive: tab.id === newActiveTab.id })));
      } else {
        setTabs(newTabs);
      }
    }
  };

  const handleNewTab = (type: 'chat' | 'settings' = 'chat') => {
    const newTabId = `${type}-${Date.now()}`;
    const newTab: ChatTab = {
      id: newTabId,
      title: type === 'chat' ? `Chat ${tabs.filter(t => t.type === 'chat').length + 1}` : 'Settings',
      isActive: true,
      type: type as 'chat' | 'import' | 'settings'
    };
    
    setTabs([...tabs.map(tab => ({ ...tab, isActive: false })), newTab]);
    setActiveTab(newTabId);
    
    if (type === 'chat') {
      createSession(newTab.title);
    }
  };

  const handleNavigation = (path: string) => {
    if (path) {
      router.push(path);
    }
  };

  // Format bytes to human readable
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  // Format duration
  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins}m`;
  };

  return (
    <TooltipProvider>
      <div className="h-screen w-full bg-background flex flex-col overflow-hidden">
      {/* Fixed Top Navbar */}
      <div className="h-12 bg-card border-b border-border flex items-center justify-between px-4 flex-shrink-0 z-50">
        {/* Left section */}
        <div className="flex items-center gap-4">
          {/* Logo and project name */}
          <div className="flex items-center gap-2">
            <Brain size={18} className="text-primary" />
            <span className="font-semibold text-sm">
              {repository?.name || 'GitMesh'}
            </span>
          </div>

          {/* Branch selector */}
          {branchList.length > 0 && (
            <DropdownMenu>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="flex items-center gap-2 px-2 py-1 h-7 bg-muted rounded text-xs hover:bg-muted/80"
                    >
                      <GitBranch size={12} />
                      <span>{selectedBranch}</span>
                    </Button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Select Branch ({branchList.length} available)</p>
                </TooltipContent>
              </Tooltip>
              <DropdownMenuContent className="bg-background border border-border shadow-lg">
                {branchList.map((branch) => (
                  <DropdownMenuItem
                    key={branch}
                    onClick={() => setSelectedBranch(branch)}
                    className={cn(
                      "flex flex-col items-start gap-1 cursor-pointer hover:bg-accent p-3",
                      selectedBranch === branch && "bg-accent"
                    )}
                  >
                    <div className="flex items-center gap-2 w-full">
                      <div className={cn("w-2 h-2 rounded-full",
                        branch === repository?.default_branch ? 'bg-blue-500' : 'bg-gray-500'
                      )}></div>
                      <span className="text-primary font-medium">{branch}</span>
                      {branch === repository?.default_branch && (
                        <span className="text-xs text-muted-foreground ml-auto">Default</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground pl-4">
                      {branch === repository?.default_branch ? 'Default branch' : ''}
                    </p>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Center section - Tab bar (only show on chat page) */}
        {pathname === '/contribution/chat' ? (
          <div className="flex-1 flex items-center justify-center max-w-2xl">
            <div className="flex items-center bg-muted/30 rounded-lg p-1 overflow-x-auto">
              {tabs.map((tab) => (
              <div
                key={tab.id}
                className={cn(
                  "flex items-center gap-2 px-3 py-1 rounded text-xs cursor-pointer transition-all",
                  tab.isActive 
                    ? "bg-background text-foreground shadow-sm" 
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                )}
                onClick={() => handleTabClick(tab.id)}
              >
                <span>{tab.title}</span>
                {tab.hasUnsavedChanges && (
                  <div className="w-1.5 h-1.5 bg-orange-500 rounded-full" />
                )}
                {tabs.length > 1 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTabClose(tab.id);
                    }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            ))}
            
            {/* Add new tab button */}
            <button
              onClick={() => handleNewTab('chat')}
              className="flex items-center justify-center w-6 h-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              <Plus size={12} />
            </button>
          </div>
        </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{repository?.name || 'GitMesh'}</span>
              {repository && (
                <>
                  <span className="text-muted-foreground">/</span>
                  <span className="text-muted-foreground">
                    {pathname.split('/').pop() || 'about'}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Right section */}
        <div className="flex items-center gap-2">
          {/* Session Info Dropdown (only show on chat page) */}
          {pathname === '/contribution/chat' && activeSession && (
            <DropdownMenu>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="flex items-center gap-2 px-2 py-1 h-7 bg-muted/50 rounded text-xs hover:bg-muted/80"
                    >
                      <Activity size={12} />
                      <span className="hidden sm:inline">{activeSession.title}</span>
                    </Button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Session Info & Quick Actions</p>
                </TooltipContent>
              </Tooltip>
              <DropdownMenuContent className="bg-background border border-border shadow-lg w-80">
                <div className="p-3 space-y-3">
                  {/* Session Details */}
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm">Current Session</h4>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Title:</span>
                        <span>{activeSession.title}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Created:</span>
                        <span>{new Date(activeSession.createdAt).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Duration:</span>
                        <span>{formatDuration(metrics.sessionDuration)}</span>
                      </div>
                    </div>
                  </div>
                  
                  <Separator />
                  
                  {/* Metrics */}
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm">Metrics</h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Latency:</span>
                        <span className="font-mono">{metrics.latency}ms</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Tokens:</span>
                        <span className="font-mono">{metrics.tokensUsed.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Context:</span>
                        <span className="font-mono">{formatBytes(metrics.contextSize)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Messages:</span>
                        <span className="font-mono">{metrics.messagesCount}</span>
                      </div>
                    </div>
                  </div>
                  
                  <Separator />
                  
                  {/* Quick Actions */}
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 text-xs"
                        onClick={() => handleNewTab('chat')}
                      >
                        <Plus size={12} className="mr-1" />
                        New Chat
                      </Button>
                    </div>
                  </div>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <Separator orientation="vertical" className="h-4" />

          {/* Sessions Button (only show on chat page) */}
          {pathname === '/contribution/chat' && (
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSessionManager(true)}
                className="flex items-center gap-2"
              >
                <List size={16} />
                <span className="hidden sm:inline">Sessions</span>
              </Button>
            </div>
          )}

          {/* Theme toggle */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </Button>

          {/* Cosmos AI Button (only show on chat page) */}
          {pathname === '/contribution/chat' && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const newTab = {
                      id: 'cosmos-' + Date.now(),
                      title: 'Cosmos AI',
                      isActive: true,
                      type: 'cosmos' as const
                    };
                    setTabs(prev => [...prev.map(t => ({ ...t, isActive: false })), newTab]);
                    setActiveTab(newTab.id);
                  }}
                  className="flex items-center gap-1 px-2 py-1 h-7 hover:bg-muted/50 text-xs"
                >
                  <Brain size={12} />
                  <span className="hidden sm:inline">Cosmos AI</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Open Cosmos AI Features</p>
              </TooltipContent>
            </Tooltip>
          )}

          {/* User menu */}
          {isAuthenticated ? (
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push('/hub')}
                className="text-xs"
              >
                <Home size={16} className="mr-1" />
                Hub
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push('/')}
            >
              <Github size={16} className="mr-1" />
              Sign In
            </Button>
          )}
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Navigation */}
        <div className="w-16 bg-card border-r border-border flex flex-col">
          <div className="p-2 flex-1">
            {/* Navigation Items */}
            <div className="space-y-2">
              {navigationItems.map((item) => (
                <Tooltip key={item.id}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => {
                        setActiveSection(item.id);
                        router.push(item.route);
                      }}
                      className={cn(
                        "w-12 h-12 flex items-center justify-center rounded-lg text-sm transition-colors",
                        activeSection === item.id 
                          ? "bg-primary/10 text-primary border border-primary/20" 
                          : "hover:bg-muted/50 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {item.icon}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    <p>{item.name}</p>
                    <p className="text-xs text-muted-foreground">{item.description}</p>
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </div>
        </div>

        {/* Main content - Full width */}
        <div className="flex-1 overflow-hidden">
          {children && pathname !== '/contribution/chat' ? (
            children
          ) : (
            <>
              {tabs.find(tab => tab.id === activeTab)?.type === 'chat' && (
                <ChatInterface />
              )}
              
              {tabs.find(tab => tab.id === activeTab)?.type === 'cosmos' && (
                <div className="flex-1 p-6 overflow-auto">
                  <div className="max-w-6xl mx-auto">
                    <div className="mb-6">
                      <h2 className="text-2xl font-bold mb-2">Cosmos AI Features</h2>
                      <p className="text-muted-foreground">
                        Explore and configure advanced AI capabilities for your codebase.
                      </p>
                    </div>
                    <CosmosFeaturesPanelRN />
                  </div>
                </div>
              )}
              
              {tabs.find(tab => tab.id === activeTab)?.type === 'settings' && (
            <div className="flex-1 p-6 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="mb-6">
                  <h2 className="text-2xl font-bold mb-2">Settings</h2>
                  <p className="text-muted-foreground">
                    Configure your GitMesh experience and preferences.
                  </p>
                </div>

                <div className="space-y-6">
                  {/* General Settings */}
                  <Card>
                    <CardHeader>
                      <CardTitle>General</CardTitle>
                      <CardDescription>Basic application settings</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="theme">Theme</Label>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        >
                          {theme === 'dark' ? <Moon size={16} className="mr-2" /> : <Sun size={16} className="mr-2" />}
                          {theme === 'dark' ? 'Dark' : 'Light'}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Chat Settings */}
                  <Card>
                    <CardHeader>
                      <CardTitle>Chat</CardTitle>
                      <CardDescription>Customize your chat experience</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <Label>Auto-scroll to new messages</Label>
                        <Button variant="outline" size="sm">Enabled</Button>
                      </div>
                      <div className="flex items-center justify-between">
                        <Label>Show timestamps</Label>
                        <Button variant="outline" size="sm">Enabled</Button>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Repository Settings */}
                  <Card>
                    <CardHeader>
                      <CardTitle>Repository</CardTitle>
                      <CardDescription>Current repository configuration</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <Label>Repository</Label>
                        <p className="text-sm text-muted-foreground mt-1">
                          {repository?.full_name || 'No repository selected'}
                        </p>
                      </div>
                      <div>
                        <Label>Default Branch</Label>
                        <p className="text-sm text-muted-foreground mt-1">
                          {repository?.default_branch || selectedBranch || 'Unknown'}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}
            </>
          )}
        </div>
      </div>

      {/* Enhanced Status bar (only show on chat page) */}
      {pathname === '/contribution/chat' && (
        <div className="h-6 bg-card border-t border-border flex items-center justify-between px-4 text-xs text-muted-foreground flex-shrink-0">
          <div className="flex items-center gap-4">
            <span>GitMesh</span>
            {repository && (
              <span>{repository.full_name}</span>
            )}
            <span>Branch: {selectedBranch}</span>
            {activeSession && (
              <>
                <Separator orientation="vertical" className="h-3" />
                <span>Session: {activeSession.title}</span>
                <span>Duration: {formatDuration(metrics.sessionDuration)}</span>
              </>
            )}
          </div>
          
          <div className="flex items-center gap-4">
            <span>Files: {state.selectedFiles.length}</span>
            <span>Messages: {metrics.messagesCount}</span>
            <span>Context: {formatBytes(metrics.contextSize)}</span>
            <span>Latency: {metrics.latency}ms</span>
            <span>Tokens: {metrics.tokensUsed.toLocaleString()}</span>
          </div>
        </div>
      )}

      {/* Session Manager Modal (only on chat page) */}
      {pathname === '/contribution/chat' && (
        <ChatSessionManager 
          isOpen={showSessionManager}
          onClose={() => setShowSessionManager(false)}
        />
      )}
      </div>
    </TooltipProvider>
  );
};

export default VSCodeInterface;
