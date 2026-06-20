#!/usr/bin/env python3
"""
Portfolio Manager - Query and manage portfolio state

Responsibilities:
- Fetch live portfolio value from Alpaca
- Fall back to database snapshots
- Validate portfolio data freshness
"""

import logging
from datetime import datetime, timezone
from typing import Any, cast

import requests

from algo.infrastructure import get_api_timeout
from algo.reporting import notify
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class PortfolioManager:
    """Query portfolio state from Alpaca and database."""

    def __init__(self, alpaca_key: str, alpaca_secret: str, alpaca_base_url: str) -> None:
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpaca_base_url = alpaca_base_url

    def _with_cursor(self, operation) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("write") as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Database operation failed: {e}")
            raise

    def get_portfolio_value(self) -> float | None:
        """Live Alpaca equity, fall back to latest snapshot, alert if using stale data."""
        if self.alpaca_key and self.alpaca_secret:
            try:
                resp = requests.get(
                    f"{self.alpaca_base_url}/v2/account",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except (ValueError, Exception) as e:
                        logger.warning(f"Invalid JSON response from portfolio API: {e}")
                    else:
                        if "portfolio_value" in data and data["portfolio_value"] is not None:
                            pv_float = float(data["portfolio_value"])
                            logger.info(
                                f"[PORTFOLIO] Live Alpaca equity: ${pv_float:.2f} (url={self.alpaca_base_url})"
                            )
                            return pv_float

                        if "equity" in data and data["equity"] is not None:
                            pv_float = float(data["equity"])
                            logger.info(
                                f"[PORTFOLIO] Live Alpaca equity (from equity field): ${pv_float:.2f} (url={self.alpaca_base_url})"
                            )
                            return pv_float

                        logger.warning(
                            f"[PORTFOLIO] Alpaca /v2/account 200 but portfolio_value/equity missing or null. Response keys: {list(data.keys())}"
                        )
                elif resp.status_code == 401:
                    logger.error(
                        f"[PORTFOLIO] Alpaca 401 Unauthorized — APCA_API_KEY_ID/APCA_API_SECRET_KEY are wrong or expired. URL: {self.alpaca_base_url}"
                    )
                elif resp.status_code == 403:
                    logger.error(
                        f"[PORTFOLIO] Alpaca 403 Forbidden — key may be live keys used with paper URL or vice versa. URL: {self.alpaca_base_url}"
                    )
                else:
                    logger.warning(
                        f"[PORTFOLIO] Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:150]}"
                    )
            except Exception as e:
                logger.warning(f"[PORTFOLIO] Could not fetch Alpaca account value: {e}")

        def _get_snapshot(cur):
            cur.execute(
                "SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots "
                "ORDER BY snapshot_date DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row and row[0]:
                pv = float(row[0])
                snapshot_date = row[1]
                logger.debug(
                    f"[PORTFOLIO] Using snapshot from {snapshot_date}: ${pv:.2f}"
                )
                if (
                    snapshot_date
                    and (datetime.now(timezone.utc).date() - snapshot_date).days > 1
                ):
                    error_msg = f"[PORTFOLIO] STALE SNAPSHOT: from {snapshot_date} (age > 1 day). Cannot trade with stale portfolio data."
                    logger.critical(error_msg)
                    try:
                        notify(
                            severity="critical",
                            title="Portfolio Value Stale — Trading Halted",
                            message=f"Portfolio snapshot from {snapshot_date} is too old. Cannot execute trades.",
                        )
                    except Exception as notif_e:
                        logger.debug(
                            f"Failed to send portfolio staleness notification: {notif_e}"
                        )
                    raise RuntimeError(error_msg)
                return pv
            return None

        try:
            return cast(float | None, self._with_cursor(_get_snapshot))
        except Exception as e:
            logger.error(f"[PORTFOLIO] Could not fetch portfolio snapshot: {e}")

        error_msg = (
            "Portfolio value unavailable: cannot fetch from Alpaca API and no recent snapshot in database. "
            "Cannot execute trades without knowing account size. "
            "Phase 6 entry execution will be halted."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
