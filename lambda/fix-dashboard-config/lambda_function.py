#!/usr/bin/env python3
"""Lambda function to fix dashboard by populating algo_config table."""

import logging
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from base_handler import LambdaHandler, LambdaResponse, create_lambda_handler

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class FixDashboardConfigHandler(LambdaHandler):
    """Lambda to fix dashboard config."""

    def handle(self, event: dict, context) -> LambdaResponse:
        """Fix dashboard by populating algo_config table."""
        try:
            from config.credential_manager import get_db_config

            db_config = get_db_config()

            conn = psycopg2.connect(
                host=db_config["host"],
                port=int(db_config["port"]),
                database=db_config["database"],
                user=db_config["user"],
                password=db_config["password"],
                sslmode="require",
            )
            cur = conn.cursor()

            sql = """
            INSERT INTO algo_config (key, value, value_type, description, updated_by)
            VALUES
              ('min_completeness_score', '70', 'int', 'Minimum data completeness %', 'lambda-fix'),
              ('min_signal_quality_score', '60', 'int', 'Minimum SQS 0-100', 'lambda-fix'),
              ('min_volume_ma_50d', '300000', 'int', 'Minimum 50-day avg volume', 'lambda-fix'),
              ('min_avg_daily_dollar_volume', '500000', 'float', 'Minimum daily dollar volume', 'lambda-fix'),
              ('earnings_blackout_days_before', '7', 'int', 'Days before earnings to block entries', 'lambda-fix'),
              ('earnings_blackout_days_after', '3', 'int', 'Days after earnings to block entries', 'lambda-fix')
            ON CONFLICT (key) DO NOTHING
            """

            logger.info("Populating algo_config table...")
            cur.execute(sql)
            conn.commit()

            # Verify
            cur.execute(
                """
                SELECT COUNT(*) FROM algo_config
                WHERE key IN (
                    'min_signal_quality_score',
                    'min_completeness_score',
                    'min_volume_ma_50d',
                    'min_avg_daily_dollar_volume',
                    'earnings_blackout_days_before',
                    'earnings_blackout_days_after'
                )
            """
            )
            count = cur.fetchone()[0]

            cur.close()
            conn.close()

            logger.info(f"SUCCESS: {count}/7 required config keys populated")
            return LambdaResponse.success(
                data={
                    "status": "fixed",
                    "keys_populated": count,
                    "message": "Dashboard config restored. Restart API Lambda for changes to take effect.",
                }
            )

        except Exception as e:
            logger.error(f"Fix failed: {e}", exc_info=True)
            return LambdaResponse.error(f"Config fix failed: {str(e)[:200]}", status_code=500)


lambda_handler = create_lambda_handler(FixDashboardConfigHandler)
