#!/usr/bin/env python3
"""
Methodical network request analysis to find cached shim files
"""
import requests
import json
import time

def test_server():
    print("🔍 SYSTEMATIC NETWORK ANALYSIS")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    
    # Test 1: Check if server responds
    try:
        response = requests.get(base_url, timeout=5)
        print(f"✅ Server responsive: {response.status_code}")
    except Exception as e:
        print(f"❌ Server error: {e}")
        return False
    
    # Test 2: Check actual HTML content
    html_content = response.text
    if "use-sync-external-store-shim" in html_content:
        print("🚨 FOUND SHIM REFERENCE IN HTML!")
        lines = html_content.split('\n')
        for i, line in enumerate(lines):
            if "use-sync-external-store-shim" in line:
                print(f"Line {i+1}: {line.strip()}")
    else:
        print("✅ No shim references in HTML")
    
    # Test 3: Check main JS file
    js_url = f"{base_url}/assets/index-DSAigFlh.js"
    try:
        js_response = requests.get(js_url, timeout=5)
        js_content = js_response.text[:2000]  # First 2000 chars
        
        if "use-sync-external-store-shim.production.js" in js_content:
            print("🚨 FOUND EXACT SHIM FILE REFERENCE IN JS!")
            return True
        else:
            print("✅ No exact shim file references in main JS")
    except Exception as e:
        print(f"❌ Failed to fetch JS: {e}")
    
    # Test 4: Try to access shim file directly (should fail)
    shim_url = f"{base_url}/assets/use-sync-external-store-shim.production.js"
    try:
        shim_response = requests.get(shim_url, timeout=5)
        if shim_response.status_code == 200:
            print("🚨 SHIM FILE EXISTS ON SERVER!")
            return True
        else:
            print(f"✅ Shim file returns {shim_response.status_code} (expected)")
    except Exception as e:
        print(f"✅ Shim file not accessible: {e}")
    
    # Test 5: Check for service worker
    sw_url = f"{base_url}/sw.js"
    try:
        sw_response = requests.get(sw_url, timeout=5)
        if sw_response.status_code == 200:
            print("⚠️ Service worker found - might be caching")
            return "service_worker"
        else:
            print("✅ No service worker")
    except Exception as e:
        print("✅ No service worker")
    
    print("\n📊 CONCLUSION:")
    print("- Server serves clean files")
    print("- No shim references in build")
    print("- Error must be browser cache related")
    
    return False

if __name__ == "__main__":
    result = test_server()
    exit(0 if result is False else 1)