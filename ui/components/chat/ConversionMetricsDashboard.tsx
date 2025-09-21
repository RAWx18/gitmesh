/**
 * Conversion Metrics Dashboard Component
 * 
 * Displays comprehensive metrics and analytics for CLI-to-web conversion
 * effectiveness, including charts, trends, and performance indicators.
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Clock, 
  Users, 
  Target,
  AlertCircle,
  CheckCircle,
  BarChart3,
  PieChart as PieChartIcon,
  Download,
  RefreshCw
} from 'lucide-react';

interface ConversionMetrics {
  daily_conversions: Record<string, number>;
  hourly_conversions: Record<string, number>;
  most_common_commands: Array<{ command: string; count: number }>;
  most_failed_commands: Array<{ command: string; count: number }>;
  users_with_conversions: number;
  sessions_with_conversions: number;
  average_response_time?: number;
  conversion_throughput?: number;
  satisfaction_trend: Array<{ date: string; satisfaction: number }>;
  accuracy_trend: Array<{ date: string; accuracy: number }>;
  error_rate: number;
  system_load_impact?: number;
  command_coverage: Record<string, number>;
  feature_completeness: number;
}

interface ConversionProgress {
  total_operations: number;
  converted_operations: number;
  failed_operations: number;
  pending_operations: number;
  conversion_percentage: number;
  success_rate: number;
  operations_by_type: Record<string, number>;
  success_by_type: Record<string, number>;
  operations_by_priority: Record<string, number>;
  average_user_satisfaction?: number;
  average_accuracy?: number;
  average_conversion_time?: number;
}

interface ConversionMetricsDashboardProps {
  sessionId?: string;
  timeRange?: number; // days
  onExportReport?: () => void;
}

export const ConversionMetricsDashboard: React.FC<ConversionMetricsDashboardProps> = ({
  sessionId,
  timeRange = 30,
  onExportReport
}) => {
  const [metrics, setMetrics] = useState<ConversionMetrics | null>(null);
  const [progress, setProgress] = useState<ConversionProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Fetch metrics data
  const fetchMetrics = async () => {
    try {
      setIsLoading(true);
      
      // Fetch metrics
      const metricsResponse = await fetch(`/api/v1/conversion/metrics?days=${timeRange}`);
      if (!metricsResponse.ok) {
        throw new Error('Failed to fetch metrics');
      }
      const metricsData = await metricsResponse.json();
      setMetrics(metricsData);

      // Fetch progress (global or session-specific)
      const progressUrl = sessionId 
        ? `/api/v1/conversion/sessions/${sessionId}/progress`
        : '/api/v1/conversion/progress/global';
      
      const progressResponse = await fetch(progressUrl);
      if (!progressResponse.ok) {
        throw new Error('Failed to fetch progress');
      }
      const progressData = await progressResponse.json();
      setProgress(progressData);

      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };

  // Prepare chart data
  const prepareDailyData = () => {
    if (!metrics) return [];
    
    return Object.entries(metrics.daily_conversions)
      .map(([date, count]) => ({
        date: new Date(date).toLocaleDateString(),
        conversions: count
      }))
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .slice(-14); // Last 14 days
  };

  const prepareHourlyData = () => {
    if (!metrics) return [];
    
    return Object.entries(metrics.hourly_conversions)
      .map(([hour, count]) => ({
        hour: `${hour}:00`,
        conversions: count
      }))
      .sort((a, b) => parseInt(a.hour) - parseInt(b.hour));
  };

  const prepareTypeData = () => {
    if (!progress) return [];
    
    return Object.entries(progress.operations_by_type).map(([type, count]) => ({
      name: type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()),
      value: count,
      success: progress.success_by_type[type] || 0
    }));
  };

  const preparePriorityData = () => {
    if (!progress) return [];
    
    const colors = {
      critical: '#ef4444',
      high: '#f97316',
      medium: '#eab308',
      low: '#22c55e'
    };
    
    return Object.entries(progress.operations_by_priority).map(([priority, count]) => ({
      name: priority.charAt(0).toUpperCase() + priority.slice(1),
      value: count,
      color: colors[priority as keyof typeof colors] || '#6b7280'
    }));
  };

  // Calculate trend indicators
  const getTrendIndicator = (current: number, previous: number) => {
    if (previous === 0) return null;
    const change = ((current - previous) / previous) * 100;
    return {
      value: Math.abs(change),
      direction: change >= 0 ? 'up' : 'down',
      isPositive: change >= 0
    };
  };

  useEffect(() => {
    fetchMetrics();
    
    // Set up periodic refresh
    const interval = setInterval(fetchMetrics, 30000); // Every 30 seconds
    return () => clearInterval(interval);
  }, [sessionId, timeRange]);

  if (isLoading && !metrics) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <div className="flex items-center space-x-2">
            <Activity className="w-5 h-5 animate-spin" />
            <span>Loading conversion metrics...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-center">
            <AlertCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
            <p className="text-red-600">Error loading metrics: {error}</p>
            <Button onClick={fetchMetrics} className="mt-2">
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Conversion Analytics</h2>
          <p className="text-muted-foreground">
            {sessionId ? 'Session-specific' : 'Global'} conversion metrics and trends
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {lastUpdated && (
            <span className="text-sm text-muted-foreground">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button onClick={fetchMetrics} variant="outline" size="sm">
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          {onExportReport && (
            <Button onClick={onExportReport} variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
          )}
        </div>
      </div>

      {/* Key Metrics Cards */}
      {progress && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Operations</p>
                  <p className="text-2xl font-bold">{progress.total_operations}</p>
                </div>
                <Activity className="w-8 h-8 text-blue-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Success Rate</p>
                  <p className="text-2xl font-bold">{Math.round(progress.success_rate)}%</p>
                </div>
                <CheckCircle className="w-8 h-8 text-green-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Avg. Time</p>
                  <p className="text-2xl font-bold">
                    {progress.average_conversion_time 
                      ? `${progress.average_conversion_time.toFixed(1)}s`
                      : 'N/A'
                    }
                  </p>
                </div>
                <Clock className="w-8 h-8 text-orange-600" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">User Satisfaction</p>
                  <p className="text-2xl font-bold">
                    {progress.average_user_satisfaction 
                      ? `${progress.average_user_satisfaction.toFixed(1)}/5`
                      : 'N/A'
                    }
                  </p>
                </div>
                <Target className="w-8 h-8 text-purple-600" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Charts and Analytics */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
          <TabsTrigger value="commands">Commands</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Daily Conversions */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <BarChart3 className="w-5 h-5" />
                  <span>Daily Conversions</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={prepareDailyData()}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="conversions" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Operation Types */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <PieChartIcon className="w-5 h-5" />
                  <span>Operations by Type</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={prepareTypeData()}
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {prepareTypeData().map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 50%)`} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* Priority Distribution */}
          {progress && Object.keys(progress.operations_by_priority).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Priority Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {preparePriorityData().map((item) => (
                    <div key={item.name} className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div 
                          className="w-3 h-3 rounded-full" 
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="font-medium">{item.name}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm text-muted-foreground">{item.value}</span>
                        <div className="w-20">
                          <Progress 
                            value={(item.value / progress.total_operations) * 100} 
                            className="h-2"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="trends" className="space-y-4">
          {/* Hourly Activity */}
          <Card>
            <CardHeader>
              <CardTitle>Hourly Activity Pattern</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={prepareHourlyData()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" />
                  <YAxis />
                  <Tooltip />
                  <Line 
                    type="monotone" 
                    dataKey="conversions" 
                    stroke="#3b82f6" 
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="commands" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Most Common Commands */}
            {metrics && metrics.most_common_commands.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Most Common Commands</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {metrics.most_common_commands.slice(0, 10).map((cmd, index) => (
                      <div key={index} className="flex items-center justify-between">
                        <code className="text-sm bg-muted px-2 py-1 rounded">
                          {cmd.command}
                        </code>
                        <Badge variant="secondary">{cmd.count}</Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Most Failed Commands */}
            {metrics && metrics.most_failed_commands.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Most Failed Commands</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {metrics.most_failed_commands.slice(0, 10).map((cmd, index) => (
                      <div key={index} className="flex items-center justify-between">
                        <code className="text-sm bg-red-50 text-red-700 px-2 py-1 rounded">
                          {cmd.command}
                        </code>
                        <Badge variant="destructive">{cmd.count}</Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          {/* Performance Metrics */}
          {metrics && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="p-6">
                  <div className="text-center">
                    <p className="text-sm font-medium text-muted-foreground">Error Rate</p>
                    <p className="text-2xl font-bold text-red-600">
                      {metrics.error_rate.toFixed(1)}%
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-6">
                  <div className="text-center">
                    <p className="text-sm font-medium text-muted-foreground">Active Users</p>
                    <p className="text-2xl font-bold text-blue-600">
                      {metrics.users_with_conversions}
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-6">
                  <div className="text-center">
                    <p className="text-sm font-medium text-muted-foreground">Active Sessions</p>
                    <p className="text-2xl font-bold text-green-600">
                      {metrics.sessions_with_conversions}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Feature Completeness */}
          {metrics && (
            <Card>
              <CardHeader>
                <CardTitle>Feature Completeness</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span>Overall Completeness</span>
                    <span className="font-bold">{metrics.feature_completeness.toFixed(1)}%</span>
                  </div>
                  <Progress value={metrics.feature_completeness} className="h-3" />
                  
                  {Object.keys(metrics.command_coverage).length > 0 && (
                    <div className="space-y-2 mt-4">
                      <h4 className="font-medium">Command Coverage</h4>
                      {Object.entries(metrics.command_coverage).map(([command, coverage]) => (
                        <div key={command} className="flex items-center justify-between text-sm">
                          <code className="bg-muted px-1 rounded">{command}</code>
                          <div className="flex items-center space-x-2">
                            <span>{coverage.toFixed(1)}%</span>
                            <div className="w-16">
                              <Progress value={coverage} className="h-1" />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ConversionMetricsDashboard;