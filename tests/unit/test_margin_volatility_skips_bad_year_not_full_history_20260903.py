"""Regression test (2026-09-03, goal: "Missing SEC/XBRL data" reduction): before this fix,
`_compute_margin_volatility` only ever looked at income_rows[:3] (the 3 most recent fiscal
years) - a single missing/implausible year anywhere in that specific window discarded the
whole computation even when a 4th+ older, real, usable year was sitting in the same
already-fetched (LIMIT 30) history. Live-confirmed 439 universe margin_volatility rows landed
on "implausible_ratio" this way. The fix scans past a bad year to find 3 usable years anywhere
in the fetched history, same "search past the immediate anchor" convention already used
elsewhere in this file (interest_coverage's multi-year fallback, dividends_paid's prior-year
rescue).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _income_row(fiscal_year, revenue, net_income):
    return (fiscal_year, revenue, None, net_income, None, None, None)


class TestMarginVolatilitySkipsBadYear:
    def test_implausible_middle_year_skipped_using_older_real_year(self):
        loader = _make_loader()
        # 2024 is a TKLF-style near-zero-revenue garbage year; a real, usable 2022 year is
        # available right behind it in the same already-fetched history.
        rows = [
            _income_row(2025, 100_000_000.0, 12_000_000.0),
            _income_row(2024, 1.0, 10_000_000.0),
            _income_row(2023, 90_000_000.0, 9_000_000.0),
            _income_row(2022, 85_000_000.0, 8_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is not None
        assert reason is None

    def test_missing_middle_year_skipped_using_older_real_year(self):
        loader = _make_loader()
        rows = [
            _income_row(2025, 100_000_000.0, 12_000_000.0),
            _income_row(2024, None, None),
            _income_row(2023, 90_000_000.0, 9_000_000.0),
            _income_row(2022, 85_000_000.0, 8_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is not None
        assert reason is None

    def test_still_implausible_when_no_older_real_year_exists(self):
        loader = _make_loader()
        # Same as the pre-existing TKLF regression test, but confirming the fallback doesn't
        # fabricate a result when there genuinely is nothing further back to use.
        rows = [
            _income_row(2025, 50_000_000.0, 5_000_000.0),
            _income_row(2024, 1.0, 10_000_000.0),
            _income_row(2023, 45_000_000.0, 4_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is None
        assert reason == "implausible_ratio"

    def test_stops_scanning_once_three_usable_years_found(self):
        loader = _make_loader()
        # A 4th, older row with an implausible margin must NOT flip the reason/behavior once
        # 3 usable years have already been collected from more recent rows.
        rows = [
            _income_row(2025, 100_000_000.0, 12_000_000.0),
            _income_row(2024, 95_000_000.0, 10_000_000.0),
            _income_row(2023, 90_000_000.0, 9_000_000.0),
            _income_row(2022, 1.0, 10_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is not None
        assert reason is None
