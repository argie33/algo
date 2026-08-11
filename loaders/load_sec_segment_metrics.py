#!/usr/bin/env python3
"""SEC-Derived Segment Metrics Loader - Revenue and Income by Business Segment.

Extracts business segment data from SEC 10-K/10-Q filings:
  - Segment Revenue: Total revenue by identified business segment
  - Segment Operating Income: Profit by segment
  - Segment Count: Number of reportable segments
  - Dominant Segment Revenue %: % revenue from largest segment
  - Segment Diversification: Herfindahl index of revenue concentration

Data Quality:
  - All metrics extracted from SEC-filed segment disclosure tables
  - Annual data from 10-K; optional quarterly from 10-Q
  - Explicit data_unavailable markers on extraction failures
  - Segment definitions follow FASB ASC 280 (Segment Reporting)

Run: python3 loaders/load_sec_segment_metrics.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.exception_handler import handle_exception
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _unavailable_marker(symbol: str, reason: str) -> dict[str, Any]:
    """Build a data_unavailable row for a symbol with no usable segment disclosure.

    Was previously called as self._unavailable_marker(...), a method that was never
    defined on this class or OptimalLoader (same bug already found and fixed in
    load_sec_cash_flow_metrics.py) - every symbol hitting either "no segment_row" or
    "unavailable or not has_data" raised AttributeError instead of getting a clean
    marker row. handle_exception() classifies AttributeError as "unexpected" and
    re-raises rather than returning a marker, so this wasn't silently swallowed - it
    failed the symbol outright, the same failure-rate-threshold risk documented in the
    cash_flow fix. Segment disclosure is genuinely sparse (most companies report a
    single segment), so this was likely hit for a large fraction of symbols.
    """
    return {
        "symbol": symbol,
        "segment_count": None,
        "largest_segment_revenue_pct": None,
        "revenue_concentration_hhi": None,
        "is_diversified": None,
        "data_unavailable": True,
        "reason": reason,
        "computed_at": date.today(),
    }


class SecSegmentMetricsLoader(OptimalLoader):
    """Extract segment metrics from SEC 10-K/10-Q filings.

    Provides business segment analysis for diversification scoring.
    Uses segment disclosure tables extracted during SEC financial statement processing.
    """

    table_name = "sec_segment_metrics"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Extract segment metrics for one symbol from SEC 10-K/10-Q.

        Returns:
            List with single metrics dict or data_unavailable marker
        """
        try:
            with DatabaseContext("read") as cur:
                # Query segment information table
                # This table is populated during financial statement processing
                # and contains parsed segment disclosures from 10-K Item 8 / 10-Q
                # NOTE: Removed data_unavailable = FALSE filter to prevent premature early exit
                # if upstream loader hasn't completed. Query all rows and check flags after fetching.
                cur.execute(
                    """
                    SELECT
                        segment_count,
                        largest_segment_revenue_pct,
                        revenue_concentration_hhi,
                        segment_data_available,
                        data_unavailable,
                        reason
                    FROM sec_segment_info
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                segment_row = cur.fetchone()

            # Check data availability
            if not segment_row:
                # No segment information available - mark unavailable
                return [_unavailable_marker(symbol, "no_segment_disclosure")]

            segment_count, largest_segment_pct, hhi, _has_data, unavailable, reason = segment_row

            # If upstream marked data unavailable with a legitimate reason, respect that
            # (e.g., "single_segment_only" is legitimate, but "data_not_yet_fetched" means retry)
            if unavailable and reason and any(x in reason.lower() for x in ["single_segment", "no_segment"]):
                return [_unavailable_marker(symbol, reason or "segment_data_unavailable")]

            # For other unavailable markers, try to proceed anyway (upstream may not be ready yet)

            # Parse metrics
            seg_count = int(segment_count) if segment_count else None
            largest_pct = safe_float(largest_segment_pct, f"{symbol}.largest_segment_revenue_pct")
            diversification_hhi = safe_float(hhi, f"{symbol}.revenue_concentration_hhi")

            # Validate minimum data
            all_missing = all([seg_count is None, largest_pct is None, diversification_hhi is None])

            return [
                {
                    "symbol": symbol,
                    "segment_count": seg_count,
                    "largest_segment_revenue_pct": largest_pct,
                    "revenue_concentration_hhi": diversification_hhi,
                    "is_diversified": seg_count >= 2 if seg_count else None,
                    "data_unavailable": all_missing,
                    "reason": "no_computable_segment_metrics" if all_missing else None,
                    "computed_at": date.today(),
                }
            ]

        except Exception as e:
            return [handle_exception(symbol, e, "sec_segment_metrics")]


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(SecSegmentMetricsLoader)
    except Exception as e:
        logger.error(f"[SEC_SEGMENT FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
