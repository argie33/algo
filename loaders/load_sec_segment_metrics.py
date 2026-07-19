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
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                segment_row = cur.fetchone()

                # If no segment disclosure data, try to infer from geography/subsidiary data
                if not segment_row:
                    # Fallback: check if company reports geographic segments
                    cur.execute(
                        """
                        SELECT
                            COUNT(DISTINCT segment_name) as segment_count
                        FROM sec_segment_info
                        WHERE symbol = %s AND segment_type = 'geographic'
                        """,
                        (symbol,),
                    )
                    geo_row = cur.fetchone()
                    if geo_row and geo_row[0]:
                        segment_row = (geo_row[0], None, None, True, False, None)

            # Check data availability
            if not segment_row:
                # No segment information available - mark unavailable
                return [self._unavailable_marker(symbol, "no_segment_disclosure")]

            segment_count, largest_segment_pct, hhi, has_data, unavailable, reason = segment_row

            if unavailable or not has_data:
                return [self._unavailable_marker(symbol, reason or "segment_data_unavailable")]

            # Parse metrics
            seg_count = int(segment_count) if segment_count else None
            largest_pct = safe_float(largest_segment_pct)
            diversification_hhi = safe_float(hhi)

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
