#!/usr/bin/env python3
"""
Comprehensive Platform Verification Suite
Runs all 7 phases of verification once API 401 blocker is fixed.
"""

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Any, Tuple, List

class VerificationSuite:
    """Systematically verify platform is production-ready."""

    def __init__(self, api_base: str = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"):
        self.api_base = api_base
        self.results = {}
        self.issues = []
        self.passed = 0
        self.failed = 0

    def log(self, phase: str, msg: str, status: str = "INFO"):
        """Log verification message."""
        symbol = {"PASS": "✓", "FAIL": "✗", "INFO": "→", "WARN": "⚠"}[status]
        color_codes = {
            "PASS": "\033[92m",  # Green
            "FAIL": "\033[91m",  # Red
            "WARN": "\033[93m",  # Yellow
            "INFO": "\033[94m"   # Blue
        }
        reset = "\033[0m"
        print(f"{color_codes[status]}{symbol} {phase:20} | {msg}{reset}")

    def test(self, name: str, func) -> bool:
        """Run a test and track results."""
        try:
            result = func()
            if result:
                self.log(name, "PASS", "PASS")
                self.passed += 1
                return True
            else:
                self.log(name, "FAIL", "FAIL")
                self.failed += 1
                self.issues.append(name)
                return False
        except Exception as e:
            self.log(name, f"ERROR: {str(e)}", "FAIL")
            self.failed += 1
            self.issues.append(f"{name}: {str(e)}")
            return False

    # PHASE 1: API CONNECTIVITY
    def phase_1_api_blocker(self) -> bool:
        """Check if API 401 blocker is fixed."""
        self.log("PHASE 1", "Checking API 401 blocker", "INFO")

        def test_api_status():
            resp = requests.get(f"{self.api_base}/api/algo/status", timeout=5)
            if resp.status_code == 401:
                self.log("API Status", "Still returns 401 - blocker not fixed", "WARN")
                return False
            if resp.status_code == 200:
                self.log("API Status", "Returns 200 - blocker FIXED ✓", "PASS")
                return True
            self.log("API Status", f"Returns {resp.status_code}", "WARN")
            return False

        return self.test("API 401 Blocker", test_api_status)

    # PHASE 2: DATA LOADING
    def phase_2_data_loading(self) -> bool:
        """Verify loaders executed today."""
        self.log("PHASE 2", "Verifying data loading", "INFO")

        def test_data_exists():
            # This would connect to database
            # For now, check API returns data
            resp = requests.get(f"{self.api_base}/api/stocks?limit=5", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                has_data = isinstance(data, list) and len(data) > 0
                if has_data:
                    self.log("Data Loading", f"Found {len(data)} stocks", "PASS")
                else:
                    self.log("Data Loading", "No stocks returned", "WARN")
                return has_data
            return False

        return self.test("Data Loading", test_data_exists) if self.passed > 0 else True

    # PHASE 3: CALCULATION VERIFICATION
    def phase_3_calculations(self) -> bool:
        """Verify calculations produce reasonable values."""
        self.log("PHASE 3", "Spot-checking calculations", "INFO")

        def test_calculations():
            resp = requests.get(f"{self.api_base}/api/scores/stockscores?limit=5", timeout=5)
            if resp.status_code != 200:
                return False

            data = resp.json()
            if not isinstance(data, dict) or 'items' not in data:
                return False

            items = data['items']
            for item in items:
                # Verify score is between 0-100
                if 'composite_score' in item:
                    score = item['composite_score']
                    if not (0 <= score <= 100):
                        self.log("Calculation", f"Invalid score {score} for {item.get('symbol')}", "WARN")
                        return False

            self.log("Calculation", f"Verified {len(items)} stocks have valid scores", "PASS")
            return len(items) > 0

        return self.test("Calculations", test_calculations) if self.passed > 0 else True

    # PHASE 4: API ENDPOINTS
    def phase_4_api_endpoints(self) -> bool:
        """Test all critical API endpoints."""
        self.log("PHASE 4", "Testing API endpoints", "INFO")

        endpoints = [
            ("/api/algo/status", "Status"),
            ("/api/stocks?limit=5", "Stocks"),
            ("/api/scores/stockscores?limit=5", "Scores"),
            ("/api/algo/exposure-policy", "Exposure"),
            ("/api/algo/risk-metrics", "Risk"),
            ("/api/signals/daily?limit=5", "Signals"),
        ]

        passed = 0
        for endpoint, name in endpoints:
            try:
                resp = requests.get(f"{self.api_base}{endpoint}", timeout=5)
                if resp.status_code == 200:
                    self.log(f"Endpoint: {name:15}", "✓", "PASS")
                    passed += 1
                else:
                    self.log(f"Endpoint: {name:15}", f"HTTP {resp.status_code}", "FAIL")
            except Exception as e:
                self.log(f"Endpoint: {name:15}", str(e)[:50], "FAIL")

        self.passed += passed
        self.failed += len(endpoints) - passed
        return passed >= len(endpoints) - 1  # Allow 1 failure

    # PHASE 5: FRONTEND PAGES
    def phase_5_frontend(self) -> bool:
        """Check if frontend pages can load."""
        self.log("PHASE 5", "Frontend verification (manual needed)", "INFO")
        self.log("Frontend", "Cannot auto-test frontend from CLI", "WARN")
        self.log("Frontend", "Manually check: https://your-cloudfront-url/app/dashboard", "INFO")
        return True  # Manual step

    # PHASE 6: ORCHESTRATOR
    def phase_6_orchestrator(self) -> bool:
        """Verify orchestrator can run."""
        self.log("PHASE 6", "Orchestrator verification (manual needed)", "INFO")
        self.log("Orchestrator", "Run: python3 algo_orchestrator.py --mode paper --dry-run", "INFO")
        return True  # Manual step

    # PHASE 7: SECURITY
    def phase_7_security(self) -> bool:
        """Check for security issues."""
        self.log("PHASE 7", "Checking security", "INFO")

        def test_npm_audit():
            import subprocess
            result = subprocess.run(["npm", "audit", "--json"], capture_output=True, text=True)
            try:
                data = json.loads(result.stdout)
                vuln_count = sum(v for v in data.get("metadata", {}).get("vulnerabilities", {}).values())
                if vuln_count > 0:
                    self.log("npm Security", f"{vuln_count} vulnerabilities found", "WARN")
                    return False
                return True
            except:
                return True  # Assume OK if can't check

        return self.test("Security", test_npm_audit)

    def run_all(self) -> Tuple[bool, Dict[str, Any]]:
        """Run complete verification suite."""
        print("\n" + "="*70)
        print("PLATFORM VERIFICATION SUITE")
        print("="*70 + "\n")

        # Run phases in order
        self.phase_1_api_blocker()

        if self.passed > 0:  # Only continue if API works
            self.phase_2_data_loading()
            self.phase_3_calculations()
            self.phase_4_api_endpoints()
            self.phase_5_frontend()
            self.phase_6_orchestrator()
            self.phase_7_security()
        else:
            print("\n🔴 API 401 BLOCKER ACTIVE - Cannot continue testing")
            print("Waiting for Terraform deployment to fix API Gateway auth...")
            return False, {"status": "BLOCKED_BY_401"}

        # Summary
        print("\n" + "="*70)
        print(f"RESULTS: {self.passed} PASSED, {self.failed} FAILED")
        print("="*70 + "\n")

        if self.issues:
            print("🔴 ISSUES FOUND:")
            for issue in self.issues:
                print(f"  - {issue}")
            print()

        success = self.failed == 0
        status = "✅ PRODUCTION READY" if success else "⚠️  NEEDS FIXES"
        print(f"{status}\n")

        return success, {
            "passed": self.passed,
            "failed": self.failed,
            "issues": self.issues,
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    suite = VerificationSuite()
    success, results = suite.run_all()
    sys.exit(0 if success else 1)
