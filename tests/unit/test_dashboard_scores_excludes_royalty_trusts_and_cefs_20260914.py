"""Regression test: /api/algo/scores excludes royalty trusts and closed-end funds via the
shared `investable_universe_conditions()` helper.

Found 2026-09-14 (`/goal` session, adversarial leaderboard audit - "poke holes, find the real
stench"): this endpoint's own investability filter (added 2026-09-07, see
test_dashboard_scores_tradability_floor_20260907.py) only checked market cap/liquidity/
`etf_symbols` - it never adopted `algo/signals/investable_universe.py`'s shared
`investable_universe_conditions()` helper (extracted 2026-09-13 for exactly this class of
drift, and already used by `lambda/api/routes/scores_handlers/stock_scores.py` and
`loaders/load_sector_industry_daily.py`). Live-verified: oil/gas royalty trusts (PBT, TPL, SBR)
ranked #2/#4/#6 of the entire quality_score leaderboard - their near-zero invested-capital
balance sheets mechanically produce ROE/ROCE/asset-turnover ratios in the 100-200%+ range,
not genuine business quality. Closed-end funds (BlackRock/Invesco/Gabelli trusts, `sector`
'Other'/`industry` 'Unknown') also passed through with meaningless "revenue"/"net_income"
figures mapped from investment-company financial statement shapes.

Fixed by joining `stock_symbols` and using `investable_universe_conditions()`, which already
excludes SIC 6792/6770/6189 (oil royalty traders/blank-check SPACs/asset-backed securities)
and non-10-K-filing closed-end funds (`has_annual_report_filing = FALSE`) - the same filter
already relied on by the separate `/api/scores` endpoint and sector/industry rankings.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))


def _mock_cursor():
    cursor = Mock()

    def fake_fetchall():
        sql = cursor.execute.call_args.args[0]
        if "FROM algo_config" in sql:
            return [("min_market_cap_millions", "300.0"), ("min_adv_dollars", "500000")]
        return []

    cursor.fetchall.side_effect = fake_fetchall
    cursor.fetchone.side_effect = lambda: None
    return cursor


class TestDashboardScoresExcludesRoyaltyTrustsAndCefs:
    def test_query_joins_stock_symbols_and_uses_shared_investable_universe_helper(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        main_query = next(sql for sql in executed_queries if "filtered_scores" in sql)
        assert "JOIN stock_symbols sy ON sy.symbol = s.symbol" in main_query
        # investable_universe_conditions() output - the SIC-based royalty-trust/SPAC/CEF
        # exclusions - must actually be spliced into the executed SQL, not just imported.
        assert "company_info_sec" in main_query
        assert "6792" in main_query, "SIC 6792 (Oil Royalty Traders) exclusion must be present"
        assert "has_annual_report_filing" in main_query
