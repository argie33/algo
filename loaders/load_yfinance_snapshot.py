#!/usr/bin/env python3
"""yfinance Snapshot Loader - Fetch ALL yfinance data once per symbol, store in DB.

CRITICAL FIX 2026-07-02: Consolidates 30,000+ redundant yfinance API calls by having
6+ loaders read from a single snapshot table instead of each calling yfinance separately.

Consolidates redundant calls from:
- value_metrics (PE, PB, PS, dividend)
- positioning_metrics (institutional/insider holdings, short interest)
- stability_metrics (beta, volatility)
- company_profile (sector, industry, country)
- earnings_history (earnings dates)
- earnings_calendar (next earnings date)
- analyst_upgrade_downgrade (analyst counts)
- analyst_sentiment_analysis (recommendation key, analyst counts)

Single fetch per symbol → yfinance_snapshot table → all loaders read from table.
Fetches once per symbol, caches 24 hours. Eliminates 30,000+ redundant API calls.
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.external.yfinance import YFinanceWrapper
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class YFinanceSnapshotLoader(OptimalLoader):
    """Fetch all yfinance data once per symbol, store in yfinance_snapshot table."""

    table_name = "yfinance_snapshot"
    primary_key = ("symbol",)
    watermark_field = "fetched_at"
    exclude_etfs_from_symbols = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch all yfinance data for a symbol, store as single snapshot record.

        Governance: Mark unavailable data explicitly. No silent fallbacks or exceptions.
        Returns data_unavailable marker instead of raising exceptions per GOVERNANCE.md.

        Returns all metrics in one row to avoid 6 separate yfinance API calls.
        Returns data_unavailable marker if ticker unavailable or data fetch fails.
        """
        ticker = YFinanceWrapper.get_ticker(symbol)
        if not ticker:
            # Ticker data unavailable (delisted, invalid, or yfinance API issue)
            logger.debug(f"[YFINANCE_SNAPSHOT] {symbol}: Ticker data unavailable (yfinance API or invalid symbol)")
            return [
                {
                    "symbol": symbol,
                    "fetched_at": datetime.now(timezone.utc),
                    "data_available": False,
                    "unavailable_reason": "yfinance_ticker_unavailable",
                }
            ]

        info = ticker.info
        if not info or not isinstance(info, dict):
            # Ticker returned invalid/empty data structure
            logger.debug(f"[YFINANCE_SNAPSHOT] {symbol}: Ticker returned invalid data structure")
            return [
                {
                    "symbol": symbol,
                    "fetched_at": datetime.now(timezone.utc),
                    "data_available": False,
                    "unavailable_reason": "yfinance_invalid_info_dict",
                }
            ]

        # Extract all yfinance metrics into single snapshot
        pe_ratio = info.get("trailingPE")
        pb_ratio = info.get("priceToBook")
        ps_ratio = info.get("priceToSalesTrailing12Months")
        peg_ratio = info.get("pegRatio")
        dividend_yield = info.get("dividendYield")
        fcf_yield = (
            info["freeCashflow"] / info["marketCap"]
            if "freeCashflow" in info
            and "marketCap" in info
            and info["freeCashflow"] is not None
            and info["marketCap"] is not None
            else None
        )
        held_percent_insiders = info.get("insidersPercentHeld")
        held_percent_institutions = info.get("heldPercentInstitutions")
        short_interest = info.get("shortPercentOfFloat")
        beta = info.get("beta")
        fifty_two_week_high = info.get("fiftyTwoWeekHigh")
        fifty_two_week_low = info.get("fiftyTwoWeekLow")
        market_cap = info.get("marketCap")
        sector = info.get("sector")
        industry = info.get("industry")
        country = info.get("country")
        exchange = info.get("exchange")
        website = info.get("website")
        long_name = info.get("longName")
        earnings_dates = info.get("earningsDates")
        earnings_date = info.get("earningsDate")
        recommendation_key = info.get("recommendationKey")
        number_of_analysts = info.get("numberOfAnalystOpinions")
        analysts_underweight = info.get("numberOfAnalystsWhoUnderweight")
        analysts_overweight = info.get("numberOfAnalystsWhoOverweight")
        analysts_hold = info.get("numberOfAnalystsWhoHold")

        critical_fields = {
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "market_cap": market_cap,
            "sector": sector,
            "long_name": long_name,
        }
        missing_critical = [k for k, v in critical_fields.items() if v is None]

        return [
            {
                "symbol": symbol,
                "fetched_at": datetime.now(timezone.utc),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "ps_ratio": ps_ratio,
                "peg_ratio": peg_ratio,
                "dividend_yield": dividend_yield,
                "fcf_yield": fcf_yield,
                "held_percent_insiders": held_percent_insiders,
                "held_percent_institutions": held_percent_institutions,
                "short_interest": short_interest,
                "beta": beta,
                "fifty_two_week_high": fifty_two_week_high,
                "fifty_two_week_low": fifty_two_week_low,
                "market_cap": market_cap,
                "sector": sector,
                "industry": industry,
                "country": country,
                "exchange": exchange,
                "website": website,
                "long_name": long_name,
                "earnings_dates": earnings_dates,
                "earnings_date": earnings_date,
                "recommendation_key": recommendation_key,
                "number_of_analysts": number_of_analysts,
                "analysts_underweight": analysts_underweight,
                "analysts_overweight": analysts_overweight,
                "analysts_hold": analysts_hold,
                "data_available": len(missing_critical) == 0,
                "unavailable_reason": (
                    f"missing_critical_fields: {','.join(missing_critical)}" if missing_critical else None
                ),
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(YFinanceSnapshotLoader)
    except Exception as e:
        logger.error(f"[YFINANCE_SNAPSHOT FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable for all symbols
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO yfinance_snapshot (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO UPDATE SET
                          data_unavailable = TRUE,
                          reason = EXCLUDED.reason,
                          updated_at = NOW()
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark yfinance_snapshot data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
