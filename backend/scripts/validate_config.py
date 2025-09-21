#!/usr/bin/env python3
"""
Configuration validation script.

This script validates the unified configuration system and checks for:
1. Required environment variables
2. Configuration consistency
3. Security best practices
4. Environment-specific requirements
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config.unified_config import get_config, validate_config, Environment
    from config.unified_config import UnifiedConfig
except ImportError as e:
    print(f"❌ Failed to import unified config: {e}")
    print("Make sure you're running this from the backend directory")
    sys.exit(1)


class ConfigValidator:
    """Configuration validator with comprehensive checks."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("🔍 Validating unified configuration...")
        
        try:
            config = get_config()
            self.info.append(f"Environment: {config.environment}")
            self.info.append(f"Database configured: {bool(config.database.url)}")
            self.info.append(f"Redis configured: {bool(config.redis.url)}")
            self.info.append(f"AI provider: {config.ai.provider}")
            
        except Exception as e:
            self.errors.append(f"Failed to load configuration: {e}")
            return False
        
        # Run validation checks
        self._validate_environment_variables()
        self._validate_security_settings(config)
        self._validate_database_config(config)
        self._validate_redis_config(config)
        self._validate_ai_config(config)
        self._validate_server_config(config)
        self._validate_environment_specific(config)
        
        return len(self.errors) == 0
    
    def _validate_environment_variables(self):
        """Validate required environment variables."""
        # Only SECRET_KEY and JWT_SECRET are truly required
        # DATABASE_URL can fall back to SUPABASE_URL
        required_vars = [
            "SECRET_KEY",
            "JWT_SECRET",
        ]
        
        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if not value or value.startswith("dev-"):
                missing_vars.append(var)
        
        # Check if we have either DATABASE_URL or SUPABASE_URL
        if not os.getenv("DATABASE_URL") and not os.getenv("SUPABASE_URL"):
            missing_vars.append("DATABASE_URL or SUPABASE_URL")
        
        if missing_vars:
            self.errors.append(f"Missing or using default values for: {', '.join(missing_vars)}")
    
    def _validate_security_settings(self, config: UnifiedConfig):
        """Validate security configuration."""
        # Check secret key length
        if len(config.security.secret_key) < 32:
            self.errors.append("SECRET_KEY must be at least 32 characters long")
        
        if len(config.security.jwt_secret) < 32:
            self.errors.append("JWT_SECRET must be at least 32 characters long")
        
        # Check for default/weak secrets
        weak_secrets = [
            "your-super-secret-key",
            "change-in-production",
            "default-secret",
            "secret-key"
        ]
        
        for weak in weak_secrets:
            if weak in config.security.secret_key.lower():
                self.warnings.append("SECRET_KEY appears to contain default/weak values")
                break
        
        for weak in weak_secrets:
            if weak in config.security.jwt_secret.lower():
                self.warnings.append("JWT_SECRET appears to contain default/weak values")
                break
    
    def _validate_database_config(self, config: UnifiedConfig):
        """Validate database configuration."""
        try:
            db_url = config.get_database_url()
            
            if not db_url.startswith(('postgresql://', 'postgresql+asyncpg://')):
                self.errors.append("DATABASE_URL must be a PostgreSQL URL")
            
            if "localhost" in db_url and config.environment == Environment.PRODUCTION:
                self.warnings.append("Using localhost database in production environment")
            
            # Check pool settings
            if config.database.pool_size < 5:
                self.warnings.append("Database pool size is quite small (< 5)")
            
            if config.database.pool_size > 50:
                self.warnings.append("Database pool size is quite large (> 50)")
                
        except Exception as e:
            self.errors.append(f"Database configuration error: {e}")
    
    def _validate_redis_config(self, config: UnifiedConfig):
        """Validate Redis configuration."""
        try:
            redis_url = config.get_redis_url()
            
            if not redis_url.startswith(('redis://', 'rediss://')):
                self.errors.append("REDIS_URL must be a valid Redis URL")
            
            if "localhost" in redis_url and config.environment == Environment.PRODUCTION:
                self.warnings.append("Using localhost Redis in production environment")
            
            # Check SSL settings for production
            if config.environment == Environment.PRODUCTION and not config.redis.ssl:
                self.warnings.append("Consider enabling Redis SSL for production")
                
        except Exception as e:
            self.errors.append(f"Redis configuration error: {e}")
    
    def _validate_ai_config(self, config: UnifiedConfig):
        """Validate AI/LLM configuration."""
        api_key = config.get_ai_api_key()
        
        if not api_key:
            self.warnings.append(f"No API key configured for AI provider: {config.ai.provider}")
        
        # Check API key format
        if api_key:
            provider = config.ai.provider.lower()
            if provider == "gemini" and not api_key.startswith("AIzaSy"):
                self.warnings.append("Gemini API key format appears incorrect")
            elif provider == "openai" and not api_key.startswith("sk-"):
                self.warnings.append("OpenAI API key format appears incorrect")
        
        # Check timeout settings
        if config.ai.timeout < 10:
            self.warnings.append("AI timeout is quite low (< 10 seconds)")
        elif config.ai.timeout > 120:
            self.warnings.append("AI timeout is quite high (> 120 seconds)")
    
    def _validate_server_config(self, config: UnifiedConfig):
        """Validate server configuration."""
        # Check CORS origins
        origins = config.get_cors_origins()
        
        if "*" in origins and config.environment == Environment.PRODUCTION:
            self.warnings.append("Wildcard CORS origins in production is not recommended")
        
        # Check frontend URL
        if "localhost" in config.server.frontend_url and config.environment == Environment.PRODUCTION:
            self.warnings.append("Frontend URL points to localhost in production")
    
    def _validate_environment_specific(self, config: UnifiedConfig):
        """Validate environment-specific requirements."""
        if config.environment == Environment.PRODUCTION:
            self._validate_production_requirements(config)
        elif config.environment == Environment.STAGING:
            self._validate_staging_requirements(config)
        else:
            self._validate_development_requirements(config)
    
    def _validate_production_requirements(self, config: UnifiedConfig):
        """Validate production-specific requirements."""
        # GitHub OAuth should be configured
        if not config.github.client_id or not config.github.client_secret:
            self.warnings.append("GitHub OAuth not configured for production")
        
        # Vault should be enabled for production
        if not config.vault.enabled:
            self.warnings.append("Consider enabling Vault for production secret management")
        
        # Debug mode should be off
        if config.logging.debug_mode:
            self.warnings.append("Debug mode is enabled in production")
    
    def _validate_staging_requirements(self, config: UnifiedConfig):
        """Validate staging-specific requirements."""
        # Less strict than production
        pass
    
    def _validate_development_requirements(self, config: UnifiedConfig):
        """Validate development-specific requirements."""
        # Check if using production-like URLs in development
        try:
            db_url = config.get_database_url()
            if "amazonaws.com" in db_url:
                self.info.append("Using cloud database in development environment")
        except ValueError:
            # Database URL not configured, which is OK for development
            pass
    
    def print_results(self):
        """Print validation results."""
        print("\n" + "="*60)
        print("CONFIGURATION VALIDATION RESULTS")
        print("="*60)
        
        if self.info:
            print("\n📋 Information:")
            for info in self.info:
                print(f"  ℹ️  {info}")
        
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")
        
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  ❌ {error}")
        else:
            print("\n✅ No configuration errors found!")
        
        print("\n" + "="*60)
        
        if self.errors:
            print("❌ Configuration validation FAILED")
            return False
        elif self.warnings:
            print("⚠️  Configuration validation PASSED with warnings")
            return True
        else:
            print("✅ Configuration validation PASSED")
            return True


