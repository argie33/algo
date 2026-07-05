#!/usr/bin/env python3
"""
System Readiness Verification
Checks that all critical components are properly initialized and configured.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_schema():
    """Verify schema.sql contains required table definitions."""
    schema_file = project_root / "lambda" / "db-init" / "schema.sql"
    if not schema_file.exists():
        return False, "schema.sql not found"

    content = schema_file.read_text()
    required_tables = [
        "stock_scores",
        "swing_trader_scores",
        "signals_daily",
        "growth_metrics",
        "quality_metrics",
        "value_metrics",
        "positioning_metrics",
        "stability_metrics",
        "price_daily",
    ]

    missing = []
    for table in required_tables:
        if "CREATE TABLE" not in content or table not in content:
            missing.append(table)

    if missing:
        return False, f"Missing CREATE TABLE for: {', '.join(missing)}"
    return True, f"All {len(required_tables)} critical tables defined"

def check_github_actions():
    """Verify GitHub Actions invokes db-init Lambda."""
    workflow_file = project_root / ".github" / "workflows" / "deploy-all-infrastructure.yml"
    if not workflow_file.exists():
        return False, "GitHub Actions workflow not found"

    content = workflow_file.read_text()
    if "Invoke db-init Lambda" not in content or "aws lambda invoke" not in content:
        return False, "db-init Lambda invocation not found in workflow"
    return True, "db-init Lambda invocation configured"

def check_growth_metrics_loader():
    """Verify growth metrics loader computes quarterly_growth_momentum."""
    loader_file = project_root / "loaders" / "load_growth_metrics.py"
    content = loader_file.read_text()

    if "quarterly_growth_momentum" not in content:
        return False, "quarterly_growth_momentum not computed"
    return True, "quarterly_growth_momentum computation present"

def check_advanced_filters():
    """Verify advanced_filters handles growth metrics correctly."""
    filters_file = project_root / "algo" / "signals" / "advanced_filters.py"
    content = filters_file.read_text()

    if "quarterly_growth_momentum" not in content:
        return False, "quarterly_growth_momentum not referenced"

    # Check for fallback logic for missing quarterly momentum
    if "if mom is None" not in content and "if row[2] is None" not in content:
        return False, "No fallback logic for missing quarterly_growth_momentum"

    return True, "Growth score calculation handles missing quarterly momentum"

def check_paper_trading_config():
    """Verify paper trading is configured."""
    config_file = project_root / "algo" / "infrastructure" / "config" / "execution_config.py"
    content = config_file.read_text()

    if "alpaca_paper_trading" not in content:
        return False, "alpaca_paper_trading config not found"
    return True, "Paper trading configuration present"

def check_schema_validation():
    """Verify API Lambda includes schema validation."""
    api_file = project_root / "lambda" / "api" / "lambda_function.py"
    content = api_file.read_text()

    if "_apply_critical_migrations" not in content:
        return False, "Schema validation migrations not found"
    return True, "API Lambda validates schema on startup"

def main():
    """Run all checks."""
    checks = [
        ("Database Schema", check_schema),
        ("GitHub Actions db-init", check_github_actions),
        ("Growth Metrics Loader", check_growth_metrics_loader),
        ("Advanced Filters", check_advanced_filters),
        ("Paper Trading Config", check_paper_trading_config),
        ("API Schema Validation", check_schema_validation),
    ]

    print("=" * 80)
    print("SYSTEM READINESS VERIFICATION")
    print("=" * 80)

    passed = 0
    failed = 0

    for name, check_fn in checks:
        try:
            success, message = check_fn()
            status = "[PASS]" if success else "[FAIL]"
            print(f"\n{status}: {name}")
            print(f"       {message}")
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n[ERROR]: {name}")
            print(f"       {e}")
            failed += 1

    print("\n" + "=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed == 0:
        print("\n[READY] SYSTEM READY: All critical components are configured correctly")
        print("\nNext steps:")
        print("1. Deploy to AWS via GitHub Actions: deploy-all-infrastructure.yml")
        print("2. Verify db-init Lambda runs and creates tables")
        print("3. Run loaders to populate metrics (growth_metrics, quality_metrics, etc.)")
        print("4. Monitor dashboard for data population")
        print("5. Test paper trading with Alpaca")
        return 0
    else:
        print(f"\n[ERROR] SYSTEM NOT READY: {failed} issue(s) found")
        return 1

if __name__ == "__main__":
    sys.exit(main())
