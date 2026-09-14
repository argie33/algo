"""Scale-mismatch guard for REIT-exclusive income-statement concepts, extracted from
sec_base.py (2026-09-13, file-size ratchet: that file sits at the 2000-line hard ceiling,
zero growth tolerance - see check_file_size_ratchet.py).

BUG FOUND 2026-09-13 (goal session: quarterly-revenue-identity backlog, MKZR live-confirmed
via real SEC companyfacts JSON): sec_base.py transform()'s `_reit_exclusive_fields` branch
(operating_lease_lease_income/real_estate_revenue_net) has no scale-sanity check at all,
unlike the general priority chain's own `_reject_scale_mismatched_revenue`
(financial_statements_value_validation.py). A REIT-exclusive concept's real-world source data
isn't immune to the same filer-side XBRL scale-tagging error TYGO already demonstrated for the
general chain (see that method's own docstring) - MKZR's real FY2025 Q2 10-Q genuinely tags
OperatingLeaseLeaseIncome at exactly 1,000,000x its own correctly-scaled
RevenueFromContractWithCustomerExcludingAssessedTax value ($8,030,316,000,000 vs $8,030,316 for
the identical period) - not an extraction-side bug, SEC's own raw companyfacts JSON carries the
inflated figure verbatim. Because this concept is processed before its ASC-606 sibling (that
one is REIT-fallback-only, sorted to the END of sec_base.py's `ordered_fields`), the garbage
value wins "revenue" first, then the REIT-fallback magnitude guard (which treats "existing
value already larger" as "don't shrink a more complete total") backwards protects the
1,000,000x-inflated garbage from ever being corrected.

Checked against ANY other raw sec_field already present on the row that also targets the same
db_field - not hardcoded to one specific concept name, so it generalizes to
real_estate_revenue_net (this set's other member) too.
"""

from decimal import Decimal
from typing import Any


def should_skip_reit_only_fallback_field(
    sec_field: str,
    db_field: str,
    value: Any,
    row: dict[str, Any],
    r: dict[str, Any],
    reit_only_fallback_fields: frozenset[str],
    reit_symbols: frozenset[str],
    insurance_symbols: frozenset[str],
    depository_institution_symbols: frozenset[str],
) -> bool:
    """True if a REIT/insurance/depository-institution filer's real "revenue" (already
    populated by an earlier concept) must not be overwritten by a minor ASC-606
    contract-revenue fallback concept.

    FIXED 2026-08-03/2026-08-09 (REIT case): equity REITs' real revenue (mostly lease
    income, out of ASC 606's scope) is silently clobbered by a small non-lease fee-income
    line under the ASC-606 tag unless this fallback-only gate protects it.

    FIXED 2026-08-22 (insurance/depository cases, real-money-readiness audit): same failure
    shape, different industry trigger. Insurance premiums/investment income (MCY: real
    Revenues=$5.99B vs. a $29.6M ASC-606 fee line) and bank net-interest-income-plus-fees
    (WAFDP: real interest_and_dividend_income_operating=$607.1M/$671.5M vs. a $25.9M/$24.9M
    ASC-606 fee line, 40 more symbols sharing this signature - ALLY, AMTB, AUBN, ...) are both
    out of ASC 606's scope the same way REIT lease income is.

    WIDENED 2026-09-01 (recovered from the growth-multi-input-blend worktree): the skip used
    to be unconditional once "revenue" held ANY value, on the assumption whatever got there
    first for a confirmed REIT/insurer/bank is always more authoritative. Live-confirmed false
    via CLDT (Chatham Lodging Trust, a hotel REIT): its real ASC-606 total ($295,871,000)
    was blocked by an unrelated, tiny investment_income_interest_and_dividend fact ($51,000)
    that happened to sit earlier in insertion order. A magnitude check (only protect the
    existing value if it isn't already SMALLER than the incoming ASC-606 candidate) fixes
    CLDT without touching the WAFDP/AMTB bank case (there the existing $607.1M interest
    income is already larger than the $25.9M ASC-606 fee, so the magnitude check still
    protects it exactly as before).
    """
    if not (sec_field in reit_only_fallback_fields and db_field in row):
        return False
    symbol = r.get("symbol")
    if not (symbol in reit_symbols or symbol in insurance_symbols or symbol in depository_institution_symbols):
        return False
    existing = row[db_field]
    if (
        isinstance(existing, (int, float, Decimal))
        and isinstance(value, (int, float, Decimal))
        and float(existing) < float(value)
    ):
        return False
    return True


