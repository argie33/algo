"""Regression test for the 2026-09-06 fix (goal: "SEC/XBRL missing data to zero" sweep,
sibling to 2026-09-02's total_cash/total_debt fix in
test_sec_valuations_total_cash_debt_before_income_statement_gate_20260902.py): market_cap
(price * shares_outstanding), pb_ratio (needs only price/shares_outstanding/
stockholders_equity), and held_percent_institutions (a completely separate positioning_metrics/
13F feed) all need neither an income statement nor a balance sheet's income-derived fields, but
the "no_income_statement" early return in SecValuationsLoader.fetch_incremental - and
ValueMetricsMixin._build_value_metrics's own separate all-NULL value_metrics marker - used to
null all three out unconditionally.

Live-confirmed 19/22 symbols hitting this early return (AADX, DPC, SIND, PBLS, ADBT, ADIG,
BSEM, AIB, KARD, AVEX, SSMR, CSQR, LFTO, FCBM, HMH, LCLN, LIME, SECZ, SUJA) have a real,
current (2026-09-04) price and a real shares_outstanding; most also have a real
stockholders_equity (pb_ratio) and/or a real, specific positioning_metrics status (2/19 a real
institutional_ownership_pct, the rest a real "no_resolved_13f_holdings" - correctly "Ownership
data unresolved", not "Missing SEC/XBRL data").

Fixed by extracting the price/shares_outstanding/stockholders_equity queries into
_get_market_cap_without_income_statement() (now also computing pb_ratio via the loader's own
real _compute_pb_ratio) and calling it from the "no_income_statement" early return, passing the
results into _unavailable_marker's new current_price/shares_outstanding/market_cap/pb_ratio
override parameters - plus two downstream fixes in ValueMetricsMixin._build_value_metrics
(vqg_value.py), whose own all-NULL value_metrics marker was (a) discarding sec_valuations'
market_cap/pb_ratio unconditionally, and (b) never calling _fetch_positioning_metrics at all
on the data_unavailable branch (that call was previously only reachable past this early return).
"""

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    """Returns canned results in call order - price, then shares_outstanding, then (only if
    both of those succeeded) stockholders_equity - matching
    _get_market_cap_without_income_statement's own call sequence."""

    def __init__(self, price_result, shares_result, equity_result=None):
        self._results = [price_result, shares_result, equity_result]
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
    def test_recovers_real_market_cap_and_pb_ratio_from_price_shares_and_equity_alone(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=(12.93,), shares_result=(172_393_518,), equity_result=(827_881_000.00,))

        current_price, shares_outstanding, market_cap, pb_ratio = loader._get_market_cap_without_income_statement(
            cur, "AADX"
        )

        assert current_price == 12.93
        assert shares_outstanding == 172_393_518
        assert market_cap == 12.93 * 172_393_518
        # bvps = 827,881,000 / 172,393,518 ~= 4.80 -> pb ~= 2.69, within [MIN_PLAUSIBLE_PB_RATIO, 1000]
        assert pb_ratio is not None
        assert 2.0 < pb_ratio < 3.0

    def test_missing_price_returns_none_for_market_cap_and_pb_ratio(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=None, shares_result=(172_393_518,))

        current_price, shares_outstanding, market_cap, pb_ratio = loader._get_market_cap_without_income_statement(
            cur, "XTND"
        )

        assert current_price is None
        assert market_cap is None
        assert pb_ratio is None

    def test_missing_shares_outstanding_returns_none_for_market_cap_and_pb_ratio(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=(4.39,), shares_result=None)

        current_price, shares_outstanding, market_cap, pb_ratio = loader._get_market_cap_without_income_statement(
            cur, "XLAB"
        )

        assert shares_outstanding is None
        assert market_cap is None
        assert pb_ratio is None

    def test_missing_stockholders_equity_returns_market_cap_but_no_pb_ratio(self):
        loader = _make_loader()
        cur = _FakeCursor(price_result=(5.85,), shares_result=(1_000_000,), equity_result=None)

        current_price, shares_outstanding, market_cap, pb_ratio = loader._get_market_cap_without_income_statement(
            cur, "GIXI"
        )

        assert market_cap == 5.85 * 1_000_000
        assert pb_ratio is None


