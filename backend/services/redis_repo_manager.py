"""
Redis Repository Manager with KeyManager Integration

Provides GitRepo-compatible interface using Redis Cloud storage with secure token management.
Integrates with existing KeyManager for secure GitHub token retrieval from HashiCorp Vault.
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:
    # Try relative imports first (when used as module)
    from ..config.settings import get_settings
    from ..config.key_manager import key_manager
    from ..integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
    from ..integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
except ImportError:
    # Fall back to absolute imports (when used directly)
    from config.settings import get_settings
    from config.key_manager import key_manager
    from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
    from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """File metadata information."""
    path: str
    name: str
    size: int
    language: str
    is_tracked: bool
    last_modified: Optional[str] = None


class RedisRepoManager:
    """
    Redis Repository Manager with KeyManager Integration
    
    Provides GitRepo-compatible interface using Redis Cloud storage with secure token management.
    Integrates with existing KeyManager for secure GitHub token retrieval from HashiCorp Vault.
    """
    
    def __init__(
        self, 
        repo_url: str, 
        branch: str = "main", 
        user_tier: str = "free", 
        username: Optional[str] = None
    ):
        """
        Initialize Redis Repository Manager.
        
        Args:
            repo_url: GitHub repository URL
            branch: Branch name (default: "main")
            user_tier: User tier for access control
            username: Username for secure token retrieval
        """
        self.repo_url = repo_url
        self.branch = branch
        self.user_tier = user_tier
        self.username = username
        
        # Initialize Cosmos configuration if not already done
        try:
            from integrations.cosmos.v1.cosmos.config import initialize_configuration
            initialize_configuration()
        except Exception as e:
            logger.warning(f"Could not initialize Cosmos configuration: {e}")
        
        # Initialize services
        self.settings = get_settings()
        self.key_manager = key_manager
        self.redis_cache = SmartRedisCache()
        
        # Parse repository information
        self.repo_name = self._extract_repo_name(repo_url)
        self.owner, self.repo = self._parse_github_url(repo_url)
        
        # Cache for file operations
        self._file_cache: Dict[str, str] = {}
        self._repo_map_cache: Optional[str] = None
        self._file_list_cache: Optional[List[str]] = None
        self._metadata_cache: Dict[str, FileMetadata] = {}
        
        # Virtual filesystem state
        self._tracked_files: Optional[List[str]] = None
        
        logger.info(f"Initialized RedisRepoManager for {self.repo_name} (branch: {self.branch})")
    
    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repository name from GitHub URL."""
        try:
            # Handle SSH URLs like git@github.com:owner/repo.git
            if repo_url.startswith('git@'):
                # Extract the part after the colon
                if ':' in repo_url:
                    path_part = repo_url.split(':', 1)[1]
                    path_parts = [part for part in path_part.strip('/').split('/') if part]
                else:
                    raise ValueError("Invalid SSH URL format")
            else:
                # Handle HTTPS URLs
                path = urlparse(repo_url).path
                path_parts = [part for part in path.strip('/').split('/') if part]
            
            if len(path_parts) < 2:
                raise ValueError("URL must contain owner and repository name")
            
            # Create full repo identifier with owner for uniqueness
            repo_name = path_parts[1].replace('.git', '')
            full_repo_name = f"{path_parts[0]}/{repo_name}"
            return full_repo_name
            
        except Exception as e:
            raise ValueError(f"Could not determine repository name from URL '{repo_url}': {e}")
    
    def _parse_github_url(self, repo_url: str) -> Tuple[str, str]:
        """Parse GitHub URL to extract owner and repository name."""
        try:
            # Handle SSH URLs like git@github.com:owner/repo.git
            if repo_url.startswith('git@'):
                # Extract the part after the colon
                if ':' in repo_url:
                    path_part = repo_url.split(':', 1)[1]
                    path_parts = [part for part in path_part.strip('/').split('/') if part]
                else:
                    raise ValueError("Invalid SSH URL format")
            else:
                # Handle HTTPS URLs
                path = urlparse(repo_url).path
                path_parts = [part for part in path.strip('/').split('/') if part]
            
            if len(path_parts) < 2:
                raise ValueError("Invalid GitHub URL format")
            
            owner = path_parts[0]
            repo = path_parts[1].replace('.git', '')
            
            return owner, repo
            
        except Exception as e:
            raise ValueError(f"Could not parse GitHub URL '{repo_url}': {e}")
    
    def _get_github_token(self, username: str) -> Optional[str]:
        """
        Retrieve GitHub token using existing KeyManager.
        
        Args:
            username: Username for token retrieval
            
        Returns:
            GitHub token or None if not available
        """
        if not username:
            logger.warning("No username provided for GitHub token retrieval")
            return None
        
        try:
            token = self.key_manager.get_github_token(username)
            if token:
                logger.info(f"Successfully retrieved GitHub token for user: {username}")
                return token
            else:
                logger.warning(f"No GitHub token found for user: {username}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve GitHub token for {username}: {e}")
            return None
    
    def _is_private_repository(self, repo_url: str) -> bool:
        """
        Check if repository requires authentication.
        
        This is a simplified check - in production, you might want to make
        an actual API call to determine repository visibility.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            True if repository is likely private, False otherwise
        """
        # For now, assume all repositories might be private and let the token
        # be used if available. The actual privacy check would require an API call.
        return True
    
    async def fetch_repository_with_auth(self, repo_url: str) -> bool:
        """
        Fetch repository with KeyManager token authentication.
        
        Args:
            repo_url: Repository URL to fetch
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Set up environment for fetch operation
            original_token = os.environ.get("GITHUB_TOKEN")
            original_tier = os.environ.get("TIER_PLAN")
            
            try:
                # Get GitHub token if username is provided
                github_token = None
                if self.username:
                    github_token = self._get_github_token(self.username)
                    if github_token and len(github_token.strip()) > 10:  # Basic validation
                        os.environ["GITHUB_TOKEN"] = github_token
                        logger.info("Using KeyManager GitHub token for repository fetch")
                    else:
                        logger.info("No valid GitHub token available, proceeding without authentication")
                        # Clear any invalid token
                        if "GITHUB_TOKEN" in os.environ:
                            del os.environ["GITHUB_TOKEN"]
                else:
                    logger.info("No username provided, proceeding without authentication")
                    # Clear any existing token to avoid conflicts
                    if "GITHUB_TOKEN" in os.environ:
                        del os.environ["GITHUB_TOKEN"]
                
                # Set tier plan
                os.environ["TIER_PLAN"] = self.user_tier
                
                # Use existing fetch_and_store_repo function with asyncio fix
                import asyncio
                try:
                    # Check if we're already in an event loop
                    loop = asyncio.get_running_loop()
                    # If we're in a running loop, use run_in_executor to avoid the error
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = loop.run_in_executor(executor, fetch_and_store_repo, repo_url)
                        success = await asyncio.wait_for(future, timeout=300)  # 5 minute timeout
                except RuntimeError:
                    # No running loop, safe to use direct call
                    success = fetch_and_store_repo(repo_url)
                
                if success:
                    logger.info(f"Successfully fetched repository: {repo_url}")
                    # Clear caches to force reload
                    self._clear_caches()
                else:
                    logger.error(f"Failed to fetch repository: {repo_url}")
                
                return success
                
            finally:
                # Restore original environment
                if original_token is not None:
                    os.environ["GITHUB_TOKEN"] = original_token
                elif "GITHUB_TOKEN" in os.environ:
                    del os.environ["GITHUB_TOKEN"]
                
                if original_tier is not None:
                    os.environ["TIER_PLAN"] = original_tier
                elif "TIER_PLAN" in os.environ:
                    del os.environ["TIER_PLAN"]
                    
        except Exception as e:
            logger.error(f"Error during authenticated repository fetch: {e}")
            # Try without authentication as fallback for public repositories
            logger.info("Attempting to fetch repository without authentication as fallback")
            try:
                # Clear any problematic tokens
                if "GITHUB_TOKEN" in os.environ:
                    del os.environ["GITHUB_TOKEN"]
                os.environ["TIER_PLAN"] = self.user_tier
                
                # Use existing fetch_and_store_repo function with asyncio fix
                import asyncio
                try:
                    # Check if we're already in an event loop
                    loop = asyncio.get_running_loop()
                    # If we're in a running loop, use run_in_executor to avoid the error
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = loop.run_in_executor(executor, fetch_and_store_repo, repo_url)
                        success = await asyncio.wait_for(future, timeout=300)  # 5 minute timeout
                except RuntimeError:
                    # No running loop, safe to use direct call
                    success = fetch_and_store_repo(repo_url)
                if success:
                    logger.info(f"Successfully fetched repository without authentication: {repo_url}")
                    self._clear_caches()
                    return True
                else:
                    logger.error(f"Failed to fetch repository even without authentication: {repo_url}")
                    return False
            except Exception as fallback_error:
                logger.error(f"Fallback fetch also failed: {fallback_error}")
                return False
    
    def _clear_caches(self) -> None:
        """Clear all internal caches."""
        self._file_cache.clear()
        self._repo_map_cache = None
        self._file_list_cache = None
        self._metadata_cache.clear()
        self._tracked_files = None
    
    async def _ensure_repository_data(self) -> bool:
        """
        Ensure repository data is available in Redis.
        
        Returns:
            True if data is available, False otherwise
        """
        try:
            # Check if repository exists in Redis
            existence_info = self.redis_cache.exists_with_metadata(self.repo_name)
            
            if existence_info['exists']:
                logger.debug(f"Repository data found in Redis: {self.repo_name}")
                return True
            
            logger.info(f"Repository data not found in Redis, fetching: {self.repo_name}")
            
            # Fetch repository data
            return await self.fetch_repository_with_auth(self.repo_url)
            
        except Exception as e:
            logger.error(f"Error ensuring repository data: {e}")
            return False
    
    async def get_file_content(self, file_path: str) -> Optional[str]:
        """
        Get file content from Redis storage.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File content or None if not found
        """
        try:
            # Check cache first
            if file_path in self._file_cache:
                return self._file_cache[file_path]
            
            # Ensure repository data is available
            if not await self._ensure_repository_data():
                logger.error(f"Repository data not available for file: {file_path}")
                return None
            
            # Get repository data from Redis
            repo_data = self.redis_cache.get_repository_data_cached(self.repo_name)
            if not repo_data:
                logger.error(f"No repository data found in Redis: {self.repo_name}")
                return None
            
            # Parse content.md to find the specific file
            content_md = repo_data.get('content', '')
            if not content_md:
                logger.error(f"No content data found for repository: {self.repo_name}")
                return None
            
            # Extract file content from content.md
            file_content = self._extract_file_from_content(content_md, file_path)
            
            if file_content is not None:
                # Cache the result
                self._file_cache[file_path] = file_content
                logger.debug(f"Retrieved file content: {file_path}")
            else:
                logger.warning(f"File not found in repository content: {file_path}")
            
            return file_content
            
        except Exception as e:
            logger.error(f"Error getting file content for {file_path}: {e}")
            return None
    
    def _extract_file_from_content(self, content_md: str, file_path: str) -> Optional[str]:
        """
        Extract specific file content from content.md format.
        
        Args:
            content_md: Content.md string from GitIngest
            file_path: Path to the file to extract
            
        Returns:
            File content or None if not found
        """
        try:
            # GitIngest format typically uses file path headers like:
            # ## path/to/file.py
            # ```python
            # file content here
            # ```
            
            # Normalize file path for matching
            normalized_path = file_path.lstrip('./')
            
            # Look for file header patterns - GitIngest uses "FILE: path/to/file.py" format
            patterns = [
                rf"^FILE: .*{re.escape(normalized_path)}\s*$",  # GitIngest format
                rf"^## {re.escape(normalized_path)}\s*$",
                rf"^### {re.escape(normalized_path)}\s*$",
                rf"^# {re.escape(normalized_path)}\s*$",
                rf"^File: {re.escape(normalized_path)}\s*$",
                rf"^{re.escape(normalized_path)}:\s*$"
            ]
            
            lines = content_md.split('\n')
            file_start_idx = None
            
            # Find the file header
            for i, line in enumerate(lines):
                for pattern in patterns:
                    if re.match(pattern, line, re.MULTILINE):
                        file_start_idx = i
                        break
                if file_start_idx is not None:
                    break
            
            if file_start_idx is None:
                return None
            
            # Find the content between code blocks or until next file
            content_lines = []
            in_code_block = False
            code_block_lang = None
            
            for i in range(file_start_idx + 1, len(lines)):
                line = lines[i]
                
                # Check for next file header
                for pattern in [r'^##?\s+\S', r'^File:\s+\S', r'^\S+:\s*$']:
                    if re.match(pattern, line) and not in_code_block:
                        # Found next file, stop here
                        return '\n'.join(content_lines).strip()
                
                # Handle code blocks
                if line.startswith('```'):
                    if not in_code_block:
                        in_code_block = True
                        code_block_lang = line[3:].strip()
                        continue
                    else:
                        in_code_block = False
                        break
                
                # Collect content lines
                if in_code_block:
                    content_lines.append(line)
                elif line.strip():  # Non-empty line outside code block
                    content_lines.append(line)
            
            return '\n'.join(content_lines).strip() if content_lines else None
            
        except Exception as e:
            logger.error(f"Error extracting file content for {file_path}: {e}")
            return None
    
    async def get_repo_map(self) -> Optional[str]:
        """
        Get repository map from Redis storage.
        
        Returns:
            Repository map string or None if not available
        """
        try:
            # Check cache first
            if self._repo_map_cache is not None:
                return self._repo_map_cache
            
            # Ensure repository data is available
            if not await self._ensure_repository_data():
                logger.error("Repository data not available for repo map")
                return None
            
            # Get repository data from Redis
            repo_data = self.redis_cache.get_repository_data_cached(self.repo_name)
            if not repo_data:
                logger.error(f"No repository data found in Redis: {self.repo_name}")
                return None
            
            # Get tree data (repository structure)
            tree_data = repo_data.get('tree', '')
            if not tree_data:
                logger.error(f"No tree data found for repository: {self.repo_name}")
                return None
            
            # Cache and return
            self._repo_map_cache = tree_data
            logger.debug(f"Retrieved repository map for: {self.repo_name}")
            return tree_data
            
        except Exception as e:
            logger.error(f"Error getting repository map: {e}")
            return None
    
    async def list_files(self, pattern: Optional[str] = None) -> List[str]:
        """
        List files in the repository.
        
        Args:
            pattern: Optional pattern to filter files
            
        Returns:
            List of file paths
        """
        try:
            # Check cache first
            if self._file_list_cache is not None:
                files = self._file_list_cache
            else:
                # Get repository map
                repo_map = await self.get_repo_map()
                if not repo_map:
                    logger.error("No repository map available")
                    return []
                
                # Extract file paths from tree structure
                files = self._extract_files_from_tree(repo_map)
                self._file_list_cache = files
            
            # Apply pattern filter if provided
            if pattern:
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f, pattern)]
            
            return files
            
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    def _extract_files_from_tree(self, tree_data: str) -> List[str]:
        """
        Extract file paths from tree structure.
        
        Args:
            tree_data: Tree structure string
            
        Returns:
            List of file paths
        """
        try:
            files = []
            lines = tree_data.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Skip directory indicators and tree symbols
                if line.endswith('/') or line.endswith('\\'):
                    continue
                
                # Remove tree symbols and extract file path
                # Common tree symbols: ├──, └──, │, ─, etc.
                clean_line = re.sub(r'^[├└│─\s]*', '', line)
                clean_line = clean_line.strip()
                
                if clean_line and not clean_line.endswith('/'):
                    # This looks like a file
                    files.append(clean_line)
            
            return files
            
        except Exception as e:
            logger.error(f"Error extracting files from tree: {e}")
            return []
    
    async def get_file_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """
        Get file metadata.
        
        Args:
            file_path: Path to the file
            
        Returns:
            FileMetadata object or None if not found
        """
        try:
            # Check cache first
            if file_path in self._metadata_cache:
                return self._metadata_cache[file_path]
            
            # Check if file exists
            content = await self.get_file_content(file_path)
            if content is None:
                return None
            
            # Determine language from file extension
            language = self._detect_language(file_path)
            
            # Create metadata
            metadata = FileMetadata(
                path=file_path,
                name=os.path.basename(file_path),
                size=len(content.encode('utf-8')),
                language=language,
                is_tracked=await self.is_file_tracked(file_path)
            )
            
            # Cache and return
            self._metadata_cache[file_path] = metadata
            return metadata
            
        except Exception as e:
            logger.error(f"Error getting file metadata for {file_path}: {e}")
            return None
    
    def _detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language name
        """
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.cs': 'csharp',
            '.php': 'php',
            '.rb': 'ruby',
            '.go': 'go',
            '.rs': 'rust',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'zsh',
            '.fish': 'fish',
            '.ps1': 'powershell',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.sass': 'sass',
            '.less': 'less',
            '.xml': 'xml',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.toml': 'toml',
            '.ini': 'ini',
            '.cfg': 'ini',
            '.conf': 'conf',
            '.md': 'markdown',
            '.rst': 'rst',
            '.txt': 'text',
            '.sql': 'sql',
            '.r': 'r',
            '.R': 'r',
            '.m': 'matlab',
            '.pl': 'perl',
            '.lua': 'lua',
            '.vim': 'vim',
            '.dockerfile': 'dockerfile',
            '.gitignore': 'gitignore',
            '.env': 'env'
        }
        
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        
        # Check for special filenames
        filename = os.path.basename(file_path.lower())
        if filename in ['dockerfile', 'makefile', 'rakefile', 'gemfile']:
            return filename
        
        return extension_map.get(ext, 'text')
    
    async def is_file_tracked(self, file_path: str) -> bool:
        """
        Check if file is tracked in the repository.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file is tracked, False otherwise
        """
        try:
            tracked_files = await self.get_tracked_files()
            return file_path in tracked_files
            
        except Exception as e:
            logger.error(f"Error checking if file is tracked: {e}")
            return False
    
    async def get_tracked_files(self) -> List[str]:
        """
        Get list of tracked files.
        
        Returns:
            List of tracked file paths
        """
        try:
            if self._tracked_files is not None:
                return self._tracked_files
            
            # For Redis-based repositories, all files in the content are considered tracked
            files = await self.list_files()
            self._tracked_files = files
            return files
            
        except Exception as e:
            logger.error(f"Error getting tracked files: {e}")
            return []
    
    def normalize_path(self, path: str) -> str:
        """
        Normalize file path for consistent handling.
        
        Args:
            path: File path to normalize
            
        Returns:
            Normalized path
        """
        try:
            # Handle empty string case
            if not path:
                return ""
            
            # Convert backslashes to forward slashes for consistency
            normalized = path.replace('\\', '/')
            
            # Convert to PurePosixPath for consistent handling
            normalized = str(PurePosixPath(normalized))
            
            # Remove leading ./ if present
            if normalized.startswith('./'):
                normalized = normalized[2:]
            
            # Handle case where path becomes just "." after normalization
            if normalized == ".":
                return ""
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing path {path}: {e}")
            return path
    
    async def get_repository_info(self) -> Dict[str, Any]:
        """
        Get repository information and metadata.
        
        Returns:
            Dictionary with repository information
        """
        try:
            # Ensure repository data is available
            if not await self._ensure_repository_data():
                return {}
            
            # Get repository data from Redis
            repo_data = self.redis_cache.get_repository_data_cached(self.repo_name)
            if not repo_data:
                return {}
            
            # Get metadata
            metadata = repo_data.get('metadata', {})
            
            # Get file count
            files = await self.list_files()
            
            return {
                'name': self.repo_name,
                'url': self.repo_url,
                'branch': self.branch,
                'owner': self.owner,
                'repo': self.repo,
                'file_count': len(files),
                'stored_at': metadata.get('stored_at'),
                'estimated_tokens': metadata.get('estimated_tokens'),
                'user_tier': metadata.get('user_tier'),
                'has_content': bool(repo_data.get('content')),
                'has_tree': bool(repo_data.get('tree')),
                'has_summary': bool(repo_data.get('summary'))
            }
            
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return {}