#!/usr/bin/env python3
"""Auto-apply @validate_api_response decorator to all API handlers.

This script automatically:
1. Scans all handler files for _get_* and _handle_* functions
2. Maps handlers to endpoint names from DASHBOARD_ENDPOINTS
3. Adds @validate_api_response decorator to each handler
4. Adds validate_api_response import if missing

Usage: python scripts/apply_response_validators.py
"""

import re
from pathlib import Path

# Mapping of handler functions to endpoint names
# Format: ("handler_function_name", "endpoint_name_in_contract")
HANDLER_TO_ENDPOINT = {
    # Config endpoints
    "_get_algo_config": "cfg",
    "_get_algo_config_key": "cfg",

    # Dashboard endpoints
    "_get_algo_positions": "pos",
    "_get_algo_status": "run",
    "_get_algo_trades": "trades",
    "_get_circuit_breakers": "cb",
    "_get_dashboard_signals": "sig",
    "_get_equity_curve": "perf",

    # Market endpoints
    "_get_data_quality": "health",
    "_get_data_status": "health",
    "_get_market": "mkt",
    "_get_market_factors": "mkt",
    "_get_market_sentiment": "mkt",
    "_get_markets": "mkt",
    "_get_trend_criteria": "mkt",

    # Metrics endpoints
    "_get_algo_metrics": "perf",
    "_get_algo_performance": "perf",
    "_get_algo_portfolio": "port",
    "_get_daily_return_histogram": "perf",
    "_get_holding_period_distribution": "perf",
    "_get_performance_analytics": "perf",
    "_get_performance_metrics_endpoint": "perf",
    "_get_portfolio_summary": "port",
    "_get_risk_metrics": "risk",
    "_get_stage_distribution": "perf",
    "_get_trade_distribution": "perf",

    # Monitoring endpoints
    "_get_algo_audit_log": "audit",
    "_get_last_run": "run",
    "_get_notifications": "notif",
    "_get_patrol_log": "health",

    # Orchestration endpoints
    "_get_orchestrator_execution_details": "run",
    "_get_orchestrator_execution_failed": "run",
    "_get_orchestrator_execution_patterns": "run",
    "_get_orchestrator_execution_recent": "run",
    "_get_orchestrator_execution_stats": "run",

    # Sector endpoints
    "_get_algo_evaluate": "sig_eval",
    "_get_sector_breadth": "srank",
    "_get_sector_position_warnings": "pos",
    "_get_sector_rotation": "sec_rot",
    "_get_sector_stage2": "srank",

    # Signal endpoints
    "_get_rejection_funnel": "sig",
    "_get_swing_scores": "scores",
    "_get_swing_scores_history": "scores",

    # External endpoints
    "_get_economic_calendar": "econ_cal",
    "_get_sentiment": "sentiment",
}


def apply_decorators_to_file(filepath: Path) -> tuple[int, int]:
    """Apply @validate_api_response decorator to handlers in a file.

    Returns: (total_handlers, updated_handlers)
    """
    with open(filepath) as f:
        content = f.read()

    original_content = content
    updated_count = 0
    total_count = 0

    # Check if validate_api_response is imported
    has_import = "validate_api_response" in content

    # Find all handler function definitions
    for handler_name, endpoint_name in HANDLER_TO_ENDPOINT.items():
        # Pattern: def _function_name(...):
        pattern = rf"(^def {handler_name}\([^)]*\)[^:]*:)"
        matches = list(re.finditer(pattern, content, re.MULTILINE))

        if matches:
            total_count += len(matches)

            # Process each match (in reverse to maintain string positions)
            for match in reversed(matches):
                # Check if decorator already applied
                start = match.start()
                before_text = content[:start]

                # Look back to see if @validate_api_response is already there
                if f'@validate_api_response("{endpoint_name}")' in before_text[-500:]:
                    continue  # Already decorated

                # Find the previous line break (where we'll insert decorator)
                insert_pos = before_text.rfind('\n') + 1

                # Insert decorator
                decorator_line = f'@validate_api_response("{endpoint_name}")\n'
                content = content[:insert_pos] + decorator_line + content[insert_pos:]
                updated_count += 1

    # Add import if needed and content changed
    if updated_count > 0 and not has_import:
        # Find the utils import line and add validate_api_response
        import_pattern = r"from routes\.utils import \((.*?)\)"
        match = re.search(import_pattern, content, re.DOTALL)
        if match:
            imports = match.group(1)
            if "validate_api_response" not in imports:
                new_imports = imports.rstrip() + ",\n    validate_api_response,"
                content = content.replace(
                    f"from routes.utils import ({imports})",
                    f"from routes.utils import ({new_imports})"
                )

    # Write back if changes made
    if content != original_content:
        with open(filepath, "w") as f:
            f.write(content)

    return total_count, updated_count


def main():
    """Apply decorators to all handler files."""
    handlers_dir = Path("lambda/api/routes/algo_handlers")

    if not handlers_dir.exists():
        print(f"ERROR: {handlers_dir} not found")
        return

    total_files = 0
    total_handlers = 0
    total_updated = 0

    for filepath in sorted(handlers_dir.glob("*.py")):
        if filepath.name.startswith("__"):
            continue

        handler_count, updated_count = apply_decorators_to_file(filepath)

        if handler_count > 0:
            total_files += 1
            total_handlers += handler_count
            total_updated += updated_count
            status = "[OK]" if updated_count > 0 else "[--]"
            print(f"{status} {filepath.name}: {updated_count}/{handler_count} updated")

    print(f"\n{'='*60}")
    print(f"Total: {total_updated}/{total_handlers} handlers decorated")
    print(f"Files modified: {total_files}")
    print(f"{'='*60}")

    if total_updated > 0:
        print("\n[SUCCESS] Decorators applied successfully!")
        print("\nNext steps:")
        print("  1. Review changes: git diff")
        print("  2. Run tests: python -m pytest tests/test_api_response_consistency.py -v")
        print("  3. If tests pass, commit: git commit -m 'fix: Apply response validation to all API endpoints'")
    else:
        print("\n[WARNING] No decorators were added. They may already be applied.")


if __name__ == "__main__":
    main()
