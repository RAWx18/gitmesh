import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContextPanel } from '../ContextPanel';
import { useRepository } from '@/contexts/RepositoryContext';
import { useBranch } from '@/contexts/BranchContext';
import { useChat } from '@/contexts/ChatContext';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

// Mock the contexts
jest.mock('@/contexts/RepositoryContext');
jest.mock('@/contexts/BranchContext');
jest.mock('@/contexts/ChatContext');
jest.mock('@/contexts/AuthContext');
jest.mock('sonner');

// Mock the UI components
jest.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockRepository = {
  name: 'test-repo',
  full_name: 'user/test-repo',
  owner: {
    login: 'user',
  },
  default_branch: 'main',
};

const mockGithubApi = {
  getRepositoryContents: jest.fn(),
  getFileContent: jest.fn(),
};

const mockChatState = {
  selectedFiles: [],
  loadingStates: {
    files: {
      adding: false,
    },
  },
  errors: {
    files: {},
  },
};

const mockChatActions = {
  addSelectedFile: jest.fn(),
  removeSelectedFile: jest.fn(),
  setFileStructure: jest.fn(),
  setLoadingState: jest.fn(),
  setError: jest.fn(),
};

describe('ContextPanel', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    jest.clearAllMocks();
    
    (useRepository as jest.Mock).mockReturnValue({
      repository: mockRepository,
    });
    
    (useBranch as jest.Mock).mockReturnValue({
      selectedBranch: 'main',
    });
    
    (useChat as jest.Mock).mockReturnValue({
      state: mockChatState,
      ...mockChatActions,
    });
    
    (useAuth as jest.Mock).mockReturnValue({
      githubApi: mockGithubApi,
    });
  });

  describe('File Browser Component', () => {
    it('should render the context panel with file browser', () => {
      render(<ContextPanel />);
      
      expect(screen.getByText('Context Files')).toBeInTheDocument();
      expect(screen.getByText('0')).toBeInTheDocument(); // Badge showing 0 files
      expect(screen.getByPlaceholderText('Search files...')).toBeInTheDocument();
    });

    it('should show add files dialog when plus button is clicked', async () => {
      render(<ContextPanel />);
      
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);
      
      expect(screen.getByText('Add Files to Context')).toBeInTheDocument();
      expect(screen.getByText(/Select files from.*to add to your chat context/)).toBeInTheDocument();
    });

    it('should load file structure when repository is available', async () => {
      const mockContents = [
        {
          name: 'README.md',
          type: 'file',
          path: 'README.md',
          size: 1024,
          sha: 'abc123',
          html_url: 'https://github.com/user/test-repo/blob/main/README.md',
        },
        {
          name: 'src',
          type: 'dir',
          path: 'src',
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);

      render(<ContextPanel />);

      await waitFor(() => {
        expect(mockGithubApi.getRepositoryContents).toHaveBeenCalledWith(
          'user',
          'test-repo',
          '',
          'main'
        );
      });
    });
  });

  describe('File Selection and Context Management', () => {
    it('should allow selecting files for context', async () => {
      const mockContents = [
        {
          name: 'test.js',
          type: 'file',
          path: 'test.js',
          size: 512,
          sha: 'def456',
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);
      mockGithubApi.getFileContent.mockResolvedValue('console.log("test");');

      render(<ContextPanel />);

      // Open add files dialog
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByText('test.js')).toBeInTheDocument();
      });

      // Select the file
      const fileCheckbox = screen.getByRole('checkbox');
      await user.click(fileCheckbox);

      // Add files to context
      const addFilesButton = screen.getByRole('button', { name: /Add 1 files/i });
      await user.click(addFilesButton);

      await waitFor(() => {
        expect(mockGithubApi.getFileContent).toHaveBeenCalledWith(
          'user',
          'test-repo',
          'test.js',
          'main'
        );
        expect(mockChatActions.addSelectedFile).toHaveBeenCalledWith({
          branch: 'main',
          path: 'test.js',
          content: 'console.log("test");',
          contentHash: expect.any(String),
        });
      });
    });

    it('should remove files from context', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'test.js',
          content: 'console.log("test");',
          addedAt: new Date(),
          size: 20,
          language: 'JavaScript',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      expect(screen.getByText('test.js')).toBeInTheDocument();

      // Find and click remove button
      const removeButton = screen.getByRole('button', { name: /Remove from context/i });
      await user.click(removeButton);

      expect(mockChatActions.removeSelectedFile).toHaveBeenCalledWith('main', 'test.js');
      expect(toast.success).toHaveBeenCalledWith('Removed test.js from context');
    });

    it('should clear all context files', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'test1.js',
          content: 'test1',
          addedAt: new Date(),
          size: 5,
          language: 'JavaScript',
        },
        {
          branch: 'main',
          path: 'test2.js',
          content: 'test2',
          addedAt: new Date(),
          size: 5,
          language: 'JavaScript',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      const clearButton = screen.getByRole('button', { name: /Clear all context files/i });
      await user.click(clearButton);

      expect(mockChatActions.removeSelectedFile).toHaveBeenCalledTimes(2);
      expect(toast.success).toHaveBeenCalledWith('Cleared all context files');
    });
  });

  describe('Visual Indicators and Metadata', () => {
    it('should show visual indicators for files in context', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'test.js',
          content: 'console.log("test");',
          addedAt: new Date(),
          size: 20,
          language: 'JavaScript',
          isModified: true,
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      // Check for context indicators
      expect(screen.getByText('JavaScript')).toBeInTheDocument();
      expect(screen.getByText('Modified')).toBeInTheDocument();
      expect(screen.getByText('20 B')).toBeInTheDocument();
    });

    it('should display file metadata correctly', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'large-file.py',
          content: 'print("hello")\n'.repeat(100),
          addedAt: new Date('2023-01-01'),
          size: 1400,
          language: 'Python',
          contentHash: 'abc123',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      expect(screen.getByText('Python')).toBeInTheDocument();
      expect(screen.getByText('1.4 KB')).toBeInTheDocument();
      expect(screen.getByText('100 lines')).toBeInTheDocument();
      expect(screen.getByText('main')).toBeInTheDocument();
      expect(screen.getByText('Hash: abc123')).toBeInTheDocument();
    });

    it('should show file preview when preview button is clicked', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'test.js',
          content: 'console.log("Hello, World!");',
          addedAt: new Date(),
          size: 26,
          language: 'JavaScript',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      const previewButton = screen.getByRole('button', { name: /Show preview/i });
      await user.click(previewButton);

      expect(screen.getByText('console.log("Hello, World!");')).toBeInTheDocument();
      expect(screen.getByText('Preview (full)')).toBeInTheDocument();
    });
  });

  describe('Search and Filtering', () => {
    it('should filter files based on search query', async () => {
      const mockContents = [
        {
          name: 'component.tsx',
          type: 'file',
          path: 'src/component.tsx',
          size: 1024,
        },
        {
          name: 'utils.js',
          type: 'file',
          path: 'src/utils.js',
          size: 512,
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);

      render(<ContextPanel />);

      // Open add files dialog
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByText('component.tsx')).toBeInTheDocument();
        expect(screen.getByText('utils.js')).toBeInTheDocument();
      });

      // Search for 'component'
      const searchInput = screen.getByPlaceholderText('Search files...');
      await user.type(searchInput, 'component');

      await waitFor(() => {
        expect(screen.getByText('component.tsx')).toBeInTheDocument();
        expect(screen.queryByText('utils.js')).not.toBeInTheDocument();
      });
    });

    it('should filter files by context status', async () => {
      const contextFiles = [
        {
          branch: 'main',
          path: 'in-context.js',
          content: 'test',
          addedAt: new Date(),
          size: 4,
          language: 'JavaScript',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      const mockContents = [
        {
          name: 'in-context.js',
          type: 'file',
          path: 'in-context.js',
          size: 4,
        },
        {
          name: 'not-in-context.js',
          type: 'file',
          path: 'not-in-context.js',
          size: 10,
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);

      render(<ContextPanel />);

      // Open add files dialog
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByText('in-context.js')).toBeInTheDocument();
        expect(screen.getByText('not-in-context.js')).toBeInTheDocument();
      });

      // Filter to show only files in context
      const filterButton = screen.getByRole('button', { name: /All Files/i });
      await user.click(filterButton);

      const inContextOption = screen.getByText('In Context Only');
      await user.click(inContextOption);

      await waitFor(() => {
        expect(screen.getByText('in-context.js')).toBeInTheDocument();
        expect(screen.queryByText('not-in-context.js')).not.toBeInTheDocument();
      });
    });
  });

  describe('Sorting and View Modes', () => {
    it('should sort files by different criteria', async () => {
      const mockContents = [
        {
          name: 'small.js',
          type: 'file',
          path: 'small.js',
          size: 100,
          last_modified: '2023-01-01T00:00:00Z',
        },
        {
          name: 'large.js',
          type: 'file',
          path: 'large.js',
          size: 1000,
          last_modified: '2023-01-02T00:00:00Z',
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);

      render(<ContextPanel />);

      // Open add files dialog
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByText('small.js')).toBeInTheDocument();
        expect(screen.getByText('large.js')).toBeInTheDocument();
      });

      // Sort by size
      const sortButton = screen.getByRole('button', { name: /Sort: name/i });
      await user.click(sortButton);

      const sizeOption = screen.getByText('Size');
      await user.click(sizeOption);

      // Files should now be sorted by size
      // This would require more complex DOM structure testing
    });

    it('should toggle between tree and list view modes', async () => {
      render(<ContextPanel />);

      // Open add files dialog
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      // Check initial tree view
      expect(screen.getByRole('button', { name: 'Tree' })).toHaveClass('bg-primary');

      // Switch to list view
      const listButton = screen.getByRole('button', { name: 'List' });
      await user.click(listButton);

      expect(listButton).toHaveClass('bg-primary');
    });
  });

  describe('Error Handling', () => {
    it('should handle file loading errors gracefully', async () => {
      mockGithubApi.getRepositoryContents.mockRejectedValue(new Error('API Error'));

      render(<ContextPanel />);

      await waitFor(() => {
        expect(mockChatActions.setError).toHaveBeenCalledWith(
          'files',
          undefined,
          'Failed to load repository files'
        );
      });

      expect(toast.error).toHaveBeenCalledWith('Failed to load repository files');
    });

    it('should handle file content loading errors', async () => {
      const mockContents = [
        {
          name: 'test.js',
          type: 'file',
          path: 'test.js',
          size: 100,
        },
      ];

      mockGithubApi.getRepositoryContents.mockResolvedValue(mockContents);
      mockGithubApi.getFileContent.mockRejectedValue(new Error('Content Error'));

      render(<ContextPanel />);

      // Open add files dialog and select file
      const addButton = screen.getByRole('button', { name: /add files to context/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(screen.getByText('test.js')).toBeInTheDocument();
      });

      const fileCheckbox = screen.getByRole('checkbox');
      await user.click(fileCheckbox);

      const addFilesButton = screen.getByRole('button', { name: /Add 1 files/i });
      await user.click(addFilesButton);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to load test.js');
      });
    });
  });

  describe('Copy Functionality', () => {
    it('should copy file content to clipboard', async () => {
      const mockClipboard = {
        writeText: jest.fn().mockResolvedValue(undefined),
      };
      Object.assign(navigator, { clipboard: mockClipboard });

      const contextFiles = [
        {
          branch: 'main',
          path: 'test.js',
          content: 'console.log("test");',
          addedAt: new Date(),
          size: 20,
          language: 'JavaScript',
        },
      ];

      (useChat as jest.Mock).mockReturnValue({
        state: {
          ...mockChatState,
          selectedFiles: contextFiles,
        },
        ...mockChatActions,
      });

      render(<ContextPanel />);

      const copyButton = screen.getByRole('button', { name: /Copy file content/i });
      await user.click(copyButton);

      expect(mockClipboard.writeText).toHaveBeenCalledWith('console.log("test");');
      expect(toast.success).toHaveBeenCalledWith('File content copied to clipboard');
    });
  });
});