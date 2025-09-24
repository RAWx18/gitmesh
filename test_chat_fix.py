#!/usr/bin/env python3
"""
Simple test script to verify chat API fixes
"""
import requests
import json

def test_chat_health():
    """Test the chat health endpoint"""
    try:
        response = requests.get("http://localhost:8000/api/v1/chat/health", timeout=10)
        print(f"Health check status: {response.status_code}")
        if response.status_code == 200:
            health_data = response.json()
            print(f"Health data: {json.dumps(health_data, indent=2)}")
            return True
        else:
            print(f"Health check failed: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Health check request failed: {e}")
        return False

def test_error_handling():
    """Test error handling by making an invalid request"""
    try:
        # Try to access a protected endpoint without auth
        response = requests.get("http://localhost:8000/api/v1/chat/sessions/invalid", timeout=10)
        print(f"Protected endpoint status: {response.status_code}")
        if response.status_code == 401:
            error_data = response.json()
            print(f"Error response: {json.dumps(error_data, indent=2)}")
            return True
        else:
            print(f"Unexpected response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error handling test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing chat API fixes...")
    
    print("\n1. Testing health endpoint...")
    health_ok = test_chat_health()
    
    print("\n2. Testing error handling...")
    error_ok = test_error_handling()
    
    if health_ok and error_ok:
        print("\n✅ All tests passed! Chat API fixes are working.")
    else:
        print("\n❌ Some tests failed. Check the backend logs.")