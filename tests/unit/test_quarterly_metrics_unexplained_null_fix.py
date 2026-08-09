"""Regression test for silently-unexplained NULLs in quarterly-derived quality/growth fields.

Live DB audit (2026-08-09) found consecutive_positive_quarters NULL with no
_unavailable_reason on 3,173/5,709 rows, eps_growth_stability on 1,838/5,709,
earnings_growth_4q_avg on 1,788/5,709, and quarterly_growth_momentum on 2,250/5,709 -
all despite >=4 quarters of history existing (the one case _compute_quarterly_metrics()
already covered with an "insufficient_quarterly_history" reason).

Two compounding bugs, both in loaders/load_value_quality_growth_metrics.py:

1. _compute_quarterly_metrics() only ever wrote these fields inside an `if <truthy>:`
   guard, with no `else` branch setting a reason. consecutive_positive_quarters=0 (a
   company with zero positive-net-income quarters in the trailing window - a real,
   common answer) was therefore dropped entirely instead of being recorded as 0. And
   whenever >=4 quarters existed but the specific quarter-over-quarter comparisons
   produced an empty growth-rate list (e.g. missing EPS/revenue in the underlying rows),
   earnings_growth_4q_avg/eps_growth_stability/quarterly_growth_momentum were left unset
   with no reason at all.

2. _insert_quality_metrics() hardcoded the quarterly_growth_momentum_unavailable_reason
   DB column to `None` unconditionally, with a comment claiming the field was "dead,
   no computation path" - false; _compute_quarterly_metrics() computes it. This
   discarded any reason bug (1) did manage to set, for quality_metrics specifically
   (growth_metrics's own insert was never affected - it already used row.get()).

Also covers _unavailable_marker(): the value_metrics branch was missing
ev_revenue/ev_revenue_unavailable_reason (608/5,709 unexplained-null rows live), and the
quality_metrics/growth_metrics branches were missing reasons for the ~16 _SHARED_TREND_FIELDS
columns entirely (each ~344-673/5,709 unexplained-null live), despite the function's own
docstring stating its purpose is to cover every *_unavailable_reason field.
"""

from loaders.load_value_quality_growth_metrics import (
    _SHARED_TREND_FIELDS,
    ValueQualityGrowthMetricsLoader,
)


class _FakeCursor:
    """Serves canned quarterly_income_statement rows; every other query (prior-year
    lookups, forward-EPS, etc.) gets an empty/None result so those callers take their
    own already-tested "no data" path instead of raising."""

    def __init__(self, quarters):
        self._quarters = quarters
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "quarterly_income_statement" in self._last_query:
            return self._quarters
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, quarters):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor(quarters)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quarters_all_net_losses():
    # (fiscal_year, fiscal_quarter, net_income, revenue, eps) x8, most-recent-first
    # (matches the loader's ORDER BY ... DESC), every quarter a net loss.
    return [
        (2026, 2, -5_000_000.0, 100_000_000.0, -0.10),
        (2026, 1, -4_000_000.0, 95_000_000.0, -0.08),
        (2025, 4, -6_000_000.0, 90_000_000.0, -0.12),
        (2025, 3, -3_000_000.0, 88_000_000.0, -0.06),
        (2025, 2, -2_000_000.0, 85_000_000.0, -0.04),
        (2025, 1, -1_000_000.0, 80_000_000.0, -0.02),
        (2024, 4, -1_500_000.0, 78_000_000.0, -0.03),
        (2024, 3, -1_200_000.0, 75_000_000.0, -0.025),
    ]


def _quarters_missing_eps_and_revenue():
    # >=4 quarters exist, but eps/revenue are None on every row - the growth-rate
    # lists end up empty even though this isn't the "<4 quarters" branch.
    return [
        (2026, 2, 1_000_000.0, None, None),
        (2026, 1, 1_000_000.0, None, None),
        (2025, 4, 1_000_000.0, None, None),
        (2025, 3, 1_000_000.0, None, None),
    ]


class TestConsecutivePositiveQuartersRecordsZero:
    def test_all_net_loss_quarters_records_zero_not_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch, _quarters_all_net_losses())

        metrics = loader._compute_quarterly_metrics("TESTCO")

        assert metrics.get("consecutive_positive_quarters") == 0
        assert "consecutive_positive_quarters" in metrics


