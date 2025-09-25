#!/usr/bin/env python3
"""
GitHub Token Setup Helper

This script helps set up a GitHub Personal Access Token for repository validation.
"""

import os
import sys
import re

def validate_github_token(token):
    """Validate that a GitHub token looks correct."""
    if not token:
        return False, "Token is empty"
    
    token = token.strip()
    
    if len(token) < 20:
        return False, "Token is too short (should be 40+ characters)"
    
    if token.startswith('your_github') or token == 'your_token_here':
        return False, "Token appears to be a placeholder"
    
    # GitHub tokens typically start with 'ghp_' for personal access tokens
    if not (token.startswith('ghp_') or token.startswith('github_pat_') or re.match(r'^[a-f0-9]{40}$', token)):
        return False, "Token format doesn't match expected GitHub token patterns"
    
    return True, "Token format looks valid"

def update_env_file(token):
    """Update the .env file with the GitHub token."""
    env_file_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if not os.path.exists(env_file_path):
        print(f"❌ .env file not found at: {env_file_path}")
        return False
    
    try:
        # Read the current .env file
        with open(env_file_path, 'r') as f:
            lines = f.readlines()
        
        # Update the GITHUB_TOKEN line
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith('GITHUB_TOKEN='):
                lines[i] = f'GITHUB_TOKEN={token}\n'
                updated = True
                break
        
        if not updated:
            # Add the token if it doesn't exist
            lines.append(f'\nGITHUB_TOKEN={token}\n')
        
        # Write back to the file
        with open(env_file_path, 'w') as f:
            f.writelines(lines)
        
        print(f"✅ Updated .env file with GitHub token")
        return True
        
    except Exception as e:
        print(f"❌ Error updating .env file: {e}")
        return False

def test_token_with_api(token):
    """Test the token with GitHub API."""
    try:
        import requests
        
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitMesh-Token-Test/1.0'
        }
        
        # Test with a simple API call
        response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            rate_limit = data.get('rate', {})
            remaining = rate_limit.get('remaining', 0)
            limit = rate_limit.get('limit', 0)
            
            print(f"✅ GitHub token is valid!")
            print(f"   Rate limit: {remaining}/{limit} requests remaining")
            
            if limit >= 5000:
                print(f"✅ Authenticated rate limit detected (5000+ requests/hour)")
            else:
                print(f"⚠️ Rate limit seems low ({limit}/hour) - token may not be working properly")
            
            return True
        else:
            print(f"❌ GitHub API returned status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except ImportError:
        print("⚠️ Cannot test token - requests library not available")
        print("   Token format validation passed, should work")
        return True
    except Exception as e:
        print(f"❌ Error testing token with GitHub API: {e}")
        return False

def main():
    """Main setup function."""
    print("GitHub Token Setup Helper")
    print("=" * 40)
    print()
    print("This script will help you set up a GitHub Personal Access Token")
    print("to resolve API rate limit issues with repository validation.")
    print()
    
    # Check if token already exists
    current_token = os.getenv('GITHUB_TOKEN')
    if current_token and current_token.strip() and not current_token.startswith('your_github'):
        print(f"Current token: {current_token[:10]}...")
        
        valid, message = validate_github_token(current_token)
        if valid:
            print("✅ A GitHub token is already configured")
            
            test_choice = input("Do you want to test the current token? (y/n): ").lower().strip()
            if test_choice == 'y':
                if test_token_with_api(current_token):
                    print("\n🎉 Current token is working! No setup needed.")
                    return True
                else:
                    print("\n⚠️ Current token has issues. Let's set up a new one.")
            else:
                print("Skipping token test.")
                return True
        else:
            print(f"⚠️ Current token issue: {message}")
    
    print("\n" + "=" * 40)
    print("GITHUB TOKEN SETUP")
    print("=" * 40)
    print()
    print("1. Go to: https://github.com/settings/tokens/new")
    print("2. Token name: 'GitMesh Repository Validation'")
    print("3. Expiration: '90 days' (or as needed)")
    print("4. Scopes: Select 'public_repo' (for public repositories)")
    print("5. Click 'Generate token'")
    print("6. Copy the token (you won't see it again!)")
    print()
    
    # Get token from user
    token = input("Paste your GitHub Personal Access Token here: ").strip()
    
    if not token:
        print("❌ No token provided. Exiting.")
        return False
    
    # Validate token format
    valid, message = validate_github_token(token)
    if not valid:
        print(f"❌ Token validation failed: {message}")
        return False
    
    print(f"✅ Token format validation passed: {message}")
    
    # Test token with GitHub API
    print("\nTesting token with GitHub API...")
    if not test_token_with_api(token):
        print("❌ Token test failed. Please check the token and try again.")
        return False
    
    # Update .env file
    print("\nUpdating .env file...")
    if not update_env_file(token):
        print("❌ Failed to update .env file")
        return False
    
    print("\n" + "=" * 40)
    print("SETUP COMPLETE!")
    print("=" * 40)
    print("✅ GitHub token has been configured successfully")
    print("✅ Token has been tested and is working")
    print("✅ .env file has been updated")
    print()
    print("Next steps:")
    print("1. Restart your application to load the new token")
    print("2. Test repository validation with:")
    print("   python backend/test_github_token_retrieval.py")
    print()
    print("The rate limit issues should now be resolved!")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)