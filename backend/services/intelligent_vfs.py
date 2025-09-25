"""
Intelligent Virtual File System - Clean Implementation

Provides seamless file access to Cosmos with indexed lookups, lazy loading,
and memory-efficient file handling. Creates a virtual file system interface
that Cosmos can interact with as if it were a real repository.
"""

import os
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from collections import OrderedDict
from datetime import datetime
import mimetypes

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class VirtualFile:
    """Represents a virtual file in the VFS."""
    path: str
    name: str
    size: int
    last_modified: datetime
    file_type: str
    encoding: str = 'utf-8'
    _content: Optional[str] = field(default=None, init=False)
    _content_loaded: bool = field(default=False, init=False)
    _checksum: Optional[str] = field(default=None, init=False)


@dataclass
class VirtualDirectory:
    """Represents a virtual directory in the VFS."""
    path: str
    name: str
    children: Dict[str, Union['VirtualDirectory', VirtualFile]] = field(default_factory=dict)
    _file_count: int = field(default=0, init=False)
    _dir_count: int = field(default=0, init=False)


@dataclass
class FileMetadata:
    """File metadata for VFS operations."""
    path: str
    name: str
    size: int
    mtime: float
    file_type: str
    language: str
    encoding: str
    is_binary: bool = False
    git_status: str = 'tracked'


class LRUCache:
    """LRU cache implementation for file content caching."""
    
    def __init__(self, max_size: int = 100, max_memory_mb: int = 50):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, Tuple[str, int]] = OrderedDict()
        self.current_memory = 0
    
    def get(self, key: str) -> Optional[str]:
        """Get item from cache, moving it to end (most recently used)."""
        if key in self.cache:
            content, size = self.cache.pop(key)
            self.cache[key] = (content, size)
            return content
        return None
    
    def put(self, key: str, content: str) -> None:
        """Put item in cache, evicting if necessary."""
        content_size = len(content.encode('utf-8'))
        
        # Remove existing entry if present
        if key in self.cache:
            _, old_size = self.cache.pop(key)
            self.current_memory -= old_size
        
        # Evict items if necessary
        while (len(self.cache) >= self.max_size or 
               self.current_memory + content_size > self.max_memory_bytes):
            if not self.cache:
                break
            oldest_key, (_, oldest_size) = self.cache.popitem(last=False)
            self.current_memory -= oldest_size
        
        # Add new item
        self.cache[key] = (content, content_size)
        self.current_memory += content_size
    
    def clear(self) -> None:
        """Clear all cached items."""
        self.cache.clear()
        self.current_memory = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'memory_usage_mb': self.current_memory / (1024 * 1024),
            'max_memory_mb': self.max_memory_bytes / (1024 * 1024)
        }


