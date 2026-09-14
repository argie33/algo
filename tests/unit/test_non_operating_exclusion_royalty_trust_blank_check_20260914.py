"""Regression test for the 2026-09-14 fix: NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE (and
its two sibling copies - coverage.py's _NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE and
get_active_symbols()'s inline non_operating_exclusion_sql) gates the SCORING z-score
peer-group population every per-symbol fetch and batch sector-neutral recompute pass uses -
a separate, narrower exclusion list than algo/signals/investable_universe.py's
investable_universe_conditions(), which only gates the leaderboard/live-trading-candidate
DISPLAY layer.

Before this fix, a genuine pass-through royalty trust like CRT (Cross Timbers Royalty Trust,
a real SEC 10-K filer with entity_type='operating', so it isn't caught by the existing
zero-SIC/other-entity-type check) still got a real quality_score computed and counted in the
Energy sector's z-score peer group - live-confirmed topping the Quality leaderboard at
quality_score=90.96 off roe=208%/roa=104%/roce=205%/asset_turnover=133%, ratios a near-zero
invested-capital balance sheet mechanically produces and no real operating company could
match. This also skews the z-score mean/stdev for every genuine Energy company sharing that
peer group, not just the trust's own (harmless downstream, since investable_universe_
conditions() hides it from every display) score.

Mirrors investable_universe_conditions()'s already-vetted, self-updating conditions exactly:
SIC 6792/6795 + "Trust" in the name (so TPL/LandBridge/EagleRock/Royal Gold/SSR Mining/Scully
Royalty/Versamet/Triple Flag, the real operating companies sharing those legacy SIC codes,
correctly stay included - see royalty_trust_cef_exclusion_overcorrection_fixed_20260914 memory
for the original TPL false-positive this mirrors; SIC 6795 found live while verifying this fix
- MSB/Mesabi Trust is the identical shape one SIC code over), and SIC 6770 + zero reported
annual revenue (so a completed de-SPAC like INV stays included).
"""

import importlib

import utils.loaders.helpers as helpers_module

coverage_module = importlib.import_module("lambda.api.routes.scores_handlers.coverage")

_ROYALTY_TRUST_FRAGMENT = (
    "s.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6792)\n"
    "                                    AND s.security_name ~* 'Trust'"
)
_BLANK_CHECK_FRAGMENT = "sic_code = 6770"


def test_royalty_trust_condition_present_in_all_three_copies() -> None:
    assert "sic_code IN (6792, 6795)" in helpers_module.NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
    assert "~* 'Trust'" in helpers_module.NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE

    with open(helpers_module.__file__, encoding="utf-8") as f:
        helpers_text = f.read()
    assert helpers_text.count("sic_code IN (6792, 6795)") == 2, (
        "expected the royalty-trust SIC-6792/6795 condition in both "
        "NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE and get_active_symbols()'s inline "
        "non_operating_exclusion_sql - grep NON_OPERATING_COMPANY_EXCLUSION_SQL to find both"
    )

    assert "sic_code IN (6792, 6795)" in coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
    assert "~* 'Trust'" in coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE


def test_blank_check_spac_condition_present_in_all_three_copies() -> None:
    with open(helpers_module.__file__, encoding="utf-8") as f:
        helpers_text = f.read()
    assert helpers_text.count(_BLANK_CHECK_FRAGMENT) == 2, (
        "expected the blank-check-SPAC SIC-6770 condition in both "
        "NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE and get_active_symbols()'s inline "
        "non_operating_exclusion_sql - grep NON_OPERATING_COMPANY_EXCLUSION_SQL to find both"
    )
    assert "annual_income_statement WHERE revenue > 0" in helpers_module.NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
    assert _BLANK_CHECK_FRAGMENT in coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
    assert "annual_income_statement WHERE revenue > 0" in coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE


def test_exclusion_template_still_formats_cleanly() -> None:
    # Guards against a stray unescaped `{`/`}` breaking .format() for existing callers -
    # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's only placeholders are
    # {symbols_alias}/{company_info_alias}, both supplied by every real caller.
    formatted = helpers_module.NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(
        symbols_alias="su", company_info_alias="cis"
    )
    assert "su.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code IN (6792, 6795))" in formatted
    assert "su.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6770)" in formatted

    formatted_coverage = coverage_module._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(
        symbols_alias="su", company_info_alias="cis"
    )
    assert "su.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code IN (6792, 6795))" in formatted_coverage
