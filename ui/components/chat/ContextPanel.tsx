"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { useRepository } from '@/contexts/RepositoryContext';
import { useBranch } from '@/contexts/BranchContext';
import { useChat } from '@/contexts/ChatContext';
import { useAuth } from '@/contexts/AuthContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  FileText, 
  Folder, 
  FolderOpen,
  Plus, 
  X, 
  Search,
  Filter,
  Code,
  File,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertCircle,
  CheckSquare,
  Square,
  Eye,
  EyeOff,
  Trash2,
  RefreshCw,
  Download,
  Clock,
  Hash,
  Check,
  GitBranch,
  Clock as ClockIcon,
  Copy as CopyIcon
} from 'lucide-react';
import { toast } from 'sonner';

interface FileSystemItem {
  name: string;
  type: 'file' | 'folder';
  path: string;
  size?: number;
  children?: FileSystemItem[];
  expanded?: boolean;
  selected?: boolean;
  lastModified?: Date;
  sha?: string;
  url?: string;
}

interface ContextFile {
  branch: string;
  path: string;
  content: string;
  contentHash?: string;
  addedAt: Date;
  size: number;
  language?: string;
  lastModified?: Date;
  isModified?: boolean;
  sha?: string;
}

interface FileMetadata {
  size: number;
  language: string;
  lastModified: Date;
  sha: string;
  isInContext: boolean;
  isModified: boolean;
  lineCount: number;
  encoding: string;
}

interface ContextPanelProps {
  className?: string;
}

