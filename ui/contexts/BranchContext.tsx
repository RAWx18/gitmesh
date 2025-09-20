"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRepository } from './RepositoryContext';
import { apiService } from '../lib/api';


const API_BASE_URL = 'http://localhost:8000/api/v1';

export type BranchType = string;

interface BranchInfo {
  name: string;
  sha: string;
  color: string;
  description: string;
  maintainer: string;
  githubUrl: string;
}

interface BranchContextType {
  selectedBranch: BranchType;
  setSelectedBranch: (branch: BranchType) => void;
  branchList: string[];
  branchInfoMap: Record<string, BranchInfo>;
  getBranchInfo: () => BranchInfo;
  isLoadingBranches: boolean;
}

const BranchContext = createContext<BranchContextType | undefined>(undefined);

export const useBranch = () => {
  const context = useContext(BranchContext);
  if (context === undefined) {
    throw new Error('useBranch must be used within a BranchProvider');
  }
  return context;
};

interface BranchProviderProps {
  children: ReactNode;
}

export const BranchProvider: React.FC<BranchProviderProps> = ({ children }) => {
  const { repository } = useRepository();
  const [branchList, setBranchList] = useState<string[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<BranchType>('');
  const [branchInfoMap, setBranchInfoMap] = useState<Record<string, BranchInfo>>({});
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  useEffect(() => {
    if (repository?.full_name) {
      const fetchBranches = async () => {
        setIsLoadingBranches(true);
        try {
          const response = await apiService.getRepositoryBranches(repository.owner.login, repository.name);

          if (response.error) {
            console.error('API error:', response.error);
            // Fallback to default branch from repository object if API fails
            const defaultBranch = repository.default_branch;
            setBranchList(defaultBranch ? [defaultBranch] : []);
            setSelectedBranch(defaultBranch || '');
            return;
          }

          const fetchedBranches = response.data || [];
          const branchNames = fetchedBranches.map((b: any) => b.name);
          
          setBranchList(branchNames);

          if (branchNames.length > 0) {
            // Set selected branch to default branch or first branch
            const defaultBranch = repository.default_branch;
            setSelectedBranch(branchNames.includes(defaultBranch) ? defaultBranch : branchNames[0]);
          } else {
            setSelectedBranch('');
          }

          const infoMap: Record<string, BranchInfo> = {};
          fetchedBranches.forEach((branch: any) => {
            infoMap[branch.name] = {
              name: branch.name,
              sha: branch.commit.sha,
              color: branch.name === repository.default_branch ? 'text-blue-600' : 'text-gray-600',
              description: branch.name === repository.default_branch ? 'Default branch' : '',
              maintainer: '',
              githubUrl: `${repository.html_url}/tree/${branch.name}`,
            };
          });
          setBranchInfoMap(infoMap);

        } catch (e) {
          console.error('Error fetching branches:', e);
          const defaultBranch = repository.default_branch;
          setBranchList(defaultBranch ? [defaultBranch] : []);
          setSelectedBranch(defaultBranch || '');
        } finally {
          setIsLoadingBranches(false);
        }
      };
      fetchBranches();
    }
  }, [repository?.full_name, repository?.default_branch]);

  const getBranchInfo = () => branchInfoMap[selectedBranch] || {
    name: selectedBranch,
    sha: '',
    color: 'text-gray-600',
    description: 'Branch details not available.',
    maintainer: '',
    githubUrl: repository ? `${repository.html_url}/tree/${selectedBranch}` : '',
  };

  return (
    <BranchContext.Provider value={{ selectedBranch, setSelectedBranch, branchList, branchInfoMap, getBranchInfo, isLoadingBranches }}>
      {children}
    </BranchContext.Provider>
  );
};