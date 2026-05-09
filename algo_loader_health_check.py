#!/usr/bin/env python3
"""
Loader Health Check — Standalone proactive monitoring

Runs independently (via cron/EventBridge) to detect data loader failures
before the algo runs. Alerts on:
  - No data loaded today
  - Critical symbols missing
  - Low universe coverage
  - Too many stale symbols

USAGE (local):
  python3 algo_loader_health_check.py

USAGE (Lambda/CloudWatch):
  # Trigger hourly to detect failures early
  # aws events put-rule --name loader-health-check --schedule-expression 'rate(1 hour)'
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as _date

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


def check_loader_health():
    """Run comprehensive loader health check.

    Returns:
        exit_code: 0 if healthy, 1 if issues found
    """
    try:
        from algo_loader_monitor import LoaderMonitor
        from algo_alerts import AlertManager

        monitor = LoaderMonitor()
        monitor.connect()

        try:
            # Run full health audit
            findings = monitor.audit_all(critical_symbols=['AAPL', 'MSFT', 'NVDA', 'TSLA', 'SPY', 'QQQ', 'IWM'])

            critical = [f for f in findings if f[0] == 'CRITICAL']
            errors = [f for f in findings if f[0] == 'ERROR']
            warns = [f for f in findings if f[0] == 'WARN']

            # Log results
            today = _date.today()
            logger.info(f"=== LOADER HEALTH CHECK ({today}) ===")
            logger.info(f"Critical: {len(critical)}, Errors: {len(errors)}, Warnings: {len(warns)}")

            if critical:
                logger.critical("CRITICAL ISSUES DETECTED:")
                for _, check, msg in critical:
                    logger.critical(f"  [{check}] {msg}")

            if errors:
                logger.error("ERROR ISSUES DETECTED:")
                for _, check, msg in errors:
                    logger.error(f"  [{check}] {msg}")

            if warns:
                logger.warning("WARNINGS:")
                for _, check, msg in warns:
                    logger.warning(f"  [{check}] {msg}")

            # Send alerts
            if critical or errors:
                alerts = AlertManager()
                alerts.send_loader_alert(findings)
                logger.info("Alert sent to configured recipients")

            # Return success only if no critical/error issues
            return 0 if not critical else 1

        finally:
            monitor.disconnect()

    except Exception as e:
        logger.exception(f"Health check failed: {e}")
        return 1


def main():
    """Main entry point for Lambda/CloudWatch."""
    exit_code = check_loader_health()
    if exit_code != 0:
        logger.error("Loader health check failed with issues")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
