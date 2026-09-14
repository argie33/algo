"""FIX (goal: "under 500" missing-XBRL push, 2026-09-10): compute_quality_row_level_reason's
early-return path (fires when every core quality ratio is None) fell through to the generic
"no_recent_balance_sheet_data_reported" ("Missing SEC/XBRL data") reason even for symbols the
balance-sheet loader itself had already identified as a genuine REIT/special-entity with zero
filings on record (loaders/helpers/sec_base.py's `_no_data_reason` writes
"no_annual_balance_data_in_sec_edgar_reit_or_special_entity" as annual_balance_sheet.reason for
exactly this case). Live-confirmed BIOT/IMC/PSQL/RPGL all showed the stale generic reason
despite the balance-sheet loader having already recorded the structural fact. Fixed by checking
_get_reit_or_special_entity_no_balance_data_symbols() (vqg_quality_recategorize.py) before the
generic fallback, same "Legitimate / not applicable" bucket as the sibling
etf_trust_no_gaap_financials/reit_special_entity categories.
"""

from loaders.helpers.vqg_shared import compute_quality_row_level_reason


def test_reit_or_special_entity_gate_wins_over_generic_fallback():
    reason = compute_quality_row_level_reason(
        "BIOT",
        None,
        None,
        frozenset(),
        frozenset(),
        frozenset({"BIOT"}),
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset({"BIOT"}),
    )
    assert reason == "reit_special_entity"


def test_generic_fallback_still_applies_when_not_reit_special_entity():
    reason = compute_quality_row_level_reason(
        "ACME",
        None,
        None,
        frozenset(),
        frozenset(),
        frozenset({"ACME"}),
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset(),
    )
    assert reason == "no_recent_balance_sheet_data_reported"


def test_reit_or_special_entity_param_defaults_to_empty_no_regression():
    reason = compute_quality_row_level_reason(
        "ACME",
        None,
        None,
        frozenset(),
        frozenset(),
        frozenset({"ACME"}),
        frozenset(),
        frozenset(),
        frozenset(),
    )
    assert reason == "no_recent_balance_sheet_data_reported"
