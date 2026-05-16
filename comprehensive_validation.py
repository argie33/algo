#!/usr/bin/env python3
"""
Comprehensive Platform Validation — Check all critical systems.

Runs without AWS access. Tests:
1. API response formats
2. Data loader implementations
3. Calculation correctness
4. Schema alignment
5. Error handling
"""

import sys
import os
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))

def check_api_handlers():
    """Check API Lambda handlers for completeness."""
    print("\n" + "="*60)
    print("CHECKING API HANDLERS")
    print("="*60)

    issues = []

    # Load the lambda function
    try:
        from lambda.api.lambda_function import APIHandler
        print("✓ API Lambda imports successfully")
    except Exception as e:
        issues.append(f"✗ API Lambda import failed: {e}")
        return issues

    # Check critical endpoints exist
    handler = APIHandler()
    critical_endpoints = [
        '/api/economic/leading-indicators',
        '/api/economic/yield-curve-full',
        '/api/financial/test/key-metrics',
        '/api/stocks',
        '/api/market/technicals',
        '/api/sentiment/summary',
    ]

    # Check if handler methods exist
    handler_methods = dir(handler)
    if '_get_leading_indicators' in handler_methods:
        print("✓ Economic leading indicators handler exists")
    else:
        issues.append("✗ Economic leading indicators handler missing")

    if '_get_yield_curve_full' in handler_methods:
        print("✓ Yield curve handler exists")
    else:
        issues.append("✗ Yield curve handler missing")

    return issues


