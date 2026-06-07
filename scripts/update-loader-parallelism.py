#!/usr/bin/env python3
"""
Update Loader Parallelism Dynamically

Allows updating parallelism values in DynamoDB without redeploying Terraform or restarting loaders.
Loaders pick up the new values at their next startup (with 5-minute cache on read).

Usage:
    # Update single loader
    python scripts/update-loader-parallelism.py --loader technical_data_daily --parallelism 3 --environment dev

    # Update multiple loaders at once
    python scripts/update-loader-parallelism.py --loader technical_data_daily --parallelism 3 \
        --loader buy_sell_daily --parallelism 4 --environment dev

    # List all current configurations
    python scripts/update-loader-parallelism.py --list --environment dev

    # Batch update from JSON file
    python scripts/update-loader-parallelism.py --from-file updates.json --environment dev

    # Reset to defaults
    python scripts/update-loader-parallelism.py --reset --environment dev
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default parallelism values for reset
DEFAULT_PARALLELISM = {
    "stock_symbols": 1,
    "sp500_constituents": 1,
    "russell2000_constituents": 1,
    "stock_prices_daily": 1,
    "financials_annual_income": 1,
    "financials_annual_balance": 1,
    "financials_annual_cashflow": 1,
    "financials_quarterly_income": 1,
    "financials_quarterly_balance": 1,
    "financials_quarterly_cashflow": 1,
    "financials_ttm_income": 1,
    "financials_ttm_cashflow": 1,
    "growth_metrics": 2,
    "quality_metrics": 2,
    "value_metrics": 2,
    "positioning_metrics": 2,
    "stability_metrics": 2,
    "stock_scores": 3,
    "earnings_history": 1,
    "earnings_calendar": 1,
    "company_profile": 2,
    "analyst_sentiment": 2,
    "analyst_upgrades_downgrades": 2,
    "industry_ranking": 4,
    "feargreed": 1,
    "aaiidata": 1,
    "naaim_data": 1,
    "sentiment": 1,
    "sentiment_aggregate": 1,
    "signal_themes": 4,
    "signal_quality_scores": 2,
    "buy_sell_daily": 3,
    "technical_data_daily": 2,
    "market_health_daily": 1,
    "algo_metrics_daily": 1,
    "swing_trader_scores": 2,
    "sector_ranking": 1,
    "fred_economic_data": 1,
    "trend_template_data": 4,
}


class LoaderConfigUpdater:
    """Update loader configuration in DynamoDB."""

    def __init__(self, environment: str, region: str = "us-east-1"):
        self.environment = environment
        self.region = region
        self.project_name = os.getenv("PROJECT_NAME", "algo")
        self.table_name = f"{self.project_name}-loader-config-{environment}"
        self.dynamodb = boto3.client("dynamodb", region_name=region)

        # Verify table exists
        try:
            self.dynamodb.describe_table(TableName=self.table_name)
        except self.dynamodb.exceptions.ResourceNotFoundException:
            raise RuntimeError(f"Table {self.table_name} not found. Create it with Terraform first.")

    def get_config(self, loader_name: str) -> Optional[Dict]:
        """Get current configuration for a loader."""
        try:
            response = self.dynamodb.get_item(
                TableName=self.table_name,
                Key={"loader_name": {"S": loader_name}}
            )
            if "Item" in response:
                item = response["Item"]
                return {
                    "loader_name": item["loader_name"]["S"],
                    "parallelism": int(item["parallelism"]["N"]),
                    "enabled": item.get("enabled", {}).get("BOOL", True),
                    "updated_at": item.get("updated_at", {}).get("S", ""),
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get config for {loader_name}: {e}")
            return None

    def update_config(self, loader_name: str, parallelism: int) -> bool:
        """Update configuration for a loader."""
        try:
            item = {
                "loader_name": {"S": loader_name},
                "parallelism": {"N": str(parallelism)},
                "enabled": {"BOOL": True},
                "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
            }
            self.dynamodb.put_item(TableName=self.table_name, Item=item)
            logger.info(f"✓ Updated {loader_name}: parallelism={parallelism}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to update {loader_name}: {e}")
            return False

    def list_configs(self) -> bool:
        """List all loader configurations."""
        try:
            response = self.dynamodb.scan(TableName=self.table_name)
            items = response.get("Items", [])

            if not items:
                logger.info("No loader configurations found")
                return True

            # Sort by loader name
            items.sort(key=lambda x: x["loader_name"]["S"])

            print(f"\nLoader Configuration ({self.table_name}):")
            print("-" * 70)
            print(f"{'Loader Name':<40} {'Parallelism':<15} {'Updated':<15}")
            print("-" * 70)

            for item in items:
                loader_name = item["loader_name"]["S"]
                parallelism = item["parallelism"]["N"]
                updated_at = item.get("updated_at", {}).get("S", "N/A")
                # Parse ISO timestamp and show relative time
                if updated_at != "N/A":
                    updated_at = updated_at.split("T")[0]  # Show just the date
                print(f"{loader_name:<40} {parallelism:<15} {updated_at:<15}")

            print("-" * 70)
            return True
        except Exception as e:
            logger.error(f"Failed to list configurations: {e}")
            return False

    def reset_to_defaults(self) -> bool:
        """Reset all loaders to default parallelism values."""
        logger.warning("Resetting all loaders to default parallelism values...")
        success_count = 0
        error_count = 0

        for loader_name, parallelism in DEFAULT_PARALLELISM.items():
            if self.update_config(loader_name, parallelism):
                success_count += 1
            else:
                error_count += 1

        logger.info(f"Reset complete: {success_count} loaders updated, {error_count} errors")
        return error_count == 0

    def update_from_file(self, file_path: str) -> bool:
        """Update configurations from a JSON file."""
        try:
            with open(file_path, "r") as f:
                updates = json.load(f)

            if not isinstance(updates, dict):
                logger.error("JSON file must contain an object with loader names as keys")
                return False

            success_count = 0
            error_count = 0

            for loader_name, config in updates.items():
                if isinstance(config, dict) and "parallelism" in config:
                    parallelism = config["parallelism"]
                else:
                    parallelism = config

                if isinstance(parallelism, int) and parallelism > 0:
                    if self.update_config(loader_name, parallelism):
                        success_count += 1
                    else:
                        error_count += 1
                else:
                    logger.error(f"Invalid parallelism value for {loader_name}: {parallelism}")
                    error_count += 1

            logger.info(f"Update complete: {success_count} loaders updated, {error_count} errors")
            return error_count == 0
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Update Loader Parallelism Dynamically",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--environment",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment (dev, staging, prod)"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )

    # Mutually exclusive actions
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--loader",
        action="append",
        dest="loader_updates",
        help="Loader name to update (can specify multiple times with --parallelism)"
    )
    action_group.add_argument(
        "--list",
        action="store_true",
        help="List all loader configurations"
    )
    action_group.add_argument(
        "--reset",
        action="store_true",
        help="Reset all loaders to default parallelism values"
    )
    action_group.add_argument(
        "--from-file",
        type=str,
        help="Update configurations from JSON file"
    )

    parser.add_argument(
        "--parallelism",
        action="append",
        type=int,
        dest="parallelism_values",
        help="Parallelism value (use with --loader, one per loader in same order)"
    )

    args = parser.parse_args()

    try:
        updater = LoaderConfigUpdater(args.environment, args.region)

        if args.list:
            return 0 if updater.list_configs() else 1

        if args.reset:
            return 0 if updater.reset_to_defaults() else 1

        if args.from_file:
            return 0 if updater.update_from_file(args.from_file) else 1

        if args.loader_updates:
            if not args.parallelism_values:
                logger.error("Must specify --parallelism value(s) for each --loader")
                return 1

            if len(args.loader_updates) != len(args.parallelism_values):
                logger.error(f"Number of --loader and --parallelism arguments must match")
                return 1

            success_count = 0
            error_count = 0

            for loader_name, parallelism in zip(args.loader_updates, args.parallelism_values):
                if parallelism <= 0:
                    logger.error(f"Parallelism must be > 0, got {parallelism}")
                    error_count += 1
                elif updater.update_config(loader_name, parallelism):
                    success_count += 1
                else:
                    error_count += 1

            return 0 if error_count == 0 else 1

        parser.print_help()
        return 1

    except RuntimeError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