class IntelligentVFS:
    """
    Intelligent Virtual File System for Cosmos integration.
    
    Provides a virtual file system interface that Cosmos can interact with
    as if it were a real repository, with optimized performance through
    indexing, caching, and lazy loading.
    """
    
    def __init__(self, repository_context, redis_manager=None):
        """
        Initialize the Intelligent VFS.
        
        Args:
            repository_context: RepositoryContext from SmartRedisRepoManager
            redis_manager: Optional SmartRedisRepoManager instance for content loading
        """
        self.repository_context = repository_context
        self.redis_manager = redis_manager
        
        # File system structure
        self.root_directory = VirtualDirectory(path='/', name='')
        self.file_index: Dict[str, VirtualFile] = {}
        self.directory_index: Dict[str, VirtualDirectory] = {}
        
        # Caching system
        self.content_cache = LRUCache(max_size=200, max_memory_mb=100)
        
        # Performance tracking
        self._access_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Git simulation data
        self.repo_root = '/'
        self.current_branch = 'main'
        self.tracked_files: Set[str] = set()
        
        # Initialize the virtual file system
        self._build_virtual_structure()
        
        logger.info(f"IntelligentVFS initialized with {len(self.file_index)} files")
    
    def _build_virtual_structure(self) -> None:
        """Build the virtual directory and file structure from repository context."""
        try:
            if not self.repository_context or not self.repository_context.file_index:
                logger.warning("No repository context or file index available")
                return
            
            # Create virtual files from file index
            for file_path, file_location in self.repository_context.file_index.items():
                self._create_virtual_file(file_path, file_location)
            
            # Build directory structure
            self._build_directory_structure()
            
            # Set up git tracking
            self.tracked_files = set(self.file_index.keys())
            
            logger.info(f"Built virtual structure: {len(self.file_index)} files, {len(self.directory_index)} directories")
            
        except Exception as e:
            logger.error(f"Error building virtual structure: {e}")
            raise
    
    def _create_virtual_file(self, file_path: str, file_location) -> None:
        """Create a virtual file from file location information."""
        try:
            # Normalize path
            normalized_path = self._normalize_path(file_path)
            
            # Create virtual file
            virtual_file = VirtualFile(
                path=normalized_path,
                name=os.path.basename(normalized_path),
                size=file_location.size,
                last_modified=datetime.now(),
                file_type=self._detect_file_type(normalized_path),
                encoding='utf-8'
            )
            
            # Store checksum for validation
            virtual_file._checksum = file_location.checksum
            
            # Add to index
            self.file_index[normalized_path] = virtual_file
            
        except Exception as e:
            logger.error(f"Error creating virtual file for {file_path}: {e}")
    
    def _build_directory_structure(self) -> None:
        """Build directory structure from file paths."""
        try:
            # Create directories for all file paths
            for file_path in self.file_index.keys():
                self._ensure_directory_path(os.path.dirname(file_path))
            
            # Populate directory children
            for file_path, virtual_file in self.file_index.items():
                dir_path = os.path.dirname(file_path)
                if dir_path in self.directory_index:
                    directory = self.directory_index[dir_path]
                    directory.children[virtual_file.name] = virtual_file
                    directory._file_count += 1
                elif dir_path == '' or dir_path == '/':
                    # Root level file
                    self.root_directory.children[virtual_file.name] = virtual_file
                    self.root_directory._file_count += 1
            
        except Exception as e:
            logger.error(f"Error building directory structure: {e}")
            raise
    
    def _ensure_directory_path(self, dir_path: str) -> None:
        """Ensure all directories in path exist."""
        if not dir_path or dir_path == '/' or dir_path in self.directory_index:
            return
        
        # Normalize path
        normalized_path = self._normalize_path(dir_path)
        if not normalized_path:
            return
        
        # Create parent directories first
        parent_path = os.path.dirname(normalized_path)
        if parent_path and parent_path != normalized_path:
            self._ensure_directory_path(parent_path)
        
        # Create this directory
        directory = VirtualDirectory(
            path=normalized_path,
            name=os.path.basename(normalized_path)
        )
        
        self.directory_index[normalized_path] = directory
        
        # Add to parent directory
        if parent_path in self.directory_index:
            parent_dir = self.directory_index[parent_path]
            parent_dir.children[directory.name] = directory
            parent_dir._dir_count += 1
        elif not parent_path or parent_path == '/':
            # Root level directory
            self.root_directory.children[directory.name] = directory
            self.root_directory._dir_count += 1
    
    def get_file(self, path: str) -> Optional[VirtualFile]:
        """Get a virtual file by path."""
        try:
            normalized_path = self._normalize_path(path)
            self._access_count += 1
            
            if normalized_path in self.file_index:
                return self.file_index[normalized_path]
            
            # Try fuzzy matching for different path formats
            for indexed_path in self.file_index.keys():
                if (indexed_path.endswith(normalized_path) or 
                    normalized_path.endswith(indexed_path) or
                    os.path.basename(indexed_path) == os.path.basename(normalized_path)):
                    return self.file_index[indexed_path]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file {path}: {e}")
            return None
    
    def get_file_content(self, path: str) -> Optional[str]:
        """Get file content with lazy loading and caching."""
        try:
            virtual_file = self.get_file(path)
            if not virtual_file:
                return None
            
            # Check if content is already loaded
            if virtual_file._content_loaded and virtual_file._content is not None:
                self._cache_hits += 1
                return virtual_file._content
            
            # Check cache
            cached_content = self.content_cache.get(virtual_file.path)
            if cached_content is not None:
                virtual_file._content = cached_content
                virtual_file._content_loaded = True
                self._cache_hits += 1
                return cached_content
            
            # Load content
            self._cache_misses += 1
            content = self._load_file_content(virtual_file)
            
            if content is not None:
                # Cache the content
                self.content_cache.put(virtual_file.path, content)
                virtual_file._content = content
                virtual_file._content_loaded = True
            
            return content
            
        except Exception as e:
            logger.error(f"Error getting file content for {path}: {e}")
            return None
    
    def _load_file_content(self, virtual_file: VirtualFile) -> Optional[str]:
        """Load file content from the repository context or Redis manager."""
        try:
            if not self.repository_context:
                return None
            
            # Use Redis manager if available
            if self.redis_manager:
                content = self.redis_manager.get_file_content(
                    self.repository_context.repo_url, 
                    virtual_file.path
                )
                if content is not None:
                    return content
            
            # Fallback to extracting from repository context content
            if virtual_file.path in self.repository_context.file_index:
                file_location = self.repository_context.file_index[virtual_file.path]
                return self._extract_content_from_context(file_location)
            
            return None
            
        except Exception as e:
            logger.error(f"Error loading content for {virtual_file.path}: {e}")
            return None
    
    def _extract_content_from_context(self, file_location) -> Optional[str]:
        """Extract file content from repository context using file location."""
        try:
            if not self.repository_context.content:
                return None
            
            lines = self.repository_context.content.split('\n')
            
            if (file_location.start_offset >= len(lines) or 
                file_location.end_offset > len(lines)):
                logger.error(f"Invalid file location offsets: {file_location.start_offset}-{file_location.end_offset}")
                return None
            
            # Extract content lines
            content_lines = []
            in_code_block = False
            
            for i in range(file_location.start_offset, file_location.end_offset):
                if i >= len(lines):
                    break
                
                line = lines[i]
                
                # Handle code blocks
                if line.strip().startswith('```'):
                    if not in_code_block:
                        in_code_block = True
                        continue
                    else:
                        in_code_block = False
                        break
                
                # Collect content
                if in_code_block:
                    content_lines.append(line)
                elif line.strip():
                    content_lines.append(line)
            
            extracted_content = '\n'.join(content_lines)
            
            # Validate checksum if available
            if hasattr(file_location, 'checksum') and file_location.checksum:
                calculated_checksum = hashlib.md5(extracted_content.encode('utf-8')).hexdigest()
                if calculated_checksum != file_location.checksum:
                    logger.warning(f"Checksum mismatch for file content")
            
            return extracted_content
            
        except Exception as e:
            logger.error(f"Error extracting content from context: {e}")
            return None
    
    def list_directory(self, path: str = '/') -> List[str]:
        """List directory contents."""
        try:
            normalized_path = self._normalize_path(path)
            
            # Handle root directory
            if not normalized_path or normalized_path == '/':
                return list(self.root_directory.children.keys())
            
            # Find directory
            if normalized_path in self.directory_index:
                directory = self.directory_index[normalized_path]
                return list(directory.children.keys())
            
            return []
            
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return []
    
    def file_exists(self, path: str) -> bool:
        """Check if a file exists in the VFS."""
        try:
            normalized_path = self._normalize_path(path)
            return normalized_path in self.file_index
        except Exception as e:
            logger.error(f"Error checking file existence for {path}: {e}")
            return False
    
    def directory_exists(self, path: str) -> bool:
        """Check if a directory exists in the VFS."""
        try:
            normalized_path = self._normalize_path(path)
            
            if not normalized_path or normalized_path == '/':
                return True  # Root always exists
            
            return normalized_path in self.directory_index
            
        except Exception as e:
            logger.error(f"Error checking directory existence for {path}: {e}")
            return False
    
    def get_file_metadata(self, path: str) -> Optional[FileMetadata]:
        """Get file metadata."""
        try:
            virtual_file = self.get_file(path)
            if not virtual_file:
                return None
            
            return FileMetadata(
                path=virtual_file.path,
                name=virtual_file.name,
                size=virtual_file.size,
                mtime=virtual_file.last_modified.timestamp(),
                file_type=virtual_file.file_type,
                language=self._detect_language(virtual_file.path),
                encoding=virtual_file.encoding,
                is_binary=self._is_binary_file(virtual_file.path),
                git_status='tracked' if virtual_file.path in self.tracked_files else 'untracked'
            )
            
        except Exception as e:
            logger.error(f"Error getting file metadata for {path}: {e}")
            return None
    
    def find_files_by_extension(self, extension: str) -> List[VirtualFile]:
        """Find files by extension."""
        try:
            if not extension.startswith('.'):
                extension = '.' + extension
            
            matches = []
            for virtual_file in self.file_index.values():
                if virtual_file.path.lower().endswith(extension.lower()):
                    matches.append(virtual_file)
            
            return matches
            
        except Exception as e:
            logger.error(f"Error finding files by extension {extension}: {e}")
            return []
    
    def find_files_by_language(self, language: str) -> List[VirtualFile]:
        """Find files by programming language."""
        try:
            matches = []
            for virtual_file in self.file_index.values():
                if self._detect_language(virtual_file.path) == language.lower():
                    matches.append(virtual_file)
            
            return matches
            
        except Exception as e:
            logger.error(f"Error finding files by language {language}: {e}")
            return []
    
    def get_tracked_files(self) -> List[str]:
        """Get list of git-tracked files."""
        return sorted(list(self.tracked_files))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get VFS statistics."""
        return {
            'total_files': len(self.file_index),
            'total_directories': len(self.directory_index),
            'access_count': self._access_count,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_ratio': self._cache_hits / max(self._access_count, 1),
            'cache_stats': self.content_cache.get_stats(),
            'repository_info': {
                'repo_url': self.repository_context.repo_url if self.repository_context else None,
                'repo_name': self.repository_context.repo_name if self.repository_context else None,
                'total_size': self.repository_context.total_size if self.repository_context else 0
            }
        }
    
    def _normalize_path(self, path: str) -> str:
        """Normalize file path for consistent handling."""
        try:
            if not path:
                return ""
            
            # Convert backslashes to forward slashes
            normalized = path.replace('\\', '/')
            
            # Convert to PurePosixPath for consistent handling
            normalized = str(PurePosixPath(normalized))
            
            # Remove leading ./ if present
            if normalized.startswith('./'):
                normalized = normalized[2:]
            
            # Handle case where path becomes just "." after normalization
            if normalized == ".":
                return ""
            
            # Remove leading slash for internal consistency
            if normalized.startswith('/'):
                normalized = normalized[1:]
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing path {path}: {e}")
            return path
    
    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type from path."""
        try:
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type:
                return mime_type
            
            # Fallback to extension-based detection
            _, ext = os.path.splitext(file_path.lower())
            
            type_map = {
                '.py': 'text/x-python',
                '.js': 'text/javascript',
                '.ts': 'text/typescript',
                '.html': 'text/html',
                '.css': 'text/css',
                '.json': 'application/json',
                '.md': 'text/markdown',
                '.txt': 'text/plain',
                '.yml': 'text/yaml',
                '.yaml': 'text/yaml',
                '.xml': 'text/xml'
            }
            
            return type_map.get(ext, 'text/plain')
            
        except Exception:
            return 'text/plain'
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        extension_map = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.jsx': 'javascript', '.tsx': 'typescript', '.java': 'java',
            '.cpp': 'cpp', '.c': 'c', '.h': 'c', '.hpp': 'cpp',
            '.cs': 'csharp', '.php': 'php', '.rb': 'ruby', '.go': 'go',
            '.rs': 'rust', '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
            '.sh': 'bash', '.bash': 'bash', '.zsh': 'zsh', '.fish': 'fish',
            '.ps1': 'powershell', '.html': 'html', '.css': 'css',
            '.scss': 'scss', '.sass': 'sass', '.less': 'less',
            '.xml': 'xml', '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml',
            '.toml': 'toml', '.ini': 'ini', '.cfg': 'ini', '.conf': 'conf',
            '.md': 'markdown', '.rst': 'rst', '.txt': 'text', '.sql': 'sql',
            '.r': 'r', '.R': 'r', '.m': 'matlab', '.pl': 'perl',
            '.lua': 'lua', '.vim': 'vim', '.dockerfile': 'dockerfile',
            '.gitignore': 'gitignore', '.env': 'env'
        }
        
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        
        # Check for special filenames
        filename = os.path.basename(file_path.lower())
        if filename in ['dockerfile', 'makefile', 'rakefile', 'gemfile']:
            return filename
        
        return extension_map.get(ext, 'text')
    
    def _is_binary_file(self, file_path: str) -> bool:
        """Check if file is likely binary based on extension."""
        binary_extensions = {
            '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
            '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac',
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
        }
        
        _, ext = os.path.splitext(file_path.lower())
        return ext in binary_extensions


