"""Regression test: pe_ratio_unavailable_reason/peg_ratio_unavailable_reason must surface
"pe_earnings_too_volatile"/"pe_earnings_tax_benefit_inflated" instead of falling through to the
generic "missing_sec_data" label when sec_valuations_ratios.py's own same-day earnings-quality
guards (_pe_earnings_too_volatile/_pe_earnings_tax_benefit_inflated) are the real reason pe_ratio
came back None.

Found live 2026-09-07 (SEC/XBRL missing-data categorization audit): those two guards
(loaders/helpers/sec_valuations_ratios.py, added earlier the same day) deliberately null a real,
positive, anchor-year-EPS-backed pe_ratio as "not a reliable value signal" - but return None with
no reason string of their own, so vqg_value.py's pe_ratio_reason cascade (which only ever sees a
real, positive, in-anchor-year EPS for these symbols) fell through to the generic
"missing_sec_data" catch-all, miscategorizing a deliberate exclusion as a "Missing SEC/XBRL data"
gap. Live-confirmed BA (4 straight loss years 2021-2024 then a 2025 profit), AES and AXON
(FY2025 net_income inflated 6-12x above pretax_income by a large tax benefit) - all three are
real S&P 500 names with complete SEC financials, not data gaps. `pe_earnings_too_volatile`/
`pe_earnings_tax_benefit_inflated` are mapped in coverage_category_rules.py to "Implausible /
rejected value", the same bucket as the sibling implausible_dcf_result/eps_scale_mismatch
exclusions.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


def _base_row(**overrides):
    row = {
        "pe_ratio": None,
        "peg_ratio": None,
        "pb_ratio": 8.5,
        "current_price": 212.25,
        "market_cap": 161_267_550_000.0,
        "reason": None,
    }
    row.update(overrides)
    return _FakeSecValRow(row)


class _QueryRoutedCursor:
    """Routes on the rendered SQL text (not a fixed shape) since _build_value_metrics issues
    several different queries in sequence for a single symbol - see
    watermark_desync_test_fixture_fix_20260907 in memory for why a single fixed-shape fake
    breaks the moment a second distinct query is added.
    """

    def __init__(self, eps_row, volatility_rows, tax_benefit_row):
        self._eps_row = eps_row
        self._volatility_rows = volatility_rows
        self._tax_benefit_row = tax_benefit_row
        self._last = None

    def execute(self, query, params=None):
        if "ORDER BY fiscal_year DESC LIMIT 3" in query and "net_income" in query:
            self._last = "volatility"
        elif "income_tax_expense" in query:
            self._last = "tax_benefit"
        else:
            self._last = "eps"

    def fetchone(self):
        if self._last == "eps":
            return self._eps_row
        if self._last == "tax_benefit":
            return self._tax_benefit_row
        return None

    def fetchall(self):
        if self._last == "volatility":
            return self._volatility_rows
        return []


class TestPeRatioEarningsQualityDistortionReason:
    def test_too_volatile_reason_propagates_to_pe_and_peg(self):
        """BA-shaped: real positive anchor-year EPS, but 2+ of the last 3 fiscal years were
        losses - must resolve to pe_earnings_too_volatile, not missing_sec_data."""
        loader = _make_loader()
        cursor = _QueryRoutedCursor(
            eps_row=(2.49,),
            volatility_rows=[(-11_817_000_000,), (-2_222_000_000,), (2_235_000_000,)],
            tax_benefit_row=None,
        )
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics("BA", _base_row())

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "pe_earnings_too_volatile"
        assert metrics["peg_ratio"] is None
        assert metrics["peg_ratio_unavailable_reason"] == "pe_earnings_too_volatile"

    def test_tax_benefit_inflated_reason_propagates_to_pe_and_peg(self):
        """AES-shaped: real positive anchor-year EPS, stable earnings history, but latest fiscal
        year's net_income is inflated by a large tax benefit relative to pretax_income."""
        loader = _make_loader()
        cursor = _QueryRoutedCursor(
            eps_row=(1.26,),
            volatility_rows=[(910_000_000,), (1_679_000_000,), (249_000_000,)],
            tax_benefit_row=(75_000_000, -181_000_000),
        )
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics("AES", _base_row(current_price=14.79, market_cap=10_530_480_000.0))

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "pe_earnings_tax_benefit_inflated"
        assert metrics["peg_ratio"] is None
        assert metrics["peg_ratio_unavailable_reason"] == "pe_earnings_tax_benefit_inflated"

    def test_stable_profitable_history_still_falls_to_missing_sec_data(self):
        """Neither guard should fire for a symbol with a stable, unremarkable earnings history -
        confirms the new checks don't over-trigger and the generic fallback still works."""
        loader = _make_loader()
        cursor = _QueryRoutedCursor(
            eps_row=(2.5,),
            volatility_rows=[(100,), (110,), (120,)],
            tax_benefit_row=(100, 20),
        )
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics("STABLECO", _base_row())

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "missing_sec_data"