def check_env_file():
    """Check if .env file exists and has required structure."""
    env_path = Path("backend/.env")
    
    if not env_path.exists():
        print("❌ .env file not found in backend directory")
        print("💡 Copy .env.example to .env and configure your values")
        return False
    
    print("✅ .env file found")
    
    # Check for new structure markers
    with open(env_path) as f:
        content = f.read()
    
    if "# ENVIRONMENT CONFIGURATION" in content:
        print("✅ .env file uses new unified structure")
    else:
        print("⚠️  .env file may need updating to new structure")
        print("💡 Check .env.example for the new format")
    
    return True


def main():
    """Main validation function."""
    print("🚀 Configuration Validation Tool")
    print("="*40)
    
    # Check environment file
    if not check_env_file():
        sys.exit(1)
    
    # Run validation
    validator = ConfigValidator()
    success = validator.validate_all()
    validator.print_results()
    
    if not success:
        print("\n💡 Fix the errors above and run validation again")
        sys.exit(1)
    
    print("\n🎉 Configuration is ready to use!")
    
    # Show usage example
    print("\n📖 Usage example:")
    print("```python")
    print("from config.unified_config import get_config")
    print("config = get_config()")
    print("print(f'Environment: {config.environment}')")
    print("print(f'Database: {config.get_database_url()}')")
    print("```")


if __name__ == "__main__":
    main()