class GitSimulator:
    """Git operations simulator for Cosmos compatibility."""
    
    def __init__(self, vfs_instance):
        """Initialize Git simulator."""
        self.vfs = vfs_instance
        self.repo_root = '/'
        self.current_branch = 'main'
        self.remote_url = self.vfs.repository_context.repo_url if self.vfs.repository_context else None
        
        # Git status simulation
        self.tracked_files: Set[str] = set()
        self.modified_files: Set[str] = set()
        self.untracked_files: Set[str] = set()
        self.staged_files: Set[str] = set()
        
        # Initialize git state
        self._initialize_git_state()
        
        logger.info(f"GitSimulator initialized for repository: {self.remote_url}")
    
    def _initialize_git_state(self) -> None:
        """Initialize git state from VFS file index."""
        try:
            # All files in VFS are considered tracked
            self.tracked_files = set(self.vfs.file_index.keys())
            
            # Simulate some files as modified (for realism)
            if self.tracked_files:
                import random
                sample_size = min(3, len(self.tracked_files))
                self.modified_files = set(random.sample(list(self.tracked_files), sample_size))
            
            logger.info(f"Git state initialized: {len(self.tracked_files)} tracked files")
            
        except Exception as e:
            logger.error(f"Error initializing git state: {e}")
    
    def get_tracked_files(self) -> List[str]:
        """Get list of tracked files."""
        return sorted(list(self.tracked_files))
    
    def get_git_status(self) -> Dict[str, Any]:
        """Get comprehensive git status information."""
        try:
            return {
                'branch': self.current_branch,
                'remote_url': self.remote_url,
                'repo_root': self.repo_root,
                'tracked_files': len(self.tracked_files),
                'modified_files': len(self.modified_files),
                'untracked_files': len(self.untracked_files),
                'staged_files': len(self.staged_files),
                'clean': len(self.modified_files) == 0 and len(self.untracked_files) == 0,
                'files': {
                    'tracked': self.get_tracked_files(),
                    'modified': sorted(list(self.modified_files)),
                    'untracked': sorted(list(self.untracked_files)),
                    'staged': sorted(list(self.staged_files))
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting git status: {e}")
            return {}
    
    def is_tracked(self, file_path: str) -> bool:
        """Check if a file is tracked by git."""
        normalized_path = self.vfs._normalize_path(file_path)
        return normalized_path in self.tracked_files
    
    def get_repository_info(self) -> Dict[str, Any]:
        """Get repository information."""
        try:
            return {
                'repo_root': self.repo_root,
                'current_branch': self.current_branch,
                'remote_url': self.remote_url,
                'repo_name': self._extract_repo_name(),
                'is_git_repo': True,
                'has_remote': self.remote_url is not None,
                'total_files': len(self.tracked_files),
                'git_dir': os.path.join(self.repo_root, '.git') if self.repo_root != '/' else '/.git'
            }
            
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return {}
    
    def _extract_repo_name(self) -> Optional[str]:
        """Extract repository name from remote URL."""
        try:
            if not self.remote_url:
                return None
            
            # Handle SSH URLs like git@github.com:owner/repo.git
            if self.remote_url.startswith('git@'):
                if ':' in self.remote_url:
                    path_part = self.remote_url.split(':', 1)[1]
                    path_parts = [part for part in path_part.strip('/').split('/') if part]
                else:
                    return None
            else:
                # Handle HTTPS URLs
                from urllib.parse import urlparse
                path = urlparse(self.remote_url).path
                path_parts = [part for part in path.strip('/').split('/') if part]
            
            if len(path_parts) >= 2:
                repo_name = path_parts[1].replace('.git', '')
                return f"{path_parts[0]}/{repo_name}"
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting repo name: {e}")
            return None


class IntelligentVFSWithGit(IntelligentVFS):
    """Extended IntelligentVFS with Git operations simulation."""
    
    def __init__(self, repository_context, redis_manager=None):
        """Initialize VFS with Git simulation."""
        super().__init__(repository_context, redis_manager)
        
        # Initialize Git simulator
        self.git_simulator = GitSimulator(self)
        
        # Update tracked files in VFS
        self.tracked_files = self.git_simulator.tracked_files
        
        logger.info("IntelligentVFS with Git simulation initialized")
    
    def get_git_status(self) -> Dict[str, Any]:
        """Get git status information."""
        return self.git_simulator.get_git_status()
    
    def is_git_tracked(self, file_path: str) -> bool:
        """Check if file is tracked by git."""
        return self.git_simulator.is_tracked(file_path)
    
    def get_repository_root(self) -> str:
        """Get repository root path."""
        return self.git_simulator.repo_root
    
    def get_current_branch(self) -> str:
        """Get current git branch."""
        return self.git_simulator.current_branch
    
    def get_remote_url(self) -> Optional[str]:
        """Get remote repository URL."""
        return self.git_simulator.remote_url
    
    def get_repository_info(self) -> Dict[str, Any]:
        """Get comprehensive repository information."""
        git_info = self.git_simulator.get_repository_info()
        vfs_stats = self.get_stats()
        
        return {
            **git_info,
            'vfs_stats': vfs_stats,
            'total_indexed_files': len(self.file_index),
            'cache_status': {
                'cached_files': len(self.content_cache.cache),
                'cache_hit_ratio': self._cache_hits / max(self._access_count, 1)
            }
        }