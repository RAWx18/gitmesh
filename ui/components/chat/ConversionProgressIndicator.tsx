/**
 * Conversion Progress Indicator Component
 * 
 * Displays real-time progress of CLI-to-web conversion operations
 * with visual indicators and detailed metrics.
 */

import React, { useState, useEffect } from 'react';
import { Progress } from '../ui/progress';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';
import { Button } from '../ui/button';
import { 
  CheckCircle, 
  XCircle, 
  Clock, 
  AlertCircle, 
  TrendingUp, 
  Activity,
  ChevronDown,
  ChevronUp,
  Info
} from 'lucide-react';

interface ConversionOperation {
  id: string;
  operation_type: string;
  original_command: string;
  converted_equivalent?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked' | 'skipped';
  priority: 'low' | 'medium' | 'high' | 'critical';
  created_at: string;
  started_at?: string;
  completed_at?: string;
  conversion_notes?: string;
  error_message?: string;
  performance_impact?: number;
}

interface ConversionProgress {
  session_id?: string;
  total_operations: number;
  converted_operations: number;
  failed_operations: number;
  pending_operations: number;
  conversion_percentage: number;
  success_rate: number;
  last_conversion?: string;
  average_conversion_time?: number;
  operations_by_type: Record<string, number>;
  success_by_type: Record<string, number>;
  operations_by_priority: Record<string, number>;
  recent_operations: string[];
  average_user_satisfaction?: number;
  average_accuracy?: number;
}

interface ConversionProgressIndicatorProps {
  sessionId: string;
  onOperationClick?: (operation: ConversionOperation) => void;
  showDetails?: boolean;
  compact?: boolean;
}

