#!/usr/bin/env python3
"""Consolidate utils directory by removing duplicate flat files and updating imports.

This script:
1. Maps duplicate flat files to their subdirectory equivalents
2. Updates all imports across the codebase
3. Verifies consistency
4. Lists files to be deleted
"""

import os
import re
from pathlib import Path
from collections import defaultdict

# Mapping of flat file to subdirectory replacement
CONSOLIDATION_MAP = {
    # Database
    "db_connection": ("db", "connection"),
    "db_retry_helper": ("db", "retry"),
    "query_cache": ("db", "query_cache"),
    "dynamodb_health_check": ("db", "dynamo_health"),
    "dynamodb_lock_manager": ("db", "dynamo_lock"),
    "rds_pool_monitor": ("db", "pool_monitor"),

    # Data
    "data_source_router": ("data", "source_router"),
    "data_provenance_tracker": ("data", "provenance"),
    "data_watermark_manager": ("data", "watermark"),
    "data_ops": ("data", "ops"),
    "data_tick_validator": ("data", "tick_validator"),

    # External
    "sec_edgar_client": ("external", "sec_edgar"),
    "yfinance_wrapper": ("external", "yfinance"),

    # Infrastructure
    "feature_flags": ("infrastructure", "feature_flags"),
    "api_endpoints": ("infrastructure", "api_endpoints"),
    "csv_sanitizer": ("infrastructure", "csv_sanitizer"),
    "correlation_context": ("infrastructure", "correlation"),
    "execution_timeout": ("infrastructure", "timeout"),
    "timezone_utils": ("infrastructure", "timezone"),
    "url_validator": ("infrastructure", "url_validator"),
    "market_timing_constants": ("infrastructure", "market_timing"),

    # Logging
    "sla_monitor": ("logging", "sla"),

    # Ops
    "orchestrator_query": ("ops", "orchestrator_query"),
    "position_sync_checker": ("ops", "position_sync"),
    "production_readiness_check": ("ops", "production_readiness"),

    # Loaders
    "loader_config": ("loaders", "config"),
    "loader_conflict_detector": ("loaders", "conflict_detector"),
    "loader_helpers": ("loaders", "helpers"),

    # Signals
    "signal_query_builder": ("signals", "query_builder"),
    "signal_scorer": ("signals", "scorer"),
    "algo_metrics_fetcher": ("signals", "metrics_fetcher"),
    "grade_classifier": ("signals", "grade_classifier"),

    # Trading
    "trade_recorder": ("trading", "recorder"),
    "trade_status": ("trading", "status"),
    "public_rate_limiter": ("trading", "rate_limiter"),
    "filter_rejection_tracker": ("trading", "rejection_tracker"),

    # Validation
    "data_validation_registry": ("validation", "registry"),
    "alpaca_response_validator": ("validation", "alpaca"),
    "aws_production_config_validator": ("validation", "aws_config"),
    "domain_validators": ("validation", "domain"),
    "financial_data_validator": ("validation", "financial"),
    "validation_framework": ("validation", "framework"),
    "freshness_validator": ("validation", "freshness"),
    "data_freshness_config": ("validation", "freshness_config"),
    "validation_integration": ("validation", "integration"),
    "parallelism_validator": ("validation", "parallelism"),
    "rate_limit_validator": ("validation", "rate_limit"),
    "schema_validator": ("validation", "schema"),

    # Misc
    "database_context": ("db", "context"),
    "data_validation_registry": ("validation", "registry"),
    "loader_failure_tracker": ("logging", "loader_failure"),
    "loader_history_tracker": ("logging", "history_tracker"),
    "orchestrator_execution_tracker": ("logging", "execution_tracker"),
}


def find_python_files(root_dir, exclude_dirs=None):
    """Find all Python files in the project."""
    if exclude_dirs is None:
        exclude_dirs = {"build", "terraform", ".git", "__pycache__", ".pytest_cache"}

    python_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Remove excluded directories from the search
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for filename in filenames:
            if filename.endswith(".py"):
                python_files.append(os.path.join(dirpath, filename))

    return python_files


def get_import_patterns(flat_name, subdirs):
    """Generate regex patterns to find imports of a flat file."""
    subdir, new_name = subdirs
    patterns = [
        # from utils.flat_name import ...
        (rf"from utils\.{flat_name} import",
         f"from utils.{subdir}.{new_name} import"),
        # from utils.flat_name import X as Y
        (rf"from utils\.{flat_name}\b",
         f"from utils.{subdir}.{new_name}"),
        # import utils.flat_name
        (rf"import utils\.{flat_name}\b",
         f"import utils.{subdir}.{new_name}"),
    ]
    return patterns


def update_imports_in_file(file_path, replacements):
    """Update imports in a single file. Returns True if changes made."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [!] Cannot read {file_path}: {e}")
        return False

    original = content
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    if content != original:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"  [ERROR] Cannot write {file_path}: {e}")
            return False

    return False


def main():
    import os
    # Get the algo directory (parent of scripts)
    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent
    utils_dir = root_dir / "utils"
    print(f"   Root dir: {root_dir}")
    print(f"   Utils dir: {utils_dir}")

    print("=" * 80)
    print("UTILS DIRECTORY CONSOLIDATION")
    print("=" * 80)

    # Collect all replacement patterns
    all_replacements = []
    for flat_name, subdirs in CONSOLIDATION_MAP.items():
        patterns = get_import_patterns(flat_name, subdirs)
        all_replacements.extend(patterns)

    # Find all Python files
    print("\n[*] Scanning for Python files...")
    python_files = find_python_files(root_dir)
    print(f"   Found {len(python_files)} Python files")

    # Update imports
    print("\n[*] Updating imports...")
    files_changed = defaultdict(int)

    for file_path in python_files:
        if update_imports_in_file(file_path, all_replacements):
            files_changed[file_path] = True

    print(f"   [OK] Updated {len(files_changed)} files with import changes")

    # List flat files to delete
    print("\n[*] Files to delete (flat duplicates):")
    files_to_delete = []
    for flat_name in CONSOLIDATION_MAP.keys():
        flat_file = utils_dir / f"{flat_name}.py"
        if flat_file.exists():
            files_to_delete.append(flat_file)
            print(f"   - {flat_file.relative_to(root_dir)}")

    print(f"\n[*] SUMMARY")
    print(f"   Total duplicate pairs found: {len(CONSOLIDATION_MAP)}")
    print(f"   Files to delete: {len(files_to_delete)}")
    print(f"   Import statements updated: {len([k for k in files_changed.values() if k])}")

    return files_to_delete


if __name__ == "__main__":
    files_to_delete = main()
