#!/usr/bin/env python3
"""
Migration script to transition from the old Redis system to the optimized system.

This script helps you:
1. Identify files using the old RedisRepoManager
2. Update imports to use OptimizedRedisRepoManager
3. Test the new system
"""

import os
import sys
import re
import glob
from typing import List, Tuple

def find_files_to_update() -> List[str]:
    """Find Python files that need to be updated."""
    
    print("🔍 Scanning for files that need updates...")
    
    # Patterns to search for
    patterns = [
        "from services.redis_repo_manager import RedisRepoManager",
        "from .redis_repo_manager import RedisRepoManager", 
        "RedisRepoManager(",
        "redis_get_repository_data",
        "get_repository_data_cached"
    ]
    
    files_to_update = set()
    
    # Search in common directories
    search_dirs = [
        "api/",
        "services/",
        "middleware/",
        "integrations/",
        "utils/"
    ]
    
    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                
                                for pattern in patterns:
                                    if pattern in content:
                                        files_to_update.add(file_path)
                                        break
                        except Exception as e:
                            print(f"   ⚠️  Could not read {file_path}: {e}")
    
    return list(files_to_update)


def analyze_file_usage(file_path: str) -> dict:
    """Analyze how a file uses the old system."""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        analysis = {
            'file': file_path,
            'uses_redis_repo_manager': 'RedisRepoManager' in content,
            'uses_redis_operations': 'redis_get_repository_data' in content,
            'uses_cached_operations': 'get_repository_data_cached' in content,
            'import_patterns': [],
            'usage_patterns': []
        }
        
        # Find import patterns
        import_patterns = [
            r'from services\.redis_repo_manager import.*',
            r'from \.redis_repo_manager import.*',
            r'import.*redis_repo_manager.*'
        ]
        
        for pattern in import_patterns:
            matches = re.findall(pattern, content)
            analysis['import_patterns'].extend(matches)
        
        # Find usage patterns
        usage_patterns = [
            r'RedisRepoManager\([^)]*\)',
            r'redis_get_repository_data\([^)]*\)',
            r'get_repository_data_cached\([^)]*\)'
        ]
        
        for pattern in usage_patterns:
            matches = re.findall(pattern, content)
            analysis['usage_patterns'].extend(matches)
        
        return analysis
        
    except Exception as e:
        return {'file': file_path, 'error': str(e)}


def suggest_updates(analysis: dict) -> List[str]:
    """Suggest updates for a file based on analysis."""
    
    suggestions = []
    
    if analysis.get('uses_redis_repo_manager'):
        suggestions.append(
            "Replace 'from services.redis_repo_manager import RedisRepoManager' "
            "with 'from services.optimized_redis_repo_manager import OptimizedRedisRepoManager'"
        )
        suggestions.append(
            "Replace 'RedisRepoManager(' with 'OptimizedRedisRepoManager('"
        )
    
    if analysis.get('uses_redis_operations'):
        suggestions.append(
            "Replace direct Redis operations with optimized service calls"
        )
    
    if analysis.get('uses_cached_operations'):
        suggestions.append(
            "Replace cached operations with optimized middleware calls"
        )
    
    return suggestions


def create_backup(file_path: str) -> str:
    """Create a backup of the original file."""
    
    backup_path = f"{file_path}.backup"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as original:
            content = original.read()
        
        with open(backup_path, 'w', encoding='utf-8') as backup:
            backup.write(content)
        
        return backup_path
        
    except Exception as e:
        print(f"   ❌ Could not create backup for {file_path}: {e}")
        return None


def apply_basic_updates(file_path: str) -> bool:
    """Apply basic automatic updates to a file."""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Basic replacements
        replacements = [
            (
                'from services.redis_repo_manager import RedisRepoManager',
                'from services.optimized_redis_repo_manager import OptimizedRedisRepoManager'
            ),
            (
                'from .redis_repo_manager import RedisRepoManager',
                'from .optimized_redis_repo_manager import OptimizedRedisRepoManager'
            ),
            (
                'RedisRepoManager(',
                'OptimizedRedisRepoManager('
            )
        ]
        
        for old, new in replacements:
            content = content.replace(old, new)
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
        
    except Exception as e:
        print(f"   ❌ Could not update {file_path}: {e}")
        return False


def main():
    """Main migration function."""
    
    print("🚀 Migration to Optimized Repository System")
    print("=" * 50)
    
    # Find files that need updates
    files_to_update = find_files_to_update()
    
    if not files_to_update:
        print("✅ No files found that need updates!")
        return
    
    print(f"📁 Found {len(files_to_update)} files that may need updates:")
    for file_path in files_to_update:
        print(f"   - {file_path}")
    
    print("\n🔍 Analyzing file usage patterns...")
    
    # Analyze each file
    analyses = []
    for file_path in files_to_update:
        analysis = analyze_file_usage(file_path)
        analyses.append(analysis)
        
        print(f"\n📄 {file_path}:")
        if 'error' in analysis:
            print(f"   ❌ Error: {analysis['error']}")
            continue
        
        if analysis['import_patterns']:
            print(f"   📥 Imports: {analysis['import_patterns']}")
        
        if analysis['usage_patterns']:
            print(f"   🔧 Usage: {analysis['usage_patterns'][:3]}...")  # Show first 3
        
        suggestions = suggest_updates(analysis)
        if suggestions:
            print(f"   💡 Suggestions:")
            for suggestion in suggestions:
                print(f"      - {suggestion}")
    
    # Ask for confirmation
    print(f"\n❓ Do you want to apply automatic updates? (y/n): ", end="")
    response = input().strip().lower()
    
    if response != 'y':
        print("❌ Migration cancelled.")
        return
    
    print("\n🔄 Applying updates...")
    
    updated_files = []
    failed_files = []
    
    for analysis in analyses:
        file_path = analysis['file']
        
        if 'error' in analysis:
            failed_files.append(file_path)
            continue
        
        # Create backup
        backup_path = create_backup(file_path)
        if not backup_path:
            failed_files.append(file_path)
            continue
        
        # Apply updates
        if apply_basic_updates(file_path):
            updated_files.append(file_path)
            print(f"   ✅ Updated {file_path} (backup: {backup_path})")
        else:
            print(f"   ⚠️  No changes needed for {file_path}")
    
    print(f"\n📊 Migration Summary:")
    print(f"   ✅ Updated files: {len(updated_files)}")
    print(f"   ❌ Failed files: {len(failed_files)}")
    
    if updated_files:
        print(f"\n📝 Updated files:")
        for file_path in updated_files:
            print(f"   - {file_path}")
    
    if failed_files:
        print(f"\n⚠️  Files that need manual review:")
        for file_path in failed_files:
            print(f"   - {file_path}")
    
    print(f"\n🧪 Next steps:")
    print(f"   1. Test the updated files to ensure they work correctly")
    print(f"   2. Run the test script: python test_optimized_system.py")
    print(f"   3. Monitor performance improvements")
    print(f"   4. Remove backup files once you're satisfied with the changes")


if __name__ == "__main__":
    # Change to backend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    main()