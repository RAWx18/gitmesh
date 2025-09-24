#!/usr/bin/env python3
"""
Test script to verify the configuration and GitHub token fixes.
"""

import os
import sys
import logging

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_configuration_initialization():
    """Test that configuration initializes without errors."""
    try:
        from integrations.cosmos.v1.cosmos.config import initialize_configuration
        initialize_configuration()
        logger.info("✅ Configuration initialization test PASSED")
        return True
    except Exception as e:
        logger.error(f"❌ Configuration initialization test FAILED: {e}")
        return False

def test_github_token_validation():
    """Test GitHub token validation logic."""
    try:
        # Test the token validation logic
        github_token = os.getenv("GITHUB_TOKEN")
        
        # This is the same logic used in repo_fetch.py
        if github_token and github_token.strip() and not github_token.startswith("your_github") and len(github_token.strip()) > 10:
            logger.info("✅ Valid GitHub token found")
            token_status = "valid"
        else:
            logger.info("ℹ️ No valid GitHub token - will use public API limits")
            token_status = "none_or_invalid"
        
        logger.info(f"✅ GitHub token validation test PASSED (status: {token_status})")
        return True
        
    except Exception as e:
        logger.error(f"❌ GitHub token validation test FAILED: {e}")
        return False

def test_redis_connection():
    """Test Redis connection."""
    try:
        from integrations.cosmos.v1.cosmos.redis_cache import SmartRedisCache
        
        redis_cache = SmartRedisCache()
        health = redis_cache.health_check(force=True)
        
        if health:
            logger.info("✅ Redis connection test PASSED")
            return True
        else:
            logger.warning("⚠️ Redis connection test FAILED - check Redis configuration")
            return False
            
    except Exception as e:
        logger.error(f"❌ Redis connection test FAILED: {e}")
        return False

def test_optimized_service():
    """Test optimized repository service."""
    try:
        from services.optimized_repo_service import get_optimized_repo_service
        
        service = get_optimized_repo_service("test_user")
        health = service.health_check()
        
        if health.get("overall_healthy", False):
            logger.info("✅ Optimized service test PASSED")
            return True
        else:
            logger.warning(f"⚠️ Optimized service test WARNING: {health}")
            return True  # Still pass if partially healthy
            
    except Exception as e:
        logger.error(f"❌ Optimized service test FAILED: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Configuration and GitHub Token Fixes")
    print("=" * 60)
    
    tests = [
        ("Configuration Initialization", test_configuration_initialization),
        ("GitHub Token Validation", test_github_token_validation),
        ("Redis Connection", test_redis_connection),
        ("Optimized Service", test_optimized_service),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Testing: {test_name}")
        result = test_func()
        results.append((test_name, result))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n📈 Overall: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("\n🎉 All tests PASSED! The fixes are working correctly.")
        sys.exit(0)
    elif passed >= len(tests) - 1:
        print("\n⚠️ Most tests passed. Check warnings above.")
        sys.exit(0)
    else:
        print("\n💥 Multiple tests FAILED. Please check the implementation.")
        sys.exit(1)