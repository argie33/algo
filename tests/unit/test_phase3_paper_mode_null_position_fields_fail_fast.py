"""Regression test for Phase 3's (paper mode) fail-fast behavior on corrupted position data.

GOVERNANCE requires Phase 3 to fail-fast rather than silently skip a position when
algo_positions has NULL quantity/avg_entry_price/stop_loss_price for an open position - see
phase3_position_monitor.py's own module docstring ("Gracefully skipping positions due to
missing data hides data quality issues and leaves positions unmonitored, which violates
fail-fast governance"). This exact code path (the paper-mode "_update_position_prices" inner
function) had no dynamic test coverage at all before this - only confirmed correct by reading
the source. This exercises the REAL run() function end-to-end against a synthetic corrupted
row via a mocked cursor (no real database writes), rather than a live DB injection, since
algo_positions holds real open positions in this shared dev environment.

Contract confirmed empirically (not assumed): the internal RuntimeError does NOT propagate
as an uncaught exception - run()'s outer try/except catches it and returns a PhaseResult with
status="error", halted=True, and the original message in .error, matching every other phase's
"return a PhaseResult, don't raise" convention.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase3_position_monitor import run as phase3_run


class _ScriptedCursor:
    """Cursor whose fetchall()/fetchone() responds based on the most recently executed
    query's SQL text, so a single mock object can stand in for the whole multi-query
    sequence phase3's paper-mode price-update path issues."""

    def __init__(self, position_row):
        self._position_row = position_row
        self._last_sql = ""

    def execute(self, sql, params=None):
        self._last_sql = sql

    def fetchall(self):
        if "FROM algo_positions" in self._last_sql:
            return [self._position_row]
        if "FROM price_daily" in self._last_sql or "latest_prices" in self._last_sql:
            # One matching, valid price row for the position's symbol
            return [("TESTSYM", 123.45, False, None)]
        return []

    def fetchone(self):
        if "CURRENT_DATE" in self._last_sql:
            return (date(2026, 8, 10),)
        return None


def _make_db_context(position_row):
    cur = _ScriptedCursor(position_row)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _run_phase3_paper_mode(position_row):
    config = {"execution_mode": "paper"}
    db_ctx = _make_db_context(position_row)

    with (
        patch("utils.db.DatabaseContext", return_value=db_ctx),
        patch("utils.db.connection_pool.get_pool_health", return_value={"available_conns": 5, "size": 10}),
    ):
        return phase3_run(
            config=config,
            run_date=date(2026, 8, 10),
            dry_run=True,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=MagicMock(),
        )


class TestPhase3PaperModeFailsFastOnCorruptedPositionData:
    def test_null_quantity_halts_with_clear_error_not_silently_skipped(self):
        row = (1, "TESTSYM", None, 100.0, date(2026, 1, 1), 90.0, 95.0)
        result = _run_phase3_paper_mode(row)

        assert result.halted is True, "corrupted position data (NULL quantity) must halt, not silently continue"
        assert result.status == "error"
        assert "NULL quantity" in result.error

    def test_null_avg_entry_price_halts_with_clear_error_not_silently_skipped(self):
        row = (1, "TESTSYM", 10.0, 100.0, date(2026, 1, 1), 90.0, None)
        result = _run_phase3_paper_mode(row)

        assert result.halted is True, "corrupted position data (NULL avg_entry_price) must halt, not silently continue"
        assert result.status == "error"
        assert "avg_entry_price is NULL" in result.error

    def test_null_stop_loss_halts_with_clear_error_not_silently_skipped(self):
        row = (1, "TESTSYM", 10.0, 100.0, date(2026, 1, 1), None, 95.0)
        result = _run_phase3_paper_mode(row)

        assert result.halted is True, "corrupted position data (NULL stop_loss) must halt, not silently continue"
        assert result.status == "error"
        assert "stop_loss" in result.error.lower()

    def test_missing_price_data_halts_with_clear_error_not_silently_skipped(self):
        """Companion 'market data unavailable' scenario: a position whose symbol has no
        current price at all (not even a data_unavailable-flagged row) must also halt fast,
        not proceed with a stale/missing price."""

        class _NoPriceCursor(_ScriptedCursor):
            def fetchall(self):
                if "FROM algo_positions" in self._last_sql:
                    return [self._position_row]
                if "FROM price_daily" in self._last_sql or "latest_prices" in self._last_sql:
                    return []  # No price row at all for this symbol
                return []

        row = (1, "TESTSYM", 10.0, 100.0, date(2026, 1, 1), 90.0, 95.0)
        cur = _NoPriceCursor(row)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=cur)
        ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch("utils.db.DatabaseContext", return_value=ctx),
            patch("utils.db.connection_pool.get_pool_health", return_value={"available_conns": 5, "size": 10}),
        ):
            result = phase3_run(
                config={"execution_mode": "paper"},
                run_date=date(2026, 8, 10),
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "a position with zero price rows must halt, not proceed unmonitored"
        assert result.status == "error"
        assert "price" in result.error.lower()
