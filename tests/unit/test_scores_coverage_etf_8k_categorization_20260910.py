"""Regression test for the 2026-09-10 missing-SEC/XBRL-under-300 push: AGG/IWM (registered
ETFs, confirmed in `etf_symbols`) were falling to load_current_reports_8k.py's generic
"symbol_not_found" (Missing SEC/XBRL data) because an ETF share class is registered under
its issuing Trust's own CIK and never appears in SEC's ticker files under the traded ETF
ticker at all. That's a permanent Investment-Company-Act-vs-Exchange-Act exemption (ETFs
file N-1A/485BPOS, never Form 8-K) - the same class of fact etf_trust_no_gaap_financials
already recognizes elsewhere, not a resolvable data gap.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_etf_no_8k_filings_categorizes_as_legitimate():
    assert scores_mod._categorize_reason("etf_no_8k_filings") == "Legitimate / not applicable"
