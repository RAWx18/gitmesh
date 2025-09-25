"""
Intelligent Virtual File System

Provides seamless file access to Cosmos with indexed lookups, lazy loading,
and memory-efficient file handling. Creates a virtual file system interface
that Cosmos can interact with as if it were a real repository.

This implementation supports:
- Indexed file access for O(1) lookups
- Lazy loading of file content to optimize memory usage
- Directory structure simulation for Cosmos navigation
- Git operations simulation for compatibility
- LRU caching with memory management
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
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items to cache
            max_memory_mb: Maximum memory usage in MB
        """
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, Tuple[str, int]] = OrderedDict()  # key -> (content, size)
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
            logger.debug(f"Evicted from cache: {oldest_key}")
        
        # Add new item
        self.cache[key] = (content, content_size)
        self.current_memory += content_size
        logger.debug(f"Cached content for {key} ({content_size} bytes)")
    
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
            'max_memory_mb': self.max_memory_bytes / (1024 * 1024),
            'hit_ratio': getattr(self, '_hit_ratio', 0.0)
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
        
        # Advanced indexing system
        self.file_indexer = FileIndexer()
        
        # Advanced caching system
        self.content_cache = AdvancedLRUCache(max_size=200, max_memory_mb=100, default_ttl=3600)
        
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
                last_modified=datetime.now(),  # Use current time as placeholder
                file_type=self._detect_file_type(normalized_path),
                encoding='utf-8'
            )
            
            # Store checksum for validation
            virtual_file._checksum = file_location.checksum
            
            # Add to indexes
            self.file_index[normalized_path] = virtual_file
            self.file_indexer.add_file(virtual_file)
            
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
            
            # Update directory counts
            self._update_directory_counts()
            
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
    
    def _update_directory_counts(self) -> None:
        """Update file and directory counts for all directories."""
        def count_recursive(directory: VirtualDirectory) -> Tuple[int, int]:
            file_count = 0
            dir_count = 0
            
            for child in directory.children.values():
                if isinstance(child, VirtualFile):
                    file_count += 1
                elif isinstance(child, VirtualDirectory):
                    dir_count += 1
                    child_files, child_dirs = count_recursive(child)
                    file_count += child_files
                    dir_count += child_dirs
            
            directory._file_count = file_count
            directory._dir_count = dir_count
            return file_count, dir_count
        
        # Update root directory
        count_recursive(self.root_directory)
        
        # Update all other directories
        for directory in self.directory_index.values():
            count_recursive(directory)   
 
    def get_file(self, path: str) -> Optional[VirtualFile]:
        """
        Get a virtual file by path.
        
        Args:
            path: File path to retrieve
            
        Returns:
            VirtualFile object or None if not found
        """
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
        """
        Get file content with lazy loading and caching.
        
        Args:
            path: File path to retrieve content for
            
        Returns:
            File content or None if not found
        """
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
            
            # Load content from Redis manager
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
        """
        List directory contents.
        
        Args:
            path: Directory path to list
            
        Returns:
            List of file and directory names
        """
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
        """
        Check if a file exists in the VFS.
        
        Args:
            path: File path to check
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            normalized_path = self._normalize_path(path)
            return normalized_path in self.file_index
            
        except Exception as e:
            logger.error(f"Error checking file existence for {path}: {e}")
            return False
    
    def directory_exists(self, path: str) -> bool:
        """
        Check if a directory exists in the VFS.
        
        Args:
            path: Directory path to check
            
        Returns:
            True if directory exists, False otherwise
        """
        try:
            normalized_path = self._normalize_path(path)
            
            if not normalized_path or normalized_path == '/':
                return True  # Root always exists
            
            return normalized_path in self.directory_index
            
        except Exception as e:
            logger.error(f"Error checking directory existence for {path}: {e}")
            return False
    
    def get_file_metadata(self, path: str) -> Optional[FileMetadata]:
        """
        Get file metadata.
        
        Args:
            path: File path
            
        Returns:
            FileMetadata object or None if not found
        """
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
    
    def get_directory_listing(self, path: str = '/') -> List[Dict[str, Any]]:
        """
        Get detailed directory listing with metadata.
        
        Args:
            path: Directory path
            
        Returns:
            List of dictionaries with file/directory information
        """
        try:
            normalized_path = self._normalize_path(path)
            
            # Get directory
            if not normalized_path or normalized_path == '/':
                directory = self.root_directory
            elif normalized_path in self.directory_index:
                directory = self.directory_index[normalized_path]
            else:
                return []
            
            listing = []
            
            for name, child in directory.children.items():
                if isinstance(child, VirtualFile):
                    listing.append({
                        'name': name,
                        'type': 'file',
                        'path': child.path,
                        'size': child.size,
                        'file_type': child.file_type,
                        'language': self._detect_language(child.path)
                    })
                elif isinstance(child, VirtualDirectory):
                    listing.append({
                        'name': name,
                        'type': 'directory',
                        'path': child.path,
                        'file_count': child._file_count,
                        'dir_count': child._dir_count
                    })
            
            # Sort listing: directories first, then files, both alphabetically
            listing.sort(key=lambda x: (x['type'] == 'file', x['name'].lower()))
            
            return listing
            
        except Exception as e:
            logger.error(f"Error getting directory listing for {path}: {e}")
            return []
    
    def find_files(self, pattern: str, path: str = '/') -> List[str]:
        """
        Find files matching a pattern.
        
        Args:
            pattern: File name pattern (supports wildcards)
            path: Directory path to search in
            
        Returns:
            List of matching file paths
        """
        try:
            import fnmatch
            
            matches = []
            
            # Search in all files if pattern contains wildcards
            if '*' in pattern or '?' in pattern:
                for file_path in self.file_index.keys():
                    if fnmatch.fnmatch(os.path.basename(file_path), pattern):
                        matches.append(file_path)
            else:
                # Exact name search
                for file_path in self.file_index.keys():
                    if os.path.basename(file_path) == pattern:
                        matches.append(file_path)
            
            return sorted(matches)
            
        except Exception as e:
            logger.error(f"Error finding files with pattern {pattern}: {e}")
            return []
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalize file path for consistent handling.
        
        Args:
            path: File path to normalize
            
        Returns:
            Normalized path
        """
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
    
    def clear_cache(self) -> None:
        """Clear all cached content."""
        self.content_cache.clear()
        
        # Clear loaded content from virtual files
        for virtual_file in self.file_index.values():
            virtual_file._content = None
            virtual_file._content_loaded = False
        
        logger.info("VFS cache cleared")
    
    def preload_files(self, file_paths: List[str]) -> int:
        """
        Preload file contents into cache.
        
        Args:
            file_paths: List of file paths to preload
            
        Returns:
            Number of files successfully preloaded
        """
        try:
            preloaded_count = 0
            
            for file_path in file_paths:
                content = self.get_file_content(file_path)
                if content is not None:
                    preloaded_count += 1
            
            logger.info(f"Preloaded {preloaded_count}/{len(file_paths)} files")
            return preloaded_count
            
        except Exception as e:
            logger.error(f"Error preloading files: {e}")
            return 0
    
    # Enhanced search and filtering methods using FileIndexer
    
    def search_files(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[VirtualFile]:
        """
        Search files using the advanced indexing system.
        
        Args:
            query: Search query (filename or pattern)
            filters: Optional filters (extension, language, size, etc.)
            
        Returns:
            List of matching VirtualFile objects
        """
        return self.file_indexer.search_files(query, filters)
    
    def find_files_by_extension(self, extension: str) -> List[VirtualFile]:
        """Find files by extension using O(1) index lookup."""
        return self.file_indexer.find_by_extension(extension)
    
    def find_files_by_language(self, language: str) -> List[VirtualFile]:
        """Find files by programming language using O(1) index lookup."""
        return self.file_indexer.find_by_language(language)
    
    def find_files_by_name(self, name: str) -> List[VirtualFile]:
        """Find files by name using O(1) index lookup."""
        return self.file_indexer.find_by_name(name)
    
    def find_files_in_directory(self, directory: str) -> List[VirtualFile]:
        """Find files in a specific directory using O(1) index lookup."""
        return self.file_indexer.find_by_directory(self._normalize_path(directory))
    
    def get_files_by_size_category(self, category: str) -> List[VirtualFile]:
        """Get files by size category (tiny, small, medium, large, huge)."""
        return self.file_indexer.find_by_size_category(category)


class FileIndexer:
    """
    Advanced file indexing system for fast O(1) lookups.
    
    Provides multiple indexing strategies:
    - Path-based index for exact matches
    - Name-based index for filename searches
    - Extension-based index for type filtering
    - Content-based index for search functionality
    """
    
    def __init__(self):
        """Initialize the file indexer."""
        # Primary indexes
        self.path_index: Dict[str, VirtualFile] = {}
        self.name_index: Dict[str, List[VirtualFile]] = {}
        self.extension_index: Dict[str, List[VirtualFile]] = {}
        self.language_index: Dict[str, List[VirtualFile]] = {}
        
        # Secondary indexes
        self.size_index: Dict[str, List[VirtualFile]] = {}  # small, medium, large
        self.directory_index: Dict[str, List[VirtualFile]] = {}
        
        # Search indexes
        self.content_keywords: Dict[str, Set[str]] = {}  # file_path -> keywords
        self.file_dependencies: Dict[str, Set[str]] = {}  # file_path -> dependencies
        
        logger.info("FileIndexer initialized")
    
    def add_file(self, virtual_file: VirtualFile) -> None:
        """Add a file to all relevant indexes."""
        try:
            # Path index (primary)
            self.path_index[virtual_file.path] = virtual_file
            
            # Name index
            if virtual_file.name not in self.name_index:
                self.name_index[virtual_file.name] = []
            self.name_index[virtual_file.name].append(virtual_file)
            
            # Extension index
            _, ext = os.path.splitext(virtual_file.path.lower())
            if ext:
                if ext not in self.extension_index:
                    self.extension_index[ext] = []
                self.extension_index[ext].append(virtual_file)
            
            # Language index
            language = self._detect_language(virtual_file.path)
            if language not in self.language_index:
                self.language_index[language] = []
            self.language_index[language].append(virtual_file)
            
            # Size index
            size_category = self._categorize_size(virtual_file.size)
            if size_category not in self.size_index:
                self.size_index[size_category] = []
            self.size_index[size_category].append(virtual_file)
            
            # Directory index
            dir_path = os.path.dirname(virtual_file.path)
            if dir_path not in self.directory_index:
                self.directory_index[dir_path] = []
            self.directory_index[dir_path].append(virtual_file)
            
        except Exception as e:
            logger.error(f"Error adding file to index: {e}")
    
    def remove_file(self, file_path: str) -> None:
        """Remove a file from all indexes."""
        try:
            virtual_file = self.path_index.get(file_path)
            if not virtual_file:
                return
            
            # Remove from path index
            del self.path_index[file_path]
            
            # Remove from name index
            if virtual_file.name in self.name_index:
                self.name_index[virtual_file.name] = [
                    f for f in self.name_index[virtual_file.name] 
                    if f.path != file_path
                ]
                if not self.name_index[virtual_file.name]:
                    del self.name_index[virtual_file.name]
            
            # Remove from other indexes similarly
            self._remove_from_secondary_indexes(virtual_file)
            
        except Exception as e:
            logger.error(f"Error removing file from index: {e}")
    
    def find_by_path(self, path: str) -> Optional[VirtualFile]:
        """Find file by exact path match."""
        return self.path_index.get(path)
    
    def find_by_name(self, name: str) -> List[VirtualFile]:
        """Find files by name."""
        return self.name_index.get(name, [])
    
    def find_by_extension(self, extension: str) -> List[VirtualFile]:
        """Find files by extension."""
        if not extension.startswith('.'):
            extension = '.' + extension
        return self.extension_index.get(extension.lower(), [])
    
    def find_by_language(self, language: str) -> List[VirtualFile]:
        """Find files by programming language."""
        return self.language_index.get(language.lower(), [])
    
    def find_by_directory(self, directory: str) -> List[VirtualFile]:
        """Find files in a specific directory."""
        return self.directory_index.get(directory, [])
    
    def find_by_size_category(self, category: str) -> List[VirtualFile]:
        """Find files by size category (small, medium, large)."""
        return self.size_index.get(category, [])
    
    def search_files(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[VirtualFile]:
        """
        Search files with optional filters.
        
        Args:
            query: Search query (filename or pattern)
            filters: Optional filters (extension, language, size, etc.)
            
        Returns:
            List of matching files
        """
        try:
            import fnmatch
            
            results = []
            
            # Start with all files if no specific query
            if not query or query == '*':
                candidates = list(self.path_index.values())
            else:
                # Search by name pattern
                candidates = []
                for name, files in self.name_index.items():
                    if fnmatch.fnmatch(name.lower(), query.lower()):
                        candidates.extend(files)
                
                # Also search by path pattern
                for path, file in self.path_index.items():
                    if fnmatch.fnmatch(os.path.basename(path).lower(), query.lower()):
                        if file not in candidates:
                            candidates.append(file)
            
            # Apply filters
            if filters:
                candidates = self._apply_filters(candidates, filters)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error searching files: {e}")
            return []
    
    def _apply_filters(self, files: List[VirtualFile], filters: Dict[str, Any]) -> List[VirtualFile]:
        """Apply filters to file list."""
        try:
            filtered = files
            
            if 'extension' in filters:
                ext = filters['extension']
                if not ext.startswith('.'):
                    ext = '.' + ext
                filtered = [f for f in filtered if f.path.lower().endswith(ext.lower())]
            
            if 'language' in filters:
                lang = filters['language'].lower()
                filtered = [f for f in filtered if self._detect_language(f.path) == lang]
            
            if 'min_size' in filters:
                min_size = filters['min_size']
                filtered = [f for f in filtered if f.size >= min_size]
            
            if 'max_size' in filters:
                max_size = filters['max_size']
                filtered = [f for f in filtered if f.size <= max_size]
            
            if 'directory' in filters:
                dir_path = filters['directory']
                filtered = [f for f in filtered if f.path.startswith(dir_path)]
            
            return filtered
            
        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            return files
    
    def _categorize_size(self, size: int) -> str:
        """Categorize file size."""
        if size < 1024:  # < 1KB
            return 'tiny'
        elif size < 10 * 1024:  # < 10KB
            return 'small'
        elif size < 100 * 1024:  # < 100KB
            return 'medium'
        elif size < 1024 * 1024:  # < 1MB
            return 'large'
        else:
            return 'huge'
    
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
        
        _, ext = os.path.splitext(file_path.lower())
        filename = os.path.basename(file_path.lower())
        
        if filename in ['dockerfile', 'makefile', 'rakefile', 'gemfile']:
            return filename
        
        return extension_map.get(ext, 'text')
    
    def _remove_from_secondary_indexes(self, virtual_file: VirtualFile) -> None:
        """Remove file from secondary indexes."""
        try:
            # Extension index
            _, ext = os.path.splitext(virtual_file.path.lower())
            if ext and ext in self.extension_index:
                self.extension_index[ext] = [
                    f for f in self.extension_index[ext] 
                    if f.path != virtual_file.path
                ]
                if not self.extension_index[ext]:
                    del self.extension_index[ext]
            
            # Language index
            language = self._detect_language(virtual_file.path)
            if language in self.language_index:
                self.language_index[language] = [
                    f for f in self.language_index[language] 
                    if f.path != virtual_file.path
                ]
                if not self.language_index[language]:
                    del self.language_index[language]
            
            # Size index
            size_category = self._categorize_size(virtual_file.size)
            if size_category in self.size_index:
                self.size_index[size_category] = [
                    f for f in self.size_index[size_category] 
                    if f.path != virtual_file.path
                ]
                if not self.size_index[size_category]:
                    del self.size_index[size_category]
            
            # Directory index
            dir_path = os.path.dirname(virtual_file.path)
            if dir_path in self.directory_index:
                self.directory_index[dir_path] = [
                    f for f in self.directory_index[dir_path] 
                    if f.path != virtual_file.path
                ]
                if not self.directory_index[dir_path]:
                    del self.directory_index[dir_path]
            
        except Exception as e:
            logger.error(f"Error removing from secondary indexes: {e}")
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get indexing statistics."""
        return {
            'total_files': len(self.path_index),
            'unique_names': len(self.name_index),
            'extensions': len(self.extension_index),
            'languages': len(self.language_index),
            'directories': len(self.directory_index),
            'size_categories': len(self.size_index),
            'index_memory_usage': self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> Dict[str, int]:
        """Estimate memory usage of indexes."""
        import sys
        
        return {
            'path_index_bytes': sys.getsizeof(self.path_index),
            'name_index_bytes': sys.getsizeof(self.name_index),
            'extension_index_bytes': sys.getsizeof(self.extension_index),
            'language_index_bytes': sys.getsizeof(self.language_index),
            'directory_index_bytes': sys.getsizeof(self.directory_index),
            'size_index_bytes': sys.getsizeof(self.size_index)
        }


class AdvancedLRUCache(LRUCache):
    """
    Advanced LRU cache with additional features:
    - TTL (Time To Live) support
    - Memory pressure handling
    - Cache warming strategies
    - Statistics tracking
    """
    
    def __init__(self, max_size: int = 100, max_memory_mb: int = 50, default_ttl: int = 3600):
        """
        Initialize advanced LRU cache.
        
        Args:
            max_size: Maximum number of items to cache
            max_memory_mb: Maximum memory usage in MB
            default_ttl: Default TTL in seconds
        """
        super().__init__(max_size, max_memory_mb)
        self.default_ttl = default_ttl
        self.ttl_cache: OrderedDict[str, float] = OrderedDict()  # key -> expiry_time
        self.access_times: Dict[str, float] = {}
        self.hit_count = 0
        self.miss_count = 0
        self.eviction_count = 0
    
    def get(self, key: str) -> Optional[str]:
        """Get item from cache with TTL checking."""
        current_time = time.time()
        
        # Check TTL first
        if key in self.ttl_cache:
            if current_time > self.ttl_cache[key]:
                # Expired, remove from cache
                self._remove_expired(key)
                self.miss_count += 1
                return None
        
        # Get from parent cache
        content = super().get(key)
        
        if content is not None:
            self.hit_count += 1
            self.access_times[key] = current_time
            # Update TTL
            self.ttl_cache[key] = current_time + self.default_ttl
            self.ttl_cache.move_to_end(key)
        else:
            self.miss_count += 1
        
        return content
    
    def put(self, key: str, content: str, ttl: Optional[int] = None) -> None:
        """Put item in cache with TTL."""
        current_time = time.time()
        ttl = ttl or self.default_ttl
        
        # Set TTL
        self.ttl_cache[key] = current_time + ttl
        self.access_times[key] = current_time
        
        # Put in parent cache
        super().put(key, content)
    
    def _remove_expired(self, key: str) -> None:
        """Remove expired item from all caches."""
        if key in self.cache:
            _, size = self.cache.pop(key)
            self.current_memory -= size
        
        if key in self.ttl_cache:
            del self.ttl_cache[key]
        
        if key in self.access_times:
            del self.access_times[key]
    
    def cleanup_expired(self) -> int:
        """Clean up expired items and return count of removed items."""
        current_time = time.time()
        expired_keys = []
        
        for key, expiry_time in self.ttl_cache.items():
            if current_time > expiry_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._remove_expired(key)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache items")
        
        return len(expired_keys)
    
    def warm_cache(self, file_paths: List[str], content_loader) -> int:
        """
        Warm cache with frequently accessed files.
        
        Args:
            file_paths: List of file paths to warm
            content_loader: Function to load content for a file path
            
        Returns:
            Number of files successfully warmed
        """
        warmed_count = 0
        
        for file_path in file_paths:
            try:
                if file_path not in self.cache:
                    content = content_loader(file_path)
                    if content is not None:
                        self.put(file_path, content)
                        warmed_count += 1
            except Exception as e:
                logger.error(f"Error warming cache for {file_path}: {e}")
        
        logger.info(f"Warmed cache with {warmed_count}/{len(file_paths)} files")
        return warmed_count
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed cache statistics."""
        total_requests = self.hit_count + self.miss_count
        hit_ratio = self.hit_count / max(total_requests, 1)
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'memory_usage_mb': self.current_memory / (1024 * 1024),
            'max_memory_mb': self.max_memory_bytes / (1024 * 1024),
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_ratio': hit_ratio,
            'eviction_count': self.eviction_count,
            'expired_items': len([k for k, v in self.ttl_cache.items() if time.time() > v]),
            'avg_access_age': self._calculate_avg_access_age()
        }
    
    def _calculate_avg_access_age(self) -> float:
        """Calculate average age of cached items since last access."""
        if not self.access_times:
            return 0.0
        
        current_time = time.time()
        total_age = sum(current_time - access_time for access_time in self.access_times.values())
        return total_age / len(self.access_times)
    
    def clear(self) -> None:
        """Clear all cached items including TTL data."""
        super().clear()
        self.ttl_cache.clear()
        self.access_times.clear()
        self.hit_count = 0
        self.miss_count = 0
        self.eviction_count = 0    
    
    # Enhanced search and filtering methods using FileIndexer
    
    def search_files(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[VirtualFile]:
        """
        Search files using the advanced indexing system.
        
        Args:
            query: Search query (filename or pattern)
            filters: Optional filters (extension, language, size, etc.)
            
        Returns:
            List of matching VirtualFile objects
        """
        return self.file_indexer.search_files(query, filters)
    
    def find_files_by_extension(self, extension: str) -> List[VirtualFile]:
        """Find files by extension using O(1) index lookup."""
        return self.file_indexer.find_by_extension(extension)
    
    def find_files_by_language(self, language: str) -> List[VirtualFile]:
        """Find files by programming language using O(1) index lookup."""
        return self.file_indexer.find_by_language(language)
    
    def find_files_by_name(self, name: str) -> List[VirtualFile]:
        """Find files by name using O(1) index lookup."""
        return self.file_indexer.find_by_name(name)
    
    def find_files_in_directory(self, directory: str) -> List[VirtualFile]:
        """Find files in a specific directory using O(1) index lookup."""
        return self.file_indexer.find_by_directory(self._normalize_path(directory))
    
    def get_files_by_size_category(self, category: str) -> List[VirtualFile]:
        """Get files by size category (tiny, small, medium, large, huge)."""
        return self.file_indexer.find_by_size_category(category)
    
    def get_file_statistics(self) -> Dict[str, Any]:
        """Get comprehensive file statistics."""
        try:
            stats = {
                'total_files': len(self.file_index),
                'total_directories': len(self.directory_index),
                'file_types': {},
                'languages': {},
                'size_distribution': {},
                'directory_distribution': {},
                'largest_files': [],
                'most_common_extensions': []
            }
            
            # Collect file type statistics
            for virtual_file in self.file_index.values():
                # File types
                file_type = virtual_file.file_type
                stats['file_types'][file_type] = stats['file_types'].get(file_type, 0) + 1
                
                # Languages
                language = self._detect_language(virtual_file.path)
                stats['languages'][language] = stats['languages'].get(language, 0) + 1
                
                # Size distribution
                size_category = self.file_indexer._categorize_size(virtual_file.size)
                stats['size_distribution'][size_category] = stats['size_distribution'].get(size_category, 0) + 1
                
                # Directory distribution
                dir_path = os.path.dirname(virtual_file.path)
                stats['directory_distribution'][dir_path] = stats['directory_distribution'].get(dir_path, 0) + 1
            
            # Get largest files (top 10)
            sorted_files = sorted(self.file_index.values(), key=lambda f: f.size, reverse=True)
            stats['largest_files'] = [
                {'path': f.path, 'size': f.size, 'size_mb': f.size / (1024 * 1024)}
                for f in sorted_files[:10]
            ]
            
            # Get most common extensions
            extension_counts = {}
            for virtual_file in self.file_index.values():
                _, ext = os.path.splitext(virtual_file.path.lower())
                if ext:
                    extension_counts[ext] = extension_counts.get(ext, 0) + 1
            
            stats['most_common_extensions'] = sorted(
                extension_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting file statistics: {e}")
            return {}
    
    def warm_cache_intelligent(self, strategy: str = 'frequent') -> int:
        """
        Intelligently warm the cache based on different strategies.
        
        Args:
            strategy: Warming strategy ('frequent', 'small', 'important', 'recent')
            
        Returns:
            Number of files warmed
        """
        try:
            files_to_warm = []
            
            if strategy == 'frequent':
                # Warm frequently accessed file types
                important_extensions = ['.py', '.js', '.ts', '.json', '.md', '.yml', '.yaml']
                for ext in important_extensions:
                    files_to_warm.extend(self.find_files_by_extension(ext))
            
            elif strategy == 'small':
                # Warm small files that load quickly
                files_to_warm = self.get_files_by_size_category('tiny')
                files_to_warm.extend(self.get_files_by_size_category('small'))
            
            elif strategy == 'important':
                # Warm important files (config, main files, etc.)
                important_names = [
                    'main.py', 'app.py', 'index.js', 'package.json', 
                    'requirements.txt', 'Dockerfile', 'README.md',
                    'config.py', 'settings.py', '.env'
                ]
                for name in important_names:
                    files_to_warm.extend(self.find_files_by_name(name))
            
            elif strategy == 'recent':
                # Warm recently accessed files (if we had access tracking)
                # For now, just warm root level files
                files_to_warm = self.find_files_in_directory('')
            
            # Remove duplicates
            unique_files = list({f.path: f for f in files_to_warm}.values())
            
            # Warm cache
            file_paths = [f.path for f in unique_files[:50]]  # Limit to 50 files
            return self.content_cache.warm_cache(file_paths, self.get_file_content)
            
        except Exception as e:
            logger.error(f"Error warming cache with strategy {strategy}: {e}")
            return 0
    
    def cleanup_cache(self) -> Dict[str, int]:
        """Clean up expired cache items and return cleanup statistics."""
        try:
            expired_count = self.content_cache.cleanup_expired()
            
            # Also clear content from virtual files that haven't been accessed recently
            cleared_files = 0
            current_time = time.time()
            
            for virtual_file in self.file_index.values():
                if (virtual_file._content_loaded and 
                    virtual_file.path not in self.content_cache.access_times):
                    virtual_file._content = None
                    virtual_file._content_loaded = False
                    cleared_files += 1
            
            logger.info(f"Cache cleanup: {expired_count} expired items, {cleared_files} cleared files")
            
            return {
                'expired_items': expired_count,
                'cleared_files': cleared_files,
                'cache_size_after': len(self.content_cache.cache)
            }
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return {'expired_items': 0, 'cleared_files': 0, 'cache_size_after': 0}
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive VFS statistics including indexing and caching."""
        try:
            base_stats = self.get_stats()
            file_stats = self.get_file_statistics()
            index_stats = self.file_indexer.get_index_stats()
            cache_stats = self.content_cache.get_detailed_stats()
            
            return {
                'vfs_stats': base_stats,
                'file_statistics': file_stats,
                'indexing_stats': index_stats,
                'caching_stats': cache_stats,
                'performance_metrics': {
                    'total_access_count': self._access_count,
                    'cache_efficiency': cache_stats['hit_ratio'],
                    'memory_efficiency': cache_stats['memory_usage_mb'] / cache_stats['max_memory_mb'],
                    'index_efficiency': len(self.file_index) / max(index_stats['total_files'], 1)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting comprehensive stats: {e}")
            return {}
    
    def optimize_performance(self) -> Dict[str, Any]:
        """
        Optimize VFS performance by cleaning up and reorganizing data.
        
        Returns:
            Dictionary with optimization results
        """
        try:
            results = {}
            
            # Clean up expired cache items
            cleanup_stats = self.cleanup_cache()
            results['cache_cleanup'] = cleanup_stats
            
            # Warm cache with important files
            warmed_count = self.warm_cache_intelligent('important')
            results['cache_warming'] = {'files_warmed': warmed_count}
            
            # Update performance metrics
            self._update_performance_metrics()
            results['performance_update'] = True
            
            logger.info(f"Performance optimization completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error during performance optimization: {e}")
            return {'error': str(e)}
    
    def _update_performance_metrics(self) -> None:
        """Update internal performance metrics."""
        try:
            # Update cache hit ratio
            total_requests = self._cache_hits + self._cache_misses
            if total_requests > 0:
                hit_ratio = self._cache_hits / total_requests
                self.content_cache._hit_ratio = hit_ratio
            
        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")
    
    def validate_integrity(self) -> Dict[str, Any]:
        """
        Validate VFS integrity and consistency.
        
        Returns:
            Dictionary with validation results
        """
        try:
            results = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'statistics': {}
            }
            
            # Check file index consistency
            if len(self.file_index) != len(self.file_indexer.path_index):
                results['errors'].append(
                    f"File index mismatch: {len(self.file_index)} vs {len(self.file_indexer.path_index)}"
                )
                results['valid'] = False
            
            # Check directory structure consistency
            orphaned_files = 0
            for file_path, virtual_file in self.file_index.items():
                dir_path = os.path.dirname(file_path)
                if dir_path and dir_path not in self.directory_index and dir_path != '/':
                    orphaned_files += 1
            
            if orphaned_files > 0:
                results['warnings'].append(f"{orphaned_files} files have missing parent directories")
            
            # Check cache consistency
            cache_inconsistencies = 0
            for file_path in self.content_cache.cache.keys():
                if file_path not in self.file_index:
                    cache_inconsistencies += 1
            
            if cache_inconsistencies > 0:
                results['warnings'].append(f"{cache_inconsistencies} cached files not in file index")
            
            # Collect statistics
            results['statistics'] = {
                'total_files': len(self.file_index),
                'total_directories': len(self.directory_index),
                'cached_files': len(self.content_cache.cache),
                'orphaned_files': orphaned_files,
                'cache_inconsistencies': cache_inconsistencies
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error validating VFS integrity: {e}")
            return {
                'valid': False,
                'errors': [f"Validation error: {e}"],
                'warnings': [],
                'statistics': {}
            }


class GitSimulator:
    """
    Git operations simulator for Cosmos compatibility.
    
    Simulates git repository interface including:
    - Tracked files listing
    - Git status simulation
    - Repository root and branch information
    - Git-compatible path resolution and normalization
    """
    
    def __init__(self, vfs_instance):
        """
        Initialize Git simulator.
        
        Args:
            vfs_instance: IntelligentVFS instance
        """
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
    
    def get_modified_files(self) -> List[str]:
        """Get list of modified files."""
        return sorted(list(self.modified_files))
    
    def get_untracked_files(self) -> List[str]:
        """Get list of untracked files."""
        return sorted(list(self.untracked_files))
    
    def get_staged_files(self) -> List[str]:
        """Get list of staged files."""
        return sorted(list(self.staged_files))
    
    def get_git_status(self) -> Dict[str, Any]:
        """
        Get comprehensive git status information.
        
        Returns:
            Dictionary with git status information
        """
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
                    'modified': self.get_modified_files(),
                    'untracked': self.get_untracked_files(),
                    'staged': self.get_staged_files()
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting git status: {e}")
            return {}
    
    def is_tracked(self, file_path: str) -> bool:
        """Check if a file is tracked by git."""
        normalized_path = self.vfs._normalize_path(file_path)
        return normalized_path in self.tracked_files
    
    def is_modified(self, file_path: str) -> bool:
        """Check if a file is modified."""
        normalized_path = self.vfs._normalize_path(file_path)
        return normalized_path in self.modified_files
    
    def is_staged(self, file_path: str) -> bool:
        """Check if a file is staged."""
        normalized_path = self.vfs._normalize_path(file_path)
        return normalized_path in self.staged_files
    
    def get_file_status(self, file_path: str) -> str:
        """
        Get git status for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Git status string ('tracked', 'modified', 'untracked', 'staged')
        """
        normalized_path = self.vfs._normalize_path(file_path)
        
        if normalized_path in self.staged_files:
            return 'staged'
        elif normalized_path in self.modified_files:
            return 'modified'
        elif normalized_path in self.tracked_files:
            return 'tracked'
        else:
            return 'untracked'
    
    def simulate_git_add(self, file_paths: List[str]) -> Dict[str, str]:
        """
        Simulate git add operation.
        
        Args:
            file_paths: List of file paths to add
            
        Returns:
            Dictionary with results for each file
        """
        results = {}
        
        for file_path in file_paths:
            normalized_path = self.vfs._normalize_path(file_path)
            
            if normalized_path in self.vfs.file_index:
                # Move from modified/untracked to staged
                if normalized_path in self.modified_files:
                    self.modified_files.remove(normalized_path)
                if normalized_path in self.untracked_files:
                    self.untracked_files.remove(normalized_path)
                
                self.staged_files.add(normalized_path)
                self.tracked_files.add(normalized_path)
                results[file_path] = 'staged'
            else:
                results[file_path] = 'not_found'
        
        return results
    
    def simulate_git_commit(self, message: str) -> Dict[str, Any]:
        """
        Simulate git commit operation.
        
        Args:
            message: Commit message
            
        Returns:
            Dictionary with commit information
        """
        try:
            if not self.staged_files:
                return {
                    'success': False,
                    'error': 'No staged files to commit'
                }
            
            # Generate fake commit hash
            import hashlib
            commit_hash = hashlib.sha1(f"{message}{time.time()}".encode()).hexdigest()[:7]
            
            # Move staged files to tracked
            committed_files = list(self.staged_files)
            self.staged_files.clear()
            
            return {
                'success': True,
                'commit_hash': commit_hash,
                'message': message,
                'files_committed': len(committed_files),
                'files': committed_files
            }
            
        except Exception as e:
            logger.error(f"Error simulating git commit: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
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
    
    def resolve_git_path(self, path: str) -> str:
        """
        Resolve path relative to git repository root.
        
        Args:
            path: Path to resolve
            
        Returns:
            Resolved path relative to repo root
        """
        try:
            # Normalize the path
            normalized = self.vfs._normalize_path(path)
            
            # If path is absolute and starts with repo root, make it relative
            if normalized.startswith(self.repo_root.lstrip('/')):
                relative_path = normalized[len(self.repo_root.lstrip('/')):]
                return relative_path.lstrip('/')
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error resolving git path {path}: {e}")
            return path
    
    def get_git_ignore_patterns(self) -> List[str]:
        """Get simulated .gitignore patterns."""
        # Common gitignore patterns
        return [
            '*.pyc',
            '__pycache__/',
            '.env',
            '.venv/',
            'venv/',
            'node_modules/',
            '.DS_Store',
            '*.log',
            '.git/',
            'dist/',
            'build/',
            '*.egg-info/',
            '.pytest_cache/',
            '.coverage',
            '.mypy_cache/'
        ]
    
    def is_ignored(self, file_path: str) -> bool:
        """
        Check if a file would be ignored by git.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file would be ignored
        """
        try:
            import fnmatch
            
            patterns = self.get_git_ignore_patterns()
            normalized_path = self.vfs._normalize_path(file_path)
            
            for pattern in patterns:
                if fnmatch.fnmatch(normalized_path, pattern):
                    return True
                
                # Check if any parent directory matches
                path_parts = normalized_path.split('/')
                for i in range(len(path_parts)):
                    partial_path = '/'.join(path_parts[:i+1])
                    if fnmatch.fnmatch(partial_path, pattern):
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if file is ignored: {e}")
            return False
    
    def get_branch_info(self) -> Dict[str, Any]:
        """Get branch information."""
        return {
            'current_branch': self.current_branch,
            'branches': [self.current_branch, 'develop', 'feature/example'],  # Simulated branches
            'remote_branches': [f'origin/{self.current_branch}', 'origin/develop'],
            'upstream': f'origin/{self.current_branch}',
            'ahead': 0,  # Commits ahead of upstream
            'behind': 0  # Commits behind upstream
        }
    
    def simulate_branch_switch(self, branch_name: str) -> Dict[str, Any]:
        """
        Simulate switching to a different branch.
        
        Args:
            branch_name: Name of branch to switch to
            
        Returns:
            Dictionary with switch results
        """
        try:
            old_branch = self.current_branch
            self.current_branch = branch_name
            
            # Simulate some file changes when switching branches
            if branch_name != old_branch:
                # Clear modified files (simulate clean switch)
                self.modified_files.clear()
                self.staged_files.clear()
            
            return {
                'success': True,
                'old_branch': old_branch,
                'new_branch': branch_name,
                'files_changed': 0  # Simulate no conflicts
            }
            
        except Exception as e:
            logger.error(f"Error simulating branch switch: {e}")
            return {
                'success': False,
                'error': str(e)
            }


# Add Git simulation to IntelligentVFS
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
    
    # Git-compatible interface methods
    
    def get_tracked_files(self) -> List[str]:
        """Get list of git-tracked files."""
        return self.git_simulator.get_tracked_files()
    
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
    
    def resolve_path(self, path: str) -> str:
        """Resolve path relative to repository root."""
        return self.git_simulator.resolve_git_path(path)
    
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
                'cache_hit_ratio': getattr(self.content_cache, '_hit_ratio', 0.0)
            }
        }
    
    def simulate_git_operations(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simulate a series of git operations.
        
        Args:
            operations: List of operation dictionaries
            
        Returns:
            List of operation results
        """
        results = []
        
        for operation in operations:
            op_type = operation.get('type')
            
            try:
                if op_type == 'add':
                    result = self.git_simulator.simulate_git_add(operation.get('files', []))
                elif op_type == 'commit':
                    result = self.git_simulator.simulate_git_commit(operation.get('message', ''))
                elif op_type == 'branch':
                    result = self.git_simulator.simulate_branch_switch(operation.get('branch'))
                elif op_type == 'status':
                    result = self.git_simulator.get_git_status()
                else:
                    result = {'error': f'Unknown operation type: {op_type}'}
                
                results.append({
                    'operation': operation,
                    'result': result
                })
                
            except Exception as e:
                results.append({
                    'operation': operation,
                    'result': {'error': str(e)}
                })
        
        return results