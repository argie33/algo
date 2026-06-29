#!/usr/bin/env python3
"""
Earnings History Loader - Optimal Pattern.

Loads historical earnings dates and actual EPS.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningshistory.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class EarningsHistoryLoader(OptimalLoader):
    table_name = "earnings_history"
    primary_key = ("symbol", "quarter")
    watermark_field = "earnings_date"
    max_fail_rate = 99.5  # Only major symbols have earnings history; allow 99.5% failure rate

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch earnings history from yfinance earnings_dates.

        Returns list of earnings records since the watermark date.
        Raises RuntimeError if no earnings history is available for the symbol.
        Logs WARNING if earnings data is present but no new records since watermark.
        """
        try:
            from datetime import datetime

            from utils.external.yfinance import get_ticker

            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)
            df = ticker.earnings_dates
            if df is None or (hasattr(df, "empty") and df.empty):
                error_msg = (
                    f"[EARNINGS_HISTORY] {symbol}: No earnings history available from yfinance. "
                    "Cannot track earnings surprises without historical data."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            rows = []
            cutoff = since.isoformat() if since else "2000-01-01"
            for idx, row in df.iterrows():
                try:
                    if hasattr(idx, "date"):
                        ed = idx.date().isoformat()
                    else:
                        ed = str(idx)[:10]
                    if ed < cutoff:
                        continue
                    # Explicitly get optional earnings fields with None defaults
                    eps_est = row.get("EPS Estimate", None)
                    eps_actual = row.get("Reported EPS", None)
                    surprise_pct = row.get("Surprise(%)", None)

                    def _float(v: Any, field_name: str = "value") -> float | None:
                        """Convert value to float, fail-fast on corruption.

                        Returns None only for legitimately missing data (None, empty string).
                        Raises ValueError for malformed/corrupted data.
                        """
                        import math

                        # Legitimately missing data
                        if v is None or (isinstance(v, str) and v.strip() == ""):
                            return None

                        # Corrupted/malformed data should fail-fast
                        try:
                            f = float(v)
                            if math.isnan(f):
                                return None
                            return round(f, 4)
                        except (TypeError, ValueError) as e:
                            raise ValueError(
                                f"[{symbol}] Malformed {field_name} value {v!r}: cannot convert to float. "
                                f"Data corruption detected for earnings history."
                            ) from e

                    # Derive quarter start date (the quarter in which earnings fall)
                    try:
                        dt = datetime.fromisoformat(ed)
                        q = (dt.month - 1) // 3 + 1
                        qstart_month = (q - 1) * 3 + 1
                        quarter_str = f"{dt.year}-{qstart_month:02d}-01"
                        fiscal_quarter = q
                        fiscal_year = dt.year
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        error_msg = (
                            f"[{symbol}] Failed to derive quarter from earnings date {ed!r}: {e}. "
                            f"Cannot use earnings data with unparseable dates — "
                            f"primary key (symbol, quarter) depends on valid date parsing."
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg) from e

                    # Determine if estimate (future) or actual (past)
                    estimated = eps_actual is None or (isinstance(eps_actual, float) and eps_actual == 0)

                    # Calculate surprise difference if both values present
                    eps_diff = None
                    if eps_actual is not None and eps_est is not None:
                        try:
                            eps_diff = float(eps_actual) - float(eps_est)
                        except (ValueError, TypeError):
                            pass

                    rows.append(
                        {
                            "symbol": symbol,
                            "quarter": quarter_str,
                            "fiscal_quarter": fiscal_quarter,
                            "fiscal_year": fiscal_year,
                            "earnings_date": ed,
                            "estimated": estimated,
                            "eps_actual": _float(eps_actual, "eps_actual"),
                            "revenue_actual": None,
                            "eps_estimate": _float(eps_est, "eps_estimate"),
                            "revenue_estimate": None,
                            "eps_surprise_pct": _float(surprise_pct, "eps_surprise_pct"),
                            "revenue_surprise_pct": None,
                            "eps_difference": eps_diff,
                            "revenue_difference": None,
                            "beat_miss_flag": None,
                            "surprise_percent": _float(surprise_pct, "surprise_pct"),
                            "estimate_revision_days": None,
                            "estimate_revision_count": None,
                            "fetched_at": None,
                        }
                    )
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.warning(f"[{symbol}] Skipped earnings row (index {idx}) due to error: {e}")

            # Deduplicate by (symbol, quarter) - keep most recent earnings_date
            if rows:
                seen: dict[tuple[str, str], dict[str, Any]] = {}
                for row in rows:
                    key = (row["symbol"], row["quarter"])
                    if key not in seen or row["earnings_date"] > seen[key]["earnings_date"]:
                        seen[key] = row
                rows = list(seen.values())
                return rows
            else:
                # No earnings records available - fail fast
                if since:
                    error_msg = (
                        f"[EARNINGS_HISTORY] {symbol}: no new earnings records since {since.isoformat()}. "
                        "Cannot update earnings data without new records available."
                    )
                else:
                    error_msg = (
                        f"[EARNINGS_HISTORY] {symbol}: no earnings history available from yfinance. "
                        "Symbol must have earnings data available to track surprises."
                    )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            error_msg = f"[EARNINGS_HISTORY] {symbol}: Failed to fetch earnings history: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate earnings row has required fields.

        Raises ValueError if required fields are missing or malformed.
        """
        if not super()._validate_row(row):
            return False

        # Validate required fields with explicit defaults
        quarter = row.get("quarter", None)
        earnings_date = row.get("earnings_date", None)
        symbol = row.get("symbol", None)

        if not quarter:
            raise ValueError(
                f"[{symbol}] Missing or empty required field 'quarter'. "
                f"Earnings row cannot be inserted without a valid quarter."
            )
        if not earnings_date:
            raise ValueError(
                f"[{symbol}] Missing or empty required field 'earnings_date'. "
                f"Earnings row cannot be inserted without a valid earnings date."
            )
        if not symbol:
            raise ValueError(
                "Missing or empty required field 'symbol'. Earnings row cannot be inserted without a valid symbol."
            )

        return True


if __name__ == "__main__":
    sys.exit(run_loader(EarningsHistoryLoader))
