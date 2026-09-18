"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up), rebuilt same day after a multi-session working-tree collision dropped the original
version of this file along with the guard function and its wiring (see
loaders/helpers/sec_zero_component_guards.py's is_narrow_long_term_debt_blocking_noncurrent_current_sum
docstring for the incident note).

AJG (Arthur J. Gallagher, CIK 0000354190) live-confirmed via real SEC companyfacts JSON: tags a
real but immaterial plain "LongTermDebt" fact alongside a real, dramatically larger
"LongTermDebtNoncurrent" fact in the SAME 10-K, every fiscal year present in
xbrl_yfinance_line_item_report:
    FY2022: LongTermDebt=$16,800,000 vs. LongTermDebtNoncurrent=$5,562,800,000 (exact yfinance
            match)
    FY2023: LongTermDebt=$23,600,000 vs. LongTermDebtNoncurrent=$7,006,000,000 (exact match)
    FY2024: LongTermDebt=$23,000,000 vs. LongTermDebtNoncurrent=$12,732,000,000 (exact match)

Before this fix, utils/external/sec_balance_sheet.py's
_fill_long_term_debt_from_noncurrent_current_split()'s primary branch only filled from the
noncurrent split when "long_term_debt" was still None for that fiscal year - so the real
LongTermDebtNoncurrent total was silently discarded whenever any plain LongTermDebt value
existed already, however immaterial.
"""

from decimal import Decimal

from loaders.helpers.sec_zero_component_guards import (
    _NONCURRENT_CURRENT_SUM_MIN_MULTIPLE,
    is_narrow_long_term_debt_blocking_noncurrent_current_sum,
)
from utils.external.sec_balance_sheet import _fill_long_term_debt_from_noncurrent_current_split


class TestIsNarrowLongTermDebtBlockingNoncurrentCurrentSum:
    def test_ajg_fy2022_fires(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(16_800_000.0, 5_562_800_000.0, None) is True

    def test_ajg_fy2023_fires(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(23_600_000.0, 7_006_000_000.0, 0.0) is True

    def test_ajg_fy2024_fires(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(23_000_000.0, 12_732_000_000.0, None) is True

    def test_empd_fy2025_fires(self) -> None:
        # EMPD FY2025: plain LongTermDebt=$34,510 vs. LongTermDebtNoncurrent-class total
        # far larger - same shape as AJG, different filer.
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(34_510.0, 49_965_531.0, None) is True

    def test_does_not_fire_below_magnitude_threshold(self) -> None:
        # A modest gap (a real debt paydown between filings) must never be treated as this bug.
        existing = 100_000_000.0
        total = existing * (_NONCURRENT_CURRENT_SUM_MIN_MULTIPLE - 1)
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(existing, total, None) is False

    def test_fires_exactly_at_magnitude_threshold(self) -> None:
        existing = 1_000_000.0
        total = existing * _NONCURRENT_CURRENT_SUM_MIN_MULTIPLE
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(existing, total, None) is True

    def test_does_not_fire_when_existing_is_none(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(None, 5_000_000_000.0, None) is False

    def test_does_not_fire_when_existing_is_zero_or_negative(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(0.0, 5_000_000_000.0, None) is False
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(-1.0, 5_000_000_000.0, None) is False

    def test_does_not_fire_when_noncurrent_is_none(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(16_800_000.0, None, None) is False

    def test_does_not_fire_when_total_is_not_positive(self) -> None:
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(16_800_000.0, 0.0, 0.0) is False

    def test_current_portion_included_in_the_sum(self) -> None:
        # Combined noncurrent+current must clear the multiple even if noncurrent alone doesn't.
        existing = 1_000_000.0
        noncurrent = 40_000_000.0  # 40x alone - below the 50x floor
        current = 20_000_000.0  # +20x current portion pushes combined total to 60x
        assert is_narrow_long_term_debt_blocking_noncurrent_current_sum(existing, noncurrent, current) is True

    def test_accepts_decimal_inputs(self) -> None:
        assert (
            is_narrow_long_term_debt_blocking_noncurrent_current_sum(
                Decimal("16800000.0"), Decimal("5562800000.0"), None
            )
            is True
        )


class TestFillLongTermDebtFromNoncurrentCurrentSplitAjgIntegration:
    def test_ajg_style_row_overridden_by_noncurrent_total(self) -> None:
        row = {
            "symbol": "AJG",
            "fiscal_year": 2022,
            "long_term_debt": 16_800_000.0,
            "long_term_debt_noncurrent": 5_562_800_000.0,
        }
        _fill_long_term_debt_from_noncurrent_current_split([row])
        assert row["long_term_debt"] == 5_562_800_000.0
        assert "long_term_debt_noncurrent" not in row
        assert "long_term_debt_current" not in row

    def test_ordinary_modest_gap_is_not_overridden(self) -> None:
        # A filer whose plain concept is genuinely close to the real total (timing/rounding)
        # must be left alone - only a dramatic (>=50x) gap is this bug's signature.
        row = {
            "symbol": "ORDINARY",
            "fiscal_year": 2024,
            "long_term_debt": 100_000_000.0,
            "long_term_debt_noncurrent": 105_000_000.0,
        }
        _fill_long_term_debt_from_noncurrent_current_split([row])
        assert row["long_term_debt"] == 100_000_000.0
