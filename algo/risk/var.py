"""
Portfolio Risk Measures — VaR, CVaR, Concentration, Beta Exposure

Institutional risk measurement for portfolio monitoring.

Metrics:
- Historical VaR: "We have 95% confidence portfolio won't lose more than $X in one day"
- Conditional VaR (Expected Shortfall): Mean loss beyond VaR threshold
- Stressed VaR: VaR using worst 12-month historical window
- Beta Exposure: Portfolio beta vs. S&P 500 (systematic risk)
- Concentration: Top holdings %, sector breakdown, industry breakdown

Alerts:
- Daily VaR > 2% of portfolio → WARNING
- Concentration > 30% in top 5 holdings → WARNING
- Beta exposure > 2.0 (2x market risk) → WARNING
"""

import logging
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class ValueAtRisk:
    """Portfolio risk metrics and concentration analysis."""

    def __init__(self, config: Any) -> None:
        self.config = config

    def historical_var(self, confidence: float = 0.95, lookback_days: int = 252) -> dict[str, Any]:
        """Compute historical simulation VaR.

        Args:
            confidence: Confidence level (default 0.95 = 95%)
            lookback_days: Historical window (default 252 = 1 year)

        Returns:
            dict with VaR dollar and %, or raises RuntimeError if insufficient data
        """
        import numpy as np

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - (%s || ' days')::interval
                    ORDER BY snapshot_date ASC
                    """,
                    (int(lookback_days),),
                )
                rows = cur.fetchall()

                if len(rows) < 5:
                    logger.critical(
                        f"Historical VaR calculation failed: only {len(rows)} portfolio snapshots found (minimum 5 required). "
                        "Cannot compute VaR with insufficient data — trading must halt."
                    )
                    raise RuntimeError(
                        f"Insufficient historical data for VaR (only {len(rows)} snapshots, need 5+). "
                        "Run daily reconciliation to populate portfolio snapshots."
                    )
                if len(rows) < 30:
                    logger.warning(f"Risk metrics using limited historical data: {len(rows)} snapshots (recommend 30+)")

                # CRITICAL: Portfolio values must be present and valid — no defaults to 0.0
                # Using 0.0 as fallback would cause VaR to be computed on corrupted data
                values = []
                for i, row in enumerate(rows):
                    if row[1] is None:
                        raise RuntimeError(
                            f"Portfolio value NULL at row {i} (date {row[0]}). "
                            "Cannot compute VaR with missing data. Check portfolio snapshot data."
                        )
                    try:
                        val = Decimal(str(float(row[1])))
                        if val <= 0:
                            raise RuntimeError(
                                f"Portfolio value invalid at row {i} (date {row[0]}): {val} "
                                "(must be positive). Check snapshot data."
                            )
                        values.append(val)
                    except (ValueError, TypeError) as e:
                        raise RuntimeError(
                            f"Portfolio value conversion failed at row {i} (date {row[0]}): {e}. "
                            "Check snapshot data integrity."
                        ) from e

                returns_decimal = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
                if not returns_decimal:
                    logger.critical(
                        "Historical VaR calculation failed: no valid returns computed from portfolio snapshots"
                    )
                    raise RuntimeError(
                        "Cannot compute VaR: no valid portfolio return data available. Verify portfolio snapshots have valid values."
                    )

                # CRITICAL: Returns must be valid — no defaults to 0.0
                returns = []
                for i, r in enumerate(returns_decimal):
                    try:
                        ret = float(float(r))
                        returns.append(ret)
                    except (ValueError, TypeError) as e:
                        raise RuntimeError(
                            f"Return computation failed at index {i}: {e}. Portfolio snapshot data may be corrupted."
                        ) from e

                if not returns:
                    logger.critical(
                        "Historical VaR calculation failed: no valid returns computed from portfolio snapshots"
                    )
                    raise RuntimeError(
                        "Cannot compute VaR: no valid portfolio return data available. "
                        "Verify portfolio snapshots have valid values."
                    )

                var_percentile = np.percentile(returns, (1 - confidence) * 100)
                current_value = values[-1]

                var_dollars = current_value * Decimal(str(abs(var_percentile)))
                var_pct = Decimal(str(abs(var_percentile))) * Decimal(100)

                return {
                    "confidence_level": confidence,
                    "var_dollars": float(var_dollars.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "var_pct": float(var_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
                    "interpretation": f"95% confident portfolio won't lose more than ${var_dollars:.2f} (or {var_pct:.2f}%) in one day",
                    "data_points": len(returns),
                }

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def cvar(self, confidence: float = 0.95, lookback_days: int = 252) -> dict[str, Any]:
        """Compute Conditional VaR (Expected Shortfall) — mean loss beyond VaR.

        Args:
            confidence: Confidence level
            lookback_days: Historical window

        Returns:
            dict with CVaR dollar and %, or raises RuntimeError if insufficient data
        """
        import numpy as np

        try:
            with DatabaseContext("read") as cur:
                rows = self._fetch_portfolio_snapshots(cur, lookback_days)
                self._validate_snapshot_count(rows)
                values = self._extract_portfolio_values(rows)
                returns = self._compute_portfolio_returns(values)

            var_threshold = np.percentile(returns, (1 - confidence) * 100)
            tail_losses = [r for r in returns if r <= var_threshold]
            self._validate_tail_losses(tail_losses)

            tail_loss_mean = Decimal(str(abs(np.mean(tail_losses))))
            cvar_pct = tail_loss_mean * Decimal(100)
            current_value = values[-1]
            cvar_dollars = current_value * tail_loss_mean

            return {
                "confidence_level": confidence,
                "cvar_dollars": float(cvar_dollars.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "cvar_pct": float(cvar_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
                "interpretation": f"Average loss on worst-case days (worse than VaR): {cvar_pct:.2f}%",
                "tail_event_count": len(tail_losses),
            }

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _fetch_portfolio_snapshots(self, cur: Any, lookback_days: int) -> list[Any]:
        """Fetch portfolio snapshots from database."""
        cur.execute(
            """
            SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
            WHERE snapshot_date >= CURRENT_DATE - (%s || ' days')::interval
            ORDER BY snapshot_date ASC
            """,
            (int(lookback_days),),
        )
        return list(cur.fetchall())

    def _validate_snapshot_count(self, rows: list[Any]) -> None:
        """Validate that we have sufficient snapshot data."""
        if len(rows) < 5:
            logger.critical(f"CVaR calculation failed: only {len(rows)} portfolio snapshots found (minimum 5 required)")
            raise RuntimeError(f"Insufficient historical data for CVaR (only {len(rows)} snapshots, need 5+)")
        if len(rows) < 30:
            logger.warning(f"Risk metrics using limited historical data: {len(rows)} snapshots (recommend 30+)")

    def _extract_portfolio_values(self, rows: list[Any]) -> list[Decimal]:
        """Extract and validate portfolio values from snapshot rows."""
        values = []
        for i, row in enumerate(rows):
            if row[1] is None:
                raise RuntimeError(
                    f"Portfolio value NULL at row {i} (date {row[0]}). "
                    "Cannot compute VaR with missing data. Check portfolio snapshot data."
                )
            try:
                val = Decimal(str(float(row[1])))
                if val <= 0:
                    raise RuntimeError(
                        f"Portfolio value invalid at row {i} (date {row[0]}): {val} "
                        "(must be positive). Check snapshot data."
                    )
                values.append(val)
            except (ValueError, TypeError) as e:
                raise RuntimeError(
                    f"Portfolio value conversion failed at row {i} (date {row[0]}): {e}. Check snapshot data integrity."
                ) from e
        return values

    def _compute_portfolio_returns(self, values: list[Decimal]) -> list[float]:
        """Compute returns from portfolio values."""
        returns_decimal = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
        if not returns_decimal:
            logger.critical("Historical VaR calculation failed: no valid returns computed from portfolio snapshots")
            raise RuntimeError(
                "Cannot compute VaR: no valid portfolio return data available. Verify portfolio snapshots have valid values."
            )

        returns = []
        for i, r in enumerate(returns_decimal):
            try:
                ret = float(float(r))
                returns.append(ret)
            except (ValueError, TypeError) as e:
                raise RuntimeError(
                    f"Return computation failed at index {i}: {e}. Portfolio snapshot data may be corrupted."
                ) from e

        if not returns:
            logger.critical("CVaR calculation failed: no valid returns computed from portfolio snapshots")
            raise RuntimeError("Cannot compute CVaR: no valid portfolio return data available")

        return returns

    def _validate_tail_losses(self, tail_losses: list[Any]) -> None:
        """Validate that we have tail loss events."""
        if not tail_losses:
            logger.critical("CVaR calculation failed: no tail loss events in historical data")
            raise RuntimeError("Cannot compute CVaR: no tail loss events found in historical returns")

    def stressed_var(self, confidence: float = 0.99) -> dict[str, Any]:
        """Compute stressed VaR using worst 12-month rolling window.

        Conservative measure for stress periods.

        Args:
            confidence: Confidence level (default 0.99 = 99%)

        Returns:
            dict with stressed VaR, or raises RuntimeError if insufficient data
        """
        import numpy as np

        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '5 years'
                    ORDER BY snapshot_date ASC
                    """)
                rows = cur.fetchall()

                if len(rows) < 365:
                    logger.critical(
                        f"Stressed VaR calculation failed: only {len(rows)} portfolio snapshots found (minimum 365 required for 5-year window)"
                    )
                    raise RuntimeError(
                        f"Insufficient historical data for Stressed VaR (only {len(rows)} snapshots, need 365+). "
                        "Portfolio must have at least 1 year of trading history."
                    )

                values = [Decimal(str(float(row[1]))) for i, row in enumerate(rows)]
                returns_decimal = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
                returns = np.array([float(float(r)) for i, r in enumerate(returns_decimal)])

                worst_var = None
                worst_start_idx = None

                for start_idx in range(len(returns) - 252):
                    window_returns = returns[start_idx : start_idx + 252]
                    var_thresh = np.percentile(window_returns, 1.0)
                    if worst_var is None or abs(var_thresh) > abs(worst_var):
                        worst_var = var_thresh
                        worst_start_idx = start_idx

                if worst_var is None or worst_start_idx is None:
                    logger.critical("Stressed VaR calculation failed: no valid worst-case window found")
                    raise RuntimeError(
                        "Cannot compute Stressed VaR: failed to identify worst 12-month rolling window. "
                        "Portfolio return data may be corrupted."
                    )

                current_value = values[-1]
                stressed_var_dollars = current_value * Decimal(str(abs(worst_var)))
                stressed_var_pct = Decimal(str(abs(worst_var))) * Decimal(100)

                return {
                    "confidence_level": confidence,
                    "stressed_var_dollars": float(
                        stressed_var_dollars.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    ),
                    "stressed_var_pct": float(stressed_var_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
                    "worst_window_period": f"{rows[worst_start_idx][0]} to {rows[worst_start_idx + 252][0]}",
                    "interpretation": f"Potential loss using worst historical 12-month period: {stressed_var_pct:.2f}%",
                }

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def beta_exposure(self) -> dict[str, Any]:
        """Compute portfolio beta exposure vs. S&P 500.

        Returns:
            dict with portfolio beta and per-position beta. If no positions exist, returns zero-exposure response.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT ap.symbol, ap.quantity, ap.current_price, ap.avg_entry_price AS entry_price
                    FROM algo_positions ap
                    WHERE ap.status = 'open'
                    """)
                positions = cur.fetchall()

                if not positions:
                    logger.info("No open positions: returning zero beta exposure")
                    return {
                        "portfolio_beta": 0.0,
                        "interpretation": "No open positions - portfolio beta is zero",
                        "positions": [],
                        "portfolio_value": 0.0,
                    }

                cur.execute(
                    "SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
                )
                portfolio_row = cur.fetchone()
                if portfolio_row is None or len(portfolio_row) < 1 or portfolio_row[0] is None:
                    logger.critical("Beta exposure calculation failed: no portfolio snapshot available")
                    raise RuntimeError(
                        "Cannot compute beta exposure without portfolio snapshot. "
                        "Portfolio must have been reconciled at least once."
                    )
                portfolio_value = Decimal(str(float(portfolio_row[0])))
                snapshot_date = portfolio_row[1] if len(portfolio_row) > 1 else None

                # CRITICAL: Validate snapshot freshness — stale portfolio value causes incorrect beta sizing
                if snapshot_date:
                    from datetime import date

                    today = date.today()
                    age_days = (today - snapshot_date).days
                    if age_days > 1:  # Allow up to 1 day old for post-market calculations
                        raise RuntimeError(
                            f"[VAR CRITICAL] Portfolio snapshot is stale ({age_days} days old, from {snapshot_date}). "
                            f"Beta calculations must use current portfolio value to be accurate. "
                            f"Portfolio snapshot must be updated daily via Phase 9 reconciliation. "
                            f"Check that daily orchestration is running."
                        )

                # Fetch SPY returns for the last 60 trading days (beta denominator)
                cur.execute("""
                    SELECT date, close FROM price_daily
                    WHERE symbol = 'SPY'
                    ORDER BY date DESC LIMIT 61
                    """)
                spy_rows = cur.fetchall()
                spy_returns = []
                if len(spy_rows) >= 2:
                    spy_prices = list(reversed([Decimal(str(float(r[1]))) for i, r in enumerate(spy_rows)]))
                    spy_returns = [
                        (spy_prices[i] - spy_prices[i - 1]) / spy_prices[i - 1] for i in range(1, len(spy_prices))
                    ]

                spy_var = Decimal(0)
                if spy_returns:
                    spy_mean_val = sum(spy_returns) / len(spy_returns)
                    spy_mean = Decimal(str(spy_mean_val))
                    spy_var = Decimal(str(sum((r - spy_mean) ** 2 for r in spy_returns) / len(spy_returns)))
                else:
                    raise RuntimeError(
                        f"[VAR CALCULATION CRITICAL] Cannot compute portfolio beta: insufficient SPY price history. "
                        f"Expected 60+ days of SPY data (got {len(spy_rows)} rows). "
                        f"SPY data is fundamental for market-relative risk assessment. "
                        f"Check that load_prices has populated price_daily with SPY data."
                    )

                total_beta_exposure = Decimal(0)
                positions_list = []

                for symbol, qty, cur_price, _entry_price in positions:
                    # CRITICAL: Do NOT use entry_price as fallback for current_price
                    if cur_price is None or qty is None:
                        raise ValueError(
                            f"[VAR CALCULATION FAILED] {symbol}: missing current_price or quantity. "
                            f"Cannot calculate portfolio VAR without complete position data."
                        )
                    safe_price = float(cur_price)
                    safe_qty = float(qty)
                    if safe_price <= 0 or safe_qty <= 0:
                        raise ValueError(
                            f"[VAR CALCULATION FAILED] {symbol}: invalid current_price ({cur_price}) or quantity ({qty}). "
                            f"Current price and quantity must be positive for portfolio VAR calculation."
                        )
                    position_value = Decimal(str(safe_qty)) * Decimal(str(safe_price))
                    if portfolio_value <= 0:
                        raise RuntimeError(
                            f"[VAR CALCULATION CRITICAL] Portfolio value is invalid ({portfolio_value}). "
                            f"Cannot compute position weights for VAR without valid total portfolio value."
                        )
                    position_weight = position_value / portfolio_value

                    # Compute 60-day beta via covariance with SPY
                    if spy_var <= 0:
                        raise RuntimeError(
                            f"[VAR CALCULATION CRITICAL] SPY variance is zero or negative ({spy_var}). "
                            f"Cannot compute meaningful beta without market volatility. "
                            f"Check SPY price data quality."
                        )
                    try:
                        cur.execute(
                            """
                            SELECT close FROM price_daily
                            WHERE symbol = %s
                            ORDER BY date DESC LIMIT 61
                            """,
                            (symbol,),
                        )
                        stock_rows = cur.fetchall()
                        if len(stock_rows) < 2:
                            raise ValueError(
                                f"[VAR CALCULATION] {symbol}: insufficient historical price data (need 2+ prices, got {len(stock_rows)}). "
                                f"Cannot calculate beta for portfolio VAR. Ensure price_daily has at least 60 days of data."
                            )
                        stock_prices = []
                        for _i, r in enumerate(stock_rows):
                            if r[0] is None:
                                raise ValueError(
                                    f"[VAR CALCULATION FAILED] {symbol}: NULL historical price in price_daily. "
                                    f"Cannot calculate beta without complete price history."
                                )
                            price = float(r[0])
                            if price <= 0:
                                raise ValueError(
                                    f"[VAR CALCULATION FAILED] {symbol}: invalid historical price ({price}). "
                                    f"All prices must be positive for beta calculation."
                                )
                            stock_prices.append(Decimal(str(price)))
                        stock_prices = list(reversed(stock_prices))
                        if len(stock_prices) < 2:
                            raise ValueError(
                                f"[VAR CALCULATION] {symbol}: insufficient valid prices ({len(stock_prices)}). "
                                f"Cannot compute beta."
                            )
                        stock_returns = [
                            (stock_prices[i] - stock_prices[i - 1]) / stock_prices[i - 1]
                            for i in range(1, len(stock_prices))
                        ]
                        n = min(len(stock_returns), len(spy_returns))
                        if n < 20:
                            raise ValueError(
                                f"[VAR CALCULATION] {symbol}: insufficient return periods ({n} < 20 required). "
                                f"Cannot calculate statistically significant beta."
                            )
                        s_rets = stock_returns[-n:]
                        m_rets = spy_returns[-n:]
                        s_mean = Decimal(str(sum(s_rets) / n))
                        m_mean = Decimal(str(sum(m_rets) / n))
                        cov = Decimal(str(sum((s_rets[i] - s_mean) * (m_rets[i] - m_mean) for i in range(n)) / n))
                        var = Decimal(str(sum((r - m_mean) ** 2 for r in m_rets) / n))
                        if var <= 0:
                            raise ValueError(
                                f"[VAR CALCULATION] {symbol}: stock variance is zero or negative ({var}). "
                                f"Cannot compute beta with zero volatility."
                            )
                        estimated_beta = (cov / var).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        raise RuntimeError(f"Beta calculation failed for {symbol}: {e}") from e

                    weighted_beta = estimated_beta * position_weight
                    total_beta_exposure += weighted_beta

                    positions_list.append(
                        {
                            "symbol": symbol,
                            "weight_pct": float(
                                float(
                                    (position_weight * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                )
                            ),
                            "estimated_beta": float(float(estimated_beta)),
                            "contribution": float(
                                float(weighted_beta.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
                            ),
                        }
                    )

                return {
                    "portfolio_beta": float(
                        float(total_beta_exposure.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    ),
                    "interpretation": f"Portfolio is {float(float(total_beta_exposure.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)))}x market risk",
                    "positions": positions_list,
                    "portfolio_value": float(float(portfolio_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))),
                }

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def concentration_report(self) -> dict[str, Any]:
        """Generate concentration report: top holdings, sectors, industries.

        Returns:
            dict with concentration metrics. If no positions exist, returns zero-concentration response.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    WITH open_trades AS (
                        SELECT DISTINCT ON (at.symbol)
                            at.symbol, at.entry_quantity as quantity, at.entry_price,
                            lp.current_price,
                            (at.entry_quantity * lp.current_price) as position_value
                        FROM algo_trades at
                        LEFT JOIN (
                            SELECT DISTINCT ON (symbol) symbol, close as current_price
                            FROM price_daily
                            WHERE symbol IN (
                                SELECT DISTINCT symbol FROM algo_trades
                                WHERE status IN ('open', 'filled', 'active', 'partially_filled')
                                  AND exit_date IS NULL
                            )
                            ORDER BY symbol, date DESC
                        ) lp ON at.symbol = lp.symbol
                        WHERE at.status IN ('open', 'filled', 'active', 'partially_filled')
                          AND at.exit_date IS NULL
                        ORDER BY at.symbol, at.trade_date DESC
                    )
                    SELECT ot.symbol, ot.quantity, ot.current_price, ot.entry_price,
                           cp.sector, cp.industry
                    FROM open_trades ot
                    LEFT JOIN company_profile cp ON ot.symbol = cp.ticker
                    ORDER BY ABS(ot.position_value) DESC
                    """)
                positions = cur.fetchall()

                if not positions:
                    logger.info("No open positions: returning zero concentration")
                    return {
                        "top_holdings": [],
                        "sector_exposure": {},
                        "industry_exposure": {},
                        "max_single_position": 0.0,
                        "herfindahl_index": 0.0,
                        "interpretation": "No open positions - portfolio concentration is zero",
                        "portfolio_value": 0.0,
                    }

                cur.execute(
                    "SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
                )
                portfolio_row = cur.fetchone()
                if portfolio_row is None or len(portfolio_row) < 1 or portfolio_row[0] is None:
                    logger.critical("Concentration report failed: no portfolio snapshot available")
                    raise RuntimeError(
                        "Cannot compute concentration without portfolio snapshot. "
                        "Portfolio must have been reconciled at least once."
                    )
                if len(portfolio_row) < 2:
                    raise RuntimeError(
                        f"[CONCENTRATION CRITICAL] Portfolio snapshot row has {len(portfolio_row)} column(s), "
                        f"need at least 2 (value, date). Query may have been corrupted. "
                        f"Cannot compute concentration without snapshot date for freshness validation."
                    )
                snapshot_date = portfolio_row[1]

                # CRITICAL: Validate snapshot freshness — stale portfolio value causes incorrect concentration metrics
                if snapshot_date is None:
                    raise RuntimeError(
                        "[CONCENTRATION CRITICAL] Portfolio snapshot has NULL date. "
                        "Cannot validate data freshness. Snapshot must always have a timestamp."
                    )
                from datetime import date

                today = date.today()
                age_days = (today - snapshot_date).days
                if age_days > 1:  # Allow up to 1 day old for post-market calculations
                    raise RuntimeError(
                        f"[CONCENTRATION CRITICAL] Portfolio snapshot is stale ({age_days} days old, from {snapshot_date}). "
                        f"Concentration metrics must use current portfolio value. "
                        f"Portfolio snapshot must be updated daily via Phase 9 reconciliation. "
                        f"Check that daily orchestration is running."
                    )
                portfolio_value = Decimal(str(portfolio_row[0]))

                top_holdings = []
                sector_exposure: dict[str, float] = {}
                industry_exposure: dict[str, float] = {}

                # CRITICAL: Validate all position pricing BEFORE computing concentration
                # Concentration metrics are only meaningful if computed on complete position data
                for symbol, _qty, cur_price, _entry_price, _sector, _industry in positions:
                    if cur_price is None or float(cur_price) <= 0:
                        raise ValueError(
                            f"[CONCENTRATION CRITICAL] Position {symbol} has invalid or missing current_price ({cur_price}). "
                            f"Concentration report cannot be computed on incomplete position data — "
                            f"result would be misleading and cause incorrect risk assessment. "
                            f"All positions must have valid current pricing. "
                            f"Check that positions table is up-to-date with current market prices."
                        )

                for symbol, qty, cur_price, _entry_price, sector, industry in positions:
                    # CRITICAL: Do NOT use entry_price as fallback for current_price
                    position_value = float(Decimal(str(qty)) * Decimal(str(cur_price)))
                    portfolio_value_float = float(portfolio_value)
                    if portfolio_value_float <= 0:
                        raise RuntimeError(
                            f"Portfolio value is invalid or zero ({portfolio_value_float}). "
                            f"Cannot compute meaningful concentration metrics. "
                            f"Portfolio must be reconciled with valid total value."
                        )
                    position_pct = position_value / portfolio_value_float * 100

                    top_holdings.append(
                        {
                            "symbol": symbol,
                            "value_dollars": round(position_value, 2),
                            "pct_of_portfolio": round(position_pct, 2),
                        }
                    )

                    # Require sector/industry fields; use "Unknown" only for truly missing data
                    if sector is None:
                        raise ValueError(f"Position {symbol} missing required 'sector' field")
                    if industry is None:
                        raise ValueError(f"Position {symbol} missing required 'industry' field")
                    if not sector:
                        sector = "Unknown"
                    if not industry:
                        industry = "Unknown"
                    if sector not in sector_exposure:
                        sector_exposure[sector] = 0.0
                    if industry not in industry_exposure:
                        industry_exposure[industry] = 0.0
                    sector_exposure[sector] += position_pct
                    industry_exposure[industry] += position_pct

                top_5_pct = sum([h["pct_of_portfolio"] for h in top_holdings[:5]])

                return {
                    "portfolio_value": round(portfolio_value, 2),
                    "position_count": len(positions),
                    "top_holdings": top_holdings[:5],
                    "top_5_concentration_pct": round(top_5_pct, 1),
                    "sector_exposure": {
                        k: round(v, 1) for k, v in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)
                    },
                    "industry_exposure": {
                        k: round(v, 1)
                        for k, v in sorted(industry_exposure.items(), key=lambda x: x[1], reverse=True)[:5]
                    },
                    "diversification_status": ("CONCENTRATED" if top_5_pct > 30 else "DIVERSIFIED"),
                }

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def generate_daily_risk_report(self, report_date: date | None = None) -> dict[str, Any]:
        """Generate comprehensive daily risk report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with all risk metrics
        """
        try:
            if not report_date:
                report_date = date.today()

            logger.info(f"Generating daily risk report for {report_date}")

            # Compute all risk metrics (each handles its own connection)
            # VaR, CVaR, stressed_var require sufficient historical data
            # Beta and concentration require open positions (return None if none exist)
            try:
                var_metrics = self.historical_var()
            except RuntimeError as e:
                logger.warning(f"Historical VaR unavailable (insufficient data): {e}")
                var_metrics = None

            try:
                cvar_metrics = self.cvar()
            except RuntimeError as e:
                logger.warning(f"Conditional VaR unavailable (insufficient data): {e}")
                cvar_metrics = None

            try:
                stressed_var = self.stressed_var()
            except RuntimeError as e:
                logger.warning(f"Stressed VaR unavailable (requires 365+ days): {e}")
                stressed_var = None

            beta = self.beta_exposure()  # Returns None if no positions
            concentration = self.concentration_report()  # Returns None if no positions

            logger.debug(f"  VaR: {var_metrics['var_pct']:.3f}%" if var_metrics else "  VaR: <insufficient data>")
            logger.debug(f"  CVaR: {cvar_metrics['cvar_pct']:.3f}%" if cvar_metrics else "  CVaR: <insufficient data>")
            logger.debug(
                f"  Stressed VaR: {stressed_var['stressed_var_pct']:.3f}%"
                if stressed_var
                else "  Stressed VaR: <requires 365+ days>"
            )
            logger.debug(f"  Beta: {beta['portfolio_beta']:.3f}" if beta else "  Beta: <no positions>")
            logger.debug(
                f"  Top 5 Concentration: {concentration['top_5_concentration_pct']:.1f}%"
                if concentration
                else "  Top 5 Concentration: <no positions>"
            )

            alerts: list[str] = []
            result: dict[str, Any] = {
                "report_date": report_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "ok",
                "var_metrics": var_metrics,
                "cvar_metrics": cvar_metrics,
                "stressed_var": stressed_var,
                "beta_exposure": beta,
                "concentration": concentration,
                "alerts": alerts,
            }

            # Alert if VaR > 2%
            if var_metrics:
                if "var_pct" not in var_metrics:
                    raise RuntimeError(
                        f"[VaR CRITICAL] var_metrics dict missing 'var_pct' key. "
                        f"Cannot evaluate risk threshold without valid VaR metric. "
                        f"Available keys: {list(var_metrics.keys())}"
                    )
                var_pct = float(var_metrics["var_pct"])
                if var_pct > 2.0:
                    msg = f"VaR Risk: Portfolio VaR is {var_pct:.2f}% (>2% threshold)"
                    alerts.append(msg)
                    logger.warning(msg)

            # Alert if concentration > 30%
            if concentration:
                if "top_5_concentration_pct" not in concentration:
                    raise RuntimeError(
                        f"[CONCENTRATION CRITICAL] concentration dict missing 'top_5_concentration_pct' key. "
                        f"Cannot evaluate concentration risk without valid metric. "
                        f"Available keys: {list(concentration.keys())}"
                    )
                conc_pct = float(concentration["top_5_concentration_pct"])
                if conc_pct > 30:
                    msg = f"Concentration Risk: Top 5 holdings are {conc_pct:.1f}% (>30%)"
                    alerts.append(msg)
                    logger.warning(msg)

            # Alert if beta > 2.0
            if beta:
                if "portfolio_beta" not in beta:
                    raise RuntimeError(
                        f"[BETA CRITICAL] beta dict missing 'portfolio_beta' key. "
                        f"Cannot evaluate leverage risk without valid beta metric. "
                        f"Available keys: {list(beta.keys())}"
                    )
                portfolio_beta = float(beta["portfolio_beta"])
                if portfolio_beta > 2.0:
                    msg = f"Beta Risk: Portfolio beta {portfolio_beta:.1f} (>2.0x market risk)"
                    alerts.append(msg)
                    logger.warning(msg)

            try:
                with DatabaseContext("write") as cur:
                    var_pct_val = float(var_metrics["var_pct"]) if var_metrics else None
                    cvar_pct_val = float(cvar_metrics["cvar_pct"]) if cvar_metrics else None
                    stressed_var_pct_val = float(stressed_var["stressed_var_pct"]) if stressed_var else None
                    portfolio_beta_val = float(beta["portfolio_beta"]) if beta else None
                    top_5_conc_val = float(concentration["top_5_concentration_pct"]) if concentration else None

                    cur.execute(
                        """
                        INSERT INTO algo_risk_daily (
                            report_date, var_pct_95, cvar_pct_95, stressed_var_pct, portfolio_beta, top_5_concentration
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (report_date) DO UPDATE SET
                            var_pct_95 = EXCLUDED.var_pct_95,
                            cvar_pct_95 = EXCLUDED.cvar_pct_95,
                            stressed_var_pct = EXCLUDED.stressed_var_pct,
                            portfolio_beta = EXCLUDED.portfolio_beta,
                            top_5_concentration = EXCLUDED.top_5_concentration
                        """,
                        (
                            report_date,
                            var_pct_val,
                            cvar_pct_val,
                            stressed_var_pct_val,
                            portfolio_beta_val,
                            top_5_conc_val,
                        ),
                    )
                    metrics_summary = []
                    if var_pct_val is not None:
                        metrics_summary.append(f"var={var_pct_val}%")
                    if cvar_pct_val is not None:
                        metrics_summary.append(f"cvar={cvar_pct_val}%")
                    if stressed_var_pct_val is not None:
                        metrics_summary.append(f"svar={stressed_var_pct_val}%")
                    if portfolio_beta_val is not None:
                        metrics_summary.append(f"beta={portfolio_beta_val}")
                    if top_5_conc_val is not None:
                        metrics_summary.append(f"conc={top_5_conc_val}%")
                    metrics_str = ", ".join(metrics_summary) if metrics_summary else "no metrics available"
                    logger.info(f"[OK] Risk report persisted: {metrics_str}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Failed to persist risk report: {e}", exc_info=True)
                raise RuntimeError(
                    f"Risk report persistence failed: {e}. "
                    f"Cannot allow trading without valid risk metrics recorded in database."
                ) from e

            return result

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Daily risk report generation error: {e}", exc_info=True)
            raise RuntimeError(
                f"Risk calculation failed: {e}. Cannot generate valid risk metrics for trading decisions."
            ) from e
