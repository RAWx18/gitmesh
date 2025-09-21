# print('RELOADING GITHUB_UTILS.PY')
"""GitHub API utilities and helper functions"""

import os
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode
import aiohttp
import logging
from cachetools import TTLCache

from config.settings import get_settings
from config.key_manager import KeyManager

logger = logging.getLogger(__name__)
settings = get_settings()


class GitHubRateLimitManager:
    """GitHub API rate limit manager."""
    
    def __init__(self):
        self.rate_limits = {}
        self.statistics = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'rate_limit_hits': 0
        }
    
    def update_rate_limit(self, token: str, headers: Dict[str, str]):
        """Update rate limit information from response headers."""
        try:
            self.rate_limits[token] = {
                'limit': int(headers.get('x-ratelimit-limit', 5000)),
                'remaining': int(headers.get('x-ratelimit-remaining', 5000)),
                'reset': int(headers.get('x-ratelimit-reset', 0)),
                'used': int(headers.get('x-ratelimit-used', 0)),
                'resource': headers.get('x-ratelimit-resource', 'core'),
                'last_updated': datetime.now()
            }
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")
    
    def get_rate_limit_status(self, token: str) -> Dict[str, Any]:
        """Get current rate limit status for token."""
        if token not in self.rate_limits:
            return {
                'limit': 5000,
                'remaining': 5000,
                'used': 0,
                'reset': int((datetime.now() + timedelta(hours=1)).timestamp()),
                'reset_date': (datetime.now() + timedelta(hours=1)).isoformat(),
                'is_near_limit': False,
                'is_rate_limited': False,
                'resource': 'core'
            }
        
        rate_limit = self.rate_limits[token]
        reset_date = datetime.fromtimestamp(rate_limit['reset'])
        
        return {
            'limit': rate_limit['limit'],
            'remaining': rate_limit['remaining'],
            'used': rate_limit['used'],
            'reset': rate_limit['reset'],
            'reset_date': reset_date.isoformat(),
            'is_near_limit': rate_limit['remaining'] < (rate_limit['limit'] * 0.2),
            'is_rate_limited': rate_limit['remaining'] <= 0,
            'resource': rate_limit['resource']
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics."""
        total_requests = self.statistics['total_requests']
        cache_hits = self.statistics['cache_hits']
        
        return {
            'total_requests': total_requests,
            'cache_hits': cache_hits,
            'cache_misses': self.statistics['cache_misses'],
            'rate_limit_hits': self.statistics['rate_limit_hits'],
            'cache_hit_rate': (cache_hits / total_requests * 100) if total_requests > 0 else 0
        }


class GitHubCacheManager:
    """GitHub API response cache manager."""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.cache = TTLCache(maxsize=max_size, ttl=ttl)
        self.statistics = {
            'hits': 0,
            'misses': 0,
            'size': 0
        }
    
    def _generate_key(self, url: str, params: Dict[str, Any] = None) -> str:
        """Generate cache key from URL and parameters."""
        if params:
            url += '?' + urlencode(sorted(params.items()), doseq=True)
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str, params: Dict[str, Any] = None) -> Optional[Any]:
        """Get cached response."""
        key = self._generate_key(url, params)
        
        if key in self.cache:
            self.statistics['hits'] += 1
            return self.cache[key]
        
        self.statistics['misses'] += 1
        return None
    
    def set(self, url: str, data: Any, params: Dict[str, Any] = None):
        """Cache response data."""
        key = self._generate_key(url, params)
        self.cache[key] = data
        self.statistics['size'] = len(self.cache)
    
    def clear(self):
        """Clear all cached data."""
        self.cache.clear()
        self.statistics['size'] = 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.statistics['hits'] + self.statistics['misses']
        
        return {
            'hits': self.statistics['hits'],
            'misses': self.statistics['misses'],
            'size': self.statistics['size'],
            'hit_rate': (self.statistics['hits'] / total_requests * 100) if total_requests > 0 else 0
        }


class GitHubAPIClient:
    """GitHub API client with rate limiting and caching."""
    
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.rate_limit_manager = GitHubRateLimitManager()
        self.cache_manager = GitHubCacheManager()
        self.timeout = aiohttp.ClientTimeout(total=30)
    
    async def _make_request(
        self,
        method: str, 
        endpoint: str, 
        token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        max_retries: int = 3
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Make GitHub API request with enhanced rate limiting and caching."""
        url = f"{self.base_url}{endpoint}"
        
        # Check cache first for GET requests
        if method.upper() == 'GET' and use_cache and not "events" in endpoint:
            cached_response = self.cache_manager.get(url, params)
            if cached_response:
                self.rate_limit_manager.statistics['cache_hits'] += 1
                return cached_response
        
        # Prepare headers
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitMesh-AI/1.0'
        }
        
        if token:
            headers['Authorization'] = f'token {token}'
        
        self.rate_limit_manager.statistics['total_requests'] += 1
        
        for attempt in range(max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.request(
                        method, url, headers=headers, params=params, json=data
                    ) as response:
                        # Update rate limit info
                        self.rate_limit_manager.update_rate_limit(token or 'public', dict(response.headers))
                        
                        # Handle rate limiting with exponential backoff
                        if response.status == 429 or (response.status == 403 and 'rate limit' in str(response.reason).lower()):
                            self.rate_limit_manager.statistics['rate_limit_hits'] += 1
                            
                            # Get retry after from headers
                            retry_after = int(response.headers.get('retry-after', 60))
                            reset_time = int(response.headers.get('x-ratelimit-reset', 0))
                            
                            if attempt < max_retries:
                                # Calculate wait time (exponential backoff with jitter)
                                base_wait = min(retry_after, 60)  # Cap at 1 minute
                                jitter = __import__('random').uniform(0.1, 0.3)
                                wait_time = base_wait * (2 ** attempt) + jitter
                                
                                logger.warning(f"Rate limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                # No more retries, raise detailed error
                                error_data = {
                                    "error": {
                                        "error_code": "RATE_LIMIT_EXCEEDED",
                                        "message": "Rate limit exceeded for requests_per_minute",
                                        "category": "rate_limit",
                                        "retry_after": retry_after,
                                        "details": {
                                            "limit_type": "requests_per_minute",
                                            "max_requests": int(response.headers.get('x-ratelimit-limit', 60)),
                                            "current_count": int(response.headers.get('x-ratelimit-used', 0)),
                                            "reset_time": datetime.fromtimestamp(reset_time).isoformat() if reset_time else None
                                        }
                                    }
                                }
                                raise Exception(f"GitHub API error: 429 Too Many Requests - {error_data}")
                        
                        if response.status == 404:
                            raise Exception(f"Resource not found: {endpoint}")
                        
                        if not response.ok:
                            error_text = await response.text()
                            raise Exception(f"GitHub API error {response.status}: {error_text}")
                        
                        response_data = await response.json()
                        response_headers = dict(response.headers)
                        
                        # Cache successful GET responses
                        if method.upper() == 'GET' and use_cache:
                            self.cache_manager.set(url, (response_data, response_headers), params)
                        
                        return response_data, response_headers
                        
            except aiohttp.ClientError as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"GitHub API request failed after {max_retries} retries: {e}")
                    raise Exception(f"GitHub API request failed: {e}")
            
            except Exception as e:
                if "rate limit" in str(e).lower() and attempt < max_retries:
                    wait_time = 60 * (2 ** attempt)  # Exponential backoff for rate limits
                    logger.warning(f"Rate limit error, waiting {wait_time}s before retry: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise
    
    async def get(self, endpoint: str, token: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request to GitHub API."""
        response_data, _ = await self._make_request('GET', endpoint, token, params)
        return response_data
    
    async def post(self, endpoint: str, token: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make POST request to GitHub API."""
        response_data, _ = await self._make_request('POST', endpoint, token, data=data, use_cache=False)
        return response_data
    
    async def put(self, endpoint: str, token: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make PUT request to GitHub API."""
        response_data, _ = await self._make_request('PUT', endpoint, token, data=data, use_cache=False)
        return response_data
    
    async def delete(self, endpoint: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Make DELETE request to GitHub API."""
        response_data, _ = await self._make_request('DELETE', endpoint, token, use_cache=False)
        return response_data

class GitHubService:
    """High-level GitHub service with all API operations."""
    
    def __init__(self, token: Optional[str] = None):
        self.client = GitHubAPIClient()
        self.key_manager = KeyManager()
        self.token = token

    def get_token(self):
        if self.token:
            return self.token
        # Cannot get token from key manager without username - return None
        # Callers should pass token explicitly via function parameters
        return None
    
    # User Operations
    
    async def get_user_profile(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Get authenticated user profile."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        return await self.client.get('/user', auth_token)
    
    async def get_user_repositories(self, token: Optional[str] = None, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """Get user repositories."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {'page': page, 'per_page': per_page, 'sort': 'updated'}
        return await self.client.get('/user/repos', auth_token, params)

    async def get_user_activity(self, username: str, token: Optional[str] = None, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """Get user public activity."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {'page': page, 'per_page': per_page}
        response = await self.client.get(f'/users/{username}/events/public', auth_token, params)
        return response

    async def get_user_starred(self, token: Optional[str] = None, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """Get user starred repositories."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {'page': page, 'per_page': per_page, 'sort': 'updated'}
        return await self.client.get('/user/starred', auth_token, params)

    # Repository Operations

    async def get_repository_details(self, owner: str, repo: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Get repository details."""
        auth_token = token or self.get_token()
        
        try:
            # Try with authentication first if token is available
            if auth_token:
                try:
                    return await self.client.get(f'/repos/{owner}/{repo}', auth_token)
                except Exception as auth_error:
                    logger.warning(f"Authenticated repository details request failed, trying unauthenticated: {auth_error}")
            
            # Try unauthenticated access for public repositories
            return await self.client.get(f'/repos/{owner}/{repo}', None)
            
        except Exception as e:
            logger.error(f"Failed to get repository details: {e}")
            raise

    async def get_repository_branches(self, owner: str, repo: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get repository branches."""
        auth_token = token or self.get_token()
        
        try:
            # Try with authentication first if token is available
            if auth_token:
                try:
                    response = await self.client.get(f'/repos/{owner}/{repo}/branches', auth_token)
                    logger.info(f"GitHub API response for branches (authenticated): {len(response) if response else 0} branches")
                    return response
                except Exception as auth_error:
                    logger.warning(f"Authenticated branch request failed, trying unauthenticated: {auth_error}")
            
            # Try unauthenticated access for public repositories
            response = await self.client.get(f'/repos/{owner}/{repo}/branches', None)
            logger.info(f"GitHub API response for branches (unauthenticated): {len(response) if response else 0} branches")
            return response
            
        except Exception as e:
            logger.error(f"Failed to get repository branches: {e}")
            return []

    async def get_repository_commits(
        self, 
        owner: str, 
        repo: str, 
        branch: str = 'main',
        page: int = 1, 
        per_page: int = 30,
        since: Optional[str] = None,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get repository commits."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {
            'sha': branch,
            'page': page,
            'per_page': per_page
        }
        if since:
            params['since'] = since
        
        try:
            return await self.client.get(f'/repos/{owner}/{repo}/commits', auth_token, params)
        except Exception as e:
            if "Resource not found" in str(e):
                logger.warning(f"Commits not found for {owner}/{repo} on branch {branch}. Returning empty list.")
                return []
            raise

    async def get_repository_issues(
        self, 
        owner: str, 
        repo: str, 
        state: str = 'open',
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get repository issues."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {
            'state': state,
            'page': page,
            'per_page': per_page,
            'sort': 'updated'
        }
        return await self.client.get(f'/repos/{owner}/{repo}/issues', auth_token, params)

    async def get_repository_pull_requests(
        self, 
        owner: str, 
        repo: str, 
        state: str = 'open',
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get repository pull requests."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {
            'state': state,
            'page': page,
            'per_page': per_page,
            'sort': 'updated'
        }
        return await self.client.get(f'/repos/{owner}/{repo}/pulls', auth_token, params)

    async def get_repository_contributors(self, owner: str, repo: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get repository contributors."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        return await self.client.get(f'/repos/{owner}/{repo}/contributors', auth_token)

    async def get_repository_languages(self, owner: str, repo: str, token: Optional[str] = None) -> Dict[str, int]:
        """Get repository languages."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        return await self.client.get(f'/repos/{owner}/{repo}/languages', auth_token)

    async def get_repository_tree(self, owner: str, repo: str, branch: str = 'main', token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get repository tree structure."""
        auth_token = token or self.get_token()
        
        try:
            # Try with authentication first if token is available
            if auth_token:
                try:
                    # Get the commit SHA for the branch
                    branch_data = await self.client.get(f'/repos/{owner}/{repo}/branches/{branch}', auth_token)
                    tree_sha = branch_data['commit']['commit']['tree']['sha']
                    
                    # Get the tree with recursive option
                    params = {'recursive': '1'}
                    tree_data = await self.client.get(f'/repos/{owner}/{repo}/git/trees/{tree_sha}', auth_token, params)
                    
                    return tree_data.get('tree', [])
                except Exception as auth_error:
                    logger.warning(f"Authenticated request failed, trying unauthenticated access: {auth_error}")
                    # Fall through to unauthenticated attempt
            
            # Try without authentication for public repositories
            try:
                # Get the commit SHA for the branch (unauthenticated)
                branch_data = await self.client.get(f'/repos/{owner}/{repo}/branches/{branch}', None)
                tree_sha = branch_data['commit']['commit']['tree']['sha']
                
                # Get the tree with recursive option (unauthenticated)
                params = {'recursive': '1'}
                tree_data = await self.client.get(f'/repos/{owner}/{repo}/git/trees/{tree_sha}', None, params)
                
                return tree_data.get('tree', [])
            except Exception as unauth_error:
                logger.error(f"Both authenticated and unauthenticated requests failed: {unauth_error}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to get repository tree: {e}")
            return []

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str = 'main', token: Optional[str] = None) -> Dict[str, Any]:
        """Get file content from repository."""
        auth_token = token or self.get_token()
        params = {'ref': branch}
        
        try:
            # Try with authentication first if token is available
            if auth_token:
                try:
                    return await self.client.get(f'/repos/{owner}/{repo}/contents/{path}', auth_token, params)
                except Exception as auth_error:
                    logger.warning(f"Authenticated file content request failed, trying unauthenticated: {auth_error}")
            
            # Try unauthenticated access for public repositories
            return await self.client.get(f'/repos/{owner}/{repo}/contents/{path}', None, params)
            
        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            raise

    # Search Operations

    async def search_repositories(
        self, 
        query: str, 
        sort: str = 'stars', 
        order: str = 'desc',
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search repositories."""
        auth_token = token or self.get_token()
        params = {
            'q': query,
            'sort': sort,
            'order': order,
            'page': page,
            'per_page': per_page
        }
        return await self.client.get('/search/repositories', auth_token, params)

    async def search_users(
        self, 
        query: str, 
        sort: str = 'followers', 
        order: str = 'desc',
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search users."""
        auth_token = token or self.get_token()
        params = {
            'q': query,
            'sort': sort,
            'order': order,
            'page': page,
            'per_page': per_page
        }
        return await self.client.get('/search/users', auth_token, params)

    async def search_organizations(
        self, 
        query: str, 
        sort: str = 'repositories', 
        order: str = 'desc',
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search organizations."""
        auth_token = token or self.get_token()
        
        # Add type:org qualifier to the query
        qualified_query = f"{query} type:org"
        
        params = {
            'q': qualified_query,
            'sort': sort,
            'order': order,
            'page': page,
            'per_page': per_page
        }
        # Use the /search/users endpoint
        return await self.client.get('/search/users', auth_token, params)

    # Trending Repositories

    async def get_trending_repositories(
        self, 
        since: str = 'weekly', 
        language: Optional[str] = None,
        page: int = 1, 
        per_page: int = 30,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get trending repositories."""
        auth_token = token or self.get_token()
        # Calculate date range
        now = datetime.now()
        if since == 'daily':
            past_date = now - timedelta(days=1)
        elif since == 'weekly':
            past_date = now - timedelta(days=7)
        elif since == 'monthly':
            past_date = now - timedelta(days=30)
        else:
            past_date = now - timedelta(days=7)
        
        # Build search query
        query = f"created:>{past_date.strftime('%Y-%m-%d')} stars:>100"
        if language:
            query += f" language:{language}"
        
        params = {
            'q': query,
            'sort': 'stars',
            'order': 'desc',
            'page': page,
            'per_page': per_page
        }
        
        search_result = await self.client.get('/search/repositories', auth_token, params)
        
        return {
            'repositories': search_result.get('items', []),
            'total': search_result.get('total_count', 0)
        }

    # Utility Methods

    async def get_repository_trees_for_all_branches(self, owner: str, repo: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Get file trees for all branches in a repository."""
        auth_token = token or self.get_token()
        
        try:
            # Try to get branches with authentication first, fall back to unauthenticated
            branches = []
            if auth_token:
                try:
                    branches = await self.get_repository_branches(owner, repo, auth_token)
                except Exception as auth_error:
                    logger.warning(f"Authenticated branch fetch failed, trying unauthenticated: {auth_error}")
            
            if not branches:
                # Try unauthenticated access for public repositories
                try:
                    branches = await self.client.get(f'/repos/{owner}/{repo}/branches', None)
                except Exception as unauth_error:
                    logger.error(f"Both authenticated and unauthenticated branch fetch failed: {unauth_error}")
                    return {}
            
            trees_by_branch = {}
            
            for branch in branches:
                try:
                    # Use the updated get_repository_tree method which handles auth fallback
                    tree = await self.get_repository_tree(owner, repo, branch['name'], auth_token)
                    trees_by_branch[branch['name']] = tree
                except Exception as e:
                    logger.error(f"Failed to get tree for branch {branch['name']}: {e}")
                    trees_by_branch[branch['name']] = {'error': str(e)}
            
            return trees_by_branch
        except Exception as e:
            logger.error(f"Failed to get trees for all branches: {e}")
            return {}
            return {}

    def is_valid_owner(self, owner: str) -> bool:
        """Validate repository owner name."""
        if not owner or len(owner) < 1 or len(owner) > 39:
            return False
        
        # GitHub username rules
        import re
        return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-])*[a-zA-Z0-9]$', owner))
    
    def get_rate_limit_status(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Get rate limit status for token."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        return self.client.rate_limit_manager.get_rate_limit_status(auth_token)

    def get_statistics(self) -> Dict[str, Any]:
        """Get API usage statistics."""
        return self.client.rate_limit_manager.get_statistics()
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.client.cache_manager.get_statistics()
    
    def clear_cache(self):
        """Clear API response cache."""
        self.client.cache_manager.clear()

    # User Profile Methods
    async def get_user_profile_by_username(self, username: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Get any user's public profile by username."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        return await self.client.get(f'/users/{username}', auth_token)
    
    async def get_user_public_repositories(self, username: str, token: Optional[str] = None, page: int = 1, per_page: int = 30, sort: str = 'updated') -> List[Dict[str, Any]]:
        """Get public repositories for a specific user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {'page': page, 'per_page': per_page, 'sort': sort, 'type': 'all'}
        return await self.client.get(f'/users/{username}/repos', auth_token, params)
    
    async def get_user_starred_repositories(self, username: str, token: Optional[str] = None, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        """Get starred repositories for a specific user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        params = {'page': page, 'per_page': per_page}
        return await self.client.get(f'/users/{username}/starred', auth_token, params)
    
    async def get_user_pinned_repositories(self, username: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pinned repositories for a user."""
        # GitHub doesn't have a direct API for pinned repos, so we'll simulate with recent popular repos
        try:
            repos = await self.get_user_public_repositories(username, token, page=1, per_page=6, sort='updated')
            # Sort by stars and return top 6
            sorted_repos = sorted(repos, key=lambda x: x.get('stargazers_count', 0), reverse=True)
            return sorted_repos[:6]
        except Exception as e:
            logger.warning(f"Failed to get pinned repositories for {username}: {e}")
            return []
    
    async def get_user_readme(self, username: str, token: Optional[str] = None) -> Optional[str]:
        """Get user profile README content."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        try:
            # GitHub profile README is in a repo with the same name as the username
            response = await self.client.get(f'/repos/{username}/{username}/contents/README.md', auth_token)
            if 'content' in response:
                import base64
                content = base64.b64decode(response['content']).decode('utf-8')
                return content
            return None
        except Exception as e:
            logger.debug(f"No README found for user {username}: {e}")
            return None
    
    async def follow_user(self, username: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Follow a user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'token {auth_token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'GitMesh/1.0'
            }
            async with session.put(f'https://api.github.com/user/following/{username}', headers=headers) as response:
                if response.status == 204:
                    return {"success": True, "message": f"Successfully followed {username}"}
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to follow user: {error_text}")
    
    async def unfollow_user(self, username: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Unfollow a user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'token {auth_token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'GitMesh/1.0'
            }
            async with session.delete(f'https://api.github.com/user/following/{username}', headers=headers) as response:
                if response.status == 204:
                    return {"success": True, "message": f"Successfully unfollowed {username}"}
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to unfollow user: {error_text}")
    
    async def is_following_user(self, username: str, token: Optional[str] = None) -> bool:
        """Check if the current user is following a specific user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'token {auth_token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'GitMesh/1.0'
                }
                async with session.get(f'https://api.github.com/user/following/{username}', headers=headers) as response:
                    return response.status == 204
        except Exception as e:
            logger.debug(f"Error checking if following {username}: {e}")
            return False

    async def get_user_organizations(self, username: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get organizations for a user."""
        auth_token = token or self.get_token()
        if not auth_token:
            raise ValueError("GitHub token not provided and not found in KeyManager")
        
        try:
            return await self.client.get(f'/users/{username}/orgs', auth_token)
        except Exception as e:
            logger.debug(f"Error fetching organizations for {username}: {e}")
            return []


# Global GitHub service instance
github_service = GitHubService()



