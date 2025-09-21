"use client";

import React, { useState, useEffect } from 'react';
import { useRepository } from '@/contexts/RepositoryContext';
import { useBranch } from '@/contexts/BranchContext';
import { useAuth } from '@/contexts/AuthContext';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  GitBranch, 
  ChevronDown, 
  Search,
  Star,
  GitFork,
  Clock,
  Users,
  Code,
  Lock,
  Globe,
  Loader2,
  RefreshCw,
  Plus,
  Check
} from 'lucide-react';
import { toast } from 'sonner';

interface Repository {
  id: number;
  name: string;
  full_name: string;
  description?: string;
  private: boolean;
  owner: {
    login: string;
    avatar_url: string;
    type: string;
  };
  html_url: string;
  clone_url: string;
  default_branch: string;
  language?: string;
  stargazers_count: number;
  forks_count: number;
  size: number;
  created_at: string;
  updated_at: string;
  pushed_at: string;
  type: 'owned' | 'collaborated' | 'starred';
}

interface RepositorySelectorProps {
  className?: string;
}

export const RepositorySelector: React.FC<RepositorySelectorProps> = ({ className }) => {
  const { repository, setRepository } = useRepository();
  const { selectedBranch, branchList, setSelectedBranch, fetchBranches } = useBranch();
  const { githubApi, user } = useAuth();
  
  // Local state
  const [isRepoDialogOpen, setIsRepoDialogOpen] = useState(false);
  const [isBranchDropdownOpen, setIsBranchDropdownOpen] = useState(false);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [filteredRepos, setFilteredRepos] = useState<Repository[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [selectedRepoType, setSelectedRepoType] = useState<'all' | 'owned' | 'collaborated' | 'starred'>('all');

  // Load repositories when dialog opens
  useEffect(() => {
    if (isRepoDialogOpen && githubApi && repositories.length === 0) {
      loadRepositories();
    }
  }, [isRepoDialogOpen, githubApi]);

  // Filter repositories based on search query and type
  useEffect(() => {
    let filtered = repositories;
    
    // Filter by type
    if (selectedRepoType !== 'all') {
      filtered = filtered.filter(repo => repo.type === selectedRepoType);
    }
    
    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(repo => 
        repo.name.toLowerCase().includes(query) ||
        repo.full_name.toLowerCase().includes(query) ||
        repo.description?.toLowerCase().includes(query) ||
        repo.language?.toLowerCase().includes(query)
      );
    }
    
    setFilteredRepos(filtered);
  }, [repositories, searchQuery, selectedRepoType]);

  // Load repositories from GitHub API
  const loadRepositories = async () => {
    if (!githubApi || !user) return;
    
    setIsLoadingRepos(true);
    try {
      // Load owned repositories
      const ownedRepos = await githubApi.getUserRepositories(user.login);
      const ownedWithType = ownedRepos.map((repo: any) => ({ ...repo, type: 'owned' as const }));
      
      // Load starred repositories (optional)
      try {
        const starredRepos = await githubApi.getUserStarredRepositories(user.login);
        const starredWithType = starredRepos.map((repo: any) => ({ ...repo, type: 'starred' as const }));
        
        // Combine and deduplicate
        const allRepos = [...ownedWithType, ...starredWithType];
        const uniqueRepos = allRepos.filter((repo, index, self) => 
          index === self.findIndex(r => r.id === repo.id)
        );
        
        setRepositories(uniqueRepos);
      } catch (error) {
        console.warn('Failed to load starred repositories:', error);
        setRepositories(ownedWithType);
      }
    } catch (error) {
      console.error('Failed to load repositories:', error);
      toast.error('Failed to load repositories');
    } finally {
      setIsLoadingRepos(false);
    }
  };

  // Handle repository selection
  const handleRepositorySelect = async (repo: Repository) => {
    setRepository(repo);
    setIsRepoDialogOpen(false);
    
    // Load branches for the selected repository
    setIsLoadingBranches(true);
    try {
      await fetchBranches(repo.owner.login, repo.name);
      // Set default branch as selected
      setSelectedBranch(repo.default_branch);
    } catch (error) {
      console.error('Failed to load branches:', error);
      toast.error('Failed to load repository branches');
    } finally {
      setIsLoadingBranches(false);
    }
  };

  // Handle branch selection
  const handleBranchSelect = (branch: string) => {
    setSelectedBranch(branch);
    setIsBranchDropdownOpen(false);
  };

  // Refresh branches
  const refreshBranches = async () => {
    if (!repository) return;
    
    setIsLoadingBranches(true);
    try {
      await fetchBranches(repository.owner.login, repository.name);
    } catch (error) {
      console.error('Failed to refresh branches:', error);
      toast.error('Failed to refresh branches');
    } finally {
      setIsLoadingBranches(false);
    }
  };

  // Format repository size
  const formatSize = (sizeKB: number) => {
    if (sizeKB < 1024) return `${sizeKB} KB`;
    if (sizeKB < 1024 * 1024) return `${(sizeKB / 1024).toFixed(1)} MB`;
    return `${(sizeKB / (1024 * 1024)).toFixed(1)} GB`;
  };

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {/* Repository Selector */}
      <Dialog open={isRepoDialogOpen} onOpenChange={setIsRepoDialogOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="flex items-center gap-2 min-w-[120px] justify-between"
              >
                <div className="flex items-center gap-2">
                  {repository?.private ? (
                    <Lock size={14} className="text-amber-500" />
                  ) : (
                    <Globe size={14} className="text-green-500" />
                  )}
                  <span className="font-medium truncate">
                    {repository?.name || 'Select repo'}
                  </span>
                </div>
                <ChevronDown size={14} />
              </Button>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <div className="space-y-1">
              <p className="font-medium">
                {repository ? repository.full_name : 'No repository selected'}
              </p>
              {repository && (
                <>
                  <p className="text-xs text-muted-foreground">
                    {repository.description || 'No description'}
                  </p>
                  <div className="flex items-center gap-2 text-xs">
                    <span>{repository.language}</span>
                    <span>•</span>
                    <span>{formatSize(repository.size)}</span>
                  </div>
                </>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
        
        <DialogContent className="max-w-4xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Code size={20} />
              Select Repository
            </DialogTitle>
            <DialogDescription>
              Choose a repository to chat with your codebase
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            {/* Search and Filters */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={16} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search repositories..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              
              <div className="flex gap-1">
                {(['all', 'owned', 'collaborated', 'starred'] as const).map((type) => (
                  <Button
                    key={type}
                    variant={selectedRepoType === type ? "default" : "outline"}
                    size="sm"
                    onClick={() => setSelectedRepoType(type)}
                    className="capitalize"
                  >
                    {type}
                  </Button>
                ))}
              </div>
              
              <Button
                variant="outline"
                size="sm"
                onClick={loadRepositories}
                disabled={isLoadingRepos}
              >
                {isLoadingRepos ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )}
              </Button>
            </div>
            
            {/* Repository List */}
            <ScrollArea className="h-96">
              {isLoadingRepos ? (
                <div className="flex items-center justify-center py-12">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 size={20} className="animate-spin" />
                    <span>Loading repositories...</span>
                  </div>
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="text-center py-12">
                  <div className="text-muted-foreground">
                    {searchQuery ? 'No repositories match your search' : 'No repositories found'}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredRepos.map((repo) => (
                    <div
                      key={repo.id}
                      onClick={() => handleRepositorySelect(repo)}
                      className={cn(
                        "p-4 rounded-lg border border-border hover:border-primary cursor-pointer transition-all",
                        repository?.id === repo.id && "bg-primary/10 border-primary"
                      )}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {repo.private ? (
                              <Lock size={16} className="text-amber-500" />
                            ) : (
                              <Globe size={16} className="text-green-500" />
                            )}
                            <h3 className="font-semibold truncate">{repo.full_name}</h3>
                            <Badge variant="outline" className="text-xs">
                              {repo.type}
                            </Badge>
                            {repository?.id === repo.id && (
                              <Check size={16} className="text-primary" />
                            )}
                          </div>
                          
                          {repo.description && (
                            <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                              {repo.description}
                            </p>
                          )}
                          
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            {repo.language && (
                              <div className="flex items-center gap-1">
                                <div className="w-2 h-2 rounded-full bg-primary"></div>
                                <span>{repo.language}</span>
                              </div>
                            )}
                            <div className="flex items-center gap-1">
                              <Star size={12} />
                              <span>{repo.stargazers_count}</span>
                            </div>
                            <div className="flex items-center gap-1">
                              <GitFork size={12} />
                              <span>{repo.forks_count}</span>
                            </div>
                            <div className="flex items-center gap-1">
                              <Clock size={12} />
                              <span>Updated {formatDate(repo.updated_at)}</span>
                            </div>
                            <span>{formatSize(repo.size)}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>

      {/* Branch Selector */}
      {repository && branchList.length > 0 && (
        <DropdownMenu open={isBranchDropdownOpen} onOpenChange={setIsBranchDropdownOpen}>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-2 min-w-[100px] justify-between"
                  disabled={isLoadingBranches}
                >
                  <div className="flex items-center gap-2">
                    <GitBranch size={14} />
                    <span className="font-medium truncate">
                      {isLoadingBranches ? 'Loading...' : selectedBranch}
                    </span>
                  </div>
                  {isLoadingBranches ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <ChevronDown size={14} className={cn(
                      "transition-transform duration-200",
                      isBranchDropdownOpen && "rotate-180"
                    )} />
                  )}
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>
              <div className="space-y-1">
                <p className="font-medium">Current branch: {selectedBranch}</p>
                <p className="text-xs text-muted-foreground">
                  {branchList.length} branches available
                </p>
              </div>
            </TooltipContent>
          </Tooltip>
          
          <DropdownMenuContent className="w-64 max-h-64 overflow-y-auto">
            <div className="flex items-center justify-between p-2">
              <DropdownMenuLabel className="flex items-center gap-2">
                <GitBranch size={16} />
                Select Branch
              </DropdownMenuLabel>
              <Button
                variant="ghost"
                size="sm"
                onClick={refreshBranches}
                disabled={isLoadingBranches}
                className="h-6 w-6 p-0"
              >
                {isLoadingBranches ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RefreshCw size={12} />
                )}
              </Button>
            </div>
            <DropdownMenuSeparator />
            
            {branchList.map((branch) => (
              <DropdownMenuItem
                key={branch}
                onClick={() => handleBranchSelect(branch)}
                className={cn(
                  "flex items-center justify-between cursor-pointer",
                  selectedBranch === branch && "bg-accent"
                )}
              >
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    branch === repository.default_branch 
                      ? 'bg-blue-500' 
                      : 'bg-gray-500'
                  )}></div>
                  <span>{branch}</span>
                </div>
                
                <div className="flex items-center gap-1">
                  {branch === repository.default_branch && (
                    <Badge variant="outline" className="text-xs px-1 py-0">
                      default
                    </Badge>
                  )}
                  {selectedBranch === branch && (
                    <Check size={14} className="text-primary" />
                  )}
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
};