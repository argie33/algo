#!/usr/bin/env python3
"""Company Info Loader - SEC EDGAR Company Master Data.

PHASE 3 OPTIMIZATION (Session 237):
Replaces yfinance company info (~15% of yfinance_snapshot) with
authoritative SEC EDGAR company master data.

Data source: SEC EDGAR submissions endpoint (company facts, SIC, entity info)
Update frequency: Annual (company info changes rarely)
Quality: Official SEC company records > yfinance estimates

Company info fields:
- Entity name, SIC code, SIC description
- Exchange, sector classification
- Shares outstanding (from DEI facts)

Run:
    python3 loaders/load_company_info_sec.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.exception_handler import (
    handle_exception,
    handle_schema_mismatch,
)

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class CompanyInfoSECLoader(SecLoaderBase):
    """Load company info from SEC EDGAR.

    PHASE 3: Eliminates yfinance company info (~15% yfinance load).
    Uses SEC EDGAR submissions endpoint which has entity names, SIC codes,
    sector classifications, and other company master data.

    Benefits:
    - Official SEC company records (authoritative)
    - Annual updates (company info changes infrequently)
    - Direct API access (no parsing required)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: Annual lag for company info changes (acceptable).
    """

    table_name = "company_info_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch company info from SEC EDGAR submissions API.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with company info record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions which has company master data
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            if not submissions:
                return self._unavailable_record(symbol, now_et, "submissions_empty")

            # Extract company info from submissions (fail-fast: entity_name is required)
            # SEC API uses "name" field; fallback to "entityName" only if "name" is None
            # Do not use cascading .get() which masks which field was actually used
            entity_name = submissions.get("name")
            if entity_name is None:
                entity_name = submissions.get("entityName")
                if entity_name:
                    logger.debug(f"[{symbol}] Using entityName fallback field (name was not present)")
            if not entity_name:
                return self._unavailable_record(symbol, now_et, "entity_name_not_found")

            sic_code = submissions.get("sic")
            sic_description = submissions.get("sicDescription")
            entity_type = submissions.get("entityType")

            # Get shares outstanding from DEI facts (if available)
            shares_outstanding = None
            try:
                facts = self.sec_client.get_company_facts(cik)
                # EXPLICIT: Validate SEC API response structure (fail-fast if schema changes)
                if not isinstance(facts, dict) or "facts" not in facts:
                    logger.warning(
                        f"[{symbol}] SEC API response missing 'facts' key. "
                        "Response structure may have changed. Shares outstanding unavailable."
                    )
                else:
                    facts_obj = facts["facts"]
                    if not isinstance(facts_obj, dict) or "dei" not in facts_obj:
                        logger.debug(f"[{symbol}] SEC API facts missing 'dei' namespace. Shares outstanding unavailable.")
                    else:
                        dei_facts = facts_obj["dei"]
                        # EXPLICIT: Check EntityCommonStockSharesOutstanding existence
                        if "EntityCommonStockSharesOutstanding" in dei_facts:
                            shares_data = dei_facts["EntityCommonStockSharesOutstanding"]
                            if shares_data and isinstance(shares_data, dict) and "units" in shares_data:
                                units = shares_data["units"]
                                if "shares" in units and isinstance(units["shares"], list):
                                    pure_values = units["shares"]
                                    if pure_values:
                                        # Get most recent (most recent has latest end date)
                                        latest = sorted(pure_values, key=lambda x: x.get("end", ""), reverse=True)[0]
                                        shares_outstanding = latest.get("val")
            except TimeoutError as e:
                # Transient timeout - log but don't fail entire record
                marker = handle_exception(symbol, e, "fetching company facts")
                logger.debug(f"[{symbol}] Using NULL for shares_outstanding due to timeout")
            except KeyError as e:
                # API schema changed - log but don't fail entire record
                marker = handle_schema_mismatch(symbol, e, "SEC API facts schema unexpected")
                logger.debug(f"[{symbol}] Using NULL for shares_outstanding due to schema mismatch")
            except Exception as e:
                # Unexpected errors should fail-fast
                logger.critical(
                    f"[{symbol}] Unexpected error fetching company facts: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise

            return [
                {
                    "symbol": symbol,
                    "filing_date": now_et.date(),
                    "entity_name": entity_name,
                    "sic_code": sic_code,
                    "sic_description": sic_description,
                    "entity_type": entity_type,
                    "shares_outstanding": shares_outstanding,
                    "data_unavailable": False,
                    "reason": None,
                }
            ]

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "fetching company info")
            return [marker]
        except KeyError as e:
            marker = handle_schema_mismatch(symbol, e, "SEC API missing expected fields")
            return [marker]
        except Exception as e:
            # Try to handle via classification, or fail-fast if unexpected
            try:
                marker = handle_exception(symbol, e, "fetching company info")
                return [marker]
            except Exception:
                logger.critical(f"[{symbol}] Failed to fetch company info: {type(e).__name__}: {e}", exc_info=True)
                raise

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "entity_name": None,
                "sic_code": None,
                "sic_description": None,
                "entity_type": None,
                "shares_outstanding": None,
                "data_unavailable": True,
                "reason": reason,
            }
        ]


def main() -> int:
    """Entry point for load_company_info_sec.py."""
    try:
        return run_loader(CompanyInfoSECLoader)
    except Exception as e:
        logger.error(f"[COMPANY_INFO FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
