#!/usr/bin/env python3
"""
Test the on-demand loading API endpoints to verify they work correctly
"""

import requests
import json
import time

# API base URL - adjust as needed
BASE_URL = "http://localhost:3000/api/stocks"

def test_endpoint(url, description):
    """Test a single endpoint and measure response time"""
    print(f"\n🧪 Testing: {description}")
    print(f"📡 URL: {url}")
    
    start_time = time.time()
    try:
        response = requests.get(url, timeout=10)
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to ms
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS - {response_time:.1f}ms")
            
            # Show data structure
            if 'data' in data:
                print(f"📊 Data available: {bool(data['data'])}")
                if isinstance(data['data'], dict):
                    print(f"🔑 Data keys: {list(data['data'].keys())}")
            elif 'coreData' in data:
                print(f"📊 Core data available: {bool(data['coreData'])}")
                print(f"🔗 On-demand endpoints: {len(data.get('onDemandEndpoints', {}))}")
            
            return True, response_time
        else:
            print(f"❌ FAILED - Status {response.status_code}: {response.text}")
            return False, None
            
    except requests.exceptions.Timeout:
        print(f"⏰ TIMEOUT - Request took longer than 10 seconds")
        return False, None
    except Exception as e:
        print(f"❌ ERROR - {str(e)}")
        return False, None

def main():
    """Test all on-demand loading endpoints"""
    print("🧪 ON-DEMAND LOADING API TEST")
    print("=" * 50)
    
    # Test symbol
    test_symbol = "AAPL"
    
    # Test endpoints in order of expected loading priority
    tests = [
        (f"{BASE_URL}/{test_symbol}", "Main stock page (ultra-fast core only)"),
        (f"{BASE_URL}/{test_symbol}/core", "Core data endpoint"),
        (f"{BASE_URL}/{test_symbol}/market", "Market data endpoint"),
        (f"{BASE_URL}/{test_symbol}/prices", "Price history endpoint"),
        (f"{BASE_URL}/{test_symbol}/financials", "Financial metrics endpoint"),
        (f"{BASE_URL}/{test_symbol}/analyst", "Analyst data endpoint"),
        (f"{BASE_URL}/{test_symbol}/technical", "Technical indicators endpoint"),
        (f"{BASE_URL}/{test_symbol}/governance", "Governance scores endpoint"),
        (f"{BASE_URL}/leadership/{test_symbol}", "Leadership team endpoint")
    ]
    
    results = []
    total_time = 0
    
    for url, description in tests:
        success, response_time = test_endpoint(url, description)
        results.append((description, success, response_time))
        if response_time:
            total_time += response_time
        time.sleep(0.5)  # Small delay between tests
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY")
    print("=" * 50)
    
    successful_tests = sum(1 for _, success, _ in results if success)
    total_tests = len(results)
    
    print(f"✅ Successful: {successful_tests}/{total_tests}")
    print(f"⏱️  Total response time: {total_time:.1f}ms")
    
    # Show response times for successful tests
    print(f"\n📊 RESPONSE TIMES:")
    for description, success, response_time in results:
        if success and response_time:
            status = "🟢 FAST" if response_time < 500 else "🟡 MEDIUM" if response_time < 2000 else "🔴 SLOW"
            print(f"  {status} {response_time:6.1f}ms - {description}")
        elif success:
            print(f"  ✅  N/A     - {description}")
        else:
            print(f"  ❌  FAILED  - {description}")
    
    print("\n🎯 ON-DEMAND LOADING STRATEGY:")
    print("1. Load main page instantly with core data only")
    print("2. Progressively load additional sections as needed")
    print("3. Cache loaded sections for better UX")
    print("4. Show loading indicators for pending sections")
    
    if successful_tests == total_tests:
        print("\n✅ All endpoints working - On-demand loading ready!")
        return True
    else:
        print(f"\n⚠️  {total_tests - successful_tests} endpoints failed - Check API server")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
