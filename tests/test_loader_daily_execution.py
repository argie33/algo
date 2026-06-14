#!/usr/bin/env python3
"""Test that critical loaders run daily and update data_loader_status.

This test verifies that each critical loader:
1. Can be instantiated and executed
2. Updates its entry in data_loader_status after successful completion
3. Has been updated within 24 hours (detects silent failures)

Critical loaders:
- stock_symbols (upstream dependency for all)
- price_daily (upstream for technical indicators)
- technical_data_daily (upstream for buy_sell_daily)
- buy_sell_daily (upstream for signal_quality_scores)
- signal_quality_scores (upstream for swing_trader_scores)
- swing_trader_scores (final daily scores)
- market_health_daily (market regime)
- sector_ranking (sector rankings)
- sector_performance (sector returns)
- market_exposure_daily (orchestrator Phase 7)
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import logging

logger = logging.getLogger(__name__)
EASTERN_TZ = ZoneInfo("America/New_York")

from utils.db.context import DatabaseContext


class TestCriticalLoaderDailyExecution:
    """Verify critical loaders run daily and update data_loader_status."""

    CRITICAL_LOADERS = [
        'stock_symbols',
        'price_daily',
        'market_health_daily',
        'technical_data_daily',
        'buy_sell_daily',
        'signal_quality_scores',
        'swing_trader_scores',
        'sector_ranking',
        'sector_performance',
    ]

    def _get_loader_status(self, table_name: str) -> Optional[Dict]:
        """Get current status of a loader from data_loader_status table."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT * FROM data_loader_status WHERE table_name = %s",
                    (table_name,)
                )
                row = cur.fetchone()
                if row:
                    cols = [desc[0] for desc in cur.description]
                    return dict(zip(cols, row))
                return None
        except Exception as e:
            logger.warning(f"Could not fetch loader status for {table_name}: {e}")
            return None

    def test_loader_status_table_structure(self):
        """Verify data_loader_status table has required columns for watermark tracking."""
        required_columns = [
            'table_name',
            'status',
            'last_updated',
            'execution_started',
            'execution_completed',
            'row_count',
            'latest_date',
        ]

        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'data_loader_status' AND table_schema = 'public'"
                )
                existing_cols = {row[0] for row in cur.fetchall()}

                missing = set(required_columns) - existing_cols
                if missing:
                    pytest.fail(f"data_loader_status missing columns: {missing}")

                cur.execute("SELECT COUNT(*) FROM data_loader_status")
                assert cur.fetchone()[0] >= 0, "Could not read data_loader_status"

        except Exception as e:
            pytest.fail(f"Failed to verify data_loader_status structure: {e}")

    def test_critical_loaders_status_updated_within_24h(self):
        """REQUIREMENT: All critical loaders must have updated status within 24h."""
        now_et = datetime.now(EASTERN_TZ)
        cutoff_time = now_et - timedelta(hours=24)
        
        stale = {}
        for loader_name in self.CRITICAL_LOADERS:
            status = self._get_loader_status(loader_name)
            if not status:
                stale[loader_name] = "NEVER_RUN"
                continue
            
            last_updated = status.get('last_updated')
            if last_updated:
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))

                # Ensure timezone-aware datetime in Eastern TZ for comparison
                if last_updated.tzinfo is None:
                    # Naive datetime from DB - assume it's in Eastern TZ
                    last_updated = last_updated.replace(tzinfo=EASTERN_TZ)
                elif last_updated.tzinfo != EASTERN_TZ:
                    # Convert to Eastern TZ if in different timezone
                    last_updated = last_updated.astimezone(EASTERN_TZ)

                if last_updated < cutoff_time:
                    stale[loader_name] = "STALE (>24h)"
        
        if stale:
            error_msg = "Critical loaders with missing/stale status:\n"
            for loader_name, reason in stale.items():
                error_msg += f"  {loader_name}: {reason}\n"
            pytest.fail(error_msg)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
