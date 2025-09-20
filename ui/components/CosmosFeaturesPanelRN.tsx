"use client";

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { 
  Brain, 
  Code2, 
  FileText, 
  GitBranch, 
  Search, 
  Zap, 
  Shield, 
  TrendingUp,
  Settings,
  Bot,
  Terminal,
  Sparkles,
  Layers,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Info,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Play,
  Square
} from 'lucide-react';

interface CosmosFeaturesPanelProps {
  className?: string;
}

interface CosmosFeature {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  status: 'available' | 'active' | 'processing';
  category: 'analysis' | 'generation' | 'optimization' | 'integration';
}

const cosmosFeatures: CosmosFeature[] = [
  {
    id: 'repo-analysis',
    title: 'Repository Analysis',
    description: 'Comprehensive analysis of your entire codebase structure',
    icon: <FileText size={16} />,
    status: 'available',
    category: 'analysis'
  },
  {
    id: 'code-review',
    title: 'AI Code Review',
    description: 'Automated code review with suggestions and improvements',
    icon: <Search size={16} />,
    status: 'available',
    category: 'analysis'
  },
  {
    id: 'code-generation',
    title: 'Code Generation',
    description: 'Generate code snippets, functions, and entire files',
    icon: <Code2 size={16} />,
    status: 'available',
    category: 'generation'
  },
  {
    id: 'refactoring',
    title: 'Smart Refactoring',
    description: 'Intelligent code refactoring and optimization suggestions',
    icon: <TrendingUp size={16} />,
    status: 'available',
    category: 'optimization'
  },
  {
    id: 'documentation',
    title: 'Auto Documentation',
    description: 'Generate comprehensive documentation for your code',
    icon: <Layers size={16} />,
    status: 'available',
    category: 'generation'
  },
  {
    id: 'testing',
    title: 'Test Generation',
    description: 'Create unit tests and integration tests automatically',
    icon: <CheckCircle size={16} />,
    status: 'available',
    category: 'generation'
  },
  {
    id: 'debugging',
    title: 'AI Debugging',
    description: 'Intelligent debugging assistance and error resolution',
    icon: <AlertCircle size={16} />,
    status: 'available',
    category: 'analysis'
  },
  {
    id: 'performance',
    title: 'Performance Analysis',
    description: 'Analyze and optimize code performance bottlenecks',
    icon: <Zap size={16} />,
    status: 'available',
    category: 'optimization'
  }
];

const categoryIcons = {
  analysis: <Search size={20} />,
  generation: <Sparkles size={20} />,
  optimization: <TrendingUp size={20} />,
  integration: <GitBranch size={20} />
};

const categoryColors = {
  analysis: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  generation: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
  optimization: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  integration: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300'
};

