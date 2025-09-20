#!/usr/bin/env python3
"""
Script to set up HashiCorp Vault for GitMesh
"""

import os
import hvac
import sys

def setup_vault():
    """Set up Vault with required configurations"""
    # Get Vault configuration from environment
    vault_addr = os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200')
    vault_token = os.getenv('VAULT_TOKEN')
    
    if not vault_token:
        print("Error: VAULT_TOKEN environment variable not set")
        print("Please run: export VAULT_TOKEN=<your-vault-token>")
        sys.exit(1)
    
    print(f"Connecting to Vault at {vault_addr}")
    
    try:
        # Initialize Vault client
        client = hvac.Client(url=vault_addr, token=vault_token)
        
        # Check if client is authenticated
        if not client.is_authenticated():
            print("Error: Failed to authenticate with Vault")
            print("Please check your VAULT_TOKEN")
            sys.exit(1)
        
        print("✓ Successfully authenticated with Vault")
        
        # Check if transit secrets engine is enabled
        try:
            client.secrets.transit.read_key(name='test-key')
            print("✓ Transit secrets engine is already enabled")
        except hvac.exceptions.InvalidPath:
            # Transit engine not enabled, enable it
            try:
                client.sys.enable_secrets_engine(
                    backend_type='transit',
                    path='transit'
                )
                print("✓ Enabled transit secrets engine")
            except Exception as e:
                if "path is already in use" in str(e):
                    print("✓ Transit secrets engine is already enabled")
                else:
                    print(f"Error enabling transit secrets engine: {e}")
                    sys.exit(1)
        except Exception as e:
            # Try to enable transit engine
            try:
                client.sys.enable_secrets_engine(
                    backend_type='transit',
                    path='transit'
                )
                print("✓ Enabled transit secrets engine")
            except Exception as enable_error:
                if "path is already in use" in str(enable_error):
                    print("✓ Transit secrets engine is already enabled")
                else:
                    print(f"Error enabling transit secrets engine: {enable_error}")
                    sys.exit(1)
        
        # Test creating a transit key
        try:
            client.secrets.transit.create_key(name='pat-encryption-key', exportable=False)
            print("✓ Created transit encryption key 'pat-encryption-key'")
        except Exception as e:
            if "already exists" in str(e) or "key already exists" in str(e):
                print("✓ Transit encryption key 'pat-encryption-key' already exists")
            else:
                print(f"Error creating transit key: {e}")
                sys.exit(1)
        
        print("\n🎉 Vault setup completed successfully!")
        print("\nYou can now start the GitMesh backend with:")
        print("cd backend && uvicorn app:app --host 0.0.0.0 --port 8000 --reload")
        
    except Exception as e:
        print(f"Error setting up Vault: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_vault()
