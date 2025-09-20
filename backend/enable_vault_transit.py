#!/usr/bin/env python3
"""
Simple script to enable Vault transit secrets engine
"""

import os
import subprocess
import sys

def enable_vault_transit():
    """Enable Vault transit secrets engine using CLI"""
    
    # Set environment variables
    vault_addr = 'http://127.0.0.1:8200'
    # vault_token =
    
    env = os.environ.copy()
    env['VAULT_ADDR'] = vault_addr
    env['VAULT_TOKEN'] = vault_token
    
    try:
        print("Enabling transit secrets engine...")
        
        # Enable transit secrets engine
        result = subprocess.run(
            ['vault', 'secrets', 'enable', 'transit'],
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ Transit secrets engine enabled successfully")
        elif "path is already in use" in result.stderr:
            print("✓ Transit secrets engine is already enabled")
        else:
            print(f"Error enabling transit: {result.stderr}")
            return False
            
        print("Vault setup completed successfully!")
        return True
        
    except FileNotFoundError:
        print("Error: 'vault' command not found. Please install HashiCorp Vault CLI.")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if enable_vault_transit():
        print("\n🎉 Ready to start GitMesh backend!")
        sys.exit(0)
    else:
        sys.exit(1)
