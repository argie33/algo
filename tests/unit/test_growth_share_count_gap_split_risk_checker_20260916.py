"""Regression tests for GrowthShareCountGapSplitRiskChecker (algo/monitoring/data_patrol/checks/
growth_share_count_gap_split_risk.py) - added 2026-09-16 /goal session after confirming the
production EPS/book-value split-discontinuity guard (loaders/helpers/vqg_growth.py,
is_split_or_share_count_scale_error via GrowthMetricsMixin._compute_period_growth) can be
silently bypassed by a real data gap: NVDA's true 10:1 split (FY2022->FY2023, ratio 9.89, only
1.10% off clean 10x - cleanly detectable) is masked because shares_outstanding_diluted/basic
are NULL for FY2023/FY2024, forcing the guard's adjacent-pair scan to compare FY2022->FY2025
instead (ratio 9.78, 2.16% off - just outside the guard's 1.5% tolerance).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.growth_share_count_gap_split_risk import (
    GrowthShareCountGapSplitRiskChecker,
)
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> GrowthShareCountGapSplitRiskChecker:
    return GrowthShareCountGapSplitRiskChecker(PatrolConfig())


def _row(symbol, fiscal_year, diluted, basic=None, **growth_fields):
    base = {
        "symbol": symbol,
        "fiscal_year": fiscal_year,
        "shares_outstanding_diluted": diluted,
        "shares_outstanding_basic": basic,
        "eps_growth_1y": None,
        "eps_growth_1y_unavailable_reason": None,
        "eps_growth_3y": None,
        "eps_growth_3y_unavailable_reason": None,
        "eps_growth_5y": None,
        "eps_growth_5y_unavailable_reason": None,
        "book_value_growth": None,
        "book_value_growth_unavailable_reason": None,
    }
    base.update(growth_fields)
    return base


class TestCheckShareCountGapMasksSplit:
    def test_nvda_shaped_gap_flagged_with_live_bypass(self) -> None:
        """The exact live-confirmed shape: FY2023/FY2024 shares NULL, so the nearest available
        pair (2022->2025) is a 2.16%-off-10x ratio, wider than the production guard's 1.5% but
        inside this check's wider detection net - and eps_growth_5y is currently non-null,
        meaning the production guard has already been bypassed for real, not just a latent risk.
        """
        checker = _checker()
        cur = MagicMock()
        # growth_metrics is per-symbol, so a LEFT JOIN against per-year annual_income_statement
        # rows repeats the SAME growth values on every row for that symbol - mirrored here.
        growth_fields = {"eps_growth_5y": 95.4, "eps_growth_5y_unavailable_reason": None}
        cur.fetchall.return_value = [
            _row("NVDA", 2021, 2510000000, **growth_fields),
            _row("NVDA", 2022, 2535000000, **growth_fields),
            _row("NVDA", 2023, None, **growth_fields),
            _row("NVDA", 2024, None, **growth_fields),
            _row("NVDA", 2025, 24800000000, **growth_fields),
        ]
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        examples = result.details["examples"]
        assert len(examples) == 1
        example = examples[0]
        assert example["symbol"] == "NVDA"
        assert example["fiscal_year_before_gap"] == 2022
        assert example["fiscal_year_after_gap"] == 2025
        assert example["gap_years"] == 3
        assert "eps_growth_5y" in example["currently_bypassed_fields"]
        assert result.details["currently_bypassed_count"] == 1

    def test_adjacent_years_with_data_not_flagged(self) -> None:
        """No gap at all (every year has shares data) - the production guard already scans
        this pair directly, nothing for this check to add.
        """
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            _row("GOOGL", 2024, 12100000000),
            _row("GOOGL", 2025, 1210000000),
        ]
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_gap_with_ordinary_dilution_ratio_not_flagged(self) -> None:
        """A multi-year gap exists, but the ratio across it (~1.2x) isn't near any clean split
        multiple - ordinary dilution/buyback drift, not a plausible masked split.
        """
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            _row("DRIFT", 2021, 100000000),
            _row("DRIFT", 2022, None),
            _row("DRIFT", 2023, None),
            _row("DRIFT", 2024, 120000000),
        ]
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_gap_with_clean_ratio_but_no_live_growth_value_is_latent_only(self) -> None:
        """A masked-split-shaped gap exists but no growth_metrics row/value currently spans
        it (e.g. thin history) - still worth flagging for review, but currently_bypassed_fields
        must be empty since nothing is actually shipping a wrong number today.
        """
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            _row("LATENT", 2021, 5000000),
            _row("LATENT", 2022, None),
            _row("LATENT", 2023, None),
            _row("LATENT", 2024, 50000000),
        ]
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        assert result.details["currently_bypassed_count"] == 0
        assert result.details["examples"][0]["currently_bypassed_fields"] == []

    def test_no_rows_logs_info(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_db_error_logged_not_raised(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = ValueError("boom")
        checker.check_share_count_gap_masks_split(cur)

        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert "failed" in checker.results[0].message
