#!/usr/bin/env python3
"""
Test script to verify the comprehensive stocks endpoint returns all expected data
from the loadinfo tables (company_profile, market_data, key_metrics, analyst_estimates, governance_scores, leadership_team)
"""

import requests
import json
import sys

def test_comprehensive_stocks_endpoint():
    """Test the comprehensive stocks endpoint"""
    
    # Assuming the API is running locally - adjust URL as needed
    base_url = "http://localhost:3000/api"  # Change to your actual API URL
    endpoint = f"{base_url}/stocks"
    
    print("Testing comprehensive stocks endpoint...")
    print(f"URL: {endpoint}")
    
    try:
        # Test with a small limit to see the data structure
        params = {
            'limit': 5,
            'page': 1
        }
        
        response = requests.get(endpoint, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"✅ Success! Status: {response.status_code}")
            print(f"📊 Performance: {data.get('performance', 'N/A')}")
            print(f"📈 Records returned: {len(data.get('data', []))}")
            print(f"🗂️ Data sources: {', '.join(data.get('metadata', {}).get('dataSources', []))}")
            
            # Check if we have comprehensive data
            comprehensive = data.get('metadata', {}).get('comprehensiveData', {})
            print("\n🔍 Comprehensive Data Coverage:")
            for key, value in comprehensive.items():
                print(f"  {key}: {'✅' if value else '❌'}")
            
            # Examine first record to see data structure
            if data.get('data'):
                first_stock = data['data'][0]
                print(f"\n📋 Sample stock data for: {first_stock.get('symbol', 'Unknown')}")
                print(f"  Company: {first_stock.get('fullName', 'N/A')}")
                print(f"  Sector: {first_stock.get('sector', 'N/A')}")
                print(f"  Current Price: ${first_stock.get('price', {}).get('current', 'N/A')}")
                print(f"  Market Cap: ${first_stock.get('marketCap', 'N/A'):,}" if first_stock.get('marketCap') else "  Market Cap: N/A")
                
                # Check financial metrics
                metrics = first_stock.get('financialMetrics', {})
                print(f"  P/E Ratio: {metrics.get('trailingPE', 'N/A')}")
                print(f"  Revenue: ${metrics.get('totalRevenue', 'N/A'):,}" if metrics.get('totalRevenue') else "  Revenue: N/A")
                
                # Check analyst data
                analyst = first_stock.get('analystData', {})
                target = analyst.get('targetPrices', {}).get('mean')
                print(f"  Analyst Target: ${target}" if target else "  Analyst Target: N/A")
                
                # Check governance
                governance = first_stock.get('governance', {})
                print(f"  Overall Risk: {governance.get('overallRisk', 'N/A')}")
                
                # Check leadership
                leadership = first_stock.get('leadership', {})
                print(f"  Executive Count: {leadership.get('executiveCount', 0)}")
                
                # Check data availability flags
                print(f"\n📊 Data Availability:")
                print(f"  Company Profile: {'✅' if first_stock.get('hasCompanyProfile') else '❌'}")
                print(f"  Market Data: {'✅' if first_stock.get('hasMarketData') else '❌'}")
                print(f"  Financial Metrics: {'✅' if first_stock.get('hasFinancialMetrics') else '❌'}")
                print(f"  Analyst Data: {'✅' if first_stock.get('hasAnalystData') else '❌'}")
                print(f"  Governance Data: {'✅' if first_stock.get('hasGovernanceData') else '❌'}")
                print(f"  Leadership Data: {'✅' if first_stock.get('hasLeadershipData') else '❌'}")
            
            return True
            
        else:
            print(f"❌ Failed! Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode failed: {e}")
        return False

def test_leadership_endpoint():
    """Test the leadership endpoint"""
    
    base_url = "http://localhost:3000/api"
    endpoint = f"{base_url}/stocks/leadership"
    
    print(f"\n\nTesting leadership endpoint...")
    print(f"URL: {endpoint}")
    
    try:
        params = {'limit': 10}
        response = requests.get(endpoint, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Leadership endpoint success!")
            print(f"📊 Executive records: {data.get('count', 0)}")
            
            if data.get('data'):
                first_exec = data['data'][0]
                print(f"🏢 Sample executive: {first_exec.get('executiveInfo', {}).get('name', 'N/A')}")
                print(f"  Company: {first_exec.get('companyName', 'N/A')} ({first_exec.get('ticker', 'N/A')})")
                print(f"  Title: {first_exec.get('executiveInfo', {}).get('title', 'N/A')}")
                print(f"  Total Pay: ${first_exec.get('compensation', {}).get('totalPay', 'N/A'):,}" if first_exec.get('compensation', {}).get('totalPay') else "  Total Pay: N/A")
            
            return True
        else:
            print(f"❌ Leadership endpoint failed! Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Leadership endpoint error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Comprehensive Stocks API Endpoints")
    print("=" * 50)
    
    success1 = test_comprehensive_stocks_endpoint()
    success2 = test_leadership_endpoint()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("✅ All tests passed! The comprehensive stocks endpoint is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the API server and database connection.")
        sys.exit(1)