class TestEmptyGrowthRateListsGetReasons:
    def test_missing_eps_and_revenue_sets_explicit_reasons(self, monkeypatch):
        loader = _make_loader(monkeypatch, _quarters_missing_eps_and_revenue())

        metrics = loader._compute_quarterly_metrics("TESTCO")

        assert metrics.get("earnings_growth_4q_avg") is None
        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") == "insufficient_eps_data"
        assert metrics.get("eps_growth_stability") is None
        assert metrics.get("eps_growth_stability_unavailable_reason") == "insufficient_eps_data"
        assert metrics.get("quarterly_growth_momentum") is None
        assert metrics.get("quarterly_growth_momentum_unavailable_reason") == "insufficient_revenue_data"

    def test_single_eps_growth_rate_gets_stability_reason_not_silent_none(self, monkeypatch):
        # Exactly 2 usable EPS values -> 1 growth rate: earnings_growth_4q_avg computes,
        # but stddev (needs >=2 rates) cannot - that gap must be explained too.
        quarters = [
            (2026, 2, 1_000_000.0, 100_000_000.0, 0.50),
            (2026, 1, 1_000_000.0, 95_000_000.0, 0.40),
            (2025, 4, 1_000_000.0, None, None),
            (2025, 3, 1_000_000.0, None, None),
        ]
        loader = _make_loader(monkeypatch, quarters)

        metrics = loader._compute_quarterly_metrics("TESTCO")

        assert metrics.get("earnings_growth_4q_avg") is not None
        assert metrics.get("eps_growth_stability") is None
        assert metrics.get("eps_growth_stability_unavailable_reason") == "insufficient_eps_growth_datapoints"


class TestUnavailableMarkerCoversAllReasonColumns:
    def _loader(self):
        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_value_metrics_marker_sets_ev_revenue_reason(self):
        marker = self._loader()._unavailable_marker("value_metrics", "TESTCO")

        assert marker["ev_revenue"] is None
        assert marker["ev_revenue_unavailable_reason"] == "missing_sec_data"

    def test_quality_metrics_marker_covers_shared_trend_fields(self):
        marker = self._loader()._unavailable_marker("quality_metrics", "TESTCO")

        for field in _SHARED_TREND_FIELDS:
            assert marker.get(field) is None
            assert marker.get(f"{field}_unavailable_reason") is not None, (
                f"quality_metrics unavailable marker left {field}_unavailable_reason unset"
            )

    def test_growth_metrics_marker_covers_shared_trend_fields(self):
        marker = self._loader()._unavailable_marker("growth_metrics", "TESTCO")

        for field in _SHARED_TREND_FIELDS:
            assert marker.get(field) is None
            assert marker.get(f"{field}_unavailable_reason") is not None, (
                f"growth_metrics unavailable marker left {field}_unavailable_reason unset"
            )


class TestDownstreamFallbackDoesNotClobberSpecificReason:
    """_compute_quality_metrics() merges _compute_quarterly_metrics()'s output, then later
    (originally unconditionally) fills a generic "insufficient_quarterly_data"/
    "no_analyst_estimates" reason for any of these fields still None. That later block must
    only fire when no specific reason was already set - otherwise it silently discards
    exactly the diagnosis _compute_quarterly_metrics() just computed.
    """

    # SELECT column order from _compute_quality_metrics's quality_row query (see the
    # "SELECT abs.stockholders_equity, ..." query this loader issues): 31 columns,
    # fiscal_year at index 8. Real revenue/net_income/etc keep the function past its
    # "all core metrics None -> _unavailable_marker" early return; everything else is None.
    _QUALITY_ROW = (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        400_000_000.0,  # 4 revenue
        60_000_000.0,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
    )

    def _run(self, monkeypatch, quarters):
        import loaders.load_value_quality_growth_metrics as mod

        cursor = _FakeCursor(quarters)
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        return loader._compute_quality_metrics("TESTCO", self._QUALITY_ROW, ev_metrics=None)

    def test_specific_eps_and_revenue_reasons_survive(self, monkeypatch):
        metrics = self._run(monkeypatch, _quarters_missing_eps_and_revenue())

        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") == "insufficient_eps_data"
        assert metrics.get("eps_growth_stability_unavailable_reason") == "insufficient_eps_data"
        assert metrics.get("quarterly_growth_momentum_unavailable_reason") == "insufficient_revenue_data"

    def test_generic_fallback_still_fires_when_truly_unset(self, monkeypatch):
        # <4 quarters: _compute_quarterly_metrics's own early return sets
        # "insufficient_quarterly_history" for these fields - also a specific reason, so the
        # generic "insufficient_quarterly_data" fallback must still stay out of the way here.
        metrics = self._run(monkeypatch, _quarters_missing_eps_and_revenue()[:2])

        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") == "insufficient_quarterly_history"


class TestInsertQualityMetricsDoesNotDiscardReason:
    def test_quarterly_growth_momentum_reason_passed_through_not_hardcoded_none(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        captured = {}

        class _CapturingCursor:
            def execute(self, query, params):
                captured["params"] = params

        row = {
            "symbol": "TESTCO",
            "roe": None,
            "operating_margin": None,
            "net_margin": None,
            "debt_to_equity": None,
            "data_unavailable": False,
            "updated_at": "2026-08-09",
            "quarterly_growth_momentum_unavailable_reason": "insufficient_revenue_data",
        }

        loader._insert_quality_metrics(_CapturingCursor(), row)

        assert "insufficient_revenue_data" in captured["params"], (
            "quarterly_growth_momentum_unavailable_reason was not passed through to the INSERT params"
        )
