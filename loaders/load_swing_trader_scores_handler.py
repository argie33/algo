#!/usr/bin/env python3
"""Vectorized swing scores loading handler extracted from VectorizedSwingScoresLoader.

Handles:
- Date range determination (intraday vs full mode)
- Phase-based data fetching (signal scores, technical data, trend data)
- Vectorized score computation
- Bulk insertion with error handling
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from utils.infrastructure.timezone import EASTERN_TZ


logger = logging.getLogger(__name__)


class VectorizedSwingScoresHandler:
    """Handles vectorized swing score computation and loading."""

    def __init__(self, loader: Any) -> None:
        """Initialize with reference to VectorizedSwingScoresLoader."""
        self.loader = loader

    def run(self, symbols: list, incremental_only: bool = False) -> dict:
        """Execute phased swing score loading with vectorized computation.

        Args:
            symbols: List of ticker symbols
            incremental_only: If True, only compute for today's data (fast intraday mode)

        Returns:
            Dict with {symbols_processed, rows_inserted, duration_sec}
        """
        import time

        start_time = time.time()

        # Phase 1: Determine date range based on mode
        start_date, end_date = self._phase_determine_date_range(incremental_only, symbols)

        try:
            # Phase 2: Fetch dependencies
            signal_scores, technical_data, trend_data = self._phase_fetch_dependencies(
                symbols, start_date, end_date
            )

            # Phase 3: Compute scores vectorized
            scores_df = self._phase_compute_scores(
                symbols, signal_scores, technical_data, trend_data
            )

            # Phase 4: Bulk insert results
            inserted = self._phase_bulk_insert(scores_df)

            # Phase 5: Finalize and return
            duration = time.time() - start_time
            logger.info(
                f"VectorizedSwingScoresLoader completed: {inserted} rows in {duration:.1f}s"
            )

            return {
                "symbols_processed": len(symbols),
                "rows_inserted": inserted,
                "duration_sec": round(duration, 2),
            }

        except Exception as e:
            logger.error(f"VectorizedSwingScoresLoader failed: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": 0,
                "error": str(e),
            }

    def _phase_determine_date_range(self, incremental_only: bool, symbols: list) -> tuple[date, date]:
        """Determine date range based on mode (intraday vs full).

        Returns: (start_date, end_date)
        """
        now_utc = datetime.now(ZoneInfo("UTC"))
        now_et = now_utc.astimezone(EASTERN_TZ)
        end_date = now_et.date()

        if incremental_only:
            start_date = end_date
            logger.info(
                f"[INTRADAY MODE] Computing swing scores for {len(symbols)} symbols, today only"
            )
        else:
            start_date = end_date - timedelta(days=30)
            logger.info(
                f"[FULL MODE] Computing swing scores for {len(symbols)} symbols, last 30 days"
            )

        return start_date, end_date

    def _phase_fetch_dependencies(
        self, symbols: list, start_date: date, end_date: date
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Fetch all required data for computation.

        Returns: (signal_scores, technical_data, trend_data)
        """
        # STEP 1: Fetch signal quality scores (critical)
        signal_scores = self.loader._fetch_signal_quality_scores(
            symbols, start_date, end_date
        )
        if signal_scores.empty:
            raise RuntimeError(
                "[SIGNAL QUALITY] No signal quality scores found. "
                "signal_quality_scores table may be empty or stale. "
                "Run load_signal_quality_scores.py first."
            )

        # STEP 2: Fetch technical data (critical)
        technical_data = self.loader._fetch_technical_data(symbols, start_date, end_date)
        if technical_data.empty:
            raise RuntimeError(
                "[TECHNICAL] No technical indicator data found. "
                "technical_data_daily table may be empty or stale. "
                "Run load_technical_data_daily_vectorized.py first."
            )

        # STEP 3: Fetch trend template data (critical)
        trend_data = self.loader._fetch_trend_template_data(symbols, start_date, end_date)
        if trend_data.empty:
            raise RuntimeError(
                "[TREND] No trend template data found. "
                "trend_template_data table may be empty or stale. "
                "Run load_trend_template_data.py first."
            )

        return signal_scores, technical_data, trend_data

    def _phase_compute_scores(
        self,
        symbols: list,
        signal_scores: pd.DataFrame,
        technical_data: pd.DataFrame,
        trend_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute scores for all symbols using vectorized operations.

        Returns: DataFrame with computed scores
        """
        # STEP 4: Compute scores for ALL symbols vectorized
        scores_df = self.loader._compute_all_scores_vectorized(
            symbols, signal_scores, technical_data, trend_data
        )

        if scores_df.empty:
            raise RuntimeError(
                "Score computation resulted in empty dataset. "
                "Check that technical and trend data have overlapping symbol/date ranges."
            )

        return scores_df

    def _phase_bulk_insert(self, scores_df: pd.DataFrame) -> int:
        """Bulk insert computed scores into database.

        Returns: Number of rows inserted
        """
        return self.loader._bulk_insert(scores_df)
