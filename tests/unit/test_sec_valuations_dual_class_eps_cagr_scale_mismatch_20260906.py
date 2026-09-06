"""Regression test for _validate_dual_class_eps_cagr (2026-09-06, goal session: "digging into
symbols we know" audit).

Live-confirmed via BRK.A/BRK.B: FY2023-2025 EPS ratio is consistently ~1500.0-1500.2 (the
real, structurally-fixed conversion ratio), but FY2020-2022 is ~2715.0 in every one of those
three years - a scaling bug in the older annual_income_statement rows for one/both siblings.
_compute_multi_year_eps_cagr picks its two endpoints (newest usable year, oldest usable year)
independently per symbol with no cross-symbol awareness, so BRK.A's endpoints (2025, 2020)
straddled a correctly-scaled year and a wrongly-scaled year while BRK.B's endpoints landed
differently - producing wildly different dcf_eps_cagr_pct (-10.93%/yr vs +0.29%/yr) for what
must be the same real-world growth rate, corrupting intrinsic_value_per_share/
margin_of_safety_pct/value_score for both tickers even though the DCF's FCF and shares
denominators were already correctly entity-wide/1500:1-scaled.
"""

from unittest.mock import MagicMock

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestDualClassEpsCagrScaleMismatch:
    def test_brka_style_scale_mismatch_discards_cagr(self) -> None:
        """FY2025/2024/2023 ratio ~1500, FY2022/2021/2020 ratio ~2715 (mirrors live BRK.A/
        BRK.B data exactly) - the CAGR's own two endpoints (2025, 2020) disagree by more than
        15%, so it must be discarded."""
        loader = _make_loader()
        income_rows = [
            (2025, 371444000000.0, 66968000000.0, 46563.0000),
            (2024, 371433000000.0, 88995000000.0, 61900.0000),
            (2023, 364482000000.0, 96223000000.0, 66412.0000),
            (2022, 302020000000.0, -22759000000.0, -44466.8047),
            (2021, 276185000000.0, 89937000000.0, 175719.9797),
            (2020, 245579000000.0, 42521000000.0, 83078.0352),
        ]
        sibling_rows = [
            (2025, 31.0400),
            (2020, 30.5993),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = sibling_rows

        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        assert cagr is not None  # sanity: the raw (buggy) CAGR is computable at all

        result = loader._validate_dual_class_eps_cagr(cur, "BRK.A", True, income_rows, cagr)
        assert result is None

    def test_consistent_sibling_ratio_keeps_cagr(self) -> None:
        """Same shape, but every year (including the endpoints) scales by a consistent 1500x -
        no real-world dual-class pair behaves like the buggy BRK.A/BRK.B case, so the CAGR
        must survive unchanged."""
        loader = _make_loader()
        income_rows = [
            (2025, 371444000000.0, 66968000000.0, 46563.0000),
            (2024, 371433000000.0, 88995000000.0, 61900.0000),
            (2023, 364482000000.0, 96223000000.0, 66412.0000),
            (2022, 302020000000.0, -22759000000.0, -44466.8047),
            (2021, 276185000000.0, 89937000000.0, 175719.9797),
            (2020, 245579000000.0, 42521000000.0, 83078.0352),
        ]
        sibling_rows = [
            (2025, 46563.0000 / 1500.0),
            (2020, 83078.0352 / 1500.0),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = sibling_rows

        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        result = loader._validate_dual_class_eps_cagr(cur, "BRK.A", True, income_rows, cagr)
        assert result == cagr

    def test_no_dual_class_sibling_skips_check(self) -> None:
        loader = _make_loader()
        cur = MagicMock()
        result = loader._validate_dual_class_eps_cagr(cur, "AAPL", False, [], -10.0)
        assert result == -10.0
        cur.execute.assert_not_called()

    def test_none_cagr_skips_check(self) -> None:
        loader = _make_loader()
        cur = MagicMock()
        result = loader._validate_dual_class_eps_cagr(cur, "BRK.A", True, [], None)
        assert result is None
        cur.execute.assert_not_called()

    def test_sibling_missing_endpoint_data_fails_open(self) -> None:
        """Can't cross-check without the sibling's EPS for both endpoint years - fail open
        (trust the CAGR) rather than discard a value this guard can't actually evaluate."""
        loader = _make_loader()
        income_rows = [
            (2025, 371444000000.0, 66968000000.0, 46563.0000),
            (2024, 371433000000.0, 88995000000.0, 61900.0000),
            (2023, 364482000000.0, 96223000000.0, 66412.0000),
            (2020, 245579000000.0, 42521000000.0, 83078.0352),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = []  # sibling has no rows for either endpoint year

        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        result = loader._validate_dual_class_eps_cagr(cur, "BRK.A", True, income_rows, cagr)
        assert result == cagr
