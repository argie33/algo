"""Zero-vs-real-component guards for SecEdgarStatementLoader.transform() (sec_base.py) -
extracted 2026-09-16 (goal: SEC-vs-yfinance divergence sweep) to keep sec_base.py under the
file-size ratchet's hard ceiling after this sweep's fixes, mechanical extraction only, no
behavior change.

All three guards close the same root-cause family: this loader's field_mapping resolves
multiple XBRL concepts onto one DB column with "first-populated-wins" / "fallback-only"
semantics, but several concepts represent one component of a multi-part total (one specific
debt instrument, one dividend class, one capex sub-category, one entity's legal-structure-
specific equity tag) rather than an alternate total for the same thing. A real "$0 of this
one component" fact was either unconditionally overwriting an already-resolved larger total
via ordinary last-processed-wins (a plain, non-fallback concept), or permanently blocking a
later, genuinely nonzero component via the fallback-only guard's "already in row" check,
which treats a stored 0 the same as a resolved real total.

Fields covered (per live SEC companyfacts JSON verification, 2026-09-16 sweep):
- long_term_debt/short_term_debt: subordinated_debt, advances_from_federal_home_loan_banks,
  senior_notes, notes_payable, unsecured_debt, FederalHomeLoanBankAdvancesLongTerm (BANR/
  AMTB/IBCP/MPB/CBNK/MYFW/PNBK).
- capex: payments_to_acquire_land, payments_to_acquire_other_productive_assets,
  payments_to_acquire_real_estate (DRH/NSC/SNPS/VICI).
- dividends_paid: PaymentsOfDividendsCommonStock vs PaymentsOfDividendsPreferredStockAnd
  PreferenceStock (CMCT) - genuinely additive, not alternatives; this loader has no
  per-field summing mechanism, so preserving the larger, already-resolved figure rather
  than zeroing it out is the safer of the two available options.
- cash_and_equivalents: CashAndCashEquivalentsAtCarryingValue is a permanently frozen $0
  across every fiscal year for CDIO/FAC/INDO/AKTX, overwriting the real, evolving combined
  cash+restricted-cash figure sec_balance_sheet.py's own design intended as a lower-fidelity
  fallback only.
- stockholders_equity: MembersEquity=0 (meant to be an LLC-only analogue, assumed mutually
  exclusive with StockholdersEquity per sec_balance_sheet.py's own comment) overwrote a
  real, correct StockholdersEquity for FLOC/INR/WBI.
- accounts_receivable: PED's real AccountsReceivableNet value was blocked by an earlier,
  real $0 under ReceivablesNetCurrent.
- income_tax_expense: BCSF's real InvestmentIncomeOperatingTaxExpenseBenefit (a BDC-specific
  concept) was blocked by an earlier, real $0 under IncomeTaxExpenseBenefit.
"""

from decimal import Decimal
from typing import Any

# Fields where a fallback-only concept's OWN real $0 must not permanently claim the slot -
# skip that first write (see is_zero_first_write_blocking_field) so a LATER, genuinely
# nonzero fallback concept still gets a chance; if nothing ever writes a nonzero value, the
# field honestly stays None rather than a confidently-wrong 0.
ZERO_FIRST_WRITE_GUARD_FIELDS = frozenset(
    {
        "long_term_debt",
        "short_term_debt",
        "capex",
        "accounts_receivable",
        "income_tax_expense",
        # ADDED 2026-09-16 (same sweep, second follow-up pass): RAVE (Rave Restaurant
        # Group, a franchisor) tags a real "CostOfRevenue" fact at $0/$1,000 (an
        # unrelated, near-zero line item for this filer) alongside a real, much larger
        # "FranchisorCosts" fact ($3,956,000 FY2023, exactly matching the yfinance-
        # flagged value) for the same fiscal year - same "unrelated concept's real $0/
        # near-0 permanently blocks a later, genuinely nonzero fallback concept" bug as
        # every other field in this set.
        "cost_of_revenue",
        # ADDED 2026-09-16 (same sweep): DTST tags a real "Dividends" bare-concept fact
        # at $0 (processed FIRST in sec_cash_flow.py's concept list, well before the
        # DividendsPreferredStock family) alongside real, nonzero
        # "DividendsPreferredStock" ($63,683) and "DividendsShareBasedCompensationCash"
        # ($1,179,357, the yfinance-matching figure) facts for the same fiscal year -
        # both later fallback-only concepts were permanently blocked by the earlier
        # real-$0 write, same bug shape as every other field in this set.
        "dividends_paid",
        # ADDED 2026-09-16 (same sweep): TITN tags a real "InterestAndDebtExpense" fact
        # at $0 (processed FIRST, fallback-only) alongside a real, nonzero
        # "FinancingInterestExpense" ($24,109,000 FY2026) - the earlier real-$0 write
        # blocked financing_interest_expense from ever populating interest_expense, which
        # in turn meant the interest_expense_other dual-concept sum (see sec_base.py's
        # transform()) summed against 0 instead of the real $24,109,000, silently
        # understating interest_expense by that whole amount. Same bug shape as every
        # other field in this set.
        "interest_expense",
    }
)

