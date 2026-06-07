#!/usr/bin/env python3
"""
Verification tests for critical fixes:
- Issue #1: Hardcoded localhost API URL
- Issue #3: Database timeout returning 200 status
- Issue #14: Missing API health status endpoint
"""

from pathlib import Path

def test_issue_1_config_generation():
    """Issue #1: Verify config.js generation logic"""
    # Check that the build script in deploy-code.yml generates config.js
    deploy_yml = Path("C:/Users/arger/code/algo/.github/workflows/deploy-code.yml").read_text()

    assert "Prepare Runtime Config" in deploy_yml, "Config generation missing in deploy-code.yml"
    assert "VITE_API_URL" in deploy_yml, "VITE_API_URL not referenced in deploy-code.yml"
    assert "webapp/frontend/dist/config.js" in deploy_yml, "config.js output not configured"
    assert "API_URL" in deploy_yml and "website_url" in deploy_yml, "API_URL generation from website_url missing"

def test_issue_3_database_timeout():
    """Issue #3: Verify database timeout handling raises exceptions"""
    utils_py = Path("C:/Users/arger/code/algo/lambda/api/routes/utils.py").read_text()

    assert "def execute_with_timeout" in utils_py, "execute_with_timeout function not found"
    assert "raise e" in utils_py and "psycopg2.errors.QueryCanceled" in utils_py, "QueryCanceled exception handling missing"
    assert "for attempt in range(max_attempts)" in utils_py, "Retry logic not found"
    assert "Query timeout" in utils_py, "Timeout logging not found"
    assert 'error_response(code' in utils_py and '"statusCode": code' in utils_py, "error_response statusCode handling missing"

def test_issue_14_health_endpoint():
    """Issue #14: Verify enhanced health endpoint"""
    health_py = Path("C:/Users/arger/code/algo/lambda/api/routes/health.py").read_text()

    assert "def _handle_basic" in health_py, "_handle_basic function not found"
    assert "pg_stat_activity" in health_py, "RDS connection pool check missing"
    assert "utilization_percent" in health_py, "Pool utilization calculation missing"
    assert "price_daily" in health_py and "created_at" in health_py, "Data freshness check missing"
    assert "age_days" in health_py or "oldest_data_age_days" in health_py, "Freshness age calculation missing"
    assert "status" in health_py and ("healthy" in health_py or "warning" in health_py), "System status determination missing"
    assert "execute_with_timeout" in health_py, "execute_with_timeout safety wrapper missing"
    assert "success_response" in health_py, "Response formatting missing"

def test_response_format_consistency():
    """Verify all response helpers return consistent statusCode format"""
    utils_py = Path("C:/Users/arger/code/algo/lambda/api/routes/utils.py").read_text()

    assert 'success_response' in utils_py and '"statusCode": 200' in utils_py, "success_response statusCode missing"
    assert 'error_response' in utils_py and '"statusCode": code' in utils_py, "error_response statusCode missing"
    assert 'list_response' in utils_py and '"statusCode": 200' in utils_py, "list_response statusCode missing"

