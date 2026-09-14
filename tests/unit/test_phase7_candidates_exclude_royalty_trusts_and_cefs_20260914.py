"""Regression test: `_get_candidates_from_buysell` (the real trade-candidate query) excludes
oil/gas royalty trusts and closed-end funds via the shared `investable_universe_conditions()`
helper.

Found 2026-09-14 (`/goal` session, adversarial leaderboard audit): this is the LIVE TRADING
candidate query - the one that decides what the algorithm can actually buy - and it only ever
excluded `etf_symbols`, never adopting `algo/signals/investable_universe.py`'s shared helper
(extracted 2026-09-13, already used by the `/api/scores` leaderboard endpoint and sector/
industry rankings). Oil/gas royalty trusts (PBT, TPL, SBR) ranked #2/#4/#6 of the entire
quality_score leaderboard - their near-zero invested-capital balance sheets mechanically
produce ROE/ROCE/asset-turnover ratios of 100-200%+, not genuine business quality - meaning a
sufficiently strong technical BUY signal on one of these could have looked like a legitimate
high-composite-score trade candidate. Fixed by joining `stock_symbols` and using
`investable_universe_conditions("ss", "sy")` in place of the bare `etf_symbols` check - this
also adds a real `sy.active = true` requirement that didn't exist before (a delisted symbol
could otherwise still clear every other filter here).
"""

import inspect

from algo.orchestrator.phase7_signal_generation import _get_candidates_from_buysell
from algo.signals.investable_universe import investable_universe_conditions


def test_query_joins_stock_symbols_and_calls_shared_investable_universe_helper():
    src = inspect.getsource(_get_candidates_from_buysell)
    assert "JOIN stock_symbols sy ON sy.symbol = bsd.symbol" in src
    assert "investable_universe_conditions(" in src
    assert '"ss", "sy"' in src


def test_shared_helper_actually_excludes_royalty_trusts_and_cefs():
    """Directly verifies the fragment this query splices in still carries the SIC-based
    royalty-trust/SPAC exclusion and the closed-end-fund exclusion - a change to
    investable_universe_conditions() that silently dropped one of these would otherwise not
    be caught by the source-text check above (which only confirms the call is present, not
    what it returns)."""
    fragment = investable_universe_conditions("ss", "sy")
    assert "6792" in fragment, "SIC 6792 (Oil Royalty Traders) exclusion must be present"
    assert "has_annual_report_filing" in fragment, "closed-end-fund exclusion must be present"
    assert "sy.active = true" in fragment