# Fields where a LATER write of exactly 0 (fallback-only OR plain) must never overwrite an
# ALREADY-resolved, genuinely nonzero total (see is_zero_overwrite_blocking_field). Never
# fires the reverse direction - a real nonzero value always still overwrites an existing 0.
ZERO_OVERWRITE_GUARD_FIELDS = frozenset(
    {
        "long_term_debt",
        "short_term_debt",
        "capex",
        "dividends_paid",
        "cash_and_equivalents",
        "stockholders_equity",
        # ADDED 2026-09-16 (same sweep, second follow-up pass): QS (QuantumScape) - the
        # real "IncomeTaxExpenseBenefit" concept correctly writes $1,544,000 FY2025
        # (matching the yfinance-flagged value), but sec_statements.py's
        # _fill_income_tax_expense_from_current_deferred_split() then computes a real $0
        # from CurrentIncomeTaxExpenseBenefit + DeferredIncomeTaxExpenseBenefit for this
        # filer and writes it directly to the SAME "income_tax_expense" identity key,
        # processed LAST in dict order, unconditionally overwriting the correct total via
        # plain (non-fallback) last-write-wins - same "component/derived-$0 blocks a real
        # total" bug shape as every other field in this set, just with a computed value
        # instead of a raw XBRL concept as the offending $0.
        "income_tax_expense",
    }
)


def redirect_secured_debt_for_reit(
    sec_field: str, db_field: str, symbol: str | None, reit_symbols: frozenset[str]
) -> str:
    """OLP (One Liberty Properties) live-confirmed via real SEC companyfacts JSON: the
    2026-09-09 "secured_debt" -> "short_term_debt" mapping (added on DE's evidence, where
    SecuredDebt is a smaller short-term-debt-adjacent sibling of DebtCurrent) is wrong for
    equity REITs, where SecuredDebt is the standard concept for their real estate mortgage
    debt - their PRIMARY long-term financing, not a short-term instrument. OLP's SecuredDebt
    grows steadily $396M (FY2021) -> $517M (FY2025), tracking total_assets ($753M -> $858M)
    the way a REIT's mortgage book should - completely implausible as "short-term debt" for
    an $858M-asset REIT. Redirects to long_term_debt for REIT-classified symbols only; DE
    and every other non-REIT filer keep the original short_term_debt mapping (returns
    db_field unchanged for them).
    """
    if sec_field == "secured_debt" and db_field == "short_term_debt" and symbol in reit_symbols:
        return "long_term_debt"
    return db_field


def is_zero_first_write_blocking_field(db_field: str, existing: Any, value: Any) -> bool:
    """True if a fallback-only concept's own real value (`value`) is nonzero and would be
    the first write for `db_field`, but the field's existing already-stored value happens to
    be an unrelated concept's real $0 - see ZERO_FIRST_WRITE_GUARD_FIELDS' module docstring
    for why a stored 0 must not block this write the way a stored nonzero total legitimately
    would.
    """
    return (
        db_field in ZERO_FIRST_WRITE_GUARD_FIELDS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) == 0.0
        and isinstance(value, (int, float, Decimal))
        and float(value) != 0.0
    )


