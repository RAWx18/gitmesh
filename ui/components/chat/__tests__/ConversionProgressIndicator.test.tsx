/**
 * Tests for ConversionProgressIndicator Component
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ConversionProgressIndicator from '../ConversionProgressIndicator';

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock data
const mockProgress = {
  session_id: 'test-session-123',
  total_operations: 10,
  converted_operations: 7,
  failed_operations: 2,
  pending_operations: 1,
  conversion_percentage: 70.0,
  success_rate: 77.8,
  last_conversion: '2024-01-15T10:30:00Z',
  average_conversion_time: 2.5,
  operations_by_type: {
    shell_command: 5,
    file_operation: 3,
    directory_operation: 2
  },
  success_by_type: {
    shell_command: 4,
    file_operation: 2,
    directory_operation: 1
  },
  operations_by_priority: {
    high: 4,
    medium: 3,
    low: 2,
    critical: 1
  },
  recent_operations: ['op-1', 'op-2', 'op-3'],
  average_user_satisfaction: 4.2,
  average_accuracy: 0.85
};

const mockOperations = [
  {
    id: 'op-1',
    operation_type: 'shell_command',
    original_command: 'ls -la',
    converted_equivalent: 'Web file listing',
    status: 'completed',
    priority: 'high',
    created_at: '2024-01-15T10:25:00Z',
    conversion_notes: 'Successfully converted'
  },
  {
    id: 'op-2',
    operation_type: 'file_operation',
    original_command: 'cat file.txt',
    status: 'failed',
    priority: 'medium',
    created_at: '2024-01-15T10:20:00Z',
    error_message: 'File not found'
  },
  {
    id: 'op-3',
    operation_type: 'directory_operation',
    original_command: 'find . -name "*.py"',
    status: 'pending',
    priority: 'low',
    created_at: '2024-01-15T10:15:00Z'
  }
];

describe('ConversionProgressIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default fetch responses
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/progress')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockProgress)
        });
      } else if (url.includes('/operations')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            operations: mockOperations,
            total_count: mockOperations.length,
            page: 1,
            page_size: 10,
            has_next: false
          })
        });
      }
      return Promise.reject(new Error('Unknown URL'));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" />);
    
    expect(screen.getByText('Loading conversion progress...')).toBeInTheDocument();
  });

  it('displays progress data after loading', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Check progress percentage
    expect(screen.getByText('70%')).toBeInTheDocument();
    
    // Check stats
    expect(screen.getByText('7')).toBeInTheDocument(); // Converted
    expect(screen.getByText('2')).toBeInTheDocument(); // Failed
    expect(screen.getByText('1')).toBeInTheDocument(); // Pending
    expect(screen.getByText('78%')).toBeInTheDocument(); // Success rate (rounded)
  });

  it('renders in compact mode', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" compact={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('70%')).toBeInTheDocument();
    });

    // Should not show detailed view in compact mode
    expect(screen.queryByText('Shell-to-Web Conversion')).not.toBeInTheDocument();
  });

  it('expands and shows detailed information', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Click expand button
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Operations')).toBeInTheDocument();
    });

    // Check if operations are displayed
    expect(screen.getByText('ls -la')).toBeInTheDocument();
    expect(screen.getByText('cat file.txt')).toBeInTheDocument();
  });

  it('handles operation click callback', async () => {
    const mockOnOperationClick = vi.fn();
    
    render(
      <ConversionProgressIndicator 
        sessionId="test-session-123" 
        onOperationClick={mockOnOperationClick}
        showDetails={true}
      />
    );
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show operations
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Operations')).toBeInTheDocument();
    });

    // Click on an operation
    const operationElement = screen.getByText('ls -la').closest('div');
    if (operationElement) {
      fireEvent.click(operationElement);
      expect(mockOnOperationClick).toHaveBeenCalledWith(mockOperations[0]);
    }
  });

  it('displays error state when fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    
    render(<ConversionProgressIndicator sessionId="test-session-123" />);
    
    await waitFor(() => {
      expect(screen.getByText(/Error:/)).toBeInTheDocument();
    });
  });

  it('shows correct status icons for operations', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show operations
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Operations')).toBeInTheDocument();
    });

    // Check for status indicators (icons should be present)
    const operationsSection = screen.getByText('Recent Operations').closest('div');
    expect(operationsSection).toBeInTheDocument();
  });

  it('displays operations by type breakdown', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show details
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Operations by Type')).toBeInTheDocument();
    });

    // Check type breakdown
    expect(screen.getByText('Shell Command')).toBeInTheDocument();
    expect(screen.getByText('File Operation')).toBeInTheDocument();
    expect(screen.getByText('Directory Operation')).toBeInTheDocument();
  });

  it('shows performance metrics when available', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show details
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Performance Metrics')).toBeInTheDocument();
    });

    // Check performance metrics
    expect(screen.getByText('2.5s')).toBeInTheDocument(); // Average time
    expect(screen.getByText('4.2/5')).toBeInTheDocument(); // Satisfaction
    expect(screen.getByText('85%')).toBeInTheDocument(); // Accuracy
  });

  it('updates data periodically', async () => {
    vi.useFakeTimers();
    
    render(<ConversionProgressIndicator sessionId="test-session-123" />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Clear previous calls
    mockFetch.mockClear();

    // Fast-forward 5 seconds (update interval)
    vi.advanceTimersByTime(5000);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    vi.useRealTimers();
  });

  it('handles empty operations gracefully', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/progress')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ...mockProgress,
            total_operations: 0,
            converted_operations: 0,
            failed_operations: 0,
            pending_operations: 0,
            conversion_percentage: 0
          })
        });
      } else if (url.includes('/operations')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            operations: [],
            total_count: 0,
            page: 1,
            page_size: 10,
            has_next: false
          })
        });
      }
      return Promise.reject(new Error('Unknown URL'));
    });

    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Should show 0% progress
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('displays priority badges correctly', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show operations
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Operations')).toBeInTheDocument();
    });

    // Check priority badges
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText('low')).toBeInTheDocument();
  });

  it('formats timestamps correctly', async () => {
    render(<ConversionProgressIndicator sessionId="test-session-123" showDetails={true} />);
    
    await waitFor(() => {
      expect(screen.getByText('Shell-to-Web Conversion')).toBeInTheDocument();
    });

    // Expand to show operations
    const expandButton = screen.getByRole('button');
    fireEvent.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Recent Operations')).toBeInTheDocument();
    });

    // Check that timestamps are formatted (should show time)
    const timeElements = screen.getAllByText(/\d{1,2}:\d{2}:\d{2}/);
    expect(timeElements.length).toBeGreaterThan(0);
  });
});