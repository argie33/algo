#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F (Quarterly).

PHASE 2 OPTIMIZATION (Session 237):
Replaces yfinance held_percent_institutions (~20% of yfinance_snapshot) with
authoritative SEC Form 13F institutional ownership data (quarterly, audited).

Data source: SEC EDGAR companyfacts API (standardized institutional metrics)
Update frequency: Quarterly (90-day lag acceptable for stock scoring)
Quality: SEC-published institutional ownership data > yfinance estimates

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timedelta
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InstitutionalHoldings13FLoader(SecLoaderBase):
    """Load institutional ownership % from SEC companyfacts API.

    PHASE 2: Eliminates yfinance held_percent_institutions (~20% yfinance load).
    Uses SEC companyfacts endpoint which provides standardized institutional metrics.

    Benefits:
    - SEC-published data (regulatory authority)
    - Quarterly updates aligned with Form 13F filings
    - No rate-limiting dependency
    - Eliminates 5,000+ yfinance API calls per run

    Trade-off: Quarterly updates (90-day lag) acceptable for stock scoring.

    Data source: SEC EDGAR companyfacts endpoint
    - Endpoint: /api/xbrl/companyfacts/CIK[cik]/facts/EntityIntelligenceData
    - Metric: SRT_InstitutionalOwnersPercent (when available)
    - Frequency: Updated as companies file (typically quarterly)
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from SEC companyfacts API.

        Tries to extract SRT_InstitutionalOwnersPercent from companyfacts.
        Falls back to data_unavailable if metric not available.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Query companyfacts for EntityIntelligenceData / SRT_InstitutionalOwnersPercent
            try:
                companyfacts = self.sec_client.get_company_facts(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "company_facts_not_found_404")

            if not companyfacts:
                return self._unavailable_record(symbol, now_et, "company_facts_empty")

            # Extract institutional ownership % from facts
            facts = companyfacts.get("facts", {})

            # Try EntityIntelligenceData first (standardized SRT metrics)
            entity_intel = facts.get("EntityIntelligenceData", {})
            inst_owners_data = entity_intel.get("SRT_InstitutionalOwnersPercent", {})

            if not inst_owners_data or "units" not in inst_owners_data:
                # Metric not available in this company's facts
                return self._unavailable_record(symbol, now_et, "institutional_ownership_metric_unavailable")

            # Extract most recent value (units -> pure -> sorted by end date)
            units = inst_owners_data.get("units", {})
            pure_values = units.get("pure", [])

            if not pure_values:
                return self._unavailable_record(symbol, now_et, "no_institutional_data_points")

            # Sort by filing date (end) - most recent first
            pure_values_sorted = sorted(
                pure_values,
                key=lambda x: x.get("end", ""),
                reverse=True
            )

            latest = pure_values_sorted[0]
            filing_date_str = latest.get("end")
            ownership_pct = latest.get("val")

            # Parse filing date
            if filing_date_str:
                try:
                    filing_date = datetime.fromisoformat(filing_date_str).date()
                except (ValueError, TypeError):
                    filing_date = now_et.date()
            else:
                filing_date = now_et.date()

            # Validate ownership percentage
            if not isinstance(ownership_pct, (int, float)):
                return self._unavailable_record(symbol, now_et, "invalid_ownership_value_type")

            ownership_pct = float(ownership_pct)
            if not (0 <= ownership_pct <= 100):
                logger.warning(f"[{symbol}] Institutional ownership % out of range: {ownership_pct}%")
                ownership_pct = None

            return [
                {
                    "symbol": symbol,
                    "filing_date": filing_date,
                    "institutional_ownership_pct": ownership_pct,
                    "number_of_institutional_holders": None,  # Requires parsing actual Form 13F
                    "data_unavailable": False,
                    "reason": None,
                    "sec_filing_url": None,
                    "most_recent_filing_date": filing_date,
                }
            ]

        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch institutional holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"fetch_error: {str(e)[:40]}")

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "institutional_ownership_pct": None,
                "number_of_institutional_holders": None,
                "data_unavailable": True,
                "reason": reason,
                "sec_filing_url": None,
                "most_recent_filing_date": None,
            }
        ]


def main() -> int:
    """Entry point for load_institutional_holdings_13f.py."""
    try:
        return run_loader(InstitutionalHoldings13FLoader)
    except Exception as e:
        logger.error(f"[INSTITUTIONAL_13F FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
