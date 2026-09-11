"""Regression test for the 2026-09-10 missing-SEC/XBRL-under-300 push: CCZ ("Comcast
Holdings ZONES", a Zero-premium Exchangeable Note - not common equity) was falling to
load_company_info_sec.py's generic "shares_outstanding_not_in_xbrl_or_filing_text"
(Missing SEC/XBRL data) purely because there is no dei:EntityCommonStockSharesOutstanding
fact for a debt-like instrument - a permanent structural fact, not a resolvable gap.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_preferred_or_debt_security_no_shares_outstanding_categorizes_as_legitimate():
    assert (
        scores_mod._categorize_reason("preferred_or_debt_security_no_shares_outstanding")
        == "Legitimate / not applicable"
    )
