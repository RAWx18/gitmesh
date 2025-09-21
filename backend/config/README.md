# Unified Configuration System

This directory contains the unified configuration system that eliminates hardcoded values and provides a centralized way to manage all application settings.

## 🎯 Goals

- **Eliminate hardcoded values** throughout the codebase
- **Centralize configuration** in one place
- **Environment-specific settings** with validation
- **Type-safe configuration** access
- **Easy testing and development** setup

## 📁 Files Overview

- `unified_config.py` - Main configuration system
- `database.py` - Database configuration (updated to use unified config)
- `features.yaml` - Feature flags and YAML-based settings
- `tier_config.py` - Tier-based access control settings
- `security_config.py` - Security and rate limiting settings
- `.env.example` - Template for environment variables
- `README.md` - This documentation

## 🚀 Quick Start

### 1. Set up environment variables

```bash
# Copy the example file
cp backend/.env.example backend/.env

# Edit with your actual values
nano backend/.env
```

### 2. Use in your code

```python
from config.unified_config import get_config

# Get configuration instance
config = get_config()

# Access configuration values
database_url = config.get_database_url()
redis_url = config.get_redis_url()
api_key = config.get_ai_api_key()
cors_origins = config.get_cors_origins()
```

### 3. Validate configuration

```bash
# Run validation script
python backend/scripts/validate_config.py

# Test configuration loading
python -m backend.config.unified_config
```

## 📋 Configuration Categories

### Environment Settings
```python
config.environment  # development, staging, production
```

### Database Configuration
```python
config.database.url          # Database URL
config.database.pool_size    # Connection pool size
config.database.max_overflow # Max overflow connections
config.database.echo         # SQL query logging
```

### Redis Configuration
```python
config.redis.url             # Redis URL
config.redis.host            # Redis host
config.redis.port            # Redis port
config.redis.password        # Redis password
config.redis.ssl             # SSL enabled
```

### Security Settings
```python
config.security.secret_key   # Application secret key
config.security.jwt_secret   # JWT signing secret
config.security.jwt_expires_in # JWT expiration time
```

### AI/LLM Configuration
```python
config.ai.provider           # AI provider (gemini, openai, anthropic)
config.ai.gemini_api_key     # Gemini API key
config.ai.default_model      # Default AI model
config.ai.temperature        # AI temperature setting
```

### Server Configuration
```python
config.server.host           # Server host
config.server.port           # Server port
config.server.frontend_url   # Frontend URL
config.server.origins_list   # CORS origins list
```

## 🔧 Environment Variables

### Required Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db

# Security
SECRET_KEY=your-super-secret-key-minimum-32-chars
JWT_SECRET=your-jwt-secret-key-minimum-32-chars

# AI Provider
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
```

### Optional Variables

```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
FRONTEND_URL=http://localhost:3000

# Redis
REDIS_URL=redis://user:pass@host:port/db
REDIS_HOST=localhost
REDIS_PORT=6379

# GitHub OAuth
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# Vault
VAULT_ENABLED=false
VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=your_vault_token
```

## 🌍 Environment-Specific Configuration

### Development
- Lenient validation
- Debug logging enabled
- Wildcard CORS origins allowed
- Local database/Redis acceptable

### Staging
- Moderate validation
- Some production-like settings
- Limited CORS origins
- Cloud services recommended

### Production
- Strict validation
- Security-focused settings
- No wildcard CORS origins
- Cloud services required
- Secrets validation enforced

## 🔍 Migration from Old System

### 1. Run migration analysis

```bash
python backend/scripts/migrate_to_unified_config.py
```

This will:
- Scan for hardcoded values
- Generate a migration report
- Create usage examples
- Provide migration suggestions

### 2. Update your code

**Before:**
```python
# Hardcoded database URL
engine = create_async_engine("postgresql://user:pass@host/db")

# Hardcoded Redis URL
redis_client = redis.from_url("redis://localhost:6379")

# Hardcoded API key
headers = {"Authorization": "Bearer sk-hardcoded-key"}
```

**After:**
```python
from config.unified_config import get_config

config = get_config()

# Use configuration
engine = create_async_engine(config.get_database_url())
redis_client = redis.from_url(config.get_redis_url())
headers = {"Authorization": f"Bearer {config.get_ai_api_key()}"}
```

### 3. Update environment variables

Update your `.env` file to use the new structure:

```bash
# Old format
SUPABASE_URL=postgresql://...
REDIS_URL=redis://...

# New format
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
```

## 🧪 Testing Configuration

### Unit Tests
```python
from config.unified_config import UnifiedConfig

def test_config():
    # Override for testing
    config = UnifiedConfig(
        database__url="sqlite:///test.db",
        redis__host="localhost",
        ai__provider="mock"
    )
    assert config.database.url == "sqlite:///test.db"
```

### Integration Tests
```python
def test_database_connection():
    config = get_config()
    engine = create_async_engine(config.get_database_url())
    # Test connection...
```

## 🔒 Security Best Practices

### Secret Management
- Use environment variables for secrets
- Never commit secrets to version control
- Use Vault in production for secret management
- Rotate secrets regularly

### Validation
- Minimum 32-character secrets
- No default/weak passwords
- Environment-specific validation
- SSL/TLS for production

### CORS Configuration
- No wildcard origins in production
- Specific domain allowlists
- Environment-specific origins

## 🐛 Troubleshooting

### Configuration Not Loading
```bash
# Check if .env file exists
ls -la backend/.env

# Validate configuration
python backend/scripts/validate_config.py

# Test loading
python -c "from config.unified_config import get_config; print(get_config().environment)"
```

### Import Errors
```python
# Make sure you're importing from the right path
from config.unified_config import get_config  # ✅ Correct
from backend.config.unified_config import get_config  # ❌ Wrong
```

### Environment Variables Not Found
```bash
# Check environment variables
env | grep DATABASE_URL
env | grep SECRET_KEY

# Source .env file manually (for testing)
export $(cat backend/.env | xargs)
```

### Database Connection Issues
```python
# Test database URL format
from config.unified_config import get_config
config = get_config()
print(f"Database URL: {config.get_database_url()}")

# Check if URL is properly formatted
# Should be: postgresql+asyncpg://user:pass@host:port/db
```

## 📚 Examples

See the `backend/examples/config_usage/` directory for complete examples:

- `database_example.py` - Database configuration usage
- `redis_example.py` - Redis configuration usage
- `api_client_example.py` - API client configuration usage

## 🔄 Migration Checklist

- [ ] Copy `.env.example` to `.env`
- [ ] Configure all required environment variables
- [ ] Run migration analysis script
- [ ] Update hardcoded values in code
- [ ] Test configuration loading
- [ ] Validate configuration
- [ ] Update deployment configurations (K8s, Docker)
- [ ] Update documentation

## 🤝 Contributing

When adding new configuration options:

1. Add to the appropriate config class in `unified_config.py`
2. Add environment variable to `.env.example`
3. Add validation in `validate_config.py`
4. Update this README
5. Add usage examples

## 📞 Support

If you encounter issues with the configuration system:

1. Check the troubleshooting section
2. Run the validation script
3. Review the migration report
4. Check the examples directory
5. Create an issue with configuration details (without secrets!)