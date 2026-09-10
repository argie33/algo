"""Regression test: the algo_trades INSERT in executor_entry_handler.py must persist
rejection_reason.

rejection_reason has a real migrated column (migration 029, "Add rejection_reason field
to algo_trades to capture Alpaca API errors") and request.rejection_reason is already
populated with Alpaca's actual rejection error earlier in this same file - but the
INSERT/ON CONFLICT UPDATE statement never referenced it in either the column list or the
params tuple, so the column was NULL for every row regardless of whether the order was
actually rejected. Same bug shape as two previously-fixed instances
(position_size_pct, alpaca_order_id) documented in this file's own comments.

Source inspection rather than a full mocked INSERT call: the surrounding function has a
large dependency graph that would need extensive mocking to exercise end-to-end here.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "trading" / "executor_entry_handler.py").read_text(encoding="utf-8")


def _trade_insert_statement() -> str:
    start = SOURCE.index("INSERT INTO algo_trades (")
    end = SOURCE.index("logger.info(", start)
    return SOURCE[start:end]


class TestRejectionReasonPersisted:
    def test_column_list_includes_rejection_reason(self):
        stmt = _trade_insert_statement()
        assert "rejection_reason" in stmt.split("VALUES")[0], (
            "algo_trades INSERT column list must include rejection_reason, or Alpaca's "
            "actual rejection error is never persisted."
        )

    def test_on_conflict_update_includes_rejection_reason(self):
        stmt = _trade_insert_statement()
        on_conflict = stmt[stmt.index("ON CONFLICT") :]
        assert "rejection_reason = EXCLUDED.rejection_reason" in on_conflict, (
            "ON CONFLICT DO UPDATE must also refresh rejection_reason, matching "
            "position_size_pct/alpaca_order_id's own treatment - a retry that gets a "
            "different rejection reason should stay in sync."
        )

    def test_params_tuple_passes_request_rejection_reason(self):
        stmt = _trade_insert_statement()
        params = stmt[stmt.index('""",') :]
        assert "request.rejection_reason" in params, (
            "the params tuple must pass request.rejection_reason - it's already populated "
            "earlier in this file, but was never threaded into this INSERT."
        )