class TestNoIncomeStatementMarkerCarriesMarketCapAndPbRatio:
    def test_marker_with_overrides_keeps_reason_and_values(self):
        loader = _make_loader()

        marker = loader._unavailable_marker(
            "AADX",
            "no_income_statement",
            current_price=12.93,
            shares_outstanding=172_393_518.0,
            market_cap=12.93 * 172_393_518,
            pb_ratio=2.69,
        )

        assert marker["reason"] == "no_income_statement"
        assert marker["data_unavailable"] is True
        assert marker["market_cap"] == 12.93 * 172_393_518
        assert marker["current_price"] == 12.93
        assert marker["shares_outstanding"] == 172_393_518.0
        assert marker["pb_ratio"] == 2.69
        # pe_ratio/etc genuinely need the income statement or aren't computed here - must
        # stay None even when market_cap/pb_ratio are recovered.
        assert marker["pe_ratio"] is None

    def test_marker_without_overrides_keeps_prior_all_null_behavior(self):
        loader = _make_loader()

        marker = loader._unavailable_marker("NODATA", "no_income_statement")

        assert marker["current_price"] is None
        assert marker["shares_outstanding"] is None
        assert marker["market_cap"] is None
        assert marker["pb_ratio"] is None


class TestBuildValueMetricsSurfacesRecoveredFields:
    """ValueMetricsMixin._build_value_metrics's own all-NULL value_metrics marker used to
    discard sec_valuations' market_cap/pb_ratio unconditionally, and never called
    _fetch_positioning_metrics at all, whenever data_unavailable was True - this is the
    downstream half of the fix."""

    def _make_value_mixin(self, monkeypatch, held_percent_institutions=None, held_percent_institutions_reason=None):
        from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        monkeypatch.setattr(loader, "_get_etf_symbols", lambda: set())
        monkeypatch.setattr(loader, "_get_preferred_or_debt_security_symbols", lambda: set())
        monkeypatch.setattr(
            loader,
            "_fetch_positioning_metrics",
            lambda symbol: (held_percent_institutions, held_percent_institutions_reason),
        )
        return loader

    def test_recovered_market_cap_and_pb_ratio_survive_the_data_unavailable_branch(self, monkeypatch):
        loader = self._make_value_mixin(monkeypatch)

        sec_val_row = {
            "data_unavailable": True,
            "reason": "no_income_statement",
            "market_cap": 12.93 * 172_393_518,
            "pb_ratio": 2.69,
        }

        marker = loader._build_value_metrics("AADX", sec_val_row)

        assert marker["data_unavailable"] is True
        assert marker["market_cap"] == 12.93 * 172_393_518
        assert marker["market_cap_unavailable_reason"] is None
        assert marker["pb_ratio"] == 2.69
        assert marker["pb_ratio_unavailable_reason"] is None
        # Every other field genuinely still needs the income statement.
        assert marker["pe_ratio"] is None
        assert marker["pe_ratio_unavailable_reason"] == "no_income_statement"

    def test_no_recovered_values_keeps_prior_all_null_behavior(self, monkeypatch):
        loader = self._make_value_mixin(monkeypatch)

        sec_val_row = {"data_unavailable": True, "reason": "no_income_statement", "market_cap": None, "pb_ratio": None}

        marker = loader._build_value_metrics("XLAB", sec_val_row)

        assert marker["market_cap"] is None
        assert marker["market_cap_unavailable_reason"] == "no_income_statement"
        assert marker["pb_ratio"] is None
        assert marker["pb_ratio_unavailable_reason"] == "no_income_statement"

    def test_pb_ratio_not_overridden_for_preferred_or_debt_security(self, monkeypatch):
        loader = self._make_value_mixin(monkeypatch)
        monkeypatch.setattr(loader, "_get_preferred_or_debt_security_symbols", lambda: {"PREFD"})

        sec_val_row = {"data_unavailable": True, "reason": "no_income_statement", "pb_ratio": 2.69}

        marker = loader._build_value_metrics("PREFD", sec_val_row)

        # The preferred/debt-security override (existing behavior) must win - a real pb_ratio
        # from sec_valuations must not clobber the "no common equity ratio" business fact.
        assert marker["pb_ratio"] is None
        assert marker["pb_ratio_unavailable_reason"] == "preferred_or_debt_security_no_common_equity_ratio"

    def test_real_institutional_ownership_recovered(self, monkeypatch):
        loader = self._make_value_mixin(
            monkeypatch, held_percent_institutions=0.12, held_percent_institutions_reason=None
        )

        sec_val_row = {"data_unavailable": True, "reason": "no_income_statement"}

        marker = loader._build_value_metrics("AIB", sec_val_row)

        assert marker["held_percent_institutions"] == 0.12
        assert marker["held_percent_institutions_unavailable_reason"] is None

    def test_no_resolved_13f_holdings_recategorized_out_of_missing_sec_data(self, monkeypatch):
        loader = self._make_value_mixin(
            monkeypatch, held_percent_institutions=None, held_percent_institutions_reason="no_resolved_13f_holdings"
        )

        sec_val_row = {"data_unavailable": True, "reason": "no_income_statement"}

        marker = loader._build_value_metrics("DPC", sec_val_row)

        assert marker["held_percent_institutions"] is None
        assert marker["held_percent_institutions_unavailable_reason"] == "no_resolved_13f_holdings"
