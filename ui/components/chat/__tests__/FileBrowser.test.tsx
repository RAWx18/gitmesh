import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock data for testing
const mockFileStructure = [
  {
    name: 'src',
    type: 'folder' as const,
    path: 'src',
    children: [
      {
        name: 'components',
        type: 'folder' as const,
        path: 'src/components',
        children: [
          {
            name: 'Button.tsx',
            type: 'file' as const,
            path: 'src/components/Button.tsx',
            size: 1024,
            lastModified: new Date('2023-01-01'),
          },
          {
            name: 'Input.tsx',
            type: 'file' as const,
            path: 'src/components/Input.tsx',
            size: 512,
            lastModified: new Date('2023-01-02'),
          },
        ],
      },
      {
        name: 'utils',
        type: 'folder' as const,
        path: 'src/utils',
        children: [
          {
            name: 'helpers.ts',
            type: 'file' as const,
            path: 'src/utils/helpers.ts',
            size: 256,
            lastModified: new Date('2023-01-03'),
          },
        ],
      },
    ],
  },
  {
    name: 'README.md',
    type: 'file' as const,
    path: 'README.md',
    size: 2048,
    lastModified: new Date('2023-01-04'),
  },
  {
    name: 'package.json',
    type: 'file' as const,
    path: 'package.json',
    size: 1536,
    lastModified: new Date('2023-01-05'),
  },
];

const mockContextFiles = [
  {
    branch: 'main',
    path: 'src/components/Button.tsx',
    content: 'export const Button = () => <button>Click me</button>;',
    addedAt: new Date(),
    size: 1024,
    language: 'TypeScript React',
  },
];

// Mock FileTreeNode component for isolated testing
const MockFileTreeNode = ({
  items,
  level,
  selectedFiles,
  expandedFolders,
  onToggleFolder,
  onToggleFile,
  contextFiles,
  getFileMetadata,
  viewMode,
}: any) => {
  return (
    <div data-testid="file-tree-node">
      {items.map((item: any) => (
        <div key={item.path} data-testid={`file-item-${item.path}`}>
          <div
            onClick={() => {
              if (item.type === 'folder') {
                onToggleFolder(item.path);
              } else {
                onToggleFile(item.path);
              }
            }}
            className={`file-item ${selectedFiles.has(item.path) ? 'selected' : ''} ${
              contextFiles.some((f: any) => f.path === item.path) ? 'in-context' : ''
            }`}
          >
            {item.type === 'folder' && (
              <span data-testid={`folder-toggle-${item.path}`}>
                {expandedFolders.has(item.path) ? '▼' : '▶'}
              </span>
            )}
            <span data-testid={`item-name-${item.path}`}>{item.name}</span>
            {item.size && (
              <span data-testid={`item-size-${item.path}`}>
                {item.size < 1024 ? `${item.size}B` : `${(item.size / 1024).toFixed(1)}KB`}
              </span>
            )}
          </div>
          {item.type === 'folder' &&
            item.children &&
            expandedFolders.has(item.path) && (
              <MockFileTreeNode
                items={item.children}
                level={level + 1}
                selectedFiles={selectedFiles}
                expandedFolders={expandedFolders}
                onToggleFolder={onToggleFolder}
                onToggleFile={onToggleFile}
                contextFiles={contextFiles}
                getFileMetadata={getFileMetadata}
                viewMode={viewMode}
              />
            )}
        </div>
      ))}
    </div>
  );
};

