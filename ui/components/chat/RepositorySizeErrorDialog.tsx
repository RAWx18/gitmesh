"use client";

import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, ExternalLink, Zap } from 'lucide-react';

interface RepositorySizeErrorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  repositoryName?: string;
  repositorySize?: string;
  maxSize?: string;
  onUpgrade?: () => void;
}

export const RepositorySizeErrorDialog: React.FC<RepositorySizeErrorDialogProps> = ({
  isOpen,
  onClose,
  repositoryName = "this repository",
  repositorySize = "unknown",
  maxSize = "150 MB",
  onUpgrade
}) => {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 rounded-full bg-amber-100 dark:bg-amber-900/20 flex items-center justify-center">
              <AlertTriangle className="w-6 h-6 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <DialogTitle className="text-xl">Repository Too Large</DialogTitle>
              <DialogDescription className="text-base mt-1">
                This repository exceeds the size limit for your current plan
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          {/* Repository Info */}
          <div className="bg-muted/50 rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Repository:</span>
              <Badge variant="outline">{repositoryName}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Size:</span>
              <Badge variant="destructive">{repositorySize}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Current limit:</span>
              <Badge variant="secondary">{maxSize}</Badge>
            </div>
          </div>

          {/* Explanation */}
          <div className="text-sm text-muted-foreground space-y-2">
            <p>
              Large repositories can cause timeouts and performance issues during processing. 
              To ensure a smooth experience, we limit repository sizes based on your plan.
            </p>
          </div>

          {/* Solutions */}
          <div className="space-y-3">
            <h4 className="font-medium text-sm">What you can do:</h4>
            
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                <span>Try a smaller repository or a specific branch with fewer files</span>
              </div>
              
              <div className="flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                <span>Use specific file selection instead of the entire repository</span>
              </div>
              
              {onUpgrade && (
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-primary mt-2 flex-shrink-0" />
                  <span>Upgrade to a higher plan for larger repository support</span>
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button
              variant="outline"
              onClick={onClose}
              className="flex-1"
            >
              Try Another Repository
            </Button>
            
            {onUpgrade && (
              <Button
                onClick={onUpgrade}
                className="flex-1 gap-2"
              >
                <Zap className="w-4 h-4" />
                Upgrade Plan
              </Button>
            )}
          </div>

          {/* Help Link */}
          <div className="text-center pt-2 border-t">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs gap-1"
              onClick={() => window.open('/docs/repository-limits', '_blank')}
            >
              <ExternalLink className="w-3 h-3" />
              Learn more about repository limits
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};