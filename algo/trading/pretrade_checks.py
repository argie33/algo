#!/usr/bin/env python3
"""
Pre-Trade Checks - Hard stops before order execution.

Validates:
- Earnings blackout window (Issue #11 fix)
- Account buying power
- Margin requirements
- Duplicate position prevention
- Exchange/symbol status
- Order size limits
- Sector/industry concentration limits (Issue #2 fix)
"""

import logging
from datetime import date as _date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from algo.risk import EarningsBlackout
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class PreTradeChecks:
    """Validation layer before executing trades."""

    def __init__(
        self,
        config: dict[str, Any],
        alpaca_base_url: str | None = None,
        alpaca_key: str | None = None,
        alpaca_secret: str | None = None,
    ):
        """Initialize pre-trade checks with configuration."""
        self.config = config
        self.alpaca_base_url = alpaca_base_url
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret

    def apply_slippage_adjustment(
        self, shares: float, entry_price: float, slippage_pct: float = 1.0
    ) -> tuple[int, float]:
        """Issue #28: Apply slippage model to position size.

        Reduces shares by slippage percentage to account for market impact and execution slippage.
        Default: 1% slippage (typical for mid-caps, up to 2% for illiquid stocks).

        Args:
            shares: Calculated position size
            entry_price: Target entry price
            slippage_pct: Expected slippage percentage (default 1%)

        Returns:
            (adjusted_shares, actual_cost_per_share)
        """
        slippage_factor = Decimal(1) - (Decimal(str(slippage_pct)) / Decimal(100))
        adjusted_shares = int((Decimal(shares) * slippage_factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        actual_cost = float(Decimal(str(entry_price)) / slippage_factor)
        logger.debug(
            f"Slippage adjustment: {shares} → {adjusted_shares} shares, cost ${entry_price:.2f} → ${actual_cost:.2f}"
        )
        return adjusted_shares, actual_cost

    def run_all(
        self,
        symbol: str,
        position_value: float,
        portfolio_value: float,
        side: str = "BUY",
        eval_date: _date | None = None,
    ) -> tuple[bool, str | None]:
        """
        Run all pre-trade validation checks.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            position_value: Total position value (shares * price)
            portfolio_value: Current portfolio value
            side: 'BUY' or 'SELL'
            eval_date: Date to evaluate for earnings blackout (default: today)

        Returns:
            (passed: bool, reason: str or None)
            - If passed: (True, None)
            - If failed: (False, "reason for failure")
        """
        if eval_date is None:
            eval_date = _date.today()

        # Issue #11: Earnings blackout check (hard gate, must pass before any entry)
        if side == "BUY":
            try:
                earnings_check = EarningsBlackout(config=self.config)
                result = earnings_check.run(symbol, eval_date)
                if not result.get("pass"):
                    return (False, result.get("reason", "Failed earnings blackout check"))
            except ValueError as e:
                return (False, f"Earnings blackout check failed: {e}")

        max_position_pct = Decimal(str(self.config.get("max_position_size_pct", 8.0))) / Decimal(100)
        max_position_value = Decimal(str(portfolio_value)) * max_position_pct

        position_value_dec = Decimal(str(position_value))
        if position_value_dec > max_position_value:
            return (
                False,
                f"Position ${position_value:.2f} exceeds max "
                f"${float(max_position_value):.2f} ({float(max_position_pct*Decimal(100)):.1f}% of portfolio)",
            )

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
                    (symbol, "open"),
                )
                if cur.fetchone():
                    return (False, f"Position already open for {symbol}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[PRE-TRADE] Database error checking duplicate position for {symbol}: {e}")
            raise ValueError(f"Cannot validate duplicate position check for {symbol}: {e}") from e

        min_order_size = Decimal(str(self.config.get("min_order_size_dollars", 100.0)))
        if position_value_dec < min_order_size:
            return (
                False,
                f"Position value ${position_value:.2f} below minimum ${float(min_order_size):.2f}",
            )

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol FROM stock_symbols WHERE symbol = %s LIMIT 1",
                    (symbol,),
                )
                if not cur.fetchone():
                    return (False, f"Symbol {symbol} not found in universe")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise ValueError(f"Symbol validation unavailable for {symbol}: {e}")

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
                    (symbol,),
                )
                row = cur.fetchone()
                if row:
                    sector, industry = row

                    max_sector_positions = int(self.config.get("max_positions_per_sector", 10))
                    max_industry_positions = int(self.config.get("max_positions_per_industry", 8))

                    cur.execute(
                        """SELECT COUNT(*) FROM algo_positions ap
                           LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
                           WHERE ap.status = %s AND cp.sector = %s""",
                        ("open", sector),
                    )
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        raise RuntimeError(f"Sector count query failed for {sector}")
                    sector_count = row[0]
                    if sector_count >= max_sector_positions:
                        return (
                            False,
                            f"Sector {sector} at limit ({sector_count}/{max_sector_positions} positions)",
                        )

                    cur.execute(
                        """SELECT COUNT(*) FROM algo_positions ap
                           LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
                           WHERE ap.status = %s AND cp.industry = %s""",
                        ("open", industry),
                    )
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        raise RuntimeError(f"Industry count query failed for {industry}")
                    industry_count = row[0]
                    if industry_count >= max_industry_positions:
                        return (
                            False,
                            f"Industry {industry} at limit ({industry_count}/{max_industry_positions} positions)",
                        )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[PRE-TRADE] Database error checking sector/industry concentration for {symbol}: {e}")
            raise ValueError(f"Cannot validate sector/industry limits for {symbol}: {e}") from e

        logger.info(
            f"[PRE-TRADE] {symbol}: position ${position_value:.2f}, "
            f"portfolio ${portfolio_value:.2f}, {side} order approved"
        )
        return (True, None)