export default function CosmosFeaturesPanelRN({ className }: CosmosFeaturesPanelProps) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>('analysis');
  const [activeFeatures, setActiveFeatures] = useState<Set<string>>(new Set());

  const categories = [...new Set(cosmosFeatures.map(f => f.category))];
  
  const toggleFeature = (featureId: string) => {
    const newActiveFeatures = new Set(activeFeatures);
    if (newActiveFeatures.has(featureId)) {
      newActiveFeatures.delete(featureId);
    } else {
      newActiveFeatures.add(featureId);
    }
    setActiveFeatures(newActiveFeatures);
  };

  const getStatusIcon = (status: CosmosFeature['status']) => {
    switch (status) {
      case 'available':
        return <Play size={14} className="text-green-500" />;
      case 'active':
        return <CheckCircle size={14} className="text-blue-500" />;
      case 'processing':
        return <RefreshCw size={14} className="text-orange-500 animate-spin" />;
      default:
        return <Square size={14} className="text-gray-400" />;
    }
  };

  return (
    <div className={`w-full max-w-4xl ${className}`}>
      {/* Header */}
      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <CardTitle className="text-xl">Cosmos AI Features</CardTitle>
              <CardDescription>
                Advanced AI capabilities for code analysis, generation, and optimization
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex justify-between text-sm mb-2">
                <span>AI Model: GPT-4</span>
                <span className="text-green-600">Connected</span>
              </div>
              <Progress value={85} className="h-2" />
            </div>
            <Badge variant="secondary" className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
              Ready
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Feature Categories */}
      <div className="space-y-4">
        {categories.map((category) => {
          const categoryFeatures = cosmosFeatures.filter(f => f.category === category);
          const isExpanded = expandedCategory === category;

          return (
            <Card key={category} className="overflow-hidden">
              <CardHeader 
                className="cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => setExpandedCategory(isExpanded ? null : category)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${categoryColors[category as keyof typeof categoryColors]}`}>
                      {categoryIcons[category as keyof typeof categoryIcons]}
                    </div>
                    <div>
                      <CardTitle className="text-lg capitalize">{category}</CardTitle>
                      <CardDescription>
                        {categoryFeatures.length} features available
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">
                      {categoryFeatures.filter(f => activeFeatures.has(f.id)).length} active
                    </Badge>
                    {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>
              </CardHeader>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <CardContent className="pt-0">
                      <Separator className="mb-4" />
                      <div className="grid gap-4 md:grid-cols-2">
                        {categoryFeatures.map((feature) => {
                          const isActive = activeFeatures.has(feature.id);
                          
                          return (
                            <motion.div
                              key={feature.id}
                              layout
                              className={`p-4 rounded-lg border transition-all cursor-pointer hover:shadow-md ${
                                isActive 
                                  ? 'border-primary bg-primary/5' 
                                  : 'border-border hover:border-primary/50'
                              }`}
                              onClick={() => toggleFeature(feature.id)}
                            >
                              <div className="flex items-start gap-3">
                                <div className="mt-1">
                                  {getStatusIcon(feature.status)}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    {feature.icon}
                                    <h4 className="font-medium text-sm">{feature.title}</h4>
                                  </div>
                                  <p className="text-xs text-muted-foreground leading-relaxed">
                                    {feature.description}
                                  </p>
                                  {isActive && (
                                    <div className="mt-2 flex items-center gap-2">
                                      <Badge className="text-xs">
                                        Active
                                      </Badge>
                                      <Button 
                                        size="sm" 
                                        variant="outline" 
                                        className="h-6 text-xs"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          // Handle feature configuration
                                        }}
                                      >
                                        Configure
                                      </Button>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </motion.div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>
          );
        })}
      </div>

      {/* Quick Actions */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-lg">Quick Actions</CardTitle>
          <CardDescription>
            Common Cosmos AI operations you can perform
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Button variant="outline" className="h-auto p-3 flex flex-col gap-2">
              <FileText size={20} />
              <span className="text-xs">Analyze Repo</span>
            </Button>
            <Button variant="outline" className="h-auto p-3 flex flex-col gap-2">
              <Code2 size={20} />
              <span className="text-xs">Generate Code</span>
            </Button>
            <Button variant="outline" className="h-auto p-3 flex flex-col gap-2">
              <Search size={20} />
              <span className="text-xs">Review Code</span>
            </Button>
            <Button variant="outline" className="h-auto p-3 flex flex-col gap-2">
              <Zap size={20} />
              <span className="text-xs">Optimize</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Model Selection */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-lg">AI Model Configuration</CardTitle>
          <CardDescription>
            Choose and configure your preferred AI models
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Primary Model</label>
              <Button variant="outline" className="w-full justify-between">
                GPT-4 <ChevronDown size={16} />
              </Button>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Backup Model</label>
              <Button variant="outline" className="w-full justify-between">
                Claude-3 <ChevronDown size={16} />
              </Button>
            </div>
          </div>
          <div className="mt-4 p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-2 text-sm">
              <Info size={16} className="text-blue-500" />
              <span>Available models: GPT-4, GPT-3.5, Claude-3, Gemini, and more</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