def reject_reit_exclusive_scale_mismatch(
    table_name: str,
    sec_field: str,
    value: Any,
    db_field: str,
    r: dict[str, Any],
    field_mapping: dict[str, str],
    logger: Any,
) -> Any:
    """Return `value` unchanged, or None if it's a clean power-of-10 (100x-1,000,000x) scale
    mismatch against another same-row raw concept targeting the same db_field."""
    if not (isinstance(value, (int, float, Decimal)) and float(value) != 0):
        return value
    for sibling_field, sibling_value in r.items():
        if (
            sibling_field == sec_field
            or field_mapping.get(sibling_field) != db_field
            or not isinstance(sibling_value, (int, float, Decimal))
            or float(sibling_value) == 0
        ):
            continue
        ratio = abs(float(value)) / abs(float(sibling_value))
        if ratio < 1:
            ratio = 1 / ratio
        if any(abs(ratio - power) / power < 0.01 for power in (100, 1000, 10000, 100000, 1000000)):
            logger.warning(
                f"[{table_name}] {r.get('symbol')}: REIT-exclusive concept '{sec_field}'="
                f"{value:,} is a {ratio:.0f}x-scaled outlier vs. sibling concept "
                f"'{sibling_field}'={sibling_value:,} for the same period - filer-side XBRL "
                "scale-tagging error, not a real business figure. Rejecting rather than "
                "storing a confidently-wrong value."
            )
            return None
    return value


def should_override_fallback_field_for_depository_institution(
    sec_field: str,
    db_field: str,
    value: Any,
    row: dict[str, Any],
    r: dict[str, Any],
    depository_institution_symbols: frozenset[str],
) -> bool:
    """True if a bank/depository-institution's real interest-income revenue concept -
    processed as plain fallback-only, LATE in sec_income_statement.py's concept list -
    should be allowed to OVERWRITE an already-populated "revenue" set earlier by a
    smaller concept (typically an ASC-606 contract-revenue concept, but not exclusively -
    magnitude-gated regardless of which field wrote first).

    FIXED 2026-09-13 (goal session: "patrols and checks" comprehensiveness audit, AX/Axos
    Financial live-confirmed via real SEC companyfacts JSON): ASC 606 explicitly excludes
    interest income from its scope, so for a bank/thrift/depository institution,
    RevenueFromContractWithCustomer(Including|Excluding)AssessedTax only ever captures a
    minor non-interest fee-income line, never the real total - same conceptual failure as
    the already-fixed REIT/insurance/depository case in should_skip_reit_only_fallback_field
    above, but the REVERSE processing order: that guard protects a real total found FIRST
    from a smaller ASC-606 concept found later; here, the ASC-606 concept (or, for FBNC's
    shape, a small "Revenues" tag) is found FIRST and wins "revenue" via the ordinary
    priority chain before the real, larger interest-income concept is ever reached - which
    then just defers, being plain fallback-only with no magnitude check. AX's real FY2022
    revenue (InterestAndDividendIncomeOperating) is $659,728,000 vs. $59,434,000 under
    RevenueFromContractWithCustomerExcludingAssessedTax - understating annual revenue ~11x
    for 9 straight fiscal years (2018-2026) with no data_unavailable/reason flag anywhere.
    Magnitude-gated (only overrides when genuinely larger) so this cannot regress a
    depository institution that legitimately has a larger, complete revenue figure of its
    own under whichever concept happened to be processed first.
    """
    if sec_field not in ("interest_and_dividend_income_operating", "interest_income_operating"):
        return False
    if r.get("symbol") not in depository_institution_symbols:
        return False
    existing = row.get(db_field)
    if not (
        isinstance(existing, (int, float, Decimal)) and isinstance(value, (int, float, Decimal)) and float(value) > 0
    ):
        return False
    return float(value) > float(existing)
