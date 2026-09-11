"""Regression test for the 2026-09-11 fix: the non-operating-company exclusion regex
(three copies - utils/loaders/helpers.py's NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE,
its inline get_active_symbols() literal, and lambda/api/routes/scores_handlers/coverage.py's
_NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) excluded Warrant/Unit/Preferred/etc. by name
but had no term for "Right"/"Rights", letting SPAC rights-offering securities (e.g. AMPGR
"Amplitech Group, Inc. - Series A Right", ~110 similar "- Rights"/"- Right" symbols) pass
through and get scored like real operating companies.

Found live-confirmed all 110 were already active=false via load_market_constituents.py's
separate SPAC detection, so this fix is currently inert in production (doesn't change any
live-scored row) - but it closes a real gap for any future rights security that reactivates
or evades that separate detector. The fix uses a negative lookbehind (`(?<!the )`) so it
does NOT catch legitimate ADRs whose descriptive text includes "...representing the right
to receive..." (AMX/RLX/WDH) - PostgreSQL's regex engine supports lookbehind (unlike
Python's `re` module's variable-width restriction), live-confirmed against the real DB.
"""

import importlib
import re

import utils.loaders.helpers as helpers_module

coverage_module = importlib.import_module("lambda.api.routes.scores_handlers.coverage")

# helpers.py's two copies are checked against the raw *source text* (regex backslashes are
# doubled on disk, e.g. `\\y`, since they live inside a Python string literal there too).
_RIGHTS_EXCLUSION_FRAGMENT_SOURCE = "(?<!the )\\\\yRights?\\\\y"
# coverage.py's copy is checked against the already-evaluated runtime string value, where
# Python has collapsed that same source-level `\\y` down to a single-backslash `\y`.
_RIGHTS_EXCLUSION_FRAGMENT_RUNTIME = "(?<!the )\\yRights?\\y"


def test_rights_exclusion_fragment_present_in_all_three_copies() -> None:
    helpers_source = helpers_module.__file__
    with open(helpers_source, encoding="utf-8") as f:
        helpers_text = f.read()

    assert helpers_text.count(_RIGHTS_EXCLUSION_FRAGMENT_SOURCE) == 2, (
        "expected the Rights exclusion in both utils/loaders/helpers.py copies "
        "(NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE and the inline get_active_symbols() "
        "literal) - grep NON_OPERATING_COMPANY_EXCLUSION_SQL to find both"
    )

    assert _RIGHTS_EXCLUSION_FRAGMENT_RUNTIME in coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE


def test_rights_regex_semantics_against_known_symbols() -> None:
    # Python's `re` doesn't support PostgreSQL's `\y` word-boundary atom, so translate to
    # `\b` for this pure-semantics check (the actual SQL runs through Postgres, verified
    # live separately) - `\b` and `\y` agree on all the cases exercised here.
    pattern = re.compile(r"(?<!the )\bRights?\b", re.IGNORECASE)

    real_rights_securities = [
        "Amplitech Group, Inc. - Series A Right",
        "ClearThink 1 Acquisition Corp. - Rights",
        "Drugs Made In America Acquisition II Corp. - Right",
    ]
    for name in real_rights_securities:
        assert pattern.search(name), f"expected {name!r} to be caught by the Rights exclusion"

    legitimate_adrs = [
        "America Movil, S.A.B. de C.V. American Depositary Shares "
        "(each representing the right to receive twenty (20) Series B Shares",
        "RLX Technology Inc. American Depositary Shares, each representing the right to "
        "receive one (1) Class A ordinary share",
        "Waterdrop Inc. American Depositary Shares (each representing the right to receive 10 Class A Ordinary Shares)",
    ]
    for name in legitimate_adrs:
        assert not pattern.search(name), f"expected {name!r} to be SPARED by the Rights exclusion"
