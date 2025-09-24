#!/usr/bin/env python3
"""
Test script to verify the asyncio fix for repository caching.
"""

import os
import sys
import asyncio
import logging

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_repository_caching():
    """Test repository caching with asyncio fix."""
    try:
        # Import the fixed repo fetch function
        from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
        
        # Test repository URL
        test_repo_url = "https://github.com/octocat/Hello-World"
        
        logger.info(f"Testing repository caching for: {test_repo_url}")
        
        # This should now work without asyncio.run() errors
        success = fetch_and_store_repo(test_repo_url)
        
        if success:
            logger.info("✅ Repository caching test PASSED")
            print("✅ Repository caching test PASSED")
        else:
            logger.error("❌ Repository caching test FAILED")
            print("❌ Repository caching test FAILED")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Repository caching test ERROR: {e}")
        print(f"❌ Repository caching test ERROR: {e}")
        return False

def test_sync_version():
    """Test the synchronous version (original issue)."""
    try:
        from integrations.cosmos.v1.cosmos.repo_fetch import fetch_and_store_repo
        
        test_repo_url = "https://github.com/octocat/Hello-World"
        
        logger.info(f"Testing synchronous repository caching for: {test_repo_url}")
        
        # This should now work without asyncio.run() errors
        success = fetch_and_store_repo(test_repo_url)
        
        if success:
            logger.info("✅ Synchronous repository caching test PASSED")
            print("✅ Synchronous repository caching test PASSED")
        else:
            logger.error("❌ Synchronous repository caching test FAILED")
            print("❌ Synchronous repository caching test FAILED")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Synchronous repository caching test ERROR: {e}")
        print(f"❌ Synchronous repository caching test ERROR: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Repository Caching with Asyncio Fix")
    print("=" * 50)
    
    # Test 1: Synchronous version (the original issue)
    print("\n📋 Test 1: Synchronous Repository Caching")
    sync_result = test_sync_version()
    
    # Test 2: Async version (to ensure it still works)
    print("\n📋 Test 2: Async Repository Caching")
    async_result = asyncio.run(test_repository_caching())
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print(f"   Synchronous Test: {'✅ PASSED' if sync_result else '❌ FAILED'}")
    print(f"   Async Test: {'✅ PASSED' if async_result else '❌ FAILED'}")
    
    if sync_result and async_result:
        print("\n🎉 All tests PASSED! The asyncio fix is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests FAILED. Please check the implementation.")
        sys.exit(1)