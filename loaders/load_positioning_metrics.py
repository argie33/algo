#!/usr/bin/env python3
"""Positioning Metrics Loader - CRITICAL for stock scoring (institutional/insider/short data).

PURPOSE:
- Fetch positioning metrics (institutional ownership %, insider ownership %, short interest %)
- These are REQUIRED by load_stock_scores.py (minimum 30% coverage needed)
- 100% SEC-based sources (no yfinance dependency)

DATA SOURCES (Session 275+):
- short_interest: FINRA Reg SHO Transparency Data (load_short_interest_finra.py)
- institutional_ownership: SEC 13F filings (load_institutional_holdings_13f.py)
- insider_ownership: SEC Form 4/5 filings (load_insider_holdings_sec.py)
- Writes to: positioning_metrics table (READ BY stock_scores.py)

DEPENDENCIES:
- load_short_interest_finra.py must run FIRST (populates short_interest_finra table)
- load_institutional_holdings_13f.py must run (populates institutional_holdings_13f table)
- load_insider_holdings_sec.py must run (populates insider_holdings_sec table)

Run:
    python3 loaders/load_positioning_metrics.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

import pandas as pd

from loaders.runner import run_loader
from loaders.technical_indicators import compute_ad_rating
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class PositioningMetricsLoader(OptimalLoader):
    """Load positioning metrics from official SEC sources.

    CRITICAL LOADER: Stock scores require 30% coverage of positioning metrics.
    Without this data, stock scoring fails pre-flight validation.

    Reads from: SEC 13F (institutional holdings), SEC Form 4/5 (insider holdings), FINRA (short interest).
    Writes to positioning_metrics table (read by stock_scores.py).
    """

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def _compute_ad_rating(self, symbol: str) -> tuple[float | None, str | None]:
        """Calculate A/D Rating (0-100 score) from Accumulation/Distribution analysis.

        Returns:
            Tuple of (ad_rating_score, unavailable_reason)
        """
        try:
            with DatabaseContext("read") as cur:
                # Fetch last 252 days of OHLCV data for A/D calculation
                cur.execute(
                    """
                    SELECT date, high, low, close, volume
                    FROM price_daily
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date ASC
                    """,
                    (symbol,),
                )
                rows = cur.fetchall()

            if not rows or len(rows) < 20:
                return None, "insufficient_price_history"

            # Build pandas series for calculation
            dates = [row[0] for row in rows]
            high = pd.Series([safe_float(row[1], f"{symbol}.high", allow_none=False) for row in rows], index=dates)
            low = pd.Series([safe_float(row[2], f"{symbol}.low", allow_none=False) for row in rows], index=dates)
            close = pd.Series([safe_float(row[3], f"{symbol}.close", allow_none=False) for row in rows], index=dates)
            volume = pd.Series([safe_float(row[4], f"{symbol}.volume", allow_none=False) for row in rows], index=dates)

            # Compute A/D rating from technical indicator
            ad_rating = compute_ad_rating(high, low, close, volume)
            return ad_rating, None if ad_rating is not None else "ad_calculation_failed"

        except Exception as e:
            logger.debug(f"[POSITIONING] A/D rating calculation failed for {symbol}: {e}")
            return None, f"ad_calculation_error: {str(e)[:50]}"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch positioning metrics from official SEC sources (TIER 1 only).

        CRITICAL (Session 275+): Removed yfinance_snapshot TIER 2 fallback.
        Governance rule: no silent fallbacks. If SEC data unavailable, report data_unavailable explicitly.

        TIER 1 (Authoritative, only tier):
        - short_interest: FINRA Reg SHO
        - institutional_ownership: SEC 13F filings
        - insider_ownership: SEC Form 4/5 filings

        Returns positioning data or data_unavailable marker if all sources exhausted.
        """
        now_et = datetime.now(EASTERN_TZ)

        # Calculate A/D rating from price and volume data
        ad_rating, ad_rating_reason = self._compute_ad_rating(symbol)

        # TIER 1: Fetch short interest from FINRA (OPTIONAL if table unavailable)
        short_interest_pct = None
        short_interest_source = None
        shares_short_prior_month = None
        short_interest_trend = None
        short_ratio = None
        short_percent_of_float = None

        try:
            with DatabaseContext("read") as cur:
                # FIX 2026-07-20: Was LIMIT 1 (latest settlement only). FINRA reports
                # settle bi-monthly, so the prior settlement's short_shares is already
                # in this table - fetching 2 rows lets us derive shares_short_prior_month
                # and short_interest_trend (both existing positioning_metrics columns that
                # no loader had ever populated) with no new data source needed.
                cur.execute(
                    """
                    SELECT short_pct, short_shares, settlement_date, days_to_cover, avg_daily_volume
                    FROM short_interest_finra
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY settlement_date DESC LIMIT 2
                    """,
                    (symbol,),
                )
                short_rows = cur.fetchall()

            if short_rows and short_rows[0][0] is not None:
                short_interest_pct = short_rows[0][0]
                short_interest_source = "finra"
                # Get short_ratio (days to cover) from FINRA
                if short_rows[0][3] is not None:
                    short_ratio = float(short_rows[0][3])
            else:
                short_interest_source = "unavailable"

            if len(short_rows) >= 2:
                shares_short_prior_month = short_rows[1][1]
                current_pct, prior_pct = short_rows[0][0], short_rows[1][0]
                if current_pct is not None and prior_pct is not None and prior_pct != 0:
                    relative_change = (current_pct - prior_pct) / prior_pct
                    if relative_change > 0.05:
                        short_interest_trend = "increasing"
                    elif relative_change < -0.05:
                        short_interest_trend = "decreasing"
                    else:
                        short_interest_trend = "stable"

            # NOTE: this is short_shares / shares_outstanding, NOT true public float -
            # SEC filings don't expose a float figure (it would require subtracting
            # insider/restricted/locked-up shares, not a standard XBRL concept). Same
            # denominator as short_interest_pct above. Real float <= shares outstanding,
            # so the true float-based percentage is typically higher than this value -
            # frontend labels this "Short % of Shares O/S" (not "of Float") for that reason.
            if short_rows and short_rows[0][1] is not None:  # short_shares
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT shares_outstanding FROM company_info_sec
                            WHERE symbol = %s AND data_unavailable = FALSE
                            ORDER BY filing_date DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        shares_row = cur.fetchone()

                    if shares_row and shares_row[0] is not None and shares_row[0] > 0:
                        short_shares = float(short_rows[0][1])
                        shares_outstanding = float(shares_row[0])
                        short_percent_of_float = (short_shares / shares_outstanding) * 100
                except Exception as e:
                    logger.debug(f"[POSITIONING] {symbol}: Could not calculate short_percent_of_float: {e}")
        except Exception as e:
            # Table may not exist or loader not running yet - treat as optional
            logger.debug(f"[POSITIONING] {symbol}: short_interest_finra unavailable: {e}")
            short_interest_source = "unavailable"

        # TIER 1: Fetch institutional ownership from SEC 13F
        institutional_pct = None
        institutional_source = None

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT institutional_ownership_pct, data_unavailable, reason
                FROM institutional_holdings_13f
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol,),
            )
            sec_inst_row = cur.fetchone()

        if sec_inst_row and sec_inst_row[0] is not None:
            institutional_pct = sec_inst_row[0]
            institutional_source = "sec_13f"
        else:
            institutional_source = "unavailable"

        # TIER 1: Fetch insider ownership from SEC Form 4/5
        insider_pct = None
        insider_source = None

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT insider_ownership_pct, data_unavailable, reason
                FROM insider_holdings_sec
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol,),
            )
            sec_insider_row = cur.fetchone()

        if sec_insider_row and sec_insider_row[0] is not None:
            insider_pct = sec_insider_row[0]
            insider_source = "sec_form4"
        else:
            insider_source = "unavailable"

        # CRITICAL (Session 275+): Removed TIER 2 yfinance_snapshot fallback.
        # Governance rule: no silent fallbacks. If SEC data unavailable, report data_unavailable explicitly.
        # yfinance_snapshot is deprecated; institutional_holdings_13f and insider_holdings_sec
        # are authoritative sources. If they fail to produce data, that's a real failure to report.

        # Final availability check: data_unavailable only if ALL three metrics are missing
        all_unavailable = (
            short_interest_source == "unavailable"
            and institutional_source == "unavailable"
            and insider_source == "unavailable"
        )

        return [
            {
                "symbol": symbol,
                "institutional_ownership_pct": institutional_pct,
                "insider_ownership_pct": insider_pct,
                "short_interest_pct": short_interest_pct,
                "shares_short_prior_month": shares_short_prior_month,
                "short_interest_trend": short_interest_trend,
                "short_percent_of_float": short_percent_of_float,
                "short_ratio": short_ratio,
                # Session 395+: Add unavailable_reason for each metric
                "institutional_ownership_pct_unavailable_reason": (
                    "missing_sec_data" if institutional_pct is None else None
                ),
                "insider_ownership_pct_unavailable_reason": "missing_sec_data" if insider_pct is None else None,
                "short_interest_pct_unavailable_reason": "missing_finra_data" if short_interest_pct is None else None,
                "shares_short_prior_month_unavailable_reason": (
                    "insufficient_history" if shares_short_prior_month is None else None
                ),
                "short_interest_trend_unavailable_reason": (
                    "insufficient_history" if short_interest_trend is None else None
                ),
                "short_percent_of_float_unavailable_reason": (
                    "missing_sec_data" if short_percent_of_float is None else None
                ),
                "short_ratio_unavailable_reason": (
                    "missing_finra_data" if short_ratio is None else None
                ),
                # These require enhanced 13F data extraction not yet implemented
                "top_10_institutions_pct": None,
                "top_10_institutions_pct_unavailable_reason": "institutional_data_not_available",
                "institutional_holders_count": None,
                "institutional_holders_count_unavailable_reason": "institutional_data_not_available",
                # A/D rating from volume-weighted technical indicator
                "ad_rating": ad_rating,
                "ad_rating_unavailable_reason": ad_rating_reason,
                "data_unavailable": all_unavailable,
                "reason": (
                    f"short_interest:{short_interest_source};institutional:{institutional_source};insider:{insider_source}"
                    if all_unavailable
                    else None
                ),
                "data_source": (
                    # Set data_source to the primary available source, or "none" if all unavailable
                    short_interest_source
                    if short_interest_source != "unavailable"
                    else (
                        institutional_source
                        if institutional_source != "unavailable"
                        else insider_source if insider_source != "unavailable" else "none"
                    )
                ),
                "source_tracking": {
                    "short_interest": short_interest_source,
                    "institutional": institutional_source,
                    "insider": insider_source,
                },
                "updated_at": now_et,
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(PositioningMetricsLoader)
    except Exception as e:
        logger.error(f"[POSITIONING FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable only for symbols with no row yet -- a crash partway through
        # must not clobber symbols already fetched and committed earlier in this same run
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO positioning_metrics (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO NOTHING
                        """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"[POSITIONING] Failed to mark positioning_metrics data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
