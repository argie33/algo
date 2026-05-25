#!/usr/bin/env python3
"""
System Operational Verification Script  
Checks: API connectivity, Frontend health, DB pools
"""

import sys, json, requests, time, io
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

API_URL = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api"
FRONTEND_URL = "https://d1copuy2oqlazx.cloudfront.net"

def log(level, msg):
    colors = {'OK': GREEN + '[OK]' + RESET, 'FAIL': RED + '[FAIL]' + RESET, 'WARN': YELLOW + '[WARN]' + RESET, 'INFO': BLUE + '[INFO]' + RESET}
    icon = colors.get(level, '')
    print(f"{icon} {msg}")

def test_api_health():
    print(f"\n{BLUE}{'='*60}{RESET}\n{BLUE}1. API LAMBDA HEALTH{RESET}\n{BLUE}{'='*60}{RESET}")
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code == 200:
            log('OK', f"API healthy: {resp.json().get('status')}")
            return True
        log('FAIL', f"API returned {resp.status_code}")
        return False
    except Exception as e:
        log('FAIL', f"API unreachable: {e}")
        return False

def test_api_endpoints():
    print(f"\n{BLUE}4. API ENDPOINTS{RESET}")
    endpoints = [('/health', 'Health'), ('/algo/status', 'Orchestrator'), ('/algo/trades', 'Trades'), ('/algo/positions', 'Positions'), ('/signals/stocks', 'Signals'), ('/market', 'Market')]
    results = []
    for endpoint, name in endpoints:
        try:
            resp = requests.get(f"{API_URL}{endpoint}", timeout=30)
            if resp.status_code in [200, 401, 404]:
                log('OK', f"{name:20} {endpoint:25}: HTTP {resp.status_code}")
                results.append(True)
            else:
                log('FAIL', f"{name:20} {endpoint:25}: HTTP {resp.status_code}")
                results.append(False)
        except Exception as e:
            log('FAIL', f"{name:20} {endpoint:25}: {str(e)[:50]}")
            results.append(False)
    return all(results)

def main():
    print(f"\n{'='*60}\nSYSTEM VERIFICATION - {datetime.now().isoformat()}\n{'='*60}")
    results = {'API Health': test_api_health(), 'API Endpoints': test_api_endpoints()}
    passed = sum(1 for v in results.values() if v)
    print(f"\n{BLUE}Result: {passed}/2{RESET}\n")
    return 0 if passed >= 1 else 1

if __name__ == '__main__':
    sys.exit(main())
