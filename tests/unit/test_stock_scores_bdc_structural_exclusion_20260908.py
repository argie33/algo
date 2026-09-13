"""REVERSED 2026-09-13: /api/scores no longer hard-denylists known BDC symbols.

Originally (2026-09-08) this test asserted the opposite - that the bulk query hard-excluded
_KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS (MAIN, HTGC, GAIN, TSLX and siblings) because their
stock_scores row was permanently frozen (the loader that would refresh it deliberately skipped
them - see frozen_subpopulation_real_root_cause_and_live_gap_20260913 in memory). That loader
gap is now fixed (load_stock_scores.py/load_risk_metrics_daily.py opt out of the exclusion via
exclude_non_operating_from_symbols=False), live-verified 2026-09-13: these symbols now carry a
fresh same-day updated_at with real risk_score/momentum_score. The special-case symbol denylist
in stock_scores.py's where_clause is removed - the generic `data_unavailable = false` filter
(already present for every symbol, based on the loader's own completeness marking) now does the
same bulk-listing suppression on a non-special-cased basis, and single-symbol lookups for a BDC
work again instead of hard-blocking.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor():
    cursor = Mock()
    cursor.fetchone.return_value = [0]
    cursor.fetchall.return_value = []
    return cursor


class TestStockScoresBdcStructuralExclusion:
    def test_bulk_query_no_longer_denylists_known_bdc_symbols(self):
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("'MAIN'" in sql and "'HTGC'" in sql for sql in executed_queries)

    def test_bulk_query_still_filters_on_generic_data_unavailable_flag(self):
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("data_unavailable = false" in sql for sql in executed_queries)
