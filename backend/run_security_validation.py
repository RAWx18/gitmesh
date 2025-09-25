#!/usr/bin/env python3
"""
Run Security Validation

Simple script to run the comprehensive security validation.
"""

import os
import sys
import subprocess

def main():
    """Run the security validation script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    validation_script = os.path.join(script_dir, 'scripts', 'security_validation.py')
    
    print("🔒 Running comprehensive security validation...")
    print("=" * 60)
    
    try:
        # Run the validation script
        result = subprocess.run([sys.executable, validation_script], 
                              capture_output=True, text=True, cwd=script_dir)
        
        # Print output
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Exit with the same code as the validation script
        sys.exit(result.returncode)
        
    except Exception as e:
        print(f"Error running security validation: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()