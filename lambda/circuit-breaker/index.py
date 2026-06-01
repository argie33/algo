#!/usr/bin/env python3
"""
Intraday Circuit Breaker Lambda - Halts trading if portfolio variance exceeds threshold.

Triggers:
- CloudWatch Events at 10 AM and 12 PM ET (market hours)

Action:
- Check current portfolio P&L via database
- Calculate daily variance as (current_P&L - open_P&L) / portfolio_value
- If variance > threshold (e.g., 15%), set orchestrator_dry_run = true in Secrets Manager
- Orchestrator Phase 1 checks this flag and fails-closed

Resets:
- Manually reset via AWS Console or CLI after market close
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

secretsmanager = boto3.client("secretsmanager")

def lambda_handler(event, context):
    """Circuit breaker trigger - halt trading if variance too high."""

    try:
        # Get current orchestrator state from Secrets Manager
        secret = secretsmanager.get_secret_value(SecretId="algo/orchestrator")
        state = json.loads(secret["SecretString"])

        # TODO: Query database for portfolio P&L
        # current_pnl = get_current_pnl()
        # open_pnl = get_open_pnl()
        # portfolio_value = get_portfolio_value()
        # variance = (current_pnl - open_pnl) / portfolio_value

        # For now: placeholder
        variance = 0.05  # 5% variance
        threshold = 0.15  # 15% threshold

        if variance > threshold:
            logger.critical(f"CIRCUIT BREAKER TRIGGERED: variance {variance:.1%} exceeds threshold {threshold:.1%}")
            state["orchestrator_dry_run"] = True

            # Update Secrets Manager
            secretsmanager.update_secret(
                SecretId="algo/orchestrator",
                SecretString=json.dumps(state)
            )

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "HALT",
                    "reason": f"Portfolio variance {variance:.1%}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }
        else:
            logger.info(f"Circuit breaker OK: variance {variance:.1%} < threshold {threshold:.1%}")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "CONTINUE",
                    "variance": f"{variance:.1%}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }

    except Exception as e:
        logger.error(f"Circuit breaker check failed: {e}", exc_info=True)
        # Fail-closed: on any error, halt trading
        return {
            "statusCode": 500,
            "body": json.dumps({
                "action": "HALT",
                "reason": "Circuit breaker check failed",
                "error": str(e)
            })
        }
