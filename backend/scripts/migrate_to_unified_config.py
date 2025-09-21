#!/usr/bin/env python3
"""
Migration script to update codebase to use unified configuration.

This script helps identify and update hardcoded values throughout the codebase
to use the new unified configuration system.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# Patterns to find hardcoded values
HARDCODED_PATTERNS = {
    'database_urls': [
        r'postgresql://[^"\']+',
        r'postgresql\+asyncpg://[^"\']+',
    ],
    'redis_urls': [
        r'redis://[^"\']+',
    ],
    'api_keys': [
        r'AIzaSy[A-Za-z0-9_-]+',
        r'sk-[A-Za-z0-9]+',
        r'Iv23li[A-Za-z0-9]+',
    ],
    'localhost_urls': [
        r'http://localhost:\d+',
        r'http://127\.0\.0\.1:\d+',
    ],
    'vault_tokens': [
        r'hvs\.[A-Za-z0-9]+',
    ],
    'jwt_tokens': [
        r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    ]
}

# Replacement suggestions
REPLACEMENT_SUGGESTIONS = {
    'database_urls': 'config.get_database_url()',
    'redis_urls': 'config.get_redis_url()',
    'api_keys': 'config.get_ai_api_key()',
    'localhost_urls': 'config.server.frontend_url or config.get_cors_origins()',
    'vault_tokens': 'config.vault.token',
    'jwt_tokens': 'config.security.jwt_secret'
}

# Files to exclude from scanning
EXCLUDE_PATTERNS = [
    r'.*\.pyc$',
    r'.*/__pycache__/.*',
    r'.*/venv/.*',
    r'.*/node_modules/.*',
    r'.*\.git/.*',
    r'.*\.env$',
    r'.*\.env\..*',
    r'.*/migrate_to_unified_config\.py$',
]


def should_exclude_file(file_path: str) -> bool:
    """Check if file should be excluded from scanning."""
    for pattern in EXCLUDE_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def find_hardcoded_values(file_path: str) -> Dict[str, List[Tuple[int, str]]]:
    """Find hardcoded values in a file."""
    if should_exclude_file(file_path):
        return {}
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return {}
    
    findings = {}
    lines = content.split('\n')
    
    for category, patterns in HARDCODED_PATTERNS.items():
        category_findings = []
        
        for pattern in patterns:
            for line_num, line in enumerate(lines, 1):
                matches = re.finditer(pattern, line)
                for match in matches:
                    category_findings.append((line_num, match.group()))
        
        if category_findings:
            findings[category] = category_findings
    
    return findings


def scan_directory(directory: str) -> Dict[str, Dict[str, List[Tuple[int, str]]]]:
    """Scan directory for hardcoded values."""
    results = {}
    
    for root, dirs, files in os.walk(directory):
        # Skip certain directories
        dirs[:] = [d for d in dirs if d not in ['venv', 'node_modules', '.git', '__pycache__']]
        
        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.yaml', '.yml', '.json')):
                file_path = os.path.join(root, file)
                findings = find_hardcoded_values(file_path)
                
                if findings:
                    results[file_path] = findings
    
    return results


def generate_migration_report(results: Dict[str, Dict[str, List[Tuple[int, str]]]]) -> str:
    """Generate a migration report."""
    report = []
    report.append("# Configuration Migration Report")
    report.append("=" * 50)
    report.append("")
    
    if not results:
        report.append("✅ No hardcoded values found!")
        return "\n".join(report)
    
    total_issues = sum(len(findings) for file_findings in results.values() for findings in file_findings.values())
    report.append(f"Found {total_issues} hardcoded values across {len(results)} files")
    report.append("")
    
    for file_path, file_findings in results.items():
        report.append(f"## {file_path}")
        report.append("-" * len(file_path))
        
        for category, findings in file_findings.items():
            report.append(f"### {category.replace('_', ' ').title()}")
            
            for line_num, value in findings:
                # Mask sensitive values
                masked_value = mask_sensitive_value(value)
                report.append(f"  Line {line_num}: {masked_value}")
                
                # Add suggestion
                suggestion = REPLACEMENT_SUGGESTIONS.get(category, "Use unified config")
                report.append(f"    → Suggestion: {suggestion}")
            
            report.append("")
        
        report.append("")
    
    # Add migration instructions
    report.append("# Migration Instructions")
    report.append("=" * 30)
    report.append("")
    report.append("1. Import unified config in your files:")
    report.append("   ```python")
    report.append("   from config.unified_config import get_config")
    report.append("   config = get_config()")
    report.append("   ```")
    report.append("")
    report.append("2. Replace hardcoded values with config calls:")
    report.append("   - Database URLs: `config.get_database_url()`")
    report.append("   - Redis URLs: `config.get_redis_url()`")
    report.append("   - API Keys: `config.get_ai_api_key()`")
    report.append("   - Server URLs: `config.server.frontend_url`")
    report.append("   - CORS Origins: `config.get_cors_origins()`")
    report.append("")
    report.append("3. Update environment variables in .env file")
    report.append("4. Test configuration loading with: `python -m config.unified_config`")
    
    return "\n".join(report)


def mask_sensitive_value(value: str) -> str:
    """Mask sensitive parts of values for reporting."""
    if len(value) > 20:
        return value[:10] + "..." + value[-5:]
    elif len(value) > 10:
        return value[:5] + "..." + value[-2:]
    else:
        return value[:3] + "..."


def create_config_usage_examples():
    """Create example files showing how to use unified config."""
    examples_dir = Path("backend/examples/config_usage")
    examples_dir.mkdir(parents=True, exist_ok=True)
    
    # Database example
    db_example = '''"""
