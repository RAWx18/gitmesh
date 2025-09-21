#!/usr/bin/env python3
"""
Simple configuration validation script.
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config.simple_config import get_config
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)


def main():
    """Main validation function."""
    print("🚀 Simple Configuration Validation")
    print("="*40)
    
    try:
        config = get_config()
        print("✅ Configuration loaded successfully!")
        
        # Basic info
        print(f"\n📋 Configuration Summary:")
        print(f"  Environment: {config.environment}")
        print(f"  AI Provider: {config.ai_provider}")
        print(f"  Tier Plan: {config.tier_plan}")
        
        # Check database
        try:
            db_url = config.get_database_url()
            print(f"  Database: ✅ Configured")
        except ValueError:
            print(f"  Database: ❌ Not configured")
        
        # Check Redis
        redis_url = config.get_redis_url()
        print(f"  Redis: ✅ Configured")
        
        # Check AI API key
        api_key = config.get_ai_api_key()
        if api_key:
            print(f"  AI API Key: ✅ Configured")
        else:
            print(f"  AI API Key: ⚠️  Not configured")
        
        # Check secrets
        if len(config.secret_key) >= 32 and not config.secret_key.startswith("dev-"):
            print(f"  Secret Key: ✅ Configured")
        else:
            print(f"  Secret Key: ⚠️  Using default/weak value")
        
        if len(config.jwt_secret) >= 32 and not config.jwt_secret.startswith("dev-"):
            print(f"  JWT Secret: ✅ Configured")
        else:
            print(f"  JWT Secret: ⚠️  Using default/weak value")
        
        # Check CORS origins
        origins = config.get_cors_origins()
        print(f"  CORS Origins: {len(origins)} configured")
        
        print(f"\n🎉 Configuration validation completed!")
        
        # Show usage example
        print(f"\n📖 Usage example:")
        print(f"```python")
        print(f"from config.simple_config import get_config")
        print(f"config = get_config()")
        print(f"db_url = config.get_database_url()")
        print(f"redis_url = config.get_redis_url()")
        print(f"api_key = config.get_ai_api_key()")
        print(f"```")
        
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()