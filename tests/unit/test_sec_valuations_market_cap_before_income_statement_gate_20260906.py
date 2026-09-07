"""Regression test for the 2026-09-06 fix (goal: "SEC/XBRL missing data to zero" sweep,
sibling to 2026-09-02's total_cash/total_debt fix in
test_sec_valuations_total_cash_debt_before_income_statement_gate_20260902.py): market_cap
(price * shares_outstanding) needs neither an income statement nor a balance sheet, but the
"no_income_statement" early return in SecValuationsLoader.fetch_incremental used to omit it
entirely, nulling it out even when a real current price_daily row and a real
company_info_sec.shares_outstanding both existed.

Live-confirmed 19/22 symbols hitting this early return (AADX, DPC, SIND, PBLS, ADBT, ADIG,
BSEM, AIB, KARD, AVEX, SSMR, CSQR, LFTO, FCBM, HMH, LCLN, LIME, SECZ, SUJA) have a real,
current (2026-09-04) price and a real shares_outstanding, purely nulled out by this gate.

Fixed by extracting the price/shares_outstanding queries into
_get_market_cap_without_income_statement() and calling it from the "no_income_statement"
early return, passing the results into _unavailable_marker's new current_price/
shares_outstanding/market_cap override parameters - plus a downstream fix in
ValueMetricsMixin._build_value_metrics (vqg_value.py), whose own all-NULL value_metrics
marker was discarding sec_valuations' market_cap unconditionally on the data_unavailable
branch.
"""

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    """Returns canned results in call order - first call is the price query, second is the
    shares_outstanding query, matching _get_market_cap_without_income_statement's own call
    sequence."""

    def __init__(self, price_result, shares_result):
        self._results = [price_result, shares_result]
        self._call = 0

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        result = self._results[self._call]
        self._call += 1
        return result


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestGetMarketCapWithoutIncomeStatement:
    def test_recovers_real_market_cap_from_price_and_shares_alone(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=(12.93,), shares_result=(172_393_518,))

        current_price, shares_outstanding, market_cap = loader._get_market_cap_without_income_statement(cur, "AADX")

        assert current_price == 12.93
        assert shares_outstanding == 172_393_518
        assert market_cap == 12.93 * 172_393_518

    def test_missing_price_returns_none_for_market_cap(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=None, shares_result=(172_393_518,))

        current_price, shares_outstanding, market_cap = loader._get_market_cap_without_income_statement(cur, "XTND")

        assert current_price is None
        assert market_cap is None

    def test_missing_shares_outstanding_returns_none_for_market_cap(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=(4.39,), shares_result=None)

        current_price, shares_outstanding, market_cap = loader._get_market_cap_without_income_statement(cur, "XLAB")

        assert shares_outstanding is None
        assert market_cap is None


class TestNoIncomeStatementMarkerCarriesMarketCap:
    def test_marker_with_market_cap_overrides_keeps_reason_and_values(self):
        loader = _make_loader()

        marker = loader._unavailable_marker(
            "AADX",
            "no_income_statement",
            current_price=12.93,
            shares_outstanding=172_393_518.0,
            market_cap=12.93 * 172_393_518,
        )

        assert marker["reason"] == "no_income_statement"
        assert marker["data_unavailable"] is True
        assert marker["market_cap"] == 12.93 * 172_393_518
        assert marker["current_price"] == 12.93
        assert marker["shares_outstanding"] == 172_393_518.0
        # pe_ratio/pb_ratio/etc genuinely need the income statement or aren't computed here -
        # must stay None even when market_cap is recovered.
        assert marker["pe_ratio"] is None

    def test_marker_without_overrides_keeps_prior_all_null_behavior(self):
        loader = _make_loader()

        marker = loader._unavailable_marker("NODATA", "no_income_statement")

        assert marker["current_price"] is None
        assert marker["shares_outstanding"] is None
        assert marker["market_cap"] is None


class TestBuildValueMetricsSurfacesRecoveredMarketCap:
    """ValueMetricsMixin._build_value_metrics's own all-NULL value_metrics marker used to
    discard sec_valuations' market_cap unconditionally whenever data_unavailable was True -
    this is the downstream half of the fix."""

    def _make_value_mixin(self):
        from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_recovered_market_cap_survives_the_data_unavailable_branch(self, monkeypatch):
        loader = self._make_value_mixin()
        monkeypatch.setattr(loader, "_get_etf_symbols", lambda: set())
        monkeypatch.setattr(loader, "_get_preferred_or_debt_security_symbols", lambda: set())

        sec_val_row = {
            "data_unavailable": True,
            "reason": "no_income_statement",
            "market_cap": 12.93 * 172_393_518,
        }

        marker = loader._build_value_metrics("AADX", sec_val_row)

        assert marker["data_unavailable"] is True
        assert marker["market_cap"] == 12.93 * 172_393_518
        assert marker["market_cap_unavailable_reason"] is None
        # Every other field genuinely still needs the income statement.
        assert marker["pe_ratio"] is None
        assert marker["pe_ratio_unavailable_reason"] == "no_income_statement"

    def test_no_market_cap_keeps_prior_all_null_behavior(self, monkeypatch):
        loader = self._make_value_mixin()
        monkeypatch.setattr(loader, "_get_etf_symbols", lambda: set())
        monkeypatch.setattr(loader, "_get_preferred_or_debt_security_symbols", lambda: set())

        sec_val_row = {"data_unavailable": True, "reason": "no_income_statement", "market_cap": None}

        marker = loader._build_value_metrics("XLAB", sec_val_row)

        assert marker["market_cap"] is None
        assert marker["market_cap_unavailable_reason"] == "no_income_statement"
