#!/usr/bin/env python3
"""
Test script to verify the coroutine fixes are working.
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

async def test_cosmos_web_wrapper():
    """Test the CosmosWebWrapper with async fixes."""
    try:
        from services.cosmos_web_wrapper import CosmosWebWrapper
        from services.redis_repo_manager import RedisRepoManager
        
        # Create a test repository manager
        repo_manager = RedisRepoManager(
            repo_url="https://github.com/RAWx18/walmart_optifresh",
            branch="main",
            user_tier="pro",
            username="test_user"
        )
        
        # Create wrapper
        wrapper = CosmosWebWrapper(repo_manager, model="gemini", user_id="test_user")
        
        # Test processing a message that should trigger repository analysis
        test_message = "What does this repository use for tracking delivery?"
        
        logger.info(f"Testing message: {test_message}")
        
        # This should now work without coroutine errors
        response = await wrapper.process_message(test_message)
        
        if response and response.content:
            logger.info("✅ CosmosWebWrapper test PASSED")
            logger.info(f"Response length: {len(response.content)} chars")
            logger.info(f"Context files used: {len(response.context_files_used)}")
            return True
        else:
            logger.error("❌ CosmosWebWrapper test FAILED - no response")
            return False
            
    except Exception as e:
        logger.error(f"❌ CosmosWebWrapper test ERROR: {e}")
        return False

async def test_repository_file_analysis():
    """Test that the repository analysis includes more than just README."""
    try:
        from services.cosmos_web_wrapper import CosmosWebWrapper
        from services.redis_repo_manager import RedisRepoManager
        
        # Create a test repository manager
        repo_manager = RedisRepoManager(
            repo_url="https://github.com/RAWx18/walmart_optifresh",
            branch="main",
            user_tier="pro",
            username="test_user"
        )
        
        # Create wrapper
        wrapper = CosmosWebWrapper(repo_manager, model="gemini", user_id="test_user")
        
        # Get important files
        important_files = wrapper._get_important_repository_files()
        
        logger.info(f"Found {len(important_files)} important files:")
        for file in important_files:
            logger.info(f"  - {file}")
        
        # Check if we have more than just README
        non_readme_files = [f for f in important_files if not f.lower().startswith('readme')]
        
        if len(non_readme_files) > 0:
            logger.info(f"✅ Repository analysis includes {len(non_readme_files)} non-README files")
            return True
        else:
            logger.warning("⚠️ Repository analysis only includes README files")
            return False
            
    except Exception as e:
        logger.error(f"❌ Repository file analysis test ERROR: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Coroutine Fixes and Enhanced Repository Analysis")
    print("=" * 70)
    
    # Test 1: CosmosWebWrapper async fixes
    print("\n📋 Test 1: CosmosWebWrapper Async Fixes")
    wrapper_result = asyncio.run(test_cosmos_web_wrapper())
    
    # Test 2: Enhanced repository file analysis
    print("\n📋 Test 2: Enhanced Repository File Analysis")
    analysis_result = asyncio.run(test_repository_file_analysis())
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 Test Results Summary:")
    print(f"   CosmosWebWrapper Async: {'✅ PASSED' if wrapper_result else '❌ FAILED'}")
    print(f"   Enhanced File Analysis: {'✅ PASSED' if analysis_result else '❌ FAILED'}")
    
    if wrapper_result and analysis_result:
        print("\n🎉 All tests PASSED! The coroutine fixes are working correctly.")
        print("💡 The AI should now analyze more files beyond just the README.")
        sys.exit(0)
    else:
        print("\n💥 Some tests FAILED. Please check the implementation.")
        sys.exit(1)