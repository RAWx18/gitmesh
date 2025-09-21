#!/usr/bin/env python3
"""
Repository Integration Service Example

This example demonstrates how to use the Repository Integration Service
to fetch, cache, and validate repository access with GitIngest.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from services.repository_integration_service import get_repository_integration_service


async def main():
    """Main example function."""
    print("Repository Integration Service Example")
    print("=" * 50)
    
    # Get the service instance
    service = get_repository_integration_service()
    
    # Example repository URLs to test
    test_repos = [
        {
            "url": "https://github.com/octocat/Hello-World",
            "branch": "master",
            "tier": "personal",
            "username": "testuser"
        },
        {
            "url": "https://github.com/microsoft/vscode",
            "branch": "main", 
            "tier": "pro",
            "username": "testuser"
        }
    ]
    
    for i, repo_config in enumerate(test_repos, 1):
        print(f"\n{i}. Testing Repository: {repo_config['url']}")
        print("-" * 40)
        
        # Step 1: Validate repository access
        print("Step 1: Validating repository access...")
        validation = service.validate_repository_access(
            repo_url=repo_config["url"],
            user_tier=repo_config["tier"],
            username=repo_config["username"],
            branch=repo_config["branch"]
        )
        
        print(f"  - Valid: {validation.is_valid}")
        print(f"  - Accessible: {validation.is_accessible}")
        print(f"  - Tier allowed: {validation.tier_allowed}")
        print(f"  - Size within limits: {validation.size_within_limits}")
        if validation.error_message:
            print(f"  - Error: {validation.error_message}")
        if validation.required_tier:
            print(f"  - Required tier: {validation.required_tier}")
        if validation.actual_size:
            print(f"  - Repository size: {validation.actual_size:,} tokens")
        
        if not validation.is_valid:
            print("  ❌ Repository access denied - skipping fetch")
            continue
        
        # Step 2: Fetch repository (if validation passed)
        print("\nStep 2: Fetching repository...")
        success, error = service.fetch_repository(
            repo_url=repo_config["url"],
            branch=repo_config["branch"],
            user_tier=repo_config["tier"],
            username=repo_config["username"]
        )
        
        if success:
            print("  ✅ Repository fetched successfully")
        else:
            print(f"  ❌ Repository fetch failed: {error}")
            continue
        
        # Step 3: Get repository information
        print("\nStep 3: Getting repository information...")
        repo_info = service.get_repository_info(
            repo_config["url"], 
            repo_config["branch"]
        )
        
        if repo_info:
            print(f"  - Name: {repo_info.name}")
            print(f"  - Owner: {repo_info.owner}")
            print(f"  - Branch: {repo_info.branch}")
            print(f"  - Size: {repo_info.size_tokens:,} tokens")
            print(f"  - Files: {repo_info.file_count}")
            print(f"  - Languages: {', '.join(repo_info.languages[:5])}")
            print(f"  - Required tier: {repo_info.access_tier_required}")
            print(f"  - Cached at: {repo_info.cached_at}")
        else:
            print("  ❌ Could not get repository information")
        
        # Step 4: Get branch information
        print("\nStep 4: Getting branch information...")
        branch_info = service.get_branch_info(
            repo_config["url"],
            repo_config["branch"]
        )
        
        if branch_info:
            print(f"  - Branch: {branch_info.name}")
            print(f"  - Is default: {branch_info.is_default}")
            print(f"  - Commit SHA: {branch_info.commit_sha}")
            print(f"  - Commit message: {branch_info.commit_message}")
            print(f"  - Commit author: {branch_info.commit_author}")
        else:
            print("  ❌ Could not get branch information")
        
        # Step 5: Get repository size analysis
        print("\nStep 5: Getting repository size analysis...")
        size_info = service.get_repository_size_info(
            repo_config["url"],
            repo_config["branch"]
        )
        
        if size_info:
            print(f"  - Token count: {size_info['token_count']:,}")
            print(f"  - File count: {size_info['file_count']}")
            print(f"  - Required tier: {size_info['required_tier']}")
            
            if size_info.get('language_breakdown'):
                print("  - Language breakdown:")
                for lang, stats in list(size_info['language_breakdown'].items())[:3]:
                    print(f"    - {lang}: {stats['files']} files, {stats['size']:,} bytes")
        else:
            print("  ❌ Could not get repository size analysis")
    
    # Step 6: List cached repositories
    print(f"\n6. Listing cached repositories...")
    print("-" * 40)
    cached_repos = service.list_cached_repositories()
    
    if cached_repos:
        print(f"Found {len(cached_repos)} cached repositories:")
        for repo in cached_repos[:5]:  # Show first 5
            print(f"  - {repo.name} ({repo.branch}) - {repo.size_tokens:,} tokens")
    else:
        print("No cached repositories found")
    
    print(f"\n✅ Repository Integration Service example completed!")


def example_without_actual_services():
    """
    Example that shows the service interface without requiring actual services.
    This demonstrates the API structure and expected behavior.
    """
    print("\nRepository Integration Service API Example")
    print("=" * 50)
    
    print("""
    # Basic Usage:
    
    from services.repository_integration_service import get_repository_integration_service
    
    # Get service instance
    service = get_repository_integration_service()
    
    # 1. Validate repository access
    validation = service.validate_repository_access(
        repo_url="https://github.com/owner/repo",
        user_tier="pro",
        username="user123",
        branch="main"
    )
    
    if validation.is_valid:
        # 2. Fetch repository
        success, error = service.fetch_repository(
            repo_url="https://github.com/owner/repo",
            branch="main",
            user_tier="pro",
            username="user123"
        )
        
        if success:
            # 3. Get repository information
            repo_info = service.get_repository_info(
                "https://github.com/owner/repo", 
                "main"
            )
            
            # 4. Get branch information
            branch_info = service.get_branch_info(
                "https://github.com/owner/repo",
                "main"
            )
            
            # 5. Get size analysis
            size_info = service.get_repository_size_info(
                "https://github.com/owner/repo",
                "main"
            )
            
            # 6. List cached repositories
            cached_repos = service.list_cached_repositories(user_tier="pro")
            
            # 7. Clear cache if needed
            service.clear_repository_cache(
                "https://github.com/owner/repo",
                "main"
            )
    
    # Key Features:
    # - GitIngest integration for repository fetching
    # - Redis-based caching with TTL
    # - Tier-based access control (personal/pro/enterprise)
    # - Repository size validation
    # - Branch and commit information
    # - Language detection and analysis
    # - Secure GitHub token management via KeyManager
    # - Comprehensive error handling and validation
    """)


if __name__ == "__main__":
    print("Repository Integration Service Examples")
    print("=" * 60)
    
    # Show API example first
    example_without_actual_services()
    
    # Note about running the full example
    print("\n" + "=" * 60)
    print("NOTE: To run the full example with actual services:")
    print("1. Ensure Redis is running and configured")
    print("2. Set up environment variables (REDIS_URL, etc.)")
    print("3. Configure HashiCorp Vault for KeyManager")
    print("4. Run: python repository_integration_example.py")
    print("=" * 60)