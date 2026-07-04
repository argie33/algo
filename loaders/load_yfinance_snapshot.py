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
from utils.external.yfinance import YFinanceWrapper
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


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

        Governance: Fail-fast on missing data. No silent fallbacks.

        Returns all metrics in one row to avoid 6 separate yfinance API calls.
        Raises RuntimeError if ticker unavailable or data fetch fails (critical data).
        """
        ticker = YFinanceWrapper.get_ticker(symbol)
        if not ticker:
            raise RuntimeError(
                f"[YFINANCE_SNAPSHOT] Ticker data unavailable for {symbol}. "
                f"Cannot fetch yfinance metrics without valid ticker. "
                f"Downstream loaders (value_metrics, positioning_metrics, stability_metrics, etc.) depend on this data."
            )

        info = ticker.info
        if not info or not isinstance(info, dict):
            raise RuntimeError(
                f"[YFINANCE_SNAPSHOT] No info dict available for {symbol}. "
                f"Ticker returned invalid/empty data structure. "
                f"Cannot proceed without valid company information."
            )

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
                "fetched_at": datetime.now(timezone.utc).isoformat(),
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
                    f"missing_critical_fields: {','.join(missing_critical)}"
                    if missing_critical
                    else None
                ),
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(YFinanceSnapshotLoader))
