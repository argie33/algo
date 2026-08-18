"""Regression test: when annual_balance_sheet is stale (>MAX_FISCAL_YEAR_AGE_YEARS old),
fetch_incremental() used to wholesale-replace quality_dict with the fully-blanked
_unavailable_marker() - discarding total_debt/total_cash/ebitda/cash_per_share too, even
though those 4 fields are computed purely from `ev_metrics` (the separately-fetched,
ungated sec_valuations row), not from the stale annual_balance_sheet join.

Live-confirmed 103 universe symbols hit this: e.g. UBS had a real, current sec_valuations
total_cash of $231,375,000,000 (matching its FY2025 annual_balance_sheet row) but
quality_metrics.total_cash was NULL with reason "missing_sec_data" - the stale-fiscal-data
gate (tripped because UBS's balance sheet was still years behind at the time) nuked a field
that never depended on that table at all.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_ev_sourced_fields_survive_stale_fiscal_data_marker():
    loader = _make_loader()
    quality_dict = {
        "total_debt": 3_769_000_000.0,
        "total_cash": 231_375_000_000.0,
        "ebitda": 8_853_000_000.0,
        "cash_per_share": 12.34,
        "total_debt_unavailable_reason": None,
        "total_cash_unavailable_reason": None,
        "ebitda_unavailable_reason": None,
        "cash_per_share_unavailable_reason": None,
        # A balance-sheet-derived field that SHOULD be wiped - it genuinely depends on
        # the stale annual_balance_sheet join.
        "roe": 12.5,
    }

    marker = loader._stale_quality_marker("UBS", quality_dict, "stale_fiscal_data: ...")

    assert marker["total_debt"] == 3_769_000_000.0
    assert marker["total_cash"] == 231_375_000_000.0
    assert marker["ebitda"] == 8_853_000_000.0
    assert marker["cash_per_share"] == 12.34
    assert marker["total_debt_unavailable_reason"] is None
    assert marker["total_cash_unavailable_reason"] is None
    assert marker["ebitda_unavailable_reason"] is None
    assert marker["cash_per_share_unavailable_reason"] is None
    # Balance-sheet-derived fields must still be blanked.
    assert marker["roe"] is None
    assert marker["roe_unavailable_reason"] == "missing_sec_data"
    assert marker["data_unavailable"] is True
    assert marker["reason"] == "stale_fiscal_data: ..."


def test_missing_ev_sourced_fields_fall_back_to_generic_marker():
    loader = _make_loader()
    quality_dict = {
        "total_debt": None,
        "total_cash": None,
        "ebitda": None,
        "cash_per_share": None,
        "total_debt_unavailable_reason": "missing_sec_data",
        "total_cash_unavailable_reason": "missing_sec_data",
        "ebitda_unavailable_reason": "missing_sec_data",
        "cash_per_share_unavailable_reason": "missing_sec_data",
    }

    marker = loader._stale_quality_marker("NODATA", quality_dict, "stale_fiscal_data: ...")

    assert marker["total_debt"] is None
    assert marker["total_cash"] is None
    assert marker["ebitda"] is None
    assert marker["cash_per_share"] is None
    assert marker["total_debt_unavailable_reason"] == "missing_sec_data"
