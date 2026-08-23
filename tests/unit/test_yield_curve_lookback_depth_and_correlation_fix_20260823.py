"""Regression test for the Yield Curve factor's history-depth fix, found 2026-08-23
(goal: exposure-model integrity review, industry-research pass).

_single_series_zscore_factor's default lookback was 800 rows (~3.2 years of daily data).
T10Y2Y's local economic_data history was only 274 rows (starting 2025-07-21, zero
recessions in-sample) because loaders/load_economic_data.py's regular run only maintains a
rolling 365-day window and this series never got an initial deep backfill; T10Y3M was
better but still only went back to 2015. Both were backfilled to their full real FRED
history (1990-2026, 9,166 rows, spans 2001/2008-09/2020) via
scripts/backfill_economic_data_history.py, and the default lookback raised to 10000 so the
z-score actually uses that depth instead of silently re-capping at ~800 rows even after the
backfill.

Also: the module's prior claim that T10Y2Y vs T10Y3M were "only -0.28 correlated" was
computed against T10Y2Y's short, unbackfilled history; re-checked against the real 26-year
sample the true correlation is 0.941 (see _yield_curve_factor's corrected docstring) - this
test doesn't re-verify that number (it's an empirical DB fact, not code logic) but confirms
the code-level fix that made a trustworthy check possible: the lookback default itself.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from algo.risk.market_exposure import MarketExposure


class TestSingleSeriesZscoreLookbackDepth:
    def test_default_lookback_requests_full_backfilled_depth_not_800(self):
        """The SQL LIMIT parameter actually sent to the DB must be the new deep default,
        not the old 800-row cap - a regression here would silently re-shrink the effective
        z-score window back to ~3.2 years even with a fully deep economic_data table.
        """
        cur = MagicMock()
        # 30 fake rows is enough to produce a valid z-score (>=15 needed); what matters is
        # the LIMIT value passed in the query params, not the row count returned.
        cur.fetchall.return_value = [(100.0 + i * 0.01,) for i in range(30)]
        me = MarketExposure()
        me._single_series_zscore_factor(date(2026, 8, 21), cur, "T10Y3M", higher_is_worse=False)

        executed_sql, params = cur.execute.call_args[0]
        assert "LIMIT %s" in executed_sql
        limit_param = params[-1]
        assert limit_param >= 9200, (
            f"lookback={limit_param} is too shallow to cover T10Y2Y/T10Y3M's real "
            f"backfilled history (9,166 rows, 1990-2026) - regressed back toward the old "
            f"800-row default that only covered ~3.2 years."
        )

    def test_inflation_expectations_query_also_uses_deep_limit(self):
        """_inflation_expectations_factor's own hardcoded SQL LIMIT (separate from
        _single_series_zscore_factor's default param) must also have been raised past the
        old 800 cap - T5YIE/T10YIE were backfilled to 5,914 rows (2003-2026).
        """
        cur = MagicMock()
        base = date(2026, 1, 1)
        cur.fetchall.return_value = [(base - timedelta(days=i), 2.0 + i * 0.001) for i in range(30)]
        me = MarketExposure()
        me._inflation_expectations_factor(date(2026, 8, 21), cur)

        executed_sql = cur.execute.call_args[0][0]
        import re

        match = re.search(r"LIMIT (\d+)", executed_sql)
        assert match is not None, "expected a literal LIMIT N in the inflation expectations query"
        assert int(match.group(1)) >= 5900, (
            f"inflation expectations query LIMIT={match.group(1)} is too shallow to cover "
            f"the real backfilled T5YIE/T10YIE history (5,914 rows, 2003-2026)."
        )
