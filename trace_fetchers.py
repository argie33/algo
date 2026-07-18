#!/usr/bin/env python3
"""Trace fetchers submodule imports."""

import os
import sys
import logging

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

try:
    logger.info("Importing dashboard.api_data_layer...")
    from dashboard.api_data_layer import API_MAX_BACKOFF
    logger.info("✓ API_MAX_BACKOFF imported")

    logger.info("Importing dashboard.fetchers_common...")
    from dashboard.fetchers_common import FETCHER_METADATA, format_fetcher_error
    logger.info("✓ fetchers_common imports done")

    logger.info("Importing dashboard.fetchers_config...")
    from dashboard.fetchers_config import (
        clear_data_status_cache,
        fetch_algo_config,
        fetch_algo_metrics,
        fetch_circuit,
        fetch_health,
        fetch_run,
    )
    logger.info("✓ fetchers_config imports done")

    logger.info("Importing dashboard.fetchers_external...")
    from dashboard.fetchers_external import (
        fetch_activity,
        fetch_audit_log,
        fetch_economic_calendar,
        fetch_economic_pulse,
        fetch_exec_history,
        fetch_industry_ranking,
        fetch_notifications,
        fetch_sentiment,
    )
    logger.info("✓ fetchers_external imports done")

    logger.info("Importing dashboard.fetchers_market...")
    from dashboard.fetchers_market import (
        clear_markets_cache,
        fetch_exp_factors,
        fetch_market,
        fetch_risk_metrics,
        fetch_sector_ranking,
        fetch_sector_rotation,
    )
    logger.info("✓ fetchers_market imports done")

    logger.info("Importing dashboard.fetchers_portfolio...")
    from dashboard.fetchers_portfolio import (
        fetch_perf,
        fetch_perf_analytics,
        fetch_portfolio,
        fetch_positions,
        fetch_recent_trades,
    )
    logger.info("✓ fetchers_portfolio imports done")

    logger.info("Importing dashboard.fetchers_signals...")
    from dashboard.fetchers_signals import (
        fetch_scores,
        fetch_signal_eval,
        fetch_signals,
    )
    logger.info("✓ fetchers_signals imports done")

    logger.info("SUCCESS: All fetchers modules imported!")

except Exception as e:
    import traceback
    logger.error(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
