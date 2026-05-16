#!/usr/bin/env python3
"""
Lambda wrapper for lightweight loaders.

Wraps OptimalLoader-based loaders for serverless execution on AWS Lambda.
Handles environment setup, invocation, and response formatting.

USAGE (local):
    python3 lambda_loader_wrapper.py loadecondata

USAGE (Lambda):
    Runtime: python3.11
    Handler: lambda_loader_wrapper.handler
    Memory: 512 MB
    Timeout: 300 seconds
    Env vars: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, APCA_API_KEY_ID, APCA_API_SECRET_KEY, etc.

DEPLOYMENT:
    aws lambda create-function --function-name econ-data-loader \
      --runtime python3.11 --handler lambda_loader_wrapper.handler \
      --memory-size 512 --timeout 300 \
      --zip-file fileb://lambda_package.zip \
      --environment Variables="{DB_HOST=...,DB_USER=stocks,...}"
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import json
import logging
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class LambdaLoaderWrapper:
    """Wrapper for running OptimalLoader subclasses on Lambda."""

    LOADER_MAPPING = {
        "econ": "loadecondata.EconDataLoader",
        "calendar": "loadcalendar.CalendarLoader",
        "sentiment": "loadsentiment.SentimentLoader",
        "feargreed": "loadfeargreed.FearGreedLoader",
        "naaim": "loadnaaim.NAAIMLoader",
        "analyst_sentiment": "loadanalystsentiment.AnalystSentimentLoader",
        "analyst_upgrade": "loadanalystupgradedowngrade.AnalystUpgradeDowngradeLoader",
        "benchmark": "loadbenchmark.BenchmarkLoader",
        "commodities": "loadcommodities.CommoditiesLoader",
        "news": "loadnews.NewsLoader",
        # Add more as needed
    }

    def __init__(self):
        self.event_data: Dict[str, Any] = {}
        self.context: Optional[Any] = None

    def handler(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """AWS Lambda handler function.

        Args:
            event: Lambda event (contains loader name, symbols, etc.)
            context: Lambda context (function info, request ID, etc.)

        Returns:
            JSON response with stats, status, and execution time.
        """
        self.event_data = event
        self.context = context
        start = datetime.utcnow()

        try:
            # Parse request
            loader_name = event.get("loader", "").lower()
            symbols = event.get("symbols")  # None = all symbols
            parallelism = event.get("parallelism", 4)
            backfill_days = event.get("backfill_days")

            log.info("LambdaLoaderWrapper invoked: loader=%s symbols=%s parallelism=%d",
                     loader_name, symbols, parallelism)

            if not loader_name or loader_name not in self.LOADER_MAPPING:
                return self._error_response(
                    f"Unknown loader: {loader_name}. Supported: {list(self.LOADER_MAPPING.keys())}",
                    start,
                    400,
                )

            # Import and run loader
            class_path = self.LOADER_MAPPING[loader_name]
            module_name, class_name = class_path.rsplit(".", 1)

            try:
                module = __import__(module_name, fromlist=[class_name])
                loader_class = getattr(module, class_name)
            except (ImportError, AttributeError) as e:
                return self._error_response(f"Failed to import {class_path}: {e}", start, 500)

            # Instantiate and run
            try:
                loader = loader_class()
                if symbols:
                    symbol_list = (
                        symbols if isinstance(symbols, list)
                        else [s.strip() for s in symbols.split(",")]
                    )
                else:
                    # Get all active symbols from DB
                    symbol_list = self._get_all_symbols()

                log.info("Running loader with %d symbols", len(symbol_list))
                stats = loader.run(
                    symbol_list,
                    parallelism=parallelism,
                    backfill_days=backfill_days,
                )
                loader.close()

                return self._success_response(stats, start)
            except Exception as e:
                log.exception("Loader execution failed")
                return self._error_response(str(e), start, 500)

        except Exception as e:
            log.exception("Unexpected error in handler")
            return self._error_response(str(e), start, 500)

    def _get_all_symbols(self) -> list:
        """Fetch active symbols from database."""
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", "stocks"),
                password=credential_manager.get_db_credentials()["password"],
                database=os.getenv("DB_NAME", "stocks"),
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT symbol FROM stock_symbols
                        WHERE symbol NOT IN ('SPY', 'QQQ')  -- Common benchmarks
                        ORDER BY symbol
                    """)
                    return [r[0] for r in cur.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            log.warning("Failed to fetch symbols from DB: %s", e)
            return []

    def _success_response(self, stats: Dict[str, Any], start: datetime) -> Dict[str, Any]:
        """Format successful response."""
        elapsed = (datetime.utcnow() - start).total_seconds()
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "stats": stats,
                "execution_time_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat(),
            }),
        }

    def _error_response(self, error: str, start: datetime, status_code: int = 500) -> Dict[str, Any]:
        """Format error response."""
        elapsed = (datetime.utcnow() - start).total_seconds()
        return {
            "statusCode": status_code,
            "body": json.dumps({
                "status": "error",
                "error": error,
                "execution_time_seconds": round(elapsed, 2),
                "timestamp": datetime.utcnow().isoformat(),
            }),
        }


# AWS Lambda entry point
_wrapper = LambdaLoaderWrapper()
handler = _wrapper.handler


# CLI entry point (for local testing)
def main():
    """Run locally for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Lambda loader locally")
    parser.add_argument("loader", help="Loader name (e.g., econ, calendar)")
    parser.add_argument("--symbols", help="Comma-separated symbols (default: all)")
    parser.add_argument("--parallelism", type=int, default=4)
    parser.add_argument("--backfill-days", type=int)
    args = parser.parse_args()

    event = {
        "loader": args.loader,
        "symbols": args.symbols,
        "parallelism": args.parallelism,
    }
    if args.backfill_days:
        event["backfill_days"] = args.backfill_days

    # Mock Lambda context
    class MockContext:
        request_id = "local-test"
        invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:loader-test"

    wrapper = LambdaLoaderWrapper()
    response = wrapper.handler(event, MockContext())

    print(json.dumps(json.loads(response["body"]), indent=2))
    return 0 if response["statusCode"] == 200 else 1


if __name__ == "__main__":
    sys.exit(main())

