"""Regression test for the 2026-09-02 fix (goal: "get all the data we need" full-coverage
audit): dividends_paid's existing same-year "unavailable row" rescue (2026-08-18 fix) only
recovers a value trapped behind acf.data_unavailable=TRUE - it does nothing when the anchor
fiscal year's dividends_paid was genuinely never extracted at all.

Live-confirmed BLK/CCL/CMS (all real, current dividend payers per dividend_data) have real
net_income/stockholders_equity for their anchor fiscal year but dividends_paid itself is NULL
that year, so payout_ratio_reason/sustainable_growth_rate_unavailable_reason both fell to
"missing_sec_data" even though the company obviously has a real, ongoing dividend policy and a
perfectly good one-year-old dividends_paid figure was already being fetched into quality_row
(as prior_year_dividends_paid, previously computed but unused by either field).

Fixed by falling back to prior_year_dividends_paid when the current year's value is missing -
a genuine non-payer has no dividends_paid in EITHER year, so this only ever substitutes a
real, one-year-old figure for a confirmed-recent payer's current-year extraction gap, never
fabricates a dividend for a symbol with no history (see test_genuine_non_payer_unaffected
below).
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=1000.0,
    net_income=100.0,
    dividends_paid=None,
    prior_year_dividends_paid=None,
):
    """35-element quality_row (index 34 = prior_year_dividends_paid, appended 2026-09-02)."""
    row = [None] * 35
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[15] = dividends_paid
    row[34] = prior_year_dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor - _compute_quality_metrics fires several unrelated fallback-year lookups
    that must all resolve to "no better data found" so only the field under test matters. No
    dividend_data lookup should ever fire once the prior-year fallback already resolved
    dividends_paid to a non-None value - see test_no_new_db_call_when_prior_year_available."""

    def __init__(self):
        self.queries: list[str] = []

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class TestDividendsPaidPriorYearFallback:
    def test_real_payer_missing_current_year_recovers_via_prior_year(self):
        loader = _make_loader()
        cur = _RoutingCursor()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "BLK",
                _quality_row(
                    stockholders_equity=55_888_000_000.0,
                    net_income=5_553_000_000.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=2_500_000_000.0,
                ),
            )

        assert metrics["payout_ratio"] is not None
        assert metrics.get("payout_ratio_unavailable_reason") is None
        assert metrics["sustainable_growth_rate"] is not None
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None

    def test_no_new_db_call_when_prior_year_available(self):
        # The prior-year fallback must be a pure in-memory substitution - no dividend_data
        # lookup fires once dividends_paid_with_prior_year_fallback is already non-None,
        # preserving the exact query-call sequence every other existing test relies on.
        loader = _make_loader()
        cur = _RoutingCursor()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            loader._compute_quality_metrics(
                "BLK",
                _quality_row(
                    stockholders_equity=55_888_000_000.0,
                    net_income=5_553_000_000.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=2_500_000_000.0,
                ),
            )

        assert not any("dividend_data" in q for q in cur.queries)

    def test_genuine_non_payer_unaffected(self):
        # Neither year has a dividends_paid figure - must still go through the existing
        # has_real_dividend_history detour and end up as a full-retention non-payer, not be
        # accidentally treated as having a fallback value.
        loader = _make_loader()
        cur = _RoutingCursor()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "NOPAY",
                _quality_row(
                    stockholders_equity=1000.0,
                    net_income=100.0,
                    dividends_paid=None,
                    prior_year_dividends_paid=None,
                ),
            )

        assert metrics["sustainable_growth_rate"] == 10.0

    def test_explicit_current_year_value_never_overwritten_by_prior_year(self):
        # Control: a real current-year dividends_paid must keep winning over the prior-year
        # fallback - this only ever fills a genuine gap, never overrides real data.
        loader = _make_loader()
        cur = _RoutingCursor()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "PAYER",
                _quality_row(
                    stockholders_equity=1000.0,
                    net_income=100.0,
                    dividends_paid=20.0,
                    prior_year_dividends_paid=999_999.0,
                ),
            )

        # retention_ratio = 1 - 20/100 = 0.8 -> SGR = 10% * 0.8 * 100 = 8.0 (uses the real
        # current-year 20.0, not the prior-year 999,999.0).
        assert metrics["sustainable_growth_rate"] == 8.0

    def test_old_34_column_fixture_unaffected(self):
        # A pre-existing 34-element fixture (no index 34 at all) must not raise IndexError -
        # the len() guard in the loader means this reads as "no prior-year data available",
        # identical to the pre-fix behavior.
        loader = _make_loader()
        cur = _RoutingCursor()
        row = [None] * 34
        row[0] = 1000.0
        row[3] = 100.0
        row[6] = 500.0
        row[7] = 100.0
        row[15] = None
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics("OLDFIXTURE", row)

        assert metrics["sustainable_growth_rate"] == 10.0