def is_zero_overwrite_blocking_field(db_field: str, existing: Any, value: Any) -> bool:
    """True if `value` (the incoming concept's own real $0) would overwrite `db_field`'s
    already-resolved, genuinely nonzero `existing` value - see ZERO_OVERWRITE_GUARD_FIELDS'
    module docstring for why this must be blocked regardless of the incoming concept's
    fallback_only status.
    """
    return (
        db_field in ZERO_OVERWRITE_GUARD_FIELDS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) != 0.0
        and isinstance(value, (int, float, Decimal))
        and float(value) == 0.0
    )


# (db_field, sec_field) pairs where the two concepts are genuinely distinct, additive
# components of the same total rather than alternates for the same fact - extracted here
# 2026-09-17 (moved out of sec_base.py to stay under the file-size ratchet's hard ceiling
# after the TITN addition, mechanical extraction only, no behavior change). Both pairs were
# live-confirmed via real SEC companyfacts JSON to co-occur in the same fiscal year for the
# named filer, each under its own distinct XBRL concept, summing to (or very near) the
# yfinance-flagged total:
# - capex: payments_to_acquire_oil_and_gas_property + payments_to_explore_and_develop_oil_
#   and_gas_properties (CRGY FY2025: $818.9M acquisition + $951.0M E&D).
# - interest_expense: financing_interest_expense (mapped to interest_expense) +
#   interest_expense_other (TITN FY2026: $24,109,000 + $18,974,000 = $43,083,000, exactly
#   matching yfinance; FY2025: $34,710,000 + $15,105,000 = $49,815,000).
# - ppe_net: property_plant_and_equipment_net + mineral_properties_net (mining filers'
#   sector-specific real net property asset, distinct from and additive to a small remaining
#   corporate PP&E balance) / property_plant_and_equipment_net + oil_and_gas_property_
#   successful_effort_method_net (O&G filers' equivalent). ADDED 2026-09-17 (goal:
#   divergence-repair trend-break sweep) - live-confirmed via real SEC companyfacts JSON:
#   THM (International Tower Hill Mines, CIK 0001134115) FY2025: MineralPropertiesNet
#   $55,375,124 + PropertyPlantAndEquipmentNet $7,465 = $55,382,589, an EXACT match to
#   yfinance's flagged $55,382,589 - proves these are genuinely additive components (mineral
#   rights vs. corporate office equipment), not alternates. PZG (Paramount Gold Nevada, CIK
#   0001629210) same pattern. RRC (Range Resources, CIK 0000315852) FY2025:
#   OilAndGasPropertySuccessfulEffortMethodNet $6,708,366,000 + PropertyPlantAndEquipmentNet
#   $4,935,000 = $6,713,301,000, same ballpark as yfinance's $6,886,743,000 (small residual
#   gap plausibly right-of-use/other assets yfinance includes that we don't track here). HPK
#   (HighPeak Energy, CIK 0001792849) same pattern. Initially wired as fallback-only, which
#   was wrong (the plain concept legitimately has real, small data for these filers, so
#   fallback-only's "only fill if nothing else found" ordering let the standard concept
#   silently overwrite the larger sector value on later processing) - corrected to additive
#   same session, before landing, after a reload produced zero DB change and exposed the bug.
# sec_base.py's transform() has no per-field summing mechanism for _aggregate_concepts (each
# concept keeps its own distinct snake_case key there) - the collision happens where
# field_mapping resolves both concepts onto the same db_field, and ordinary last-listed-wins
# would otherwise silently discard whichever processed first, understating the total.
ADDITIVE_CONCEPT_PAIRS = frozenset(
    {
        ("capex", "payments_to_acquire_oil_and_gas_property"),
        ("capex", "payments_to_explore_and_develop_oil_and_gas_properties"),
        ("interest_expense", "interest_expense_other"),
        ("ppe_net", "property_plant_and_equipment_net"),
    }
)


def is_additive_concept_pair(db_field: str, sec_field: str, existing: Any, value: Any) -> bool:
    """True if `sec_field` is a known-additive component for `db_field` (see
    ADDITIVE_CONCEPT_PAIRS) and both the already-resolved `existing` value and the incoming
    `value` are real numbers - i.e. this is a genuine sum-instead-of-overwrite case, not a
    first write.
    """
    return (
        (db_field, sec_field) in ADDITIVE_CONCEPT_PAIRS
        and isinstance(existing, (int, float, Decimal))
        and isinstance(value, (int, float, Decimal))
    )