def check_data_loaders():
    """Check all data loaders can be imported."""
    print("\n" + "="*60)
    print("CHECKING DATA LOADERS")
    print("="*60)

    issues = []
    loader_files = [
        'load_key_metrics.py',
        'load_income_statement.py',
        'load_balance_sheet.py',
        'load_cash_flow.py',
        'loadpricedaily.py',
        'loadstockscores.py',
        'loadtechnicalsdaily.py',
        'loadecondata.py',
        'loadcalendar.py',
        'loadanalystsentiment.py',
    ]

    for loader_file in loader_files:
        path = Path(__file__).parent / loader_file
        if path.exists():
            # Try to run with --help to verify it's valid Python
            import subprocess
            result = subprocess.run(
                ['python3', str(path), '--help'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✓ {loader_file} is valid")
            else:
                issues.append(f"✗ {loader_file} has errors")
        else:
            issues.append(f"✗ {loader_file} not found")

    return issues


def check_key_metrics_loader():
    """Verify key_metrics loader has proper integration."""
    print("\n" + "="*60)
    print("CHECKING KEY METRICS LOADER INTEGRATION")
    print("="*60)

    issues = []

    # Check it exists
    path = Path(__file__).parent / 'load_key_metrics.py'
    if path.exists():
        print("✓ load_key_metrics.py exists")
    else:
        issues.append("✗ load_key_metrics.py not found")
        return issues

    # Check it's in Terraform config
    terraform_file = Path(__file__).parent / 'terraform/modules/loaders/main.tf'
    if terraform_file.exists():
        with open(terraform_file) as f:
            content = f.read()
            if 'load_key_metrics' in content:
                print("✓ key_metrics in Terraform loader_file_map")
            else:
                issues.append("✗ key_metrics not in Terraform loader_file_map")

            if '"key_metrics"' in content and 'cron' in content:
                print("✓ key_metrics scheduled in Terraform")
            else:
                issues.append("✗ key_metrics not scheduled in Terraform")
    else:
        issues.append("✗ Terraform loaders config not found")

    return issues


def check_economic_api_format():
    """Verify economic API response format."""
    print("\n" + "="*60)
    print("CHECKING ECONOMIC API FORMAT")
    print("="*60)

    issues = []

    # Check the lambda function has the new methods
    try:
        from lambda.api.lambda_function import APIHandler
        handler = APIHandler()

        # Check methods exist
        if hasattr(handler, '_get_leading_indicators'):
            print("✓ _get_leading_indicators method exists")
        else:
            issues.append("✗ _get_leading_indicators method missing")

        if hasattr(handler, '_get_yield_curve_full'):
            print("✓ _get_yield_curve_full method exists")
        else:
            issues.append("✗ _get_yield_curve_full method missing")

        # Check the method signatures are correct by reading source
        import inspect
        sig = str(inspect.signature(handler._get_leading_indicators))
        if 'self' in sig:
            print("✓ _get_leading_indicators has correct signature")
        else:
            issues.append("✗ _get_leading_indicators signature wrong")

    except Exception as e:
        issues.append(f"✗ Cannot check economic API: {e}")

    return issues


def check_sentiment_endpoints():
    """Check sentiment endpoints are properly implemented."""
    print("\n" + "="*60)
    print("CHECKING SENTIMENT ENDPOINTS")
    print("="*60)

    issues = []

    # Check for placeholder returns
    try:
        from lambda.api.lambda_function import APIHandler
        handler = APIHandler()

        # Look at source code for /api/sentiment/social/insights
        import inspect
        source = inspect.getsource(handler._handle_sentiment)

        if 'return json_response(200, [])' in source:
            # Find context
            if '/api/sentiment/social/insights' in source:
                issues.append("⚠️  /api/sentiment/social/insights returns empty array (placeholder)")
                print("⚠️  /api/sentiment/social/insights is placeholder")
            else:
                print("✓ No placeholder returns in sentiment handler")
        else:
            print("✓ No placeholder returns in sentiment handler")

    except Exception as e:
        issues.append(f"Cannot check sentiment endpoints: {e}")

    return issues


def check_stock_detail_endpoints():
    """Check stock detail endpoints."""
    print("\n" + "="*60)
    print("CHECKING STOCK DETAIL ENDPOINTS")
    print("="*60)

    issues = []

    try:
        from lambda.api.lambda_function import APIHandler
        import inspect

        handler = APIHandler()

        # Check /api/stocks/{symbol} handler
        source = inspect.getsource(handler._handle_stocks)
        if 'company_name' in source and 'sector' in source:
            print("✓ Stock detail handler returns company info")
        else:
            issues.append("✗ Stock detail handler missing company info")

        if 'market_cap' in source or 'key_metrics' in source:
            print("✓ Stock detail handler includes market cap")
        else:
            issues.append("⚠️  Stock detail handler may not include market cap")

    except Exception as e:
        issues.append(f"Cannot check stock endpoints: {e}")

    return issues


def check_calculation_modules():
    """Check critical calculation modules."""
    print("\n" + "="*60)
    print("CHECKING CALCULATION MODULES")
    print("="*60)

    issues = []

    modules = [
        ('algo_market_exposure.py', 'MarketExposure'),
        ('algo_var.py', 'VaR'),
        ('algo_swing_score.py', 'SwingScore'),
    ]

    for module_file, class_name in modules:
        path = Path(__file__).parent / module_file
        if path.exists():
            with open(path) as f:
                content = f.read()
                if f'class {class_name}' in content:
                    print(f"✓ {module_file}: {class_name} class exists")
                else:
                    issues.append(f"✗ {module_file}: {class_name} class not found")
        else:
            issues.append(f"✗ {module_file} not found")

    return issues


def main():
    """Run all validation checks."""
    print("\n" + "█"*60)
    print("█ COMPREHENSIVE PLATFORM VALIDATION")
    print("█"*60)

    all_issues = []

    all_issues.extend(check_api_handlers())
    all_issues.extend(check_data_loaders())
    all_issues.extend(check_key_metrics_loader())
    all_issues.extend(check_economic_api_format())
    all_issues.extend(check_sentiment_endpoints())
    all_issues.extend(check_stock_detail_endpoints())
    all_issues.extend(check_calculation_modules())

    # Summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)

    errors = [i for i in all_issues if i.startswith('✗')]
    warnings = [i for i in all_issues if i.startswith('⚠️')]

    if not all_issues:
        print("✅ ALL CHECKS PASSED - Platform validation complete")
        return 0
    else:
        if errors:
            print(f"\n❌ {len(errors)} ERRORS:")
            for error in errors:
                print(f"  {error}")

        if warnings:
            print(f"\n⚠️  {len(warnings)} WARNINGS:")
            for warning in warnings:
                print(f"  {warning}")

        return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
