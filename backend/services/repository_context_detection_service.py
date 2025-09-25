"""
Repository Context Detection Service

Automatically detects repository and branch context from /contribution page
and manages Redis caching with GitIngest integration.
"""

import os
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import redis
import requests

try:
    from ..config.key_manager import key_manager
    from ..services.repository_validation_service import repository_validation_service
    from ..integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
except ImportError:
    from config.key_manager import key_manager
    from services.repository_validation_service import repository_validation_service
    from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo

logger = logging.getLogger(__name__)


@dataclass
class RepositoryContext:
    """Repository context information."""
    url: str
    branch: str
    name: str
    owner: str
    is_private: bool
    size_mb: Optional[float] = None
    file_count: Optional[int] = None
    cached_at: Optional[datetime] = None
    validation_status: str = "unknown"  # unknown, valid, invalid, too_large
    error_message: Optional[str] = None


@dataclass
class SuggestedFile:
    """File suggested for context."""
    path: str
    name: str
    relevance_score: float
    language: Optional[str] = None
    size_bytes: Optional[int] = None
    show_plus_icon: bool = True


class RepositoryContextDetectionService:
    """Service for detecting and managing repository context."""
    
    def __init__(self):
        self.key_manager = key_manager
        self.validation_service = repository_validation_service
        
        # Initialize Redis connection
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Repository context detection service initialized with Redis")
        except Exception as e:
            logger.warning(f"Redis not available for repository context service: {e}")
            self.redis_available = False
            self.redis_client = None
    
    def detect_repository_context(self, page_context: Dict[str, Any]) -> Optional[RepositoryContext]:
        """
        Detect repository context from /contribution page context.
        
        Args:
            page_context: Context from the /contribution page
            
        Returns:
            RepositoryContext if detected, None otherwise
        """
        try:
            # Method 1: Direct repository URL from context
            repo_url = page_context.get('repository_url')
            if repo_url:
                logger.info(f"Repository URL detected from page context: {repo_url}")
                return self._create_repository_context(repo_url, page_context.get('branch', 'main'))
            
            # Method 2: Repository ID (owner/repo format)
            repo_id = page_context.get('repository_id')
            if repo_id and '/' in repo_id:
                repo_url = f"https://github.com/{repo_id}"
                logger.info(f"Repository URL constructed from ID: {repo_url}")
                return self._create_repository_context(repo_url, page_context.get('branch', 'main'))
            
            # Method 3: Separate owner and repo fields
            owner = page_context.get('owner')
            repo = page_context.get('repo')
            if owner and repo:
                repo_url = f"https://github.com/{owner}/{repo}"
                logger.info(f"Repository URL constructed from owner/repo: {repo_url}")
                return self._create_repository_context(repo_url, page_context.get('branch', 'main'))
            
            # Method 4: Extract from current URL or session storage
            current_url = page_context.get('current_url', '')
            if '/contribution' in current_url:
                # Try to extract repository info from URL parameters
                import urllib.parse
                parsed_url = urllib.parse.urlparse(current_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                if 'repo' in query_params:
                    repo_param = query_params['repo'][0]
                    try:
                        # Try to decode as JSON (encoded repository object)
                        repo_data = json.loads(urllib.parse.unquote(repo_param))
                        if isinstance(repo_data, dict) and 'full_name' in repo_data:
                            repo_url = f"https://github.com/{repo_data['full_name']}"
                            branch = repo_data.get('default_branch', 'main')
                            logger.info(f"Repository URL extracted from URL parameter: {repo_url}")
                            return self._create_repository_context(repo_url, branch)
                    except (json.JSONDecodeError, KeyError):
                        # Try as simple owner/repo format
                        if '/' in repo_param:
                            repo_url = f"https://github.com/{repo_param}"
                            logger.info(f"Repository URL from simple URL parameter: {repo_url}")
                            return self._create_repository_context(repo_url, page_context.get('branch', 'main'))
            
            logger.warning("No repository context could be detected from page context")
            return None
            
        except Exception as e:
            logger.error(f"Error detecting repository context: {e}")
            return None
    
    def _create_repository_context(self, repo_url: str, branch: str) -> RepositoryContext:
        """Create repository context from URL and branch."""
        try:
            # Parse repository URL
            if not repo_url.startswith('https://github.com/'):
                raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
            
            # Extract owner and repo name
            path_parts = repo_url.replace('https://github.com/', '').split('/')
            if len(path_parts) < 2:
                raise ValueError(f"Invalid repository URL format: {repo_url}")
            
            owner = path_parts[0]
            repo_name = path_parts[1]
            
            # Check if repository is private (basic heuristic)
            is_private = self._check_if_private_repository(repo_url)
            
            return RepositoryContext(
                url=repo_url,
                branch=branch,
                name=repo_name,
                owner=owner,
                is_private=is_private,
                validation_status="unknown"
            )
            
        except Exception as e:
            logger.error(f"Error creating repository context: {e}")
            raise
    
    def _check_if_private_repository(self, repo_url: str) -> bool:
        """Check if repository is private by attempting public access."""
        try:
            # Try to access the repository's public API endpoint
            api_url = repo_url.replace('https://github.com/', 'https://api.github.com/repos/')
            response = requests.get(api_url, timeout=5)
            
            if response.status_code == 200:
                repo_data = response.json()
                return repo_data.get('private', False)
            elif response.status_code == 404:
                # Could be private or non-existent
                return True
            else:
                # Assume private if we can't determine
                return True
                
        except Exception as e:
            logger.warning(f"Could not determine if repository is private: {e}")
            return True  # Assume private for safety
    
    async def validate_repository_size(self, repo_context: RepositoryContext, user_id: Optional[str] = None) -> RepositoryContext:
        """
        Validate repository size using the validation service.
        
        Args:
            repo_context: Repository context to validate
            user_id: User ID for token retrieval
            
        Returns:
            Updated repository context with validation results
        """
        try:
            validation_result = await self.validation_service.validate_repository_for_chat(
                repo_context.url, user_id
            )
            
            # Update context with validation results
            repo_context.size_mb = validation_result.size_mb
            repo_context.validation_status = "valid" if validation_result.is_valid else "invalid"
            repo_context.error_message = validation_result.error_message
            
            if validation_result.error_type == "repository_too_large":
                repo_context.validation_status = "too_large"
            elif validation_result.error_type == "github_rate_limit":
                repo_context.validation_status = "rate_limited"
                # Use the user-friendly message from validation result
                repo_context.error_message = validation_result.user_message or validation_result.error_message
            
            logger.info(f"Repository validation completed: {repo_context.validation_status}")
            return repo_context
            
        except Exception as e:
            logger.error(f"Error validating repository size: {e}")
            repo_context.validation_status = "error"
            repo_context.error_message = str(e)
            return repo_context
    
    def ensure_repository_cached(self, repo_context: RepositoryContext, user_id: Optional[str] = None) -> bool:
        """
        Ensure repository data is cached in Redis, fetching with GitIngest if needed.
        
        Args:
            repo_context: Repository context
            user_id: User ID for token retrieval
            
        Returns:
            True if repository is cached, False otherwise
        """
        if not self.redis_available:
            logger.warning("Redis not available, cannot cache repository data")
            return False
        
        try:
            cache_key = self._get_repository_cache_key(repo_context.url, repo_context.branch)
            
            # Check if already cached
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                try:
                    repo_data = json.loads(cached_data)
                    # Check if cache is still valid (24 hours)
                    cached_at = datetime.fromisoformat(repo_data.get('cached_at', ''))
                    if datetime.now() - cached_at < timedelta(hours=24):
                        logger.info(f"Repository data found in cache: {repo_context.url}")
                        return True
                    else:
                        logger.info(f"Repository cache expired, will refresh: {repo_context.url}")
                except (json.JSONDecodeError, ValueError, KeyError):
                    logger.warning(f"Invalid cached data for repository: {repo_context.url}")
            
            # Fetch repository data using GitIngest
            logger.info(f"Fetching repository data with GitIngest: {repo_context.url}")
            
            # Get GitHub token for user if available
            github_token = None
            if user_id:
                try:
                    github_token = self.key_manager.get_github_token(user_id)
                    if github_token:
                        logger.info(f"Using GitHub token for user {user_id}")
                except Exception as e:
                    logger.warning(f"Could not retrieve GitHub token: {e}")
            
            # Fetch repository with GitIngest
            repo_data = self._fetch_repository_with_gitingest(
                repo_url=repo_context.url,
                branch=repo_context.branch,
                github_token=github_token
            )
            
            if repo_data:
                # Add metadata
                repo_data['cached_at'] = datetime.now().isoformat()
                repo_data['repository_url'] = repo_context.url
                repo_data['branch'] = repo_context.branch
                
                # Cache the data with 24-hour TTL
                self.redis_client.setex(
                    cache_key,
                    timedelta(hours=24),
                    json.dumps(repo_data)
                )
                
                # Update repository context with file count
                repo_context.file_count = len(repo_data.get('files', []))
                repo_context.cached_at = datetime.now()
                
                logger.info(f"Repository data cached successfully: {repo_context.file_count} files")
                return True
            else:
                logger.error(f"Failed to fetch repository data with GitIngest")
                return False
                
        except Exception as e:
            logger.error(f"Error ensuring repository is cached: {e}")
            return False
    
    def get_cached_repository_data(self, repo_url: str, branch: str = "main") -> Optional[Dict[str, Any]]:
        """
        Get cached repository data from Redis.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            Cached repository data or None
        """
        if not self.redis_available:
            return None
        
        try:
            cache_key = self._get_repository_cache_key(repo_url, branch)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                repo_data = json.loads(cached_data)
                # Check if cache is still valid
                cached_at = datetime.fromisoformat(repo_data.get('cached_at', ''))
                if datetime.now() - cached_at < timedelta(hours=24):
                    return repo_data
                else:
                    # Cache expired, remove it
                    self.redis_client.delete(cache_key)
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached repository data: {e}")
            return None
    
    def get_suggested_files(self, repo_context: RepositoryContext, limit: int = 10) -> List[SuggestedFile]:
        """
        Get suggested files for context based on repository analysis.
        
        Args:
            repo_context: Repository context
            limit: Maximum number of files to suggest
            
        Returns:
            List of suggested files
        """
        try:
            # Get cached repository data
            repo_data = self.get_cached_repository_data(repo_context.url, repo_context.branch)
            if not repo_data:
                logger.warning(f"No cached data available for suggestions: {repo_context.url}")
                return []
            
            files = repo_data.get('files', [])
            if not files:
                return []
            
            # Score files based on importance
            scored_files = []
            for file_info in files:
                file_path = file_info.get('path', '')
                file_name = os.path.basename(file_path)
                file_size = file_info.get('size', 0)
                
                # Calculate relevance score
                score = self._calculate_file_relevance_score(file_path, file_name, file_size)
                
                if score > 0:  # Only include files with positive scores
                    suggested_file = SuggestedFile(
                        path=file_path,
                        name=file_name,
                        relevance_score=score,
                        language=self._detect_file_language(file_path),
                        size_bytes=file_size,
                        show_plus_icon=True
                    )
                    scored_files.append(suggested_file)
            
            # Sort by relevance score and return top files
            scored_files.sort(key=lambda f: f.relevance_score, reverse=True)
            return scored_files[:limit]
            
        except Exception as e:
            logger.error(f"Error getting suggested files: {e}")
            return []
    
    def _calculate_file_relevance_score(self, file_path: str, file_name: str, file_size: int) -> float:
        """Calculate relevance score for a file."""
        score = 0.0
        
        # Important files get higher scores
        important_files = {
            'README.md': 10.0,
            'README.rst': 9.0,
            'README.txt': 8.0,
            'package.json': 9.0,
            'requirements.txt': 8.0,
            'Cargo.toml': 8.0,
            'pom.xml': 8.0,
            'build.gradle': 8.0,
            'Dockerfile': 7.0,
            'docker-compose.yml': 7.0,
            'main.py': 7.0,
            'index.js': 7.0,
            'index.ts': 7.0,
            'app.py': 7.0,
            'server.js': 7.0,
            'main.go': 7.0,
            'main.rs': 7.0,
        }
        
        if file_name.lower() in [k.lower() for k in important_files.keys()]:
            for important_file, important_score in important_files.items():
                if file_name.lower() == important_file.lower():
                    score += important_score
                    break
        
        # Code files get medium scores
        code_extensions = {
            '.py': 5.0, '.js': 5.0, '.ts': 5.0, '.java': 5.0, '.cpp': 5.0,
            '.c': 5.0, '.go': 5.0, '.rs': 5.0, '.php': 4.0, '.rb': 4.0,
            '.swift': 4.0, '.kt': 4.0, '.scala': 4.0, '.clj': 4.0
        }
        
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext in code_extensions:
            score += code_extensions[file_ext]
        
        # Configuration files get medium scores
        config_extensions = {
            '.json': 3.0, '.yaml': 3.0, '.yml': 3.0, '.toml': 3.0,
            '.ini': 2.0, '.conf': 2.0, '.config': 2.0
        }
        
        if file_ext in config_extensions:
            score += config_extensions[file_ext]
        
        # Penalize very large files
        if file_size > 100000:  # 100KB
            score *= 0.5
        elif file_size > 50000:  # 50KB
            score *= 0.8
        
        # Penalize files in certain directories
        path_lower = file_path.lower()
        if any(dir_name in path_lower for dir_name in ['node_modules', '.git', '__pycache__', 'target', 'build', 'dist']):
            score *= 0.1
        
        # Boost files in important directories
        if any(dir_name in path_lower for dir_name in ['src', 'lib', 'app', 'core', 'main']):
            score *= 1.2
        
        return score
    
    def _detect_file_language(self, file_path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        ext_to_lang = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.go': 'Go',
            '.rs': 'Rust',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.clj': 'Clojure',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.less': 'LESS',
            '.md': 'Markdown',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.toml': 'TOML',
            '.xml': 'XML',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.bash': 'Bash',
            '.zsh': 'Zsh',
            '.fish': 'Fish'
        }
        
        file_ext = os.path.splitext(file_path)[1].lower()
        return ext_to_lang.get(file_ext)
    
    def clear_repository_cache(self, repo_url: str, branch: str = "main") -> bool:
        """
        Clear repository cache from Redis.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            
        Returns:
            True if cache was cleared, False otherwise
        """
        if not self.redis_available:
            return False
        
        try:
            cache_key = self._get_repository_cache_key(repo_url, branch)
            result = self.redis_client.delete(cache_key)
            logger.info(f"Repository cache cleared: {repo_url} (branch: {branch})")
            return result > 0
            
        except Exception as e:
            logger.error(f"Error clearing repository cache: {e}")
            return False
    
    def cleanup_user_cache(self, user_id: str) -> int:
        """
        Clean up all repository caches for a user when they navigate away from /contribution.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of cache entries cleared
        """
        if not self.redis_available:
            return 0
        
        try:
            # Find all cache keys for this user
            pattern = f"repo_cache:*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Cleaned up {deleted} repository cache entries for user {user_id}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error cleaning up user cache: {e}")
            return 0
    
    def _fetch_repository_with_gitingest(self, repo_url: str, branch: str, github_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch repository data using GitIngest.
        
        Args:
            repo_url: Repository URL
            branch: Branch name
            github_token: GitHub token for authentication
            
        Returns:
            Repository data or None if failed
        """
        try:
            from gitingest import ingest
            
            # Configure GitIngest options
            options = {
                'include_patterns': ['*'],
                'exclude_patterns': [
                    '.git/*', 
                    'node_modules/*', 
                    '__pycache__/*',
                    '*.pyc',
                    '.DS_Store',
                    'Thumbs.db',
                    '*.log',
                    'dist/*',
                    'build/*',
                    'target/*',
                    '.vscode/*',
                    '.idea/*'
                ],
                'max_file_size': 1024 * 1024  # 1MB per file
            }
            
            # Add GitHub token if available
            if github_token:
                options['github_token'] = github_token
            
            # Use GitIngest to fetch repository
            logger.info(f"Fetching repository with GitIngest: {repo_url} (branch: {branch})")
            
            # GitIngest expects the repository URL in a specific format
            if branch != 'main' and branch != 'master':
                # For non-default branches, we need to specify the branch
                ingest_url = f"{repo_url}/tree/{branch}"
            else:
                ingest_url = repo_url
            
            # Fetch the repository
            result = ingest(ingest_url, **options)
            
            if result and hasattr(result, 'files'):
                # Convert GitIngest result to our format
                files = []
                for file_info in result.files:
                    files.append({
                        'path': file_info.path,
                        'content': file_info.content,
                        'size': len(file_info.content.encode('utf-8')),
                        'type': 'file'
                    })
                
                repo_data = {
                    'files': files,
                    'repository_url': repo_url,
                    'branch': branch,
                    'total_files': len(files),
                    'total_size': sum(f['size'] for f in files),
                    'fetched_at': datetime.now().isoformat()
                }
                
                logger.info(f"Successfully fetched {len(files)} files from repository")
                return repo_data
            else:
                logger.error("GitIngest returned empty or invalid result")
                return None
                
        except ImportError:
            logger.error("GitIngest not available - install with: pip install gitingest")
            return None
        except Exception as e:
            logger.error(f"Error fetching repository with GitIngest: {e}")
            return None

    def _get_repository_cache_key(self, repo_url: str, branch: str) -> str:
        """Generate Redis cache key for repository data."""
        # Normalize the URL and branch for consistent caching
        normalized_url = repo_url.lower().rstrip('/')
        normalized_branch = branch.lower()
        return f"repo_cache:{normalized_url}:{normalized_branch}"
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        if not self.redis_available:
            return {"redis_available": False}
        
        try:
            pattern = "repo_cache:*"
            keys = self.redis_client.keys(pattern)
            
            stats = {
                "redis_available": True,
                "total_cached_repositories": len(keys),
                "cache_keys": keys[:10] if keys else [],  # Show first 10 keys
                "memory_usage": self.redis_client.memory_usage() if hasattr(self.redis_client, 'memory_usage') else None
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"redis_available": True, "error": str(e)}


# Global instance
repository_context_service = RepositoryContextDetectionService()