Example: Using unified config for database operations
"""
from config.unified_config import get_config
from sqlalchemy.ext.asyncio import create_async_engine

def create_database_engine():
    config = get_config()
    
    # Instead of hardcoded URL
    # engine = create_async_engine("postgresql://...")
    
    # Use unified config
    engine = create_async_engine(
        config.get_database_url(),
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        echo=config.database.echo
    )
    return engine
'''
    
    with open(examples_dir / "database_example.py", "w") as f:
        f.write(db_example)
    
    # Redis example
    redis_example = '''"""
Example: Using unified config for Redis operations
"""
import redis.asyncio as redis
from config.unified_config import get_config

async def create_redis_client():
    config = get_config()
    
    # Instead of hardcoded connection
    # client = redis.from_url("redis://...")
    
    # Use unified config
    client = redis.from_url(
        config.get_redis_url(),
        socket_timeout=config.redis.socket_timeout,
        socket_connect_timeout=config.redis.connect_timeout,
        max_connections=config.redis.max_connections,
        decode_responses=config.redis.decode_responses
    )
    return client
'''
    
    with open(examples_dir / "redis_example.py", "w") as f:
        f.write(redis_example)
    
    # API client example
    api_example = '''"""
Example: Using unified config for API clients
"""
from config.unified_config import get_config
import httpx

def create_ai_client():
    config = get_config()
    
    # Instead of hardcoded API key
    # headers = {"Authorization": "Bearer sk-..."}
    
    # Use unified config
    api_key = config.get_ai_api_key()
    if not api_key:
        raise ValueError(f"No API key configured for provider: {config.ai.provider}")
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    client = httpx.AsyncClient(
        headers=headers,
        timeout=config.ai.timeout
    )
    return client
'''
    
    with open(examples_dir / "api_client_example.py", "w") as f:
        f.write(api_example)
    
    print(f"✅ Created configuration usage examples in {examples_dir}")


def main():
    """Main migration function."""
    print("🔍 Scanning codebase for hardcoded configuration values...")
    
    # Scan backend directory
    backend_dir = Path(__file__).parent.parent
    results = scan_directory(str(backend_dir))
    
    # Generate report
    report = generate_migration_report(results)
    
    # Save report
    report_path = backend_dir / "config_migration_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"📋 Migration report saved to: {report_path}")
    
    # Create usage examples
    create_config_usage_examples()
    
    # Print summary
    if results:
        total_issues = sum(len(findings) for file_findings in results.values() for findings in file_findings.values())
        print(f"⚠️  Found {total_issues} hardcoded values that need migration")
        print(f"📁 Check {len(results)} files listed in the report")
    else:
        print("✅ No hardcoded values found!")
    
    print("\n🚀 Next steps:")
    print("1. Review the migration report")
    print("2. Update files to use unified config")
    print("3. Test with: python -m config.unified_config")
    print("4. Update .env file with new structure")


if __name__ == "__main__":
    main()