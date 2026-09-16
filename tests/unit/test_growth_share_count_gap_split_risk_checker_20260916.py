"""Regression tests for GrowthShareCountGapSplitRiskChecker (algo/monitoring/data_patrol/checks/
growth_share_count_gap_split_risk.py) - added 2026-09-16 /goal session after confirming (against
the real local DB, not just hypothesized) that GrowthMetricsMixin.shares_by_year's
company_info_sec fallback - a single CURRENT share-count snapshot applied to every fiscal year
lacking real annual_income_statement shares - can put a real split's adjacent-year ratio just
outside the production guard's tight EPS_SPLIT_GUARD_CLEAN_TOLERANCE. NVDA-shaped: FY2023/
FY2024 shares NULL, resolved via company_info_sec's 24.1B snapshot; FY2022's real 2.535B vs
that fallback gives ratio 9.507 (4.93% off clean 10x) - outside the 1.5% production tolerance.
Running the real loader against NVDA's real rows confirmed eps_growth_5y=22.88 ships today (the
known pre/post-split-blended wrong value).
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
        "eps_growth_3y": None,
        "eps_growth_5y": None,
        "book_value_growth": None,
    }
    base.update(growth_fields)
    return base


def _run(checker, income_rows, fallback_rows):
    cur = MagicMock()
    cur.fetchall.side_effect = [income_rows, fallback_rows]
    checker.check_share_count_gap_masks_split(cur)
    return cur


class TestCheckShareCountGapMasksSplit:
    def test_nvda_shaped_fallback_substitution_flagged_with_live_bypass(self) -> None:
        """The exact live-confirmed shape: FY2023/FY2024 shares NULL, resolved via
        company_info_sec's 24.1B CURRENT snapshot fallback. FY2022 (real 2.535B) vs FY2023
        (fallback 24.1B) is 4.93% off clean 10x - wider than the production guard's 1.5% but
        inside this check's detection net. eps_growth_5y is currently non-null, meaning the
        production guard has already been bypassed for real, not just a latent risk.
        """
        checker = _checker()
        growth_fields = {"eps_growth_5y": 22.88}
        income_rows = [
            _row("NVDA", 2021, 2510000000, **growth_fields),
            _row("NVDA", 2022, 2535000000, **growth_fields),
            _row("NVDA", 2023, None, **growth_fields),
            _row("NVDA", 2024, None, **growth_fields),
            _row("NVDA", 2025, 24804000000, **growth_fields),
        ]
        fallback_rows = [{"symbol": "NVDA", "shares_outstanding": 24100000000}]
        _run(checker, income_rows, fallback_rows)

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        examples = result.details["examples"]
        assert len(examples) == 1
        example = examples[0]
        assert example["symbol"] == "NVDA"
        assert example["fiscal_year_before"] == 2022
        assert example["fiscal_year_after"] == 2023
        assert example["mask_reason"] == "fallback_substituted"
        assert "eps_growth_5y" in example["currently_bypassed_fields"]
        assert result.details["currently_bypassed_count"] == 1

    def test_true_data_gap_no_fallback_flagged_as_data_gap(self) -> None:
        """No company_info_sec fallback exists at all - the intervening years are a genuine
        gap, not a fallback substitution. Distinct mask_reason from the NVDA case.
        """
        checker = _checker()
        income_rows = [
            _row("GAPCO", 2021, 2500000000),
            _row("GAPCO", 2022, 2530000000),
            _row("GAPCO", 2023, None),
            _row("GAPCO", 2024, None),
            _row("GAPCO", 2025, 24800000000),
        ]
        _run(checker, income_rows, fallback_rows=[])

        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        example = result.details["examples"][0]
        assert example["mask_reason"] == "data_gap"
        assert example["fiscal_year_before"] == 2022
        assert example["fiscal_year_after"] == 2025
        assert example["currently_bypassed_fields"] == []

    def test_ratio_within_production_tight_tolerance_not_flagged(self) -> None:
        """Adjacent real years, ratio well inside the production guard's own 1.5% tolerance -
        the guard already catches this, nothing for this check to add.
        """
        checker = _checker()
        income_rows = [
            _row("CLEAN", 2024, 25070000000),
            _row("CLEAN", 2025, 2535000000),
        ]
        _run(checker, income_rows, fallback_rows=[])

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_adjacent_real_years_near_miss_out_of_scope(self) -> None:
        """Two genuinely adjacent real-data years with a near-but-not-quite ratio (no gap, no
        fallback involved) is a tolerance-calibration question, not a gap/fallback masking one -
        explicitly out of this check's scope, so it must not be flagged.
        """
        checker = _checker()
        income_rows = [
            _row("NEARMISS", 2024, 2535000000),
            _row("NEARMISS", 2025, 24100000000),  # 4.93% off 10x, both years real (adjacent)
        ]
        _run(checker, income_rows, fallback_rows=[])

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_old_history_outside_cagr_window_not_flagged(self) -> None:
        """REGRESSION: an unrestricted full-history scan flagged NVDA's own 2019->2020 boundary
        (ratio 9.75, coincidentally near 10x via the same fallback constant) even though it's 7
        years before the symbol's latest fiscal year and never used by any real growth-field
        CAGR (max offset is 5 years) - drowned the real, in-window 2022->2023 finding among ~650
        other old-history false positives on the live DB. Only years within the most recent
        _MAX_OFFSET_YEARS of the symbol's latest fiscal year may be flagged.
        """
        checker = _checker()
        income_rows = [
            _row("OLDNOISE", 2018, 2400000000),
            _row("OLDNOISE", 2019, 2472000000),
            _row("OLDNOISE", 2020, None),  # fallback boundary vs 2019 real: ~9.75x - out of window
            # In-window years (latest 2026, floor 2021): unremarkable drift, no clean-multiple ratio.
            _row("OLDNOISE", 2021, 100000000),
            _row("OLDNOISE", 2022, 102000000),
            _row("OLDNOISE", 2023, 104000000),
            _row("OLDNOISE", 2024, 106000000),
            _row("OLDNOISE", 2025, 108000000),
            _row("OLDNOISE", 2026, 110000000),
        ]
        fallback_rows = [{"symbol": "OLDNOISE", "shares_outstanding": 24100000000}]
        _run(checker, income_rows, fallback_rows)

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_ordinary_dilution_ratio_not_flagged(self) -> None:
        """A multi-year gap exists, but the ratio across it (~1.2x) isn't near any clean split
        multiple - ordinary dilution/buyback drift, not a plausible masked split.
        """
        checker = _checker()
        income_rows = [
            _row("DRIFT", 2021, 100000000),
            _row("DRIFT", 2022, None),
            _row("DRIFT", 2023, None),
            _row("DRIFT", 2024, 120000000),
        ]
        _run(checker, income_rows, fallback_rows=[])

        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_no_rows_logs_info(self) -> None:
        checker = _checker()
        _run(checker, income_rows=[], fallback_rows=[])

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
