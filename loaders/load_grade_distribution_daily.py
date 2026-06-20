#!/usr/bin/env python3
"""Grade Distribution Daily Loader - Pre-compute universe grade breakdown.

HIGH-SEVERITY ISSUE: Grade Distribution not pre-calculated.

Calculates the distribution of swing_trader_scores grades (A/B/C/D) daily,
enabling dashboard to display grade breakdown without scanning entire table.

Grade thresholds:
- A: score >= 80
- B: score >= 60 and < 80
- C: score >= 40 and < 60
- D: score < 40

Runs after swing_trader_scores is loaded (end of day pipeline).
"""

import logging
import sys
from datetime import date, datetime
from typing import Any
from typing import List, Optional

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)
ET = EASTERN_TZ


class GradeDistributionDailyLoader(OptimalLoader):
    """Compute grade distribution from swing_trader_scores."""

    table_name = "grade_distribution_daily"
    primary_key = ("report_date",)
    watermark_field = "report_date"

    # Allow multiple updates per day
    allow_multiple_updates_per_day = True

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Compute grade distribution from latest swing_trader_scores.

        Counts stocks in each grade bucket:
        - num_grade_a: count where score >= 80
        - num_grade_b: count where 60 <= score < 80
        - num_grade_c: count where 40 <= score < 60
        - num_grade_d: count where score < 40
        - total_graded: total stocks with grades
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext("read") as cur:
                # Get latest swing_trader_scores date
                cur.execute("""
                    SELECT MAX(date) as latest_date FROM swing_trader_scores
                """)
                latest_row = cur.fetchone() or {}
                latest_date = latest_row.get("latest_date")

                if not latest_date:
                    logger.warning(
                        f"No swing_trader_scores available for {report_date}"
                    )
                    return None

                # Compute grade distribution
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE score >= 80) as num_grade_a,
                        COUNT(*) FILTER (WHERE score >= 60 AND score < 80) as num_grade_b,
                        COUNT(*) FILTER (WHERE score >= 40 AND score < 60) as num_grade_c,
                        COUNT(*) FILTER (WHERE score < 40) as num_grade_d,
                        COUNT(*) as total_graded
                    FROM swing_trader_scores
                    WHERE date = %s
                """,
                    (latest_date,),
                )

                stats: dict[str, Any] = cur.fetchone() or {}

                result = {
                    "report_date": report_date,
                    "score_date": latest_date,  # Date of swing_trader_scores used
                    "num_grade_a": (
                        int(stats.get("num_grade_a"))
                        if stats.get("num_grade_a") is not None
                        else None
                    ),
                    "num_grade_b": (
                        int(stats.get("num_grade_b"))
                        if stats.get("num_grade_b") is not None
                        else None
                    ),
                    "num_grade_c": (
                        int(stats.get("num_grade_c"))
                        if stats.get("num_grade_c") is not None
                        else None
                    ),
                    "num_grade_d": (
                        int(stats.get("num_grade_d"))
                        if stats.get("num_grade_d") is not None
                        else None
                    ),
                    "total_graded": (
                        int(stats.get("total_graded"))
                        if stats.get("total_graded") is not None
                        else None
                    ),
                    "updated_at": datetime.now(ET),
                }

                logger.info(
                    f"Grade distribution: A={result['num_grade_a']} B={result['num_grade_b']} "
                    f"C={result['num_grade_c']} D={result['num_grade_d']} (total={result['total_graded']})"
                )

                return [result] if result else None

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def main():
    try:
        loader = GradeDistributionDailyLoader()
        result = loader.load_global()

        if result > 0:
            logger.info(f"SUCCESS: {result} grade distribution records computed")
            return 0
        else:
            logger.error("FAILED: No grade distribution computed (insufficient data)")
            return 1
    except Exception as e:
        logger.error(f"Grade distribution daily load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
