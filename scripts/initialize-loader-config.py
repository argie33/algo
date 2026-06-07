#!/usr/bin/env python3
"""
Initialize Loader Configuration in DynamoDB

Populates the loader config table with default parallelism values from Terraform.
Run this script after deploying the DynamoDB table to seed initial configuration.

Usage:
    python scripts/initialize-loader-config.py --environment dev
    python scripts/initialize-loader-config.py --environment prod
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default parallelism values from terraform/modules/loaders/main.tf
DEFAULT_LOADER_CONFIG = {
    # Reference data — tiny lists, parallelism=1
    "stock_symbols": {"parallelism": 1},
    "sp500_constituents": {"parallelism": 1},
    "russell2000_constituents": {"parallelism": 1},

    # Unified Price Loader
    "stock_prices_daily": {"parallelism": 1},

    # Financial statements
    "financials_annual_income": {"parallelism": 1},
    "financials_annual_balance": {"parallelism": 1},
    "financials_annual_cashflow": {"parallelism": 1},
    "financials_quarterly_income": {"parallelism": 1},
    "financials_quarterly_balance": {"parallelism": 1},
    "financials_quarterly_cashflow": {"parallelism": 1},
    "financials_ttm_income": {"parallelism": 1},
    "financials_ttm_cashflow": {"parallelism": 1},

    # Computed metrics
    "growth_metrics": {"parallelism": 2},
    "quality_metrics": {"parallelism": 2},
    "value_metrics": {"parallelism": 2},
    "positioning_metrics": {"parallelism": 2},
    "stability_metrics": {"parallelism": 2},
    "stock_scores": {"parallelism": 3},

    # Earnings data
    "earnings_history": {"parallelism": 1},
    "earnings_calendar": {"parallelism": 1},

    # Company & analyst data
    "company_profile": {"parallelism": 2},
    "analyst_sentiment": {"parallelism": 2},
    "analyst_upgrades_downgrades": {"parallelism": 2},
    "industry_ranking": {"parallelism": 4},

    # Market sentiment data
    "feargreed": {"parallelism": 1},
    "aaiidata": {"parallelism": 1},
    "naaim_data": {"parallelism": 1},

    # Sentiment aggregation
    "sentiment": {"parallelism": 1},
    "sentiment_aggregate": {"parallelism": 1},

    # Signal processing
    "signal_themes": {"parallelism": 4},
    "signal_quality_scores": {"parallelism": 2},

    # BUY/SELL signals
    "buy_sell_daily": {"parallelism": 3},

    # Technical indicators
    "technical_data_daily": {"parallelism": 2},

    # Market health
    "market_health_daily": {"parallelism": 1},

    # Algo metrics
    "algo_metrics_daily": {"parallelism": 1},

    # Swing trader scores
    "swing_trader_scores": {"parallelism": 2},

    # Sector ranking
    "sector_ranking": {"parallelism": 1},

    # FRED macro data
    "fred_economic_data": {"parallelism": 1},

    # Trend template
    "trend_template_data": {"parallelism": 4},
}


def initialize_loader_config(environment: str, region: str = "us-east-1"):
    """Initialize loader configuration in DynamoDB."""
    project_name = os.getenv("PROJECT_NAME", "algo")
    table_name = f"{project_name}-loader-config-{environment}"

    logger.info(f"Initializing loader config table: {table_name}")
    logger.info(f"Region: {region}")

    try:
        dynamodb = boto3.client("dynamodb", region_name=region)

        # Check if table exists
        try:
            dynamodb.describe_table(TableName=table_name)
            logger.info(f"Table {table_name} exists")
        except dynamodb.exceptions.ResourceNotFoundException:
            logger.error(f"Table {table_name} not found. Create it with Terraform first.")
            return False

        # Initialize each loader configuration
        success_count = 0
        error_count = 0

        for loader_name, config in DEFAULT_LOADER_CONFIG.items():
            try:
                item = {
                    "loader_name": {"S": loader_name},
                    "parallelism": {"N": str(config["parallelism"])},
                    "enabled": {"BOOL": True},
                    "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
                }

                dynamodb.put_item(TableName=table_name, Item=item)
                logger.info(f"  ✓ {loader_name}: parallelism={config['parallelism']}")
                success_count += 1
            except Exception as e:
                logger.error(f"  ✗ {loader_name}: {e}")
                error_count += 1

        logger.info(f"\nInitialization complete: {success_count} loaders configured, {error_count} errors")
        return error_count == 0

    except Exception as e:
        logger.error(f"Failed to initialize loader config: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Initialize Loader Configuration in DynamoDB")
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

    args = parser.parse_args()

    success = initialize_loader_config(args.environment, args.region)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
