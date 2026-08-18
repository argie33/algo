"""Regression test: `_get_data_status`'s data_loader_status enrichment
(lambda/api/routes/algo_handlers/market.py) must not trust a stale-but-present
data_loader_status row for tables no loader ever writes to.

Live-confirmed 2026-08-18: circuit_breaker_status and algo_trades are written directly by
orchestrator phases (Phase 9, Phase 6-8), not by any loader, but both had legacy
data_loader_status rows (from a one-time seed / historical standalone script run) frozen at
last_updated=2026-08-17 00:00:00. The dashboard reported circuit_breaker_status as "30.1h
stale" and flagged it in critical_stale (it's the Phase 2 trading-halt gate table) while the
real table had a row from 7 minutes earlier. The enrichment loop's `needs_refresh` check only
fired on NULL row_count/last_updated, so a stale-but-non-NULL legacy row passed through
uncorrected forever - refreshing never happened because there was nothing "missing" to
trigger it. Fixed by always re-querying the live table for a known set of orchestrator-owned
table names, regardless of whether data_loader_status looks complete.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))

from routes.algo_handlers.market import (
    ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS,
    _row_needs_live_refresh,
)


def test_stale_but_complete_circuit_breaker_row_still_forces_refresh():
    """The core bug: a non-NULL, seemingly-complete row must still be refreshed for a
    table data_loader_status doesn't actually track updates for."""
    row = {"table_name": "circuit_breaker_status", "row_count": 28, "last_updated": "2026-08-17T00:00:00"}

    assert _row_needs_live_refresh(row) is True


def test_stale_but_complete_algo_trades_row_still_forces_refresh():
    row = {"table_name": "algo_trades", "row_count": 68, "last_updated": "2026-08-17T00:00:00"}

    assert _row_needs_live_refresh(row) is True


def test_null_last_updated_still_forces_refresh_for_unrelated_table():
    """Preserve the original NULL-triggered refresh behavior for tables outside the
    orchestrator-owned set."""
    row = {"table_name": "some_regular_loader_table", "row_count": None, "last_updated": None}

    assert _row_needs_live_refresh(row) is True


def test_complete_row_for_a_real_loader_tracked_table_does_not_force_refresh():
    """A table NOT in ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS, with complete data_loader_status
    values, must not be forced through the extra live-refresh query - that would be needless
    for tables where data_loader_status genuinely is kept in sync by their own loader."""
    row = {"table_name": "price_daily", "row_count": 4959, "last_updated": "2026-08-18T05:00:00"}

    assert _row_needs_live_refresh(row) is False


def test_circuit_breaker_status_uses_updated_at_not_date_only_check_date():
    """check_date is a DATE column (midnight-only) - using it as the refresh timestamp
    column would cap precision at 24h even after the staleness bug above is fixed.
    updated_at is a real timestamp column on circuit_breaker_status."""
    assert ORCHESTRATOR_OWNED_TABLE_TS_COLUMNS["circuit_breaker_status"] == "updated_at"
