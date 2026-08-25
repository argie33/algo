"""Regression test for the 2026-08-25 fix (goal session, financial-review audit):
algo/risk/var.py's concentration_report() already documents "Concentration > 30% in top 5
holdings -> WARNING" as this system's own institutional convention, but it only ever fired as
a Phase 9 (end-of-cycle) REPORT - nothing previously stopped Phase 8 from opening the entry
that pushes the book over that exact threshold in the first place. A portfolio can also
satisfy every PER-POSITION cap (max_position_size_pct) while still breaching this AGGREGATE
one (e.g. five positions each just under an 8% per-position cap already sum past 30%).

PreTradeChecks._check_top5_concentration() (algo/trading/pretrade_checks.py) now blocks a new
entry that would push the top-5-holdings share of portfolio value above
max_top5_concentration_pct (default 30%, reusing var.py's own convention).
"""

from decimal import Decimal

from algo.trading.pretrade_checks import PreTradeChecks


def _config(**overrides):
    base = {"max_top5_concentration_pct": 30.0}
    base.update(overrides)
    return base


class _FakeCursor:
    def __init__(self, position_rows):
        self._position_rows = position_rows

    def execute(self, query, params=None):
        assert "FROM algo_positions" in query

    def fetchall(self):
        return self._position_rows


class TestTop5ConcentrationCheck:
    def test_no_open_positions_candidate_alone_under_cap_passes(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(position_rows=[])
        # $10k candidate on a $100k portfolio = 10%, well under 30%.
        ok, reason = checks._check_top5_concentration("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_five_positions_each_under_per_position_cap_still_breach_aggregate(self):
        checks = PreTradeChecks(config=_config(max_top5_concentration_pct=30.0))
        # 4 existing positions at $7,500 each (7.5% of $100k, under an 8% per-position cap)
        # plus this $7,500 candidate = 5 * 7.5% = 37.5% > 30% cap.
        cur = _FakeCursor(position_rows=[(100, 75.0), (100, 75.0), (100, 75.0), (100, 75.0)])
        ok, reason = checks._check_top5_concentration("NEWSYM", Decimal("7500"), Decimal("100000"), cur)
        assert ok is False
        assert reason is not None
        assert "30.0" in reason

    def test_more_than_five_positions_only_top_5_counted(self):
        checks = PreTradeChecks(config=_config(max_top5_concentration_pct=30.0))
        # 6 existing positions at $1,000 each (1% each) - top 5 of those + candidate
        # ($1,000) = 6 * 1% = 6%, well under 30%. The 6th (smallest) position must NOT
        # be double-counted or otherwise distort the top-5 sum.
        cur = _FakeCursor(position_rows=[(10, 100.0)] * 6)
        ok, reason = checks._check_top5_concentration("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_zero_portfolio_value_fails_open(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(position_rows=[])
        ok, reason = checks._check_top5_concentration("NEWSYM", Decimal("1000"), Decimal("0"), cur)
        assert ok is True
        assert reason is None

    def test_missing_config_key_raises(self):
        checks = PreTradeChecks(config={})
        cur = _FakeCursor(position_rows=[])
        try:
            checks._check_top5_concentration("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
            raise AssertionError("expected KeyError for missing max_top5_concentration_pct config")
        except KeyError:
            pass