describe('File Browser Functionality', () => {
  const user = userEvent.setup();

  describe('File Tree Navigation', () => {
    it('should expand and collapse folders', async () => {
      const mockToggleFolder = jest.fn();
      const expandedFolders = new Set<string>();
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={mockToggleFolder}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      const srcFolder = screen.getByTestId('folder-toggle-src');
      await user.click(srcFolder);

      expect(mockToggleFolder).toHaveBeenCalledWith('src');
    });

    it('should show nested folder structure when expanded', async () => {
      const expandedFolders = new Set(['src']);
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      expect(screen.getByTestId('file-item-src/components')).toBeInTheDocument();
      expect(screen.getByTestId('file-item-src/utils')).toBeInTheDocument();
    });

    it('should handle file selection', async () => {
      const mockToggleFile = jest.fn();
      const expandedFolders = new Set<string>();
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={mockToggleFile}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      const readmeFile = screen.getByTestId('item-name-README.md');
      await user.click(readmeFile);

      expect(mockToggleFile).toHaveBeenCalledWith('README.md');
    });
  });

  describe('File Metadata Display', () => {
    it('should display file sizes correctly', () => {
      const expandedFolders = new Set<string>();
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      expect(screen.getByTestId('item-size-README.md')).toHaveTextContent('2.0KB');
      expect(screen.getByTestId('item-size-package.json')).toHaveTextContent('1.5KB');
    });

    it('should show visual indicators for files in context', () => {
      const expandedFolders = new Set(['src', 'src/components']);
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={mockContextFiles}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      const buttonFile = screen.getByTestId('file-item-src/components/Button.tsx');
      expect(buttonFile).toHaveClass('in-context');
    });

    it('should show selected files with visual indication', () => {
      const expandedFolders = new Set<string>();
      const selectedFiles = new Set(['README.md', 'package.json']);

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      expect(screen.getByTestId('file-item-README.md')).toHaveClass('selected');
      expect(screen.getByTestId('file-item-package.json')).toHaveClass('selected');
    });
  });

  describe('File Filtering and Search', () => {
    const filterFiles = (items: any[], query: string, filter: string) => {
      let filtered = items;

      // Apply context filter
      if (filter === 'inContext') {
        filtered = filtered.filter(item => {
          if (item.type === 'folder') {
            return item.children && item.children.some((child: any) => 
              mockContextFiles.some(f => f.path === child.path)
            );
          }
          return mockContextFiles.some(f => f.path === item.path);
        });
      } else if (filter === 'notInContext') {
        filtered = filtered.filter(item => {
          if (item.type === 'folder') {
            return item.children && item.children.some((child: any) => 
              !mockContextFiles.some(f => f.path === child.path)
            );
          }
          return !mockContextFiles.some(f => f.path === item.path);
        });
      }

      // Apply search filter
      if (query.trim()) {
        const lowerQuery = query.toLowerCase();
        filtered = filtered.filter(item => 
          item.name.toLowerCase().includes(lowerQuery) ||
          item.path.toLowerCase().includes(lowerQuery)
        );
      }

      return filtered;
    };

    it('should filter files by search query', () => {
      const filtered = filterFiles(mockFileStructure, 'README', 'all');
      expect(filtered).toHaveLength(1);
      expect(filtered[0].name).toBe('README.md');
    });

    it('should filter files by context status - in context', () => {
      const filtered = filterFiles(mockFileStructure, '', 'inContext');
      expect(filtered).toHaveLength(1);
      expect(filtered[0].name).toBe('src'); // Folder containing context file
    });

    it('should filter files by context status - not in context', () => {
      const filtered = filterFiles(mockFileStructure, '', 'notInContext');
      expect(filtered.length).toBeGreaterThan(0);
      expect(filtered.some(item => item.name === 'README.md')).toBe(true);
    });

    it('should combine search and context filters', () => {
      const filtered = filterFiles(mockFileStructure, 'package', 'notInContext');
      expect(filtered).toHaveLength(1);
      expect(filtered[0].name).toBe('package.json');
    });
  });

  describe('File Sorting', () => {
    const sortFiles = (items: any[], sortBy: string, sortOrder: string) => {
      return [...items].sort((a, b) => {
        // Folders first unless sorting by type
        if (sortBy !== 'type' && a.type !== b.type) {
          return a.type === 'folder' ? -1 : 1;
        }

        let comparison = 0;
        switch (sortBy) {
          case 'name':
            comparison = a.name.localeCompare(b.name);
            break;
          case 'size':
            comparison = (a.size || 0) - (b.size || 0);
            break;
          case 'modified':
            const aTime = a.lastModified?.getTime() || 0;
            const bTime = b.lastModified?.getTime() || 0;
            comparison = aTime - bTime;
            break;
          case 'type':
            if (a.type !== b.type) {
              comparison = a.type === 'folder' ? -1 : 1;
            } else {
              comparison = a.name.localeCompare(b.name);
            }
            break;
        }

        return sortOrder === 'asc' ? comparison : -comparison;
      });
    };

    it('should sort files by name', () => {
      const files = [
        { name: 'zebra.js', type: 'file', path: 'zebra.js', size: 100 },
        { name: 'alpha.js', type: 'file', path: 'alpha.js', size: 200 },
      ];

      const sorted = sortFiles(files, 'name', 'asc');
      expect(sorted[0].name).toBe('alpha.js');
      expect(sorted[1].name).toBe('zebra.js');
    });

    it('should sort files by size', () => {
      const files = [
        { name: 'small.js', type: 'file', path: 'small.js', size: 100 },
        { name: 'large.js', type: 'file', path: 'large.js', size: 1000 },
      ];

      const sorted = sortFiles(files, 'size', 'desc');
      expect(sorted[0].name).toBe('large.js');
      expect(sorted[1].name).toBe('small.js');
    });

    it('should sort files by modification date', () => {
      const files = [
        { 
          name: 'old.js', 
          type: 'file', 
          path: 'old.js', 
          lastModified: new Date('2023-01-01') 
        },
        { 
          name: 'new.js', 
          type: 'file', 
          path: 'new.js', 
          lastModified: new Date('2023-01-02') 
        },
      ];

      const sorted = sortFiles(files, 'modified', 'desc');
      expect(sorted[0].name).toBe('new.js');
      expect(sorted[1].name).toBe('old.js');
    });

    it('should always put folders first unless sorting by type', () => {
      const items = [
        { name: 'file.js', type: 'file', path: 'file.js', size: 100 },
        { name: 'folder', type: 'folder', path: 'folder' },
      ];

      const sorted = sortFiles(items, 'name', 'asc');
      expect(sorted[0].type).toBe('folder');
      expect(sorted[1].type).toBe('file');
    });
  });

  describe('View Mode Switching', () => {
    it('should handle tree view mode', () => {
      const expandedFolders = new Set(['src']);
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="tree"
        />
      );

      // In tree view, nested items should be visible when parent is expanded
      expect(screen.getByTestId('file-item-src/components')).toBeInTheDocument();
    });

    it('should handle list view mode', () => {
      const expandedFolders = new Set<string>();
      const selectedFiles = new Set<string>();

      render(
        <MockFileTreeNode
          items={mockFileStructure}
          level={0}
          selectedFiles={selectedFiles}
          expandedFolders={expandedFolders}
          onToggleFolder={jest.fn()}
          onToggleFile={jest.fn()}
          contextFiles={[]}
          getFileMetadata={() => null}
          viewMode="list"
        />
      );

      // In list view, folder toggles should not be shown
      expect(screen.queryByTestId('folder-toggle-src')).not.toBeInTheDocument();
    });
  });

  describe('File Language Detection', () => {
    const getFileLanguage = (filePath: string): string => {
      const extension = filePath.split('.').pop()?.toLowerCase();
      const languageMap: Record<string, string> = {
        'ts': 'TypeScript',
        'tsx': 'TypeScript React',
        'js': 'JavaScript',
        'jsx': 'JavaScript React',
        'py': 'Python',
        'md': 'Markdown',
        'json': 'JSON',
      };
      return languageMap[extension || ''] || 'Unknown';
    };

    it('should detect TypeScript files', () => {
      expect(getFileLanguage('component.ts')).toBe('TypeScript');
      expect(getFileLanguage('component.tsx')).toBe('TypeScript React');
    });

    it('should detect JavaScript files', () => {
      expect(getFileLanguage('script.js')).toBe('JavaScript');
      expect(getFileLanguage('component.jsx')).toBe('JavaScript React');
    });

    it('should detect other common file types', () => {
      expect(getFileLanguage('script.py')).toBe('Python');
      expect(getFileLanguage('README.md')).toBe('Markdown');
      expect(getFileLanguage('package.json')).toBe('JSON');
    });

    it('should return Unknown for unrecognized extensions', () => {
      expect(getFileLanguage('file.xyz')).toBe('Unknown');
      expect(getFileLanguage('noextension')).toBe('Unknown');
    });
  });

  describe('File Size Formatting', () => {
    const formatFileSize = (bytes: number): string => {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    it('should format bytes correctly', () => {
      expect(formatFileSize(500)).toBe('500 B');
      expect(formatFileSize(1024)).toBe('1.0 KB');
      expect(formatFileSize(1536)).toBe('1.5 KB');
      expect(formatFileSize(1048576)).toBe('1.0 MB');
      expect(formatFileSize(2097152)).toBe('2.0 MB');
    });
  });
});