"""Regression test (2026-09-11, /goal session): a live leaderboard review surfaced two
China-domiciled consumer-lending ADRs (XYF, JFIN) scoring well on Quality/Value despite a
real, well-documented risk category (HFCAA audit-access restrictions, VIE structures) that
no financial-statement ratio or price series can see. algo/risk/governance_risk_watchlist.py
adds a small, explicitly-scoped, hand-verified flag - informational only, same non-invasive
precedent as the ROE distress-artifact flag (test_roe_distress_artifact_flag_20260911.py).
"""

import importlib

from algo.risk.governance_risk_watchlist import is_known_hfcaa_risk_adr

financials = importlib.import_module("lambda.api.routes.financials")
stock_details = importlib.import_module("lambda.api.routes.scores_handlers.stock_details")


class TestIsKnownHfcaaRiskAdr:
    def test_flagged_symbols(self):
        assert is_known_hfcaa_risk_adr("XYF") is True
        assert is_known_hfcaa_risk_adr("JFIN") is True

    def test_case_insensitive(self):
        assert is_known_hfcaa_risk_adr("xyf") is True

    def test_unflagged_symbol(self):
        assert is_known_hfcaa_risk_adr("NVDA") is False
        assert is_known_hfcaa_risk_adr("WTM") is False


def test_key_metrics_includes_governance_risk_flag():
    import inspect

    source = inspect.getsource(financials.handle)
    start = source.index('if endpoint == "key-metrics"')
    end = source.index("if endpoint ==", start + 1)
    block = source[start:end]
    assert "governance_risk_flag" in block
    assert "is_known_hfcaa_risk_adr" in block


def test_stock_details_includes_governance_risk_flag():
    import inspect

    source = inspect.getsource(stock_details._get_stock_details)
    assert "governance_risk_flag" in source
    assert "is_known_hfcaa_risk_adr" in source
