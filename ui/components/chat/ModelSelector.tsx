"use client";

import React, { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  Brain, 
  ChevronDown, 
  Zap, 
  Star, 
  Clock,
  DollarSign,
  Shield,
  Sparkles
} from 'lucide-react';

// Model configuration based on Cosmos MODEL_ALIASES
interface ModelInfo {
  alias: string;
  name: string;
  provider: string;
  tier: 'free' | 'pro' | 'enterprise';
  category: 'fast' | 'balanced' | 'advanced' | 'reasoning';
  description: string;
  features: string[];
  maxTokens?: number;
  costTier: 'low' | 'medium' | 'high';
  speed: 'fast' | 'medium' | 'slow';
}

const AVAILABLE_MODELS: ModelInfo[] = [
  // Fast models
  {
    alias: 'flash',
    name: 'Gemini 2.5 Flash',
    provider: 'Google',
    tier: 'free',
    category: 'fast',
    description: 'Fast and efficient for quick responses',
    features: ['Fast responses', 'Code analysis', 'General chat'],
    maxTokens: 32000,
    costTier: 'low',
    speed: 'fast'
  },
  {
    alias: 'flash-lite',
    name: 'Gemini 2.5 Flash Lite',
    provider: 'Google',
    tier: 'free',
    category: 'fast',
    description: 'Lightweight and ultra-fast',
    features: ['Ultra-fast', 'Basic code help', 'Simple queries'],
    maxTokens: 16000,
    costTier: 'low',
    speed: 'fast'
  },
  {
    alias: 'haiku',
    name: 'Claude 3.5 Haiku',
    provider: 'Anthropic',
    tier: 'free',
    category: 'fast',
    description: 'Quick and concise responses',
    features: ['Fast responses', 'Code review', 'Concise answers'],
    maxTokens: 200000,
    costTier: 'low',
    speed: 'fast'
  },
  
  // Balanced models
  {
    alias: 'gemini',
    name: 'Gemini 2.5 Pro',
    provider: 'Google',
    tier: 'pro',
    category: 'balanced',
    description: 'Balanced performance and capability',
    features: ['Code generation', 'Analysis', 'Problem solving'],
    maxTokens: 128000,
    costTier: 'medium',
    speed: 'medium'
  },
  {
    alias: '4o',
    name: 'GPT-4o',
    provider: 'OpenAI',
    tier: 'pro',
    category: 'balanced',
    description: 'Versatile and capable',
    features: ['Code generation', 'Reasoning', 'Creative tasks'],
    maxTokens: 128000,
    costTier: 'medium',
    speed: 'medium'
  },
  
  // Advanced models
  {
    alias: 'sonnet',
    name: 'Claude Sonnet 4',
    provider: 'Anthropic',
    tier: 'pro',
    category: 'advanced',
    description: 'Advanced reasoning and code understanding',
    features: ['Advanced reasoning', 'Complex code analysis', 'Architecture design'],
    maxTokens: 200000,
    costTier: 'high',
    speed: 'medium'
  },
  {
    alias: 'opus',
    name: 'Claude Opus 4',
    provider: 'Anthropic',
    tier: 'enterprise',
    category: 'advanced',
    description: 'Most capable model for complex tasks',
    features: ['Highest capability', 'Complex reasoning', 'Advanced code generation'],
    maxTokens: 200000,
    costTier: 'high',
    speed: 'slow'
  },
  {
    alias: 'gemini-exp',
    name: 'Gemini 2.5 Pro Experimental',
    provider: 'Google',
    tier: 'enterprise',
    category: 'advanced',
    description: 'Experimental features and capabilities',
    features: ['Experimental features', 'Latest capabilities', 'Advanced reasoning'],
    maxTokens: 128000,
    costTier: 'high',
    speed: 'medium'
  },
  
  // Reasoning models
  {
    alias: 'r1',
    name: 'DeepSeek Reasoner',
    provider: 'DeepSeek',
    tier: 'pro',
    category: 'reasoning',
    description: 'Specialized for complex reasoning tasks',
    features: ['Deep reasoning', 'Problem solving', 'Mathematical analysis'],
    maxTokens: 64000,
    costTier: 'medium',
    speed: 'slow'
  },
  {
    alias: 'deepseek',
    name: 'DeepSeek Chat',
    provider: 'DeepSeek',
    tier: 'pro',
    category: 'balanced',
    description: 'Strong coding and reasoning capabilities',
    features: ['Code generation', 'Reasoning', 'Technical analysis'],
    maxTokens: 64000,
    costTier: 'medium',
    speed: 'medium'
  },
  
  // Specialized models
  {
    alias: 'grok3',
    name: 'Grok 3 Beta',
    provider: 'xAI',
    tier: 'enterprise',
    category: 'advanced',
    description: 'Latest generation reasoning model',
    features: ['Advanced reasoning', 'Real-time data', 'Creative problem solving'],
    maxTokens: 128000,
    costTier: 'high',
    speed: 'medium'
  }
];

