"""
Universal Lambda handler for running Python data loaders.

This allows any loader (loadpricedaily.py, loadeodhd.py, etc.) to run on AWS Lambda
instead of ECS Fargate, reducing costs by 70% for small loaders (<5min, <512MB).

Usage (CloudFormation or Lambda console):
    - Function: PythonLoaderExecutor (or similar)
    - Runtime: Python 3.11+ with pandas, psycopg2, yfinance, etc.
    - Environment: LOADER_NAME, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, ALPACA_API_KEY, etc.
    - Timeout: 600s (10 min for safety, adjust per loader)
    - Memory: 512MB (sufficient for most loaders)

Invocation examples:
    aws lambda invoke --function-name PythonLoaderExecutor \
      --payload '{"loader": "loadpricedaily", "symbols": ["AAPL", "MSFT"]}' \
      /tmp/out.json
"""

import json
import os
import sys
import logging
from datetime import datetime

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Handlers
success_count = 0
error_count = 0


def lambda_handler(event, context):
    """
    AWS Lambda entry point.

    Event format:
    {
        "loader": "loadpricedaily",  # Name of loader without .py
        "symbols": ["AAPL", "MSFT"], # Optional: specific symbols to load
        "days": 30,                  # Optional: override backfill days
        "force_full": False          # Optional: ignore watermarks, do full refresh
    }
    """
    global success_count, error_count
    success_count = 0
    error_count = 0

    try:
        loader_name = event.get("loader")
        if not loader_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing 'loader' parameter"}),
            }

        symbols = event.get("symbols", None)
        days = event.get("days", None)
        force_full = event.get("force_full", False)

        logger.info(f"Starting loader: {loader_name}")
        logger.info(f"  Symbols: {symbols}")
        logger.info(f"  Backfill days: {days}")
        logger.info(f"  Force full refresh: {force_full}")

        # Dynamically import and run the loader
        result = run_loader(loader_name, symbols, days, force_full)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "loader": loader_name,
                "status": "success",
                "result": result,
                "duration_sec": context.get_remaining_time_in_millis() / 1000 if hasattr(context, 'get_remaining_time_in_millis') else 0,
            }),
        }

    except Exception as e:
        logger.exception(f"Loader execution failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "status": "failed",
            }),
        }


def run_loader(loader_name, symbols=None, days=None, force_full=False):
    """
    Dynamically load and execute a Python loader.

    Args:
        loader_name: Name of loader file without .py (e.g., 'loadpricedaily')
        symbols: Optional list of symbols to process
        days: Optional backfill days override
        force_full: Whether to ignore watermarks and do full refresh

    Returns:
        dict with statistics about the load
    """
    try:
        # Set environment variables for backfill if specified
        if days is not None:
            os.environ["BACKFILL_DAYS"] = str(days)

        if force_full:
            os.environ["FORCE_FULL_REFRESH"] = "1"

        # Dynamically import the loader module
        loader_module = __import__(loader_name)

        # Try to find the loader class (convention: className = CamelCase of file name)
        class_name = "".join(word.capitalize() for word in loader_name.split("_"))
        if not hasattr(loader_module, class_name):
            # Fallback: look for any class that inherits from OptimalLoader or WatermarkLoader
            loader_class = None
            for attr_name in dir(loader_module):
                attr = getattr(loader_module, attr_name)
                if isinstance(attr, type) and attr_name.endswith("Loader"):
                    loader_class = attr
                    break
            if not loader_class:
                raise ValueError(
                    f"Could not find loader class in {loader_name}. "
                    f"Expected class name: {class_name} or *Loader"
                )
        else:
            loader_class = getattr(loader_module, class_name)

        # Instantiate and run the loader
        loader = loader_class()

        # Get symbols to process
        if symbols is None:
            # Load all active symbols
            from db_helper import DatabaseHelper
            db = DatabaseHelper()
            symbols = db.get_active_symbols()
            logger.info(f"Loaded {len(symbols)} active symbols from database")

        # Execute loader
        logger.info(f"Starting loader with {len(symbols)} symbols")
        stats = loader.run(symbols)

        logger.info(
            f"Loader completed: {stats.get('rows_inserted', 0)} rows inserted, "
            f"{stats.get('symbols_failed', 0)} symbols failed"
        )

        return stats

    except ImportError as e:
        raise ValueError(f"Could not import loader module '{loader_name}': {e}")
    except Exception as e:
        logger.exception(f"Error running loader: {e}")
        raise


def lambda_handler_streaming(event, context):
    """
    Alternative handler for streaming/batched loader execution.
    Useful for coordinating multiple loaders in parallel via EventBridge.

    Event format:
    {
        "loaders": [
            {"loader": "loadpricedaily"},
            {"loader": "loadeodhd"},
            {"loader": "loadeconomicdata"}
        ]
    }
    """
    loaders = event.get("loaders", [])
    results = {}

    for loader_config in loaders:
        try:
            result = lambda_handler(loader_config, context)
            results[loader_config.get("loader")] = json.loads(result["body"])
        except Exception as e:
            results[loader_config.get("loader")] = {"error": str(e), "status": "failed"}

    return {
        "statusCode": 200,
        "body": json.dumps({
            "loaders_executed": len(loaders),
            "results": results,
        }),
    }


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        "loader": "loadpricedaily",
        "symbols": ["AAPL", "MSFT"],
        "days": 7,
    }

    class MockContext:
        def get_remaining_time_in_millis(self):
            return 300000

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
