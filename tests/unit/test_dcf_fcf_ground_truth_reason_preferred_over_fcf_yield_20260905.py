"""Regression test (2026-09-05, goal session: "SEC/XBRL missing data to zero" / implausible-
values sweep): intrinsic_value_unavailable_reason/margin_of_safety_unavailable_reason must
prefer sec_valuations.dcf_fcf_unavailable_reason (migration 1258) over the fcf_yield-based
guess in intrinsic_value_reason_from_fcf_yield() when both are present.

Root cause: fcf_yield's own FCF base never receives the DCF-only net-borrowing adjustment
_compute_dcf_intrinsic_value's `fcf` input does (loaders/helpers/sec_valuations_dcf.py's
_get_net_borrowing_for_dcf), so the two can disagree in sign. Live-confirmed via a debug trace
against 17 real "implausible_dcf_result" universe symbols (APTV, AER, ASB, and 14 more): 13 of
17 had fcf_yield > 0 but the DCF's real fcf negative or None (a balance-sheet debt paydown/
issuance), meaning the fcf_yield-based guess mislabeled a real "negative_free_cash_flow"/
"missing_cash_flow_data" case (categorized "Legitimate / not applicable") as
"implausible_dcf_result" (categorized "Implausible / rejected value").
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _run(monkeypatch, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("APTV", _FakeSecValRow(sec_val_fields))


class TestDcfFcfGroundTruthReasonPreferred:
    def test_positive_fcf_yield_but_negative_dcf_fcf_reports_negative_free_cash_flow(self, monkeypatch):
        # This exact combination (fcf_yield > 0, intrinsic_value_per_share None) used to always
        # produce "implausible_dcf_result" via intrinsic_value_reason_from_fcf_yield - now the
        # ground-truth dcf_fcf_unavailable_reason column wins instead.
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=13.18,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            dcf_fcf_unavailable_reason="negative_free_cash_flow",
            enterprise_value=1_000_000_000.0,
            market_cap=10_549_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "negative_free_cash_flow"
        assert result["margin_of_safety_unavailable_reason"] == "negative_free_cash_flow"

    def test_missing_cash_flow_data_reason_also_preferred(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=13.18,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            dcf_fcf_unavailable_reason="missing_cash_flow_data",
            enterprise_value=1_000_000_000.0,
            market_cap=10_549_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "missing_cash_flow_data"

    def test_no_ground_truth_column_falls_back_to_fcf_yield_guess(self, monkeypatch):
        # Rows load_sec_valuations.py hasn't reprocessed yet (no dcf_fcf_unavailable_reason key
        # at all) must keep working exactly as before.
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=6.0,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "implausible_dcf_result"

    def test_genuine_implausible_dcf_result_still_reported_when_ground_truth_says_so(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=6.0,
            intrinsic_value_per_share=None,
            margin_of_safety_pct=None,
            dcf_fcf_unavailable_reason="implausible_dcf_result",
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["intrinsic_value_unavailable_reason"] == "implausible_dcf_result"
