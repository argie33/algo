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
    {"long_term_debt", "short_term_debt", "capex", "accounts_receivable", "income_tax_expense"}
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