export const ConversionProgressIndicator: React.FC<ConversionProgressIndicatorProps> = ({
  sessionId,
  onOperationClick,
  showDetails = true,
  compact = false
}) => {
  const [progress, setProgress] = useState<ConversionProgress | null>(null);
  const [recentOperations, setRecentOperations] = useState<ConversionOperation[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch conversion progress
  const fetchProgress = async () => {
    try {
      const response = await fetch(`/api/v1/conversion/sessions/${sessionId}/progress`);
      if (!response.ok) {
        throw new Error('Failed to fetch conversion progress');
      }
      const data = await response.json();
      setProgress(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // Fetch recent operations
  const fetchRecentOperations = async () => {
    try {
      const response = await fetch(`/api/v1/conversion/sessions/${sessionId}/operations?page=1&page_size=10`);
      if (!response.ok) {
        throw new Error('Failed to fetch recent operations');
      }
      const data = await response.json();
      setRecentOperations(data.operations || []);
    } catch (err) {
      console.error('Error fetching recent operations:', err);
    }
  };

  // Initial load and periodic updates
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      await Promise.all([fetchProgress(), fetchRecentOperations()]);
      setIsLoading(false);
    };

    loadData();

    // Set up periodic updates
    const interval = setInterval(() => {
      fetchProgress();
      fetchRecentOperations();
    }, 5000); // Update every 5 seconds

    return () => clearInterval(interval);
  }, [sessionId]);

  // Get status color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      case 'in_progress':
        return 'text-blue-600';
      case 'pending':
        return 'text-yellow-600';
      case 'blocked':
        return 'text-orange-600';
      default:
        return 'text-gray-600';
    }
  };

  // Get status icon
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-600" />;
      case 'in_progress':
        return <Activity className="w-4 h-4 text-blue-600 animate-pulse" />;
      case 'pending':
        return <Clock className="w-4 h-4 text-yellow-600" />;
      case 'blocked':
        return <AlertCircle className="w-4 h-4 text-orange-600" />;
      default:
        return <Info className="w-4 h-4 text-gray-600" />;
    }
  };

  // Get priority badge variant
  const getPriorityVariant = (priority: string) => {
    switch (priority) {
      case 'critical':
        return 'destructive';
      case 'high':
        return 'default';
      case 'medium':
        return 'secondary';
      case 'low':
        return 'outline';
      default:
        return 'secondary';
    }
  };

  if (isLoading) {
    return (
      <Card className={compact ? "p-2" : ""}>
        <CardContent className={compact ? "p-2" : ""}>
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 animate-spin" />
            <span className="text-sm text-muted-foreground">Loading conversion progress...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={compact ? "p-2" : ""}>
        <CardContent className={compact ? "p-2" : ""}>
          <div className="flex items-center space-x-2 text-red-600">
            <XCircle className="w-4 h-4" />
            <span className="text-sm">Error: {error}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!progress) {
    return null;
  }

  // Compact view
  if (compact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center space-x-2 p-2 bg-muted/50 rounded-md">
              <TrendingUp className="w-4 h-4 text-blue-600" />
              <Progress value={progress.conversion_percentage} className="w-20 h-2" />
              <span className="text-xs font-medium">
                {Math.round(progress.conversion_percentage)}%
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <div className="text-sm">
              <div>Conversion Progress: {Math.round(progress.conversion_percentage)}%</div>
              <div>Operations: {progress.converted_operations}/{progress.total_operations}</div>
              <div>Success Rate: {Math.round(progress.success_rate)}%</div>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center space-x-2">
            <TrendingUp className="w-5 h-5 text-blue-600" />
            <span>Shell-to-Web Conversion</span>
          </CardTitle>
          {showDetails && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Main Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Overall Progress</span>
            <span className="font-medium">{Math.round(progress.conversion_percentage)}%</span>
          </div>
          <Progress value={progress.conversion_percentage} className="h-2" />
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="text-center">
            <div className="font-semibold text-green-600">{progress.converted_operations}</div>
            <div className="text-muted-foreground">Converted</div>
          </div>
          <div className="text-center">
            <div className="font-semibold text-red-600">{progress.failed_operations}</div>
            <div className="text-muted-foreground">Failed</div>
          </div>
          <div className="text-center">
            <div className="font-semibold text-yellow-600">{progress.pending_operations}</div>
            <div className="text-muted-foreground">Pending</div>
          </div>
          <div className="text-center">
            <div className="font-semibold text-blue-600">{Math.round(progress.success_rate)}%</div>
            <div className="text-muted-foreground">Success Rate</div>
          </div>
        </div>

        {/* Expanded Details */}
        {isExpanded && showDetails && (
          <div className="space-y-4 pt-4 border-t">
            {/* Recent Operations */}
            {recentOperations.length > 0 && (
              <div>
                <h4 className="font-medium mb-2">Recent Operations</h4>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {recentOperations.slice(0, 5).map((operation) => (
                    <div
                      key={operation.id}
                      className={`flex items-center justify-between p-2 rounded-md bg-muted/50 ${
                        onOperationClick ? 'cursor-pointer hover:bg-muted' : ''
                      }`}
                      onClick={() => onOperationClick?.(operation)}
                    >
                      <div className="flex items-center space-x-2 flex-1 min-w-0">
                        {getStatusIcon(operation.status)}
                        <code className="text-xs bg-background px-1 rounded truncate">
                          {operation.original_command}
                        </code>
                        <Badge variant={getPriorityVariant(operation.priority)} className="text-xs">
                          {operation.priority}
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground ml-2">
                        {new Date(operation.created_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Operation Types Breakdown */}
            {Object.keys(progress.operations_by_type).length > 0 && (
              <div>
                <h4 className="font-medium mb-2">Operations by Type</h4>
                <div className="space-y-1">
                  {Object.entries(progress.operations_by_type).map(([type, count]) => {
                    const successCount = progress.success_by_type[type] || 0;
                    const successRate = count > 0 ? (successCount / count) * 100 : 0;
                    
                    return (
                      <div key={type} className="flex items-center justify-between text-sm">
                        <span className="capitalize">{type.replace('_', ' ')}</span>
                        <div className="flex items-center space-x-2">
                          <span className="text-muted-foreground">
                            {successCount}/{count}
                          </span>
                          <div className="w-16">
                            <Progress value={successRate} className="h-1" />
                          </div>
                          <span className="w-10 text-right font-medium">
                            {Math.round(successRate)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Performance Metrics */}
            {(progress.average_conversion_time || progress.average_user_satisfaction || progress.average_accuracy) && (
              <div>
                <h4 className="font-medium mb-2">Performance Metrics</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  {progress.average_conversion_time && (
                    <div className="text-center">
                      <div className="font-semibold">
                        {progress.average_conversion_time.toFixed(1)}s
                      </div>
                      <div className="text-muted-foreground">Avg. Time</div>
                    </div>
                  )}
                  {progress.average_user_satisfaction && (
                    <div className="text-center">
                      <div className="font-semibold">
                        {progress.average_user_satisfaction.toFixed(1)}/5
                      </div>
                      <div className="text-muted-foreground">Satisfaction</div>
                    </div>
                  )}
                  {progress.average_accuracy && (
                    <div className="text-center">
                      <div className="font-semibold">
                        {Math.round(progress.average_accuracy * 100)}%
                      </div>
                      <div className="text-muted-foreground">Accuracy</div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ConversionProgressIndicator;