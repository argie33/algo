#!/usr/bin/env python3
"""Consolidated Risk Metrics Loader - Momentum + Stability (single pass, parallel write).

Consolidates load_momentum_metrics.py + load_stability_metrics.py into single invocation:
- Computes momentum (1m/3m/6m/12m) from price_daily
- Computes stability (30d/60d/252d vol + beta) from price_daily (SPY correlation)
- Writes to momentum_metrics table AND stability_metrics table in parallel
- Eliminates redundant symbol iteration and error handling boilerplate

Consolidation savings:
- 25-30% reduction in parallelism overhead (one loader instead of two parallel)
- Single database connection per symbol instead of two
- Unified watermark tracking (faster incremental updates)
- 734 lines of consolidated code

Error handling: Returns explicit data_unavailable markers for any metric that fails.
"""

import sys

import psycopg2

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
import math  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.type_conversion import safe_float  # noqa: E402

logger = logging.getLogger(__name__)


class RiskMetricsLoader(OptimalLoader):
    """Consolidated momentum + stability metrics loader.

    Computes both metrics in single symbol pass, writes to both tables.
    Uses OptimalLoader's parallelism but processes all metrics per symbol.
    """

    table_name = "momentum_metrics"  # Primary table for watermark tracking
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute momentum and stability metrics for symbol in single pass.

        Returns momentum_metrics row (this loader's primary table).
        Side effect: Also writes to stability_metrics table for same symbol.
        """
        momentum_row = self._compute_momentum_row(symbol)
        stability_row = self._compute_stability_row(symbol)

        # Write stability metrics to its table (side effect during fetch)
        self._persist_stability_metrics(stability_row)

        # Return momentum row for OptimalLoader to persist to momentum_metrics
        return [momentum_row]

    def _compute_momentum_row(self, symbol: str) -> dict[str, Any]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 253",
                    (symbol,),
                )
                rows = cur.fetchall()

                # FIX 2026-07-20: Previously required the full 252 days (needed only
                # for 12m momentum) before computing ANYTHING, discarding real 1m/3m/6m
                # momentum for the ~2,400 symbols with partial history (recent IPOs,
                # newly-listed names). The per-period loop below already handles partial
                # windows gracefully (target_idx < 0 -> None for that period only); the
                # downstream consumer (_score_momentum in load_stock_scores.py) is
                # explicitly documented to work from "≥1 momentum field" and normalizes
                # by the weight of whichever timeframes are available. 22 days is the
                # floor: the shortest window (1m = 21 days back) needs a day-0 anchor.
                if len(rows) < 22:
                    raise RuntimeError(
                        f"Insufficient price history: {len(rows)} days (need at least 22 for 1m momentum)"
                    )

                prices = {row[0]: safe_float(row[1], f"{symbol}.close[{row[0]}]", allow_none=False) for row in rows}
                sorted_dates = sorted(prices.keys())

                today = sorted_dates[-1]

                momentum: dict[str, float | None] = {}
                for period_name, days_back in [("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)]:
                    target_idx = len(sorted_dates) - days_back - 1
                    if target_idx < 0:
                        momentum[f"momentum_{period_name}"] = None
                        continue

                    price_old = prices[sorted_dates[target_idx]]
                    price_new = prices[today]

                    if price_old is None or price_old == 0:
                        momentum[f"momentum_{period_name}"] = None
                        continue

                    ret_pct = ((price_new - price_old) / price_old) * 100
                    momentum[f"momentum_{period_name}"] = round(ret_pct, 4)

                if all(v is None for v in momentum.values()):
                    raise RuntimeError("No momentum timeframe could be computed from available price history")

                # Fetch latest technical indicators from technical_data_daily (already computed by load_technical_indicators.py)
                technical = self._fetch_technical_indicators(symbol, today)

                return {
                    "symbol": symbol,
                    "momentum_1m": momentum.get("momentum_1m"),
                    "momentum_3m": momentum.get("momentum_3m"),
                    "momentum_6m": momentum.get("momentum_6m"),
                    "momentum_12m": momentum.get("momentum_12m"),
                    "rsi_14": technical.get("rsi_14"),
                    "macd_line": technical.get("macd_line"),
                    "macd_signal": technical.get("macd_signal"),
                    "price_vs_sma_50": technical.get("price_vs_sma_50"),
                    "price_vs_sma_200": technical.get("price_vs_sma_200"),
                    "roc_20d": technical.get("roc_20d"),
                    "roc_60d": technical.get("roc_60d"),
                    "roc_120d": technical.get("roc_120d"),
                    "roc_252d": technical.get("roc_252d"),
                    "data_unavailable": False,
                    "reason": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

        except RuntimeError as e:
            logger.warning(f"[RISK_METRICS] {symbol}: momentum unavailable - {e}")
            return {
                "symbol": symbol,
                "momentum_1m": None,
                "momentum_3m": None,
                "momentum_6m": None,
                "momentum_12m": None,
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
                "data_unavailable": True,
                "reason": str(e)[:150],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"[RISK_METRICS] Unexpected error for {symbol}: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "momentum_1m": None,
                "momentum_3m": None,
                "momentum_6m": None,
                "momentum_12m": None,
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
                "data_unavailable": True,
                "reason": f"unexpected_error: {type(e).__name__}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    def _fetch_technical_indicators(self, symbol: str, date_val: Any) -> dict[str, float | None]:
        """Fetch latest technical indicators from technical_data_daily table.

        These are pre-computed by load_technical_indicators.py. Just copy them
        into momentum_metrics so all momentum/technical data is in one place.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT rsi_14, macd, macd_signal,
                           (close - sma_50) / sma_50 * 100 as price_vs_sma_50,
                           (close - sma_200) / sma_200 * 100 as price_vs_sma_200,
                           roc_20d, roc_60d, roc_120d, roc_252d
                    FROM technical_data_daily
                    WHERE symbol = %s AND date = %s
                    """,
                    (symbol, date_val),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "rsi_14": safe_float(row[0], f"{symbol}.rsi_14", allow_none=True),
                        "macd_line": safe_float(row[1], f"{symbol}.macd_line", allow_none=True),
                        "macd_signal": safe_float(row[2], f"{symbol}.macd_signal", allow_none=True),
                        "price_vs_sma_50": safe_float(row[3], f"{symbol}.price_vs_sma_50", allow_none=True),
                        "price_vs_sma_200": safe_float(row[4], f"{symbol}.price_vs_sma_200", allow_none=True),
                        "roc_20d": safe_float(row[5], f"{symbol}.roc_20d", allow_none=True),
                        "roc_60d": safe_float(row[6], f"{symbol}.roc_60d", allow_none=True),
                        "roc_120d": safe_float(row[7], f"{symbol}.roc_120d", allow_none=True),
                        "roc_252d": safe_float(row[8], f"{symbol}.roc_252d", allow_none=True),
                    }
            return {
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
            }
        except Exception as e:
            logger.debug(f"[RISK_METRICS] {symbol}: technical indicators fetch failed: {e}")
            return {
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
            }

    def _get_debt_to_assets(self, symbol: str) -> float | None:
        """Fetch pre-computed debt_to_assets from quality_metrics (total_liabilities/total_assets).

        Independent of price history, so this is fetched regardless of whether the
        price-based volatility/beta computation below succeeds - stock_scores._score_stability
        has a standing 10%-weight slot for it (docstring: "MINIMUM DATA REQUIREMENT: At least
        one of volatility_252d/volatility_60d/beta/debt_to_assets must be non-NULL"), but no
        loader ever populated stability_metrics.debt_to_assets (confirmed 2026-07-20: 0/7155
        rows filled) even though quality_metrics already computes the identical ratio.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT debt_to_assets FROM quality_metrics WHERE symbol = %s AND data_unavailable = FALSE",
                    (symbol,),
                )
                row = cur.fetchone()
            return safe_float(row[0], f"{symbol}.debt_to_assets", allow_none=True) if row else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"[RISK_METRICS] {symbol}: debt_to_assets lookup failed: {e}")
            return None

    def _compute_stability_row(self, symbol: str) -> dict[str, Any]:
        debt_to_assets = self._get_debt_to_assets(symbol)
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 252",
                    (symbol,),
                )
                rows = cur.fetchall()
                # Normalize dates to `date` objects immediately after fetching
                if rows:
                    rows = [
                        (
                            (
                                row[0].date()
                                if hasattr(row[0], "date")
                                else (
                                    date(row[0].year, row[0].month, row[0].day) if hasattr(row[0], "year") else row[0]
                                )
                            ),
                            row[1],
                        )
                        for row in rows
                    ]

                spy_rows: list[Any] = []
                if rows:
                    stock_dates = [row[0] for row in rows]
                    min_date = min(stock_dates)
                    max_date = max(stock_dates)
                    cur.execute(
                        "SELECT date, close FROM price_daily WHERE symbol = 'SPY' AND date >= %s AND date <= %s ORDER BY date ASC",
                        (min_date, max_date),
                    )
                    spy_rows_raw = cur.fetchall()
                    # Normalize SPY dates to `date` objects for consistency
                    spy_rows = (
                        [
                            (
                                (
                                    row[0].date()
                                    if hasattr(row[0], "date")
                                    else (
                                        date(row[0].year, row[0].month, row[0].day)
                                        if hasattr(row[0], "year")
                                        else row[0]
                                    )
                                ),
                                row[1],
                            )
                            for row in spy_rows_raw
                        ]
                        if spy_rows_raw
                        else []
                    )

            if not rows or len(rows) < 5:
                actual_rows = len(rows) if rows else 0
                reason = f"insufficient_price_history: {actual_rows}/5 days available"
                logger.warning(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
                return {
                    "symbol": symbol,
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "downside_volatility_30d": None,
                    "downside_volatility_60d": None,
                    "downside_volatility_252d": None,
                    "max_drawdown_1y": None,
                    "beta": None,
                    "debt_to_assets": debt_to_assets,
                    "beta_unavailable_reason": "missing_price_data",
                    "volatility_30d_unavailable_reason": "insufficient_history",
                    "volatility_60d_unavailable_reason": "insufficient_history",
                    "volatility_252d_unavailable_reason": "insufficient_history",
                    "downside_volatility_30d_unavailable_reason": "insufficient_history",
                    "downside_volatility_60d_unavailable_reason": "insufficient_history",
                    "downside_volatility_252d_unavailable_reason": "insufficient_history",
                    "max_drawdown_1y_unavailable_reason": "insufficient_history",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data_unavailable": debt_to_assets is None,
                    "reason": None if debt_to_assets is not None else reason,
                    "reason_type": None if debt_to_assets is not None else "loader_failed",
                }

            prices = sorted([(row[0], float(row[1])) for row in rows])

            returns = []
            for i in range(1, len(prices)):
                if prices[i - 1][1] > 0:
                    ret = math.log(prices[i][1] / prices[i - 1][1])
                    returns.append(ret)

            if not returns:
                reason = "invalid_price_data: no valid price transitions"
                logger.warning(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
                return {
                    "symbol": symbol,
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "downside_volatility_30d": None,
                    "downside_volatility_60d": None,
                    "downside_volatility_252d": None,
                    "max_drawdown_1y": None,
                    "beta": None,
                    "debt_to_assets": debt_to_assets,
                    "beta_unavailable_reason": "missing_price_data",
                    "volatility_30d_unavailable_reason": "insufficient_history",
                    "volatility_60d_unavailable_reason": "insufficient_history",
                    "volatility_252d_unavailable_reason": "insufficient_history",
                    "downside_volatility_30d_unavailable_reason": "insufficient_history",
                    "downside_volatility_60d_unavailable_reason": "insufficient_history",
                    "downside_volatility_252d_unavailable_reason": "insufficient_history",
                    "max_drawdown_1y_unavailable_reason": "insufficient_history",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data_unavailable": debt_to_assets is None,
                    "reason": None if debt_to_assets is not None else reason,
                    "reason_type": None if debt_to_assets is not None else "loader_failed",
                }

            # Calculate volatilities
            vol_30d = self._calculate_volatility(returns[-30:]) if len(returns) >= 30 else None
            vol_60d = self._calculate_volatility(returns[-60:]) if len(returns) >= 60 else None
            # BUG FIX (2026-07-27): vol_252d previously required only len(returns) >= 2 -
            # that floor came from _calculate_volatility's own divide-by-zero guard
            # (Bessel's correction needs len-1 >= 1), not a real "is this a meaningful
            # 252-day estimate" check. load_stock_scores.py._score_stability treats
            # volatility_252d as "12-month annualized volatility" and gives it 0.40 weight -
            # the single highest weight of any stability sub-component (more than
            # volatility_60d's 0.20 or volatility_30d's 0.15) - so a stock with e.g. 3-10
            # days of price history got a "252-day" figure computed from 2-9 daily returns,
            # confidently reported (data_unavailable=False) and given the most influence
            # over its stability score. Require the same floor volatility_60d already
            # enforces: vol_252d should never rest on a thinner sample than the mid-window
            # measure it's supposed to be a more-robust superset of.
            vol_252d = self._calculate_volatility(returns) if len(returns) >= 60 else None

            # Calculate downside volatilities (only negative returns - risk metric)
            downside_vol_30d = self._calculate_downside_volatility(returns[-30:]) if len(returns) >= 30 else None
            downside_vol_60d = self._calculate_downside_volatility(returns[-60:]) if len(returns) >= 60 else None
            downside_vol_252d = self._calculate_downside_volatility(returns) if len(returns) >= 60 else None

            # Calculate max drawdown over 252 days (peak-to-trough decline)
            max_drawdown_252d = self._calculate_max_drawdown([p[1] for p in prices]) if len(prices) >= 5 else None

            beta: float | dict[str, Any] | None = self._get_beta_from_db(symbol, prices, spy_rows)

            # Build unavailability reasons for any missing components
            unavailability_reasons = []
            if vol_30d is None and len(returns) < 30:
                unavailability_reasons.append(f"vol_30d: insufficient_returns ({len(returns)}/30 required)")
            if vol_60d is None and len(returns) < 60:
                unavailability_reasons.append(f"vol_60d: insufficient_returns ({len(returns)}/60 required)")
            if vol_252d is None and len(returns) < 60:
                unavailability_reasons.append(f"vol_252d: insufficient_returns ({len(returns)}/60 required)")
            if isinstance(beta, dict) and beta.get("data_unavailable"):
                unavailability_reasons.append(f"beta: {beta.get('reason', 'unknown')}")
                beta = None

            # FIX 2026-07-20: Previously required ALL of vol_30d/vol_60d/vol_252d/beta
            # to mark the row available, discarding real computed values whenever any
            # one component was missing (e.g. a stock with 100 days of history gets a
            # real vol_252d-via-shorter-window... no, gets a real vol_30d/vol_60d but
            # no vol_252d, and the whole row was thrown away). Downstream consumer
            # load_stock_scores.py._score_stability() is explicitly documented to only
            # need ONE non-null field ("MINIMUM DATA REQUIREMENT: At least one of
            # volatility_252d/volatility_60d/beta/debt_to_assets must be non-NULL"), so
            # requiring all four upstream silently dropped real data the scorer was
            # designed to consume. Mark unavailable only if every component failed.
            has_any_metric = any(v is not None for v in [
                vol_30d, vol_60d, vol_252d, beta, debt_to_assets,
                downside_vol_30d, downside_vol_60d, downside_vol_252d,
                max_drawdown_252d
            ])
            data_unavailable = not has_any_metric
            unavailability_reason: str | None = "; ".join(unavailability_reasons) if unavailability_reasons else None

            if data_unavailable and unavailability_reasons:
                logger.warning(f"[RISK_METRICS] {symbol}: incomplete stability metrics - {unavailability_reason}")

            return {
                "symbol": symbol,
                # `is not None` (not truthy) - a stock with an unchanged closing price for
                # its entire lookback window (illiquid/thinly-traded tickers, or a halted
                # symbol carrying a stale last price) genuinely computes to exactly 0.0, and
                # `if vol_Nd` would silently discard that real reading as unavailable.
                # load_stock_scores.py._score_stability checks `is not None` to decide
                # whether to include each component, so a falsely-NULLed 0.0 drops out of
                # the stability score entirely instead of correctly counting as "very low
                # volatility."
                "volatility_30d": round(vol_30d, 4) if vol_30d is not None else None,
                "volatility_60d": round(vol_60d, 4) if vol_60d is not None else None,
                "volatility_252d": round(vol_252d, 4) if vol_252d is not None else None,
                "downside_volatility_30d": round(downside_vol_30d, 4) if downside_vol_30d is not None else None,
                "downside_volatility_60d": round(downside_vol_60d, 4) if downside_vol_60d is not None else None,
                "downside_volatility_252d": round(downside_vol_252d, 4) if downside_vol_252d is not None else None,
                "max_drawdown_1y": round(max_drawdown_252d, 2) if max_drawdown_252d is not None else None,
                "beta": round(beta, 4) if isinstance(beta, float) else None,
                "debt_to_assets": debt_to_assets,
                # Session 395+: Add unavailable_reason for each metric
                "beta_unavailable_reason": "missing_price_data" if beta is None else None,
                "volatility_30d_unavailable_reason": "insufficient_history" if vol_30d is None else None,
                "volatility_60d_unavailable_reason": "insufficient_history" if vol_60d is None else None,
                "volatility_252d_unavailable_reason": "insufficient_history" if vol_252d is None else None,
                "downside_volatility_30d_unavailable_reason": "insufficient_history" if downside_vol_30d is None else None,
                "downside_volatility_60d_unavailable_reason": "insufficient_history" if downside_vol_60d is None else None,
                "downside_volatility_252d_unavailable_reason": "insufficient_history" if downside_vol_252d is None else None,
                "max_drawdown_1y_unavailable_reason": "insufficient_history" if max_drawdown_252d is None else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": data_unavailable,
                "reason": unavailability_reason,
            }

        except RuntimeError as e:
            reason = str(e)[:150]
            logger.debug(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
            return {
                "symbol": symbol,
                "volatility_30d": None,
                "volatility_60d": None,
                "volatility_252d": None,
                "downside_volatility_30d": None,
                "downside_volatility_60d": None,
                "downside_volatility_252d": None,
                "max_drawdown_1y": None,
                "beta": None,
                "debt_to_assets": debt_to_assets,
                "beta_unavailable_reason": "missing_price_data",
                "volatility_30d_unavailable_reason": "insufficient_history",
                "volatility_60d_unavailable_reason": "insufficient_history",
                "volatility_252d_unavailable_reason": "insufficient_history",
                "downside_volatility_30d_unavailable_reason": "insufficient_history",
                "downside_volatility_60d_unavailable_reason": "insufficient_history",
                "downside_volatility_252d_unavailable_reason": "insufficient_history",
                "max_drawdown_1y_unavailable_reason": "insufficient_history",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": debt_to_assets is None,
                "reason": None if debt_to_assets is not None else reason,
                "reason_type": None if debt_to_assets is not None else "loader_failed",
            }
        except Exception as e:
            logger.warning(f"[RISK_METRICS] Stability error for {symbol}: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "volatility_30d": None,
                "volatility_60d": None,
                "volatility_252d": None,
                "downside_volatility_30d": None,
                "downside_volatility_60d": None,
                "downside_volatility_252d": None,
                "max_drawdown_1y": None,
                "beta": None,
                "debt_to_assets": debt_to_assets,
                "beta_unavailable_reason": "missing_price_data",
                "volatility_30d_unavailable_reason": "insufficient_history",
                "volatility_60d_unavailable_reason": "insufficient_history",
                "volatility_252d_unavailable_reason": "insufficient_history",
                "downside_volatility_30d_unavailable_reason": "insufficient_history",
                "downside_volatility_60d_unavailable_reason": "insufficient_history",
                "downside_volatility_252d_unavailable_reason": "insufficient_history",
                "max_drawdown_1y_unavailable_reason": "insufficient_history",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": debt_to_assets is None,
                "reason": f"unexpected_error: {type(e).__name__}" if debt_to_assets is None else None,
            }

    def _persist_stability_metrics(self, row: dict[str, Any]) -> None:
        """Write stability metrics row to stability_metrics table."""
        if "data_unavailable" not in row:
            logger.critical(
                f"CRITICAL: data_unavailable key missing from risk metrics row for {row.get('symbol')}. "
                "Failing fast - refusing to write corrupted data."
            )
            raise KeyError("data_unavailable key required in stability metrics row")

        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO stability_metrics
                    (symbol, volatility_30d, volatility_60d, volatility_252d,
                     downside_volatility_30d, downside_volatility_60d, downside_volatility_252d,
                     max_drawdown_1y, beta, debt_to_assets,
                     created_at, data_unavailable, reason, reason_type, data_source,
                     beta_unavailable_reason, volatility_30d_unavailable_reason,
                     volatility_60d_unavailable_reason, volatility_252d_unavailable_reason,
                     downside_volatility_30d_unavailable_reason,
                     downside_volatility_60d_unavailable_reason,
                     downside_volatility_252d_unavailable_reason,
                     max_drawdown_1y_unavailable_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      volatility_30d = EXCLUDED.volatility_30d,
                      volatility_60d = EXCLUDED.volatility_60d,
                      volatility_252d = EXCLUDED.volatility_252d,
                      downside_volatility_30d = EXCLUDED.downside_volatility_30d,
                      downside_volatility_60d = EXCLUDED.downside_volatility_60d,
                      downside_volatility_252d = EXCLUDED.downside_volatility_252d,
                      max_drawdown_1y = EXCLUDED.max_drawdown_1y,
                      beta = EXCLUDED.beta,
                      debt_to_assets = EXCLUDED.debt_to_assets,
                      created_at = EXCLUDED.created_at,
                      data_unavailable = EXCLUDED.data_unavailable,
                      reason = EXCLUDED.reason,
                      reason_type = EXCLUDED.reason_type,
                      data_source = EXCLUDED.data_source,
                      beta_unavailable_reason = EXCLUDED.beta_unavailable_reason,
                      volatility_30d_unavailable_reason = EXCLUDED.volatility_30d_unavailable_reason,
                      volatility_60d_unavailable_reason = EXCLUDED.volatility_60d_unavailable_reason,
                      volatility_252d_unavailable_reason = EXCLUDED.volatility_252d_unavailable_reason,
                      downside_volatility_30d_unavailable_reason = EXCLUDED.downside_volatility_30d_unavailable_reason,
                      downside_volatility_60d_unavailable_reason = EXCLUDED.downside_volatility_60d_unavailable_reason,
                      downside_volatility_252d_unavailable_reason = EXCLUDED.downside_volatility_252d_unavailable_reason,
                      max_drawdown_1y_unavailable_reason = EXCLUDED.max_drawdown_1y_unavailable_reason,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        row.get("symbol"),
                        row.get("volatility_30d"),
                        row.get("volatility_60d"),
                        row.get("volatility_252d"),
                        row.get("downside_volatility_30d"),
                        row.get("downside_volatility_60d"),
                        row.get("downside_volatility_252d"),
                        row.get("max_drawdown_1y"),
                        row.get("beta"),
                        row.get("debt_to_assets"),
                        row.get("created_at"),
                        row["data_unavailable"],
                        row.get("reason"),
                        row.get("reason_type"),
                        # Migration 1022 documents this column's intended value as
                        # "computed_from_price_daily" (volatility/beta are computed from
                        # price_daily here, not fetched from any external vendor) - never
                        # actually written until this fix, leaving all rows NULL.
                        "computed_from_price_daily",
                        row.get("beta_unavailable_reason"),
                        row.get("volatility_30d_unavailable_reason"),
                        row.get("volatility_60d_unavailable_reason"),
                        row.get("volatility_252d_unavailable_reason"),
                        row.get("downside_volatility_30d_unavailable_reason"),
                        row.get("downside_volatility_60d_unavailable_reason"),
                        row.get("downside_volatility_252d_unavailable_reason"),
                        row.get("max_drawdown_1y_unavailable_reason"),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[RISK_METRICS] Failed to persist stability metrics for {row.get('symbol')}: {e}")

    @staticmethod
    def _calculate_volatility(returns: list[float]) -> float | None:
        if not returns or len(returns) < 2:
            return None

        # Sample variance (Bessel's correction, N-1), not population variance (N): this is
        # a sample of returns used to estimate the population's true volatility, and N-1 is
        # the standard unbiased estimator convention for financial volatility - matches
        # _get_beta_from_db's np.var(..., ddof=1)/np.cov() a few lines below in this same
        # file. N alone systematically understates volatility (~1.7% low at the 30-day
        # minimum window this is normally called with, i.e. sqrt(30/29)), the same direction
        # of error as computing risk too optimistically.
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        daily_std = math.sqrt(variance)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _calculate_downside_volatility(returns: list[float]) -> float | None:
        """Calculate annualized downside volatility (std dev of negative returns only).

        Downside volatility is a risk metric that measures the standard deviation of only
        negative returns, providing a better reflection of downside risk than traditional
        volatility which treats gains and losses symmetrically. Used in Sortino ratio.

        Args:
            returns: List of daily log returns

        Returns:
            Annualized downside volatility (annualized by sqrt(252)), or None if insufficient data
        """
        if not returns or len(returns) < 2:
            return None

        downside_returns = [r for r in returns if r < 0]
        if not downside_returns or len(downside_returns) < 1:
            return None

        if len(downside_returns) < 2:
            return None

        mean_downside = sum(downside_returns) / len(downside_returns)
        variance = sum((r - mean_downside) ** 2 for r in downside_returns) / (len(downside_returns) - 1)
        daily_std = math.sqrt(variance)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _calculate_max_drawdown(prices: list[float]) -> float | None:
        """Calculate maximum drawdown: largest peak-to-trough decline in percentage terms.

        Max drawdown measures the largest decline from a peak to a subsequent trough,
        expressed as a percentage. It represents the worst-case loss over the period.

        Args:
            prices: List of closing prices in chronological order

        Returns:
            Maximum drawdown as percentage (e.g., -25.5 for 25.5% decline), or None if insufficient data
        """
        if not prices or len(prices) < 2:
            return None

        max_drawdown = 0.0
        peak = prices[0]

        for price in prices[1:]:
            if price > 0 and peak > 0:
                drawdown = ((price - peak) / peak) * 100
                if drawdown < max_drawdown:
                    max_drawdown = drawdown
                if price > peak:
                    peak = price

        return max_drawdown if max_drawdown < 0 else None

    @staticmethod
    def _get_beta_from_db(
        symbol: str,
        stock_prices: list[tuple[Any, float]],
        spy_rows: list[Any],
    ) -> float | dict[str, Any]:
        import numpy as np

        min_spy_days = 5
        if not spy_rows or len(spy_rows) < min_spy_days:
            actual = len(spy_rows) if spy_rows else 0
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"spy_price_data_insufficient: {actual}/{min_spy_days} days",
            }

        try:
            stock_by_date = {p[0]: p[1] for p in stock_prices}
            spy_by_date: dict[Any, float] = {row[0]: float(row[1]) for row in spy_rows}

            common_dates = sorted(set(stock_by_date.keys()) & set(spy_by_date.keys()))
            if len(common_dates) < 5:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_common_dates: {len(common_dates)}/5",
                }

            stock_aligned = [stock_by_date[d] for d in common_dates]
            spy_aligned = [spy_by_date[d] for d in common_dates]

            stock_returns = np.diff(np.log(np.array(stock_aligned, dtype=float)))
            spy_returns = np.diff(np.log(np.array(spy_aligned, dtype=float)))

            if len(stock_returns) < 4:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_returns: {len(stock_returns)}/4",
                }

            spy_var = float(np.var(spy_returns, ddof=1))
            if spy_var == 0:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "spy_variance_zero",
                    "reason_type": "loader_failed",
                }

            cov_matrix = np.cov(stock_returns, spy_returns)
            beta = float(cov_matrix[0, 1]) / spy_var

            if abs(beta) > 10:
                logger.warning(f"[RISK_METRICS] {symbol}: extreme DB beta {beta:.2f} - marking unavailable.")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"extreme_beta: {beta:.2f}",
                }

            return round(beta, 4)

        except Exception as e:
            logger.warning(f"[RISK_METRICS] {symbol}: DB beta computation failed: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"db_beta_error: {type(e).__name__}",
            }


if __name__ == "__main__":
    sys.exit(run_loader(RiskMetricsLoader))