interface ModelSelectorProps {
  selectedModel: string;
  onModelChange: (model: string) => void;
  userTier?: 'free' | 'pro' | 'enterprise';
  className?: string;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedModel,
  onModelChange,
  userTier = 'free',
  className
}) => {
  const [isOpen, setIsOpen] = useState(false);

  // Filter models based on user tier
  const availableModels = useMemo(() => {
    const tierHierarchy = { free: 0, pro: 1, enterprise: 2 };
    const userTierLevel = tierHierarchy[userTier];
    
    return AVAILABLE_MODELS.filter(model => {
      const modelTierLevel = tierHierarchy[model.tier];
      return modelTierLevel <= userTierLevel;
    });
  }, [userTier]);

  // Group models by category
  const modelsByCategory = useMemo(() => {
    const categories = {
      fast: availableModels.filter(m => m.category === 'fast'),
      balanced: availableModels.filter(m => m.category === 'balanced'),
      advanced: availableModels.filter(m => m.category === 'advanced'),
      reasoning: availableModels.filter(m => m.category === 'reasoning'),
    };
    
    // Remove empty categories
    return Object.fromEntries(
      Object.entries(categories).filter(([_, models]) => models.length > 0)
    );
  }, [availableModels]);

  // Get current model info
  const currentModel = availableModels.find(m => m.alias === selectedModel) || availableModels[0];

  // Get category icon
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'fast':
        return <Zap size={14} className="text-green-500" />;
      case 'balanced':
        return <Star size={14} className="text-blue-500" />;
      case 'advanced':
        return <Sparkles size={14} className="text-purple-500" />;
      case 'reasoning':
        return <Brain size={14} className="text-orange-500" />;
      default:
        return <Brain size={14} />;
    }
  };

  // Get tier badge color
  const getTierBadgeColor = (tier: string) => {
    switch (tier) {
      case 'free':
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
      case 'pro':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      case 'enterprise':
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200';
    }
  };

  // Get speed indicator
  const getSpeedIndicator = (speed: string) => {
    switch (speed) {
      case 'fast':
        return <div className="flex gap-0.5"><div className="w-1 h-3 bg-green-500 rounded-full"></div><div className="w-1 h-3 bg-green-500 rounded-full"></div><div className="w-1 h-3 bg-green-500 rounded-full"></div></div>;
      case 'medium':
        return <div className="flex gap-0.5"><div className="w-1 h-3 bg-yellow-500 rounded-full"></div><div className="w-1 h-3 bg-yellow-500 rounded-full"></div><div className="w-1 h-3 bg-gray-300 rounded-full"></div></div>;
      case 'slow':
        return <div className="flex gap-0.5"><div className="w-1 h-3 bg-red-500 rounded-full"></div><div className="w-1 h-3 bg-gray-300 rounded-full"></div><div className="w-1 h-3 bg-gray-300 rounded-full"></div></div>;
      default:
        return null;
    }
  };

  // Get cost indicator
  const getCostIndicator = (costTier: string) => {
    switch (costTier) {
      case 'low':
        return <div className="flex gap-0.5"><DollarSign size={10} className="text-green-500" /></div>;
      case 'medium':
        return <div className="flex gap-0.5"><DollarSign size={10} className="text-yellow-500" /><DollarSign size={10} className="text-yellow-500" /></div>;
      case 'high':
        return <div className="flex gap-0.5"><DollarSign size={10} className="text-red-500" /><DollarSign size={10} className="text-red-500" /><DollarSign size={10} className="text-red-500" /></div>;
      default:
        return null;
    }
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(
                "flex items-center gap-2 min-w-[140px] justify-between",
                className
              )}
            >
              <div className="flex items-center gap-2">
                {getCategoryIcon(currentModel?.category || 'balanced')}
                <span className="font-medium">{currentModel?.alias || 'gemini'}</span>
              </div>
              <ChevronDown size={14} className={cn(
                "transition-transform duration-200",
                isOpen && "rotate-180"
              )} />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>
          <div className="space-y-1">
            <p className="font-medium">{currentModel?.name}</p>
            <p className="text-xs text-muted-foreground">{currentModel?.description}</p>
            <div className="flex items-center gap-2 text-xs">
              <span>Speed:</span>
              {getSpeedIndicator(currentModel?.speed || 'medium')}
              <span>Cost:</span>
              {getCostIndicator(currentModel?.costTier || 'medium')}
            </div>
          </div>
        </TooltipContent>
      </Tooltip>
      
      <DropdownMenuContent className="w-80 max-h-96 overflow-y-auto">
        <DropdownMenuLabel className="flex items-center gap-2">
          <Brain size={16} />
          Select AI Model
          <Badge className={cn("text-xs", getTierBadgeColor(userTier))}>
            {userTier}
          </Badge>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        
        {Object.entries(modelsByCategory).map(([category, models]) => (
          <div key={category}>
            <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wide">
              {getCategoryIcon(category)}
              {category} Models
            </DropdownMenuLabel>
            
            {models.map((model) => (
              <DropdownMenuItem
                key={model.alias}
                onClick={() => {
                  onModelChange(model.alias);
                  setIsOpen(false);
                }}
                className={cn(
                  "flex flex-col items-start gap-2 p-3 cursor-pointer",
                  selectedModel === model.alias && "bg-accent"
                )}
              >
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{model.alias}</span>
                    <Badge className={cn("text-xs", getTierBadgeColor(model.tier))}>
                      {model.tier}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    {getSpeedIndicator(model.speed)}
                    {getCostIndicator(model.costTier)}
                  </div>
                </div>
                
                <div className="w-full">
                  <p className="text-sm font-medium text-foreground">{model.name}</p>
                  <p className="text-xs text-muted-foreground mb-2">{model.description}</p>
                  
                  <div className="flex flex-wrap gap-1">
                    {model.features.slice(0, 3).map((feature, index) => (
                      <Badge key={index} variant="outline" className="text-xs px-1 py-0">
                        {feature}
                      </Badge>
                    ))}
                  </div>
                  
                  <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                    <span>{model.provider}</span>
                    {model.maxTokens && (
                      <span>{(model.maxTokens / 1000).toFixed(0)}K tokens</span>
                    )}
                  </div>
                </div>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </div>
        ))}
        
        {userTier !== 'enterprise' && (
          <div className="p-3 bg-muted/50 rounded-lg m-2">
            <div className="flex items-center gap-2 mb-1">
              <Shield size={14} className="text-primary" />
              <span className="text-sm font-medium">Upgrade for more models</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {userTier === 'free' 
                ? 'Upgrade to Pro or Enterprise for advanced models'
                : 'Upgrade to Enterprise for the most powerful models'
              }
            </p>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};