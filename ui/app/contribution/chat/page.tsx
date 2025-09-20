"use client";

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import { useRepository } from '@/contexts/RepositoryContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  MessageSquare, 
  FileText, 
  Code2, 
  GitBranch, 
  Settings,
  Bot,
  Zap,
  Sparkles,
  BookOpen,
  Search,
  Filter,
  Users,
  Activity,
  TrendingUp,
  Shield,
  Globe,
  Database,
  Upload,
  Type,
  ChevronRight,
  ChevronLeft,
  Maximize2,
  Minimize2
} from 'lucide-react';
import { VSCodeInterface } from '@/components/VSCodeInterface';
import { ChatProvider } from '@/contexts/ChatContext';
import { toast } from 'sonner';

interface ImportedData {
  type: 'branch' | 'file' | 'text' | 'control-panel';
  branch?: string;
  branches?: string[];
  files?: Array<{branch: string, path: string, content?: string}>;
  fileStructures?: Record<string, any[]>;
  dataTypes?: string[];
  title?: string;
  content?: string;
}

export default function ChatPage() {
  const { token, user } = useAuth();
  const { repository } = useRepository();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [importedData, setImportedData] = useState<ImportedData | null>(null);

  // Demo repository setup for testing
  React.useEffect(() => {
    if (!repository && token === 'demo-token') {
      const demoRepository = {
        name: 'beetle-app',
        full_name: 'demo-user/beetle-app',
        description: 'A demo repository for testing Beetle features',
        owner: {
          login: 'demo-user',
          avatar_url: 'https://github.com/github.png',
          type: 'User'
        },
        language: 'TypeScript',
        stargazers_count: 42,
        forks_count: 8,
        html_url: 'https://github.com/demo-user/beetle-app',
        clone_url: 'https://github.com/demo-user/beetle-app.git',
        default_branch: '',
        created_at: '2023-01-01T00:00:00Z',
        updated_at: new Date().toISOString(),
        private: false,
        type: 'owned' as const
      };
      // Note: You'll need to implement setRepository in your RepositoryContext
    }
  }, [repository, token]);

  // Load imported data from localStorage on component mount
  React.useEffect(() => {
    const savedImports = localStorage.getItem('beetle_imported_data');
    if (savedImports) {
      try {
        const imports = JSON.parse(savedImports);
        if (imports.length > 0) {
          // Get the most recent import
          const latestImport = imports[imports.length - 1];
          setImportedData(latestImport.data);
        }
      } catch (error) {
        console.error('Error loading imported data:', error);
      }
    }
  }, []);

  const features = [
    {
      icon: <Code2 size={20} />,
      title: "Advanced Code Analysis",
      description: "Cosmos AI provides deep code understanding and intelligent responses"
    },
    {
      icon: <FileText size={20} />,
      title: "Repository-Wide Context",
      description: "Analyze entire codebases with Cosmos's powerful context engine"
    },
    {
      icon: <GitBranch size={20} />,
      title: "Multi-Model Support",
      description: "Choose from multiple AI models including GPT-4, Claude, and more"
    },
    {
      icon: <Search size={20} />,
      title: "Semantic Code Search",
      description: "Find code patterns and structures using natural language queries"
    },
    {
      icon: <Bot size={20} />,
      title: "Cosmos AI Integration",
      description: "Powered by Cosmos - the most advanced AI coding assistant"
    },
    {
      icon: <Zap size={20} />,
      title: "Real-time Processing",
      description: "Get instant responses with streaming AI capabilities"
    },
    {
      icon: <Shield size={20} />,
      title: "Cloud-Based Security",
      description: "Enterprise-grade security with cloud-based processing"
    },
    {
      icon: <TrendingUp size={20} />,
      title: "Code Improvements",
      description: "Get suggestions for code optimization and best practices"
    }
  ];

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted/20">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <MessageSquare size={24} className="text-primary" />
            </div>
            <CardTitle>Connect to Start Chatting</CardTitle>
            <CardDescription>
              Sign in with your GitHub account to start chatting with your codebase
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" size="lg">
              Connect GitHub Account
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!repository) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted/20">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <GitBranch size={24} className="text-primary" />
            </div>
            <CardTitle>Select a Repository</CardTitle>
            <CardDescription>
              Choose a repository to start chatting with your codebase
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" size="lg">
              Browse Repositories
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <ChatProvider>
      <div className="fixed inset-0 bg-background">
        <VSCodeInterface />
      </div>
    </ChatProvider>
  );
}