export const ContextPanel: React.FC<ContextPanelProps> = ({ className }) => {
  const { repository } = useRepository();
  const { selectedBranch } = useBranch();
  const { githubApi } = useAuth();
  const { 
    state, 
    addSelectedFile, 
    removeSelectedFile, 
    setFileStructure,
    setLoadingState,
    setError 
  } = useChat();

  // Local state
  const [isAddFileDialogOpen, setIsAddFileDialogOpen] = useState(false);
  const [fileStructure, setLocalFileStructure] = useState<FileSystemItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [showPreview, setShowPreview] = useState<string | null>(null);
  const [fileFilter, setFileFilter] = useState<'all' | 'inContext' | 'notInContext'>('all');
  const [sortBy, setSortBy] = useState<'name' | 'size' | 'modified' | 'type'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [viewMode, setViewMode] = useState<'tree' | 'list'>('tree');
  const [fileMetadataCache, setFileMetadataCache] = useState<Map<string, FileMetadata>>(new Map());

  // Get context files from chat state
  const contextFiles: ContextFile[] = state.selectedFiles.map(file => ({
    ...file,
    addedAt: new Date(), // This should come from the actual data
    size: file.content.length,
    language: getFileLanguage(file.path)
  }));

  // Load file structure when repository or branch changes
  useEffect(() => {
    if (repository && selectedBranch && githubApi) {
      loadFileStructure();
    }
  }, [repository, selectedBranch, githubApi]);

  // Load file structure from GitHub API
  const loadFileStructure = async () => {
    if (!repository || !selectedBranch || !githubApi) return;

    setIsLoadingFiles(true);
    setError('files', undefined, null);
    
    try {
      // Get repository contents
      const contents = await githubApi.getRepositoryContents(
        repository.owner.login,
        repository.name,
        '',
        selectedBranch
      );
      
      const structure = await buildFileStructure(contents);
      setLocalFileStructure(structure);
      setFileStructure(selectedBranch, structure);
    } catch (error) {
      console.error('Failed to load file structure:', error);
      setError('files', undefined, 'Failed to load repository files');
      toast.error('Failed to load repository files');
    } finally {
      setIsLoadingFiles(false);
    }
  };

  // Build hierarchical file structure
  const buildFileStructure = async (contents: any[]): Promise<FileSystemItem[]> => {
    const items: FileSystemItem[] = [];
    
    for (const item of contents) {
      if (item.type === 'file') {
        const fileItem: FileSystemItem = {
          name: item.name,
          type: 'file',
          path: item.path,
          size: item.size,
          lastModified: item.last_modified ? new Date(item.last_modified) : new Date(),
          sha: item.sha,
          url: item.html_url
        };
        
        // Cache file metadata
        const metadata: FileMetadata = {
          size: item.size || 0,
          language: getFileLanguage(item.path),
          lastModified: fileItem.lastModified!,
          sha: item.sha || '',
          isInContext: contextFiles.some(f => f.path === item.path),
          isModified: false, // TODO: Implement modification detection
          lineCount: 0, // Will be calculated when content is loaded
          encoding: 'utf-8'
        };
        
        setFileMetadataCache(prev => new Map(prev.set(item.path, metadata)));
        items.push(fileItem);
      } else if (item.type === 'dir') {
        try {
          // Load folder contents recursively (with depth limit)
          const folderContents = await githubApi!.getRepositoryContents(
            repository!.owner.login,
            repository!.name,
            item.path,
            selectedBranch
          );
          
          const children = await buildFileStructure(folderContents);
          items.push({
            name: item.name,
            type: 'folder',
            path: item.path,
            children,
            expanded: false,
            lastModified: item.last_modified ? new Date(item.last_modified) : new Date()
          });
        } catch (error) {
          console.warn(`Failed to load folder ${item.path}:`, error);
          items.push({
            name: item.name,
            type: 'folder',
            path: item.path,
            children: [],
            expanded: false,
            lastModified: new Date()
          });
        }
      }
    }
    
    return sortFileItems(items);
  };

  // Sort file items based on current sort settings
  const sortFileItems = (items: FileSystemItem[]): FileSystemItem[] => {
    return items.sort((a, b) => {
      // Always put folders first unless sorting by type
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
        default:
          comparison = a.name.localeCompare(b.name);
      }
      
      return sortOrder === 'asc' ? comparison : -comparison;
    });
  };

  // Get file language from extension
  const getFileLanguage = (filePath: string): string => {
    const extension = filePath.split('.').pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
      'ts': 'TypeScript',
      'tsx': 'TypeScript React',
      'js': 'JavaScript',
      'jsx': 'JavaScript React',
      'py': 'Python',
      'java': 'Java',
      'cpp': 'C++',
      'c': 'C',
      'cs': 'C#',
      'php': 'PHP',
      'rb': 'Ruby',
      'go': 'Go',
      'rs': 'Rust',
      'swift': 'Swift',
      'kt': 'Kotlin',
      'scala': 'Scala',
      'html': 'HTML',
      'css': 'CSS',
      'scss': 'SCSS',
      'sass': 'Sass',
      'less': 'Less',
      'json': 'JSON',
      'xml': 'XML',
      'yaml': 'YAML',
      'yml': 'YAML',
      'md': 'Markdown',
      'txt': 'Text',
      'sql': 'SQL',
      'sh': 'Shell',
      'bash': 'Bash',
      'zsh': 'Zsh',
      'fish': 'Fish'
    };
    return languageMap[extension || ''] || 'Unknown';
  };

  // Get file icon based on type
  const getFileIcon = (fileName: string, isFolder: boolean = false) => {
    if (isFolder) {
      return <Folder size={14} className="text-amber-500" />;
    }
    
    const extension = fileName.split('.').pop()?.toLowerCase();
    const iconClass = "text-blue-500";
    
    switch (extension) {
      case 'ts':
      case 'tsx':
        return <Code size={14} className="text-blue-600" />;
      case 'js':
      case 'jsx':
        return <Code size={14} className="text-yellow-500" />;
      case 'py':
        return <Code size={14} className="text-green-600" />;
      case 'java':
        return <Code size={14} className="text-red-500" />;
      case 'html':
        return <Code size={14} className="text-orange-500" />;
      case 'css':
      case 'scss':
        return <Code size={14} className="text-pink-500" />;
      case 'json':
        return <Code size={14} className="text-green-500" />;
      case 'md':
        return <FileText size={14} className="text-purple-500" />;
      default:
        return <File size={14} className={iconClass} />;
    }
  };

  // Toggle folder expansion
  const toggleFolder = (path: string) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  };

  // Toggle file selection
  const toggleFileSelection = (path: string) => {
    setSelectedFiles(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  };

  // Add selected files to context
  const addFilesToContext = async () => {
    if (!repository || !selectedBranch || !githubApi || selectedFiles.size === 0) {
      return;
    }

    setLoadingState('files', 'adding', true);
    
    try {
      for (const filePath of selectedFiles) {
        try {
          // Fetch file content
          const fileContent = await githubApi.getFileContent(
            repository.owner.login,
            repository.name,
            filePath,
            selectedBranch
          );
          
          // Add to context
          addSelectedFile({
            branch: selectedBranch,
            path: filePath,
            content: fileContent,
            contentHash: btoa(fileContent).slice(0, 8) // Simple hash
          });
        } catch (error) {
          console.error(`Failed to load file ${filePath}:`, error);
          toast.error(`Failed to load ${filePath}`);
        }
      }
      
      setSelectedFiles(new Set());
      setIsAddFileDialogOpen(false);
      toast.success(`Added ${selectedFiles.size} files to context`);
    } catch (error) {
      console.error('Failed to add files to context:', error);
      toast.error('Failed to add files to context');
    } finally {
      setLoadingState('files', 'adding', false);
    }
  };

  // Remove file from context
  const removeFromContext = (file: ContextFile) => {
    removeSelectedFile(file.branch, file.path);
    toast.success(`Removed ${file.path.split('/').pop()} from context`);
  };

  // Clear all context files
  const clearAllContext = () => {
    contextFiles.forEach(file => {
      removeSelectedFile(file.branch, file.path);
    });
    toast.success('Cleared all context files');
  };

  // Format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Calculate total context size
  const totalContextSize = contextFiles.reduce((sum, file) => sum + file.size, 0);

  // Filter files based on search query and filter settings
  const filterFiles = (items: FileSystemItem[], query: string): FileSystemItem[] => {
    let filtered = items;
    
    // Apply context filter
    if (fileFilter !== 'all') {
      filtered = filtered.filter(item => {
        if (item.type === 'folder') {
          // Keep folders that have matching children
          const hasMatchingChildren = item.children && 
            filterFiles(item.children, '').some(child => 
              fileFilter === 'inContext' 
                ? contextFiles.some(f => f.path === child.path)
                : !contextFiles.some(f => f.path === child.path)
            );
          return hasMatchingChildren;
        } else {
          const isInContext = contextFiles.some(f => f.path === item.path);
          return fileFilter === 'inContext' ? isInContext : !isInContext;
        }
      });
    }
    
    // Apply search query filter
    if (query.trim()) {
      const lowerQuery = query.toLowerCase();
      const searchFiltered: FileSystemItem[] = [];
      
      for (const item of filtered) {
        if (item.type === 'file') {
          if (item.name.toLowerCase().includes(lowerQuery) || 
              item.path.toLowerCase().includes(lowerQuery)) {
            searchFiltered.push(item);
          }
        } else if (item.type === 'folder' && item.children) {
          const filteredChildren = filterFiles(item.children, query);
          if (filteredChildren.length > 0 || item.name.toLowerCase().includes(lowerQuery)) {
            searchFiltered.push({
              ...item,
              children: filteredChildren,
              expanded: true // Auto-expand folders with matches
            });
          }
        }
      }
      
      return searchFiltered;
    }
    
    return filtered;
  };

  // Get file metadata with enhanced information
  const getFileMetadata = (filePath: string): FileMetadata | null => {
    return fileMetadataCache.get(filePath) || null;
  };

  // Check if file is currently in context
  const isFileInContext = (filePath: string): boolean => {
    return contextFiles.some(f => f.path === filePath);
  };

  // Get context file status indicator
  const getContextStatusIcon = (filePath: string) => {
    const isInContext = isFileInContext(filePath);
    const metadata = getFileMetadata(filePath);
    
    if (isInContext) {
      return (
        <div className="flex items-center gap-1">
          <CheckSquare size={12} className="text-green-500" />
          {metadata?.isModified && (
            <div className="w-2 h-2 bg-orange-500 rounded-full" title="Modified since added" />
          )}
        </div>
      );
    }
    return null;
  };

  const filteredFileStructure = filterFiles(fileStructure, searchQuery);

  return (
    <div className={cn("flex flex-col h-full bg-card/30", className)}>
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-primary" />
            <h3 className="font-semibold">Context Files</h3>
            <Badge variant="outline" className="text-xs">
              {contextFiles.length}
            </Badge>
          </div>
          
          <div className="flex items-center gap-1">
            <Dialog open={isAddFileDialogOpen} onOpenChange={setIsAddFileDialogOpen}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DialogTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                      <Plus size={16} />
                    </Button>
                  </DialogTrigger>
                </TooltipTrigger>
                <TooltipContent>Add files to context</TooltipContent>
              </Tooltip>
              
              <DialogContent className="max-w-2xl max-h-[80vh]">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <Plus size={20} />
                    Add Files to Context
                  </DialogTitle>
                  <DialogDescription>
                    Select files from {repository?.name}/{selectedBranch} to add to your chat context
                  </DialogDescription>
                </DialogHeader>
                
                <div className="space-y-4">
                  {/* Search and Filters */}
                  <div className="space-y-3">
                    <div className="relative">
                      <Search size={16} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
                      <Input
                        placeholder="Search files..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-10"
                      />
                    </div>
                    
                    {/* Filter and Sort Controls */}
                    <div className="flex items-center gap-2 text-xs">
                      {/* Context Filter */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" size="sm" className="h-7 text-xs">
                            <Filter size={12} className="mr-1" />
                            {fileFilter === 'all' ? 'All Files' : 
                             fileFilter === 'inContext' ? 'In Context' : 'Not in Context'}
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onClick={() => setFileFilter('all')}>
                            All Files
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setFileFilter('inContext')}>
                            In Context Only
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setFileFilter('notInContext')}>
                            Not in Context
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                      
                      {/* Sort Options */}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" size="sm" className="h-7 text-xs">
                            Sort: {sortBy}
                            {sortOrder === 'desc' && <ChevronDown size={12} className="ml-1" />}
                            {sortOrder === 'asc' && <ChevronUp size={12} className="ml-1" />}
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onClick={() => {
                            setSortBy('name');
                            setSortOrder(sortBy === 'name' && sortOrder === 'asc' ? 'desc' : 'asc');
                          }}>
                            Name
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => {
                            setSortBy('size');
                            setSortOrder(sortBy === 'size' && sortOrder === 'asc' ? 'desc' : 'asc');
                          }}>
                            Size
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => {
                            setSortBy('modified');
                            setSortOrder(sortBy === 'modified' && sortOrder === 'asc' ? 'desc' : 'asc');
                          }}>
                            Modified
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => {
                            setSortBy('type');
                            setSortOrder(sortBy === 'type' && sortOrder === 'asc' ? 'desc' : 'asc');
                          }}>
                            Type
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                      
                      {/* View Mode Toggle */}
                      <div className="flex border rounded">
                        <Button
                          variant={viewMode === 'tree' ? 'default' : 'ghost'}
                          size="sm"
                          className="h-7 px-2 text-xs rounded-r-none"
                          onClick={() => setViewMode('tree')}
                        >
                          Tree
                        </Button>
                        <Button
                          variant={viewMode === 'list' ? 'default' : 'ghost'}
                          size="sm"
                          className="h-7 px-2 text-xs rounded-l-none"
                          onClick={() => setViewMode('list')}
                        >
                          List
                        </Button>
                      </div>
                    </div>
                  </div>
                  
                  {/* File Tree */}
                  <ScrollArea className="h-96 border rounded-lg">
                    {isLoadingFiles ? (
                      <div className="flex items-center justify-center py-12">
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Loader2 size={20} className="animate-spin" />
                          <span>Loading files...</span>
                        </div>
                      </div>
                    ) : filteredFileStructure.length === 0 ? (
                      <div className="text-center py-12 text-muted-foreground">
                        {searchQuery ? 'No files match your search' : 'No files found'}
                      </div>
                    ) : (
                      <div className="p-2">
                        <FileTreeNode
                          items={filteredFileStructure}
                          level={0}
                          selectedFiles={selectedFiles}
                          expandedFolders={expandedFolders}
                          onToggleFolder={toggleFolder}
                          onToggleFile={toggleFileSelection}
                          contextFiles={contextFiles}
                          getFileMetadata={getFileMetadata}
                          viewMode={viewMode}
                        />
                      </div>
                    )}
                  </ScrollArea>
                  
                  {/* Actions */}
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-muted-foreground">
                      {selectedFiles.size} files selected
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        onClick={() => {
                          setSelectedFiles(new Set());
                          setIsAddFileDialogOpen(false);
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        onClick={addFilesToContext}
                        disabled={selectedFiles.size === 0 || state.loadingStates.files.adding}
                      >
                        {state.loadingStates.files.adding ? (
                          <Loader2 size={16} className="animate-spin mr-2" />
                        ) : (
                          <Plus size={16} className="mr-2" />
                        )}
                        Add {selectedFiles.size} files
                      </Button>
                    </div>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
            
            {contextFiles.length > 0 && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="h-8 w-8 p-0"
                    onClick={clearAllContext}
                  >
                    <Trash2 size={16} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Clear all context files</TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
        
        {/* Context Stats */}
        {contextFiles.length > 0 && (
          <div className="text-xs text-muted-foreground space-y-1">
            <div className="flex justify-between">
              <span>Total size:</span>
              <span>{formatFileSize(totalContextSize)}</span>
            </div>
            <div className="flex justify-between">
              <span>Files:</span>
              <span>{contextFiles.length}</span>
            </div>
          </div>
        )}
      </div>

      {/* Context Files List */}
      <ScrollArea className="flex-1 p-2">
        {contextFiles.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-12 h-12 bg-muted rounded-full flex items-center justify-center mx-auto mb-3">
              <FileText size={20} className="text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground mb-2">No files in context</p>
            <p className="text-xs text-muted-foreground">
              Add files to provide context for your AI conversations
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {contextFiles.map((file, index) => {
              const metadata = getFileMetadata(file.path);
              const lineCount = file.content.split('\n').length;
              
              return (
                <div
                  key={`${file.branch}-${file.path}`}
                  className="group p-3 rounded-lg border border-border hover:border-primary/50 transition-colors bg-green-50/50 dark:bg-green-950/10"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-2 flex-1 min-w-0">
                      {getFileIcon(file.path)}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm truncate text-green-700 dark:text-green-300">
                            {file.path.split('/').pop()}
                          </span>
                          {file.language && (
                            <Badge variant="outline" className="text-xs px-1 py-0 border-green-200 text-green-700 dark:border-green-800 dark:text-green-300">
                              {file.language}
                            </Badge>
                          )}
                          {file.isModified && (
                            <Badge variant="outline" className="text-xs px-1 py-0 border-orange-200 text-orange-700 dark:border-orange-800 dark:text-orange-300">
                              Modified
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">
                          {file.path}
                        </p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Hash size={10} />
                            <span>{formatFileSize(file.size)}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <Code size={10} />
                            <span>{lineCount} lines</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <GitBranch size={10} />
                            <span>{file.branch}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <ClockIcon size={10} />
                            <span title={file.addedAt.toLocaleString()}>
                              {formatRelativeTime(file.addedAt)}
                            </span>
                          </div>
                        </div>
                        
                        {/* File Hash for Change Detection */}
                        {file.contentHash && (
                          <div className="mt-1 text-xs text-muted-foreground font-mono">
                            Hash: {file.contentHash}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => setShowPreview(showPreview === file.path ? null : file.path)}
                          >
                            {showPreview === file.path ? <EyeOff size={12} /> : <Eye size={12} />}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {showPreview === file.path ? 'Hide preview' : 'Show preview'}
                        </TooltipContent>
                      </Tooltip>
                      
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => {
                              navigator.clipboard.writeText(file.content);
                              toast.success('File content copied to clipboard');
                            }}
                          >
                            <CopyIcon size={12} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Copy file content</TooltipContent>
                      </Tooltip>
                      
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 text-red-500 hover:text-red-600"
                            onClick={() => removeFromContext(file)}
                          >
                            <X size={12} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Remove from context</TooltipContent>
                      </Tooltip>
                    </div>
                  </div>
                  
                  {/* Enhanced File Preview */}
                  {showPreview === file.path && (
                    <div className="mt-3 pt-3 border-t border-border">
                      <div className="space-y-2">
                        {/* Preview Header */}
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">
                            Preview ({file.content.length > 1000 ? 'truncated' : 'full'})
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-muted-foreground">
                              {lineCount} lines, {formatFileSize(file.size)}
                            </span>
                          </div>
                        </div>
                        
                        {/* Code Preview */}
                        <div className="bg-muted/50 rounded p-3 text-xs font-mono max-h-40 overflow-y-auto border">
                          <pre className="whitespace-pre-wrap text-foreground">
                            {file.content.slice(0, 1000)}
                            {file.content.length > 1000 && (
                              <span className="text-muted-foreground">
                                \n... ({file.content.length - 1000} more characters)
                              </span>
                            )}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
};

// File Tree Node Component
interface FileTreeNodeProps {
  items: FileSystemItem[];
  level: number;
  selectedFiles: Set<string>;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  onToggleFile: (path: string) => void;
  contextFiles: ContextFile[];
  getFileMetadata: (path: string) => FileMetadata | null;
  viewMode: 'tree' | 'list';
}

const FileTreeNode: React.FC<FileTreeNodeProps> = ({
  items,
  level,
  selectedFiles,
  expandedFolders,
  onToggleFolder,
  onToggleFile,
  contextFiles,
  getFileMetadata,
  viewMode
}) => {
  const isFileInContext = (path: string) => contextFiles.some(f => f.path === path);
  
  return (
    <div>
      {items.map((item) => {
        const metadata = getFileMetadata(item.path);
        const inContext = isFileInContext(item.path);
        
        return (
          <div key={item.path}>
            <div
              className={cn(
                "group flex items-center gap-2 py-1.5 px-2 rounded hover:bg-muted/50 cursor-pointer transition-colors",
                selectedFiles.has(item.path) && "bg-primary/10",
                inContext && "bg-green-50 dark:bg-green-950/20 border-l-2 border-green-500"
              )}
              style={{ paddingLeft: viewMode === 'tree' ? `${level * 16 + 8}px` : '8px' }}
              onClick={() => {
                if (item.type === 'folder') {
                  onToggleFolder(item.path);
                } else {
                  onToggleFile(item.path);
                }
              }}
            >
              {/* Expand/Collapse for folders (only in tree view) */}
              {viewMode === 'tree' && item.type === 'folder' ? (
                expandedFolders.has(item.path) ? (
                  <ChevronDown size={14} className="text-muted-foreground" />
                ) : (
                  <ChevronRight size={14} className="text-muted-foreground" />
                )
              ) : viewMode === 'tree' ? (
                <div className="w-3.5" />
              ) : null}
              
              {/* Selection Checkbox */}
              <div className={cn(
                "w-4 h-4 border rounded flex-shrink-0 transition-colors cursor-pointer flex items-center justify-center",
                selectedFiles.has(item.path) ? "bg-primary border-primary" : "border-muted-foreground/30"
              )}>
                {selectedFiles.has(item.path) && (
                  <Check size={10} className="text-primary-foreground" />
                )}
              </div>
              
              {/* File/Folder Icon */}
              <div className="flex-shrink-0">
                {item.type === 'folder' ? (
                  expandedFolders.has(item.path) ? (
                    <FolderOpen size={14} className="text-amber-500" />
                  ) : (
                    <Folder size={14} className="text-amber-500" />
                  )
                ) : (
                  getFileIcon(item.name)
                )}
              </div>
              
              {/* File/Folder Name and Metadata */}
              <div className="flex-1 min-w-0 flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={cn(
                    "text-sm truncate",
                    inContext && "font-medium text-green-700 dark:text-green-300"
                  )}>
                    {item.name}
                  </span>
                  
                  {/* Context Indicator */}
                  {inContext && (
                    <div className="flex items-center gap-1">
                      <CheckSquare size={12} className="text-green-500" />
                      {metadata?.isModified && (
                        <div className="w-2 h-2 bg-orange-500 rounded-full" title="Modified since added" />
                      )}
                    </div>
                  )}
                  
                  {/* Language Badge for files */}
                  {item.type === 'file' && metadata?.language && metadata.language !== 'Unknown' && (
                    <Badge variant="outline" className="text-xs px-1 py-0 h-4">
                      {metadata.language}
                    </Badge>
                  )}
                </div>
                
                {/* File Metadata */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                  {item.type === 'file' && (
                    <>
                      <span>{formatFileSize(item.size || 0)}</span>
                      {item.lastModified && (
                        <>
                          <span>•</span>
                          <span title={item.lastModified.toLocaleString()}>
                            {formatRelativeTime(item.lastModified)}
                          </span>
                        </>
                      )}
                    </>
                  )}
                  
                  {/* Quick Actions */}
                  <div className="flex items-center gap-1 ml-2">
                    {item.type === 'file' && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-5 w-5 p-0"
                            onClick={(e) => {
                              e.stopPropagation();
                              // TODO: Implement file preview
                            }}
                          >
                            <Eye size={10} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Preview file</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                </div>
              </div>
            </div>
            
            {/* Children for expanded folders (only in tree view) */}
            {viewMode === 'tree' && 
             item.type === 'folder' && 
             item.children && 
             expandedFolders.has(item.path) && (
              <FileTreeNode
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
        );
      })}
    </div>
  );
};

// Helper function to format relative time
const formatRelativeTime = (date: Date): string => {
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  
  if (diffInSeconds < 60) return 'just now';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)}d ago`;
  
  return date.toLocaleDateString();
};