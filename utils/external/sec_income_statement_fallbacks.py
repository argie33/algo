"""Income-statement fallback post-processing helpers, extracted from
utils/external/sec_income_statement.py (2026-09-05, file-size ratchet: that file exceeded
the 800-line new-file cap once first split out of sec_statements.py, needing a further
split). Bodies are verbatim, no logic changed - only moved file. Each of these fires after
get_income_statement()'s primary _aggregate_concepts() extraction, filling gaps that
extraction's one-column "last value wins" merge can't express (continuing/discontinued EPS
split, dual-class dimensional EPS/shares, income tax current+deferred split, validated
pretax-income promotion, and derived operating income).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _fill_earnings_per_share_from_continuing_discontinued_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: earnings_per_share_{basic,diluted} = ...FromContinuingOperations +
    ...FromDiscontinuedOperations, for IFRS filers (IAS 33.68) that only tag the
    continuing/discontinued EPS split rather than a single combined concept - see the
    _INCOME_IFRS_ALIASES comment above these four concepts for the live-confirmed TV
    (Grupo Televisa) case this recovers. Same "fallback-only, sum two real parts, never
    overwrite a real combined value" pattern as
    _fill_long_term_debt_from_noncurrent_current_split below. Discontinued defaults to 0
    when absent (most filers most years have none, and the taxonomy only requires a
    Discontinued tag when discontinued operations are real) rather than leaving the whole
    figure NULL for the common case of a filer that only ever tags the Continuing concept.

    Also falls diluted back into the basic-only "earnings_per_share_basic" key (downstream
    field_mapping's sole source for annual_income_statement.earnings_per_share - see
    load_financial_statements.py's _FIELD_MAPPING) when a filer tags no Basic-shaped EPS
    concept at all, TV's case: it tags only the Diluted split, never Basic in any form.
    Diluted is a close, honestly-approximate stand-in for Basic (differs only by the
    dilutive effect of options/convertibles) - the same "blended figure beats permanently
    NULL" judgment this file already makes for
    WeightedAverageNumberOfShareOutstandingBasicAndDiluted share-count filers. Only fires
    when a filer has no real Basic-shaped fact of its own; a filer reporting genuine Basic
    EPS keeps it untouched.
    """
    for row in rows:
        basic_cont = row.pop("earnings_per_share_basic_continuing", None)
        basic_disc = row.pop("earnings_per_share_basic_discontinued", None)
        if row.get("earnings_per_share_basic") is None and basic_cont is not None:
            row["earnings_per_share_basic"] = basic_cont + (basic_disc or 0)

        diluted_cont = row.pop("earnings_per_share_diluted_continuing", None)
        diluted_disc = row.pop("earnings_per_share_diluted_discontinued", None)
        if row.get("earnings_per_share_diluted") is None and diluted_cont is not None:
            row["earnings_per_share_diluted"] = diluted_cont + (diluted_disc or 0)

        if row.get("earnings_per_share_basic") is None and row.get("earnings_per_share_diluted") is not None:
            row["earnings_per_share_basic"] = row["earnings_per_share_diluted"]


def _fill_eps_shares_from_dual_class_dimensional_facts(
    rows: list[dict[str, Any]], client: Any, symbol: str, security_name: str | None = None
) -> None:
    """Last-resort fallback: recover EPS/weighted-average-share facts tagged only under a
    us-gaap:StatementClassOfStockAxis dimensional context, for symbols whose own share class
    is determinable either from a dot-suffix ticker (BRK.A/BRK.B, CRD.A/CRD.B, GTN.A, GEF.B,
    ...) or, for a bare ticker, from `security_name` stating the class explicitly (e.g. "Greif
    Inc. Class A Common Stock" for GEF) - see resolve_class_letter's docstring. `security_name`
    is optional and defaults to None (dot-suffix-only resolution) so this stays callable with
    no DB access; loaders/helpers/sec_base.py (which already does per-run bulk DB lookups like
    _get_reit_symbols) is the intended source when it's available.

    See loaders/helpers/sec_dual_class_eps.py's module docstring (Berkshire live-confirmed
    2026-09-02) for why no concept alias can ever close this gap - same root cause family as
    _fill_long_term_debt_from_segment_dimensional_facts above, different axis/concepts. Only
    fires for a fiscal year still missing ANY of the 4 target fields after every tier above;
    never overwrites a real value. Bounded to the most recent 3 missing fiscal years per
    symbol, same rationale as the debt fallback's identical cap (live scoring only reads the
    latest 1-2 annual rows; an unbounded scan of a symbol's full history risks the same
    zombie-thread/rate-limiter contention already found and fixed there).
    """
    from loaders.helpers.sec_dual_class_eps import extract_dual_class_eps_shares, resolve_class_letter
    from loaders.helpers.sec_segment_debt import find_10k_for_fiscal_year

    class_letter = resolve_class_letter(symbol, security_name)
    if class_letter is None:
        return

    target_fields = (
        "earnings_per_share_basic",
        "earnings_per_share_diluted",
        "weighted_average_number_of_shares_outstanding_basic",
        "weighted_average_number_of_diluted_shares_outstanding",
    )
    all_missing_years = [
        row["fiscal_year"] for row in rows if row.get("fiscal_year") and any(row.get(f) is None for f in target_fields)
    ]
    if not all_missing_years:
        return
    missing_years = sorted(set(all_missing_years), reverse=True)[:3]

    try:
        cik = client.symbol_to_cik(symbol)
        submissions = client.get_submissions(cik)
    except Exception:
        logger.debug(
            f"[DUAL_CLASS_EPS] {symbol}: could not fetch submissions for dual-class EPS fallback", exc_info=True
        )
        return

    field_map = {
        "eps_basic": "earnings_per_share_basic",
        "eps_diluted": "earnings_per_share_diluted",
        "shares_basic": "weighted_average_number_of_shares_outstanding_basic",
        "shares_diluted": "weighted_average_number_of_diluted_shares_outstanding",
    }

    for row in rows:
        if row.get("fiscal_year") not in missing_years or not any(row.get(f) is None for f in target_fields):
            continue
        located = find_10k_for_fiscal_year(submissions, int(row["fiscal_year"]))
        if located is None:
            continue
        accession, period_end = located
        try:
            xml_text = client.get_filing_xml(cik, accession, "10-K")
        except Exception:
            logger.debug(
                f"[DUAL_CLASS_EPS] {symbol} FY{row['fiscal_year']}: could not fetch instance XML "
                f"({accession}) for dual-class EPS fallback",
                exc_info=True,
            )
            continue
        result = extract_dual_class_eps_shares(xml_text, class_letter, period_end)
        if not result:
            continue
        filled = []
        for src_key, dest_key in field_map.items():
            if row.get(dest_key) is None and src_key in result:
                row[dest_key] = result[src_key]
                filled.append(dest_key)
        if filled:
            logger.info(
                f"[DUAL_CLASS_EPS] {symbol} FY{row['fiscal_year']}: recovered {filled} via class "
                f"'{class_letter}' StatementClassOfStockAxis dimensional match ({accession})"
            )


def _fill_income_tax_expense_from_current_deferred_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: income_tax_expense = CurrentIncomeTaxExpenseBenefit +
    DeferredIncomeTaxExpenseBenefit.

    Only fires when the primary "income_tax_expense" column (from the plain
    "IncomeTaxExpenseBenefit" concept, fetched above) is still empty for that fiscal year -
    never overwrites a real value. Unlike the long_term_debt Noncurrent/Current split above,
    BOTH components must be present to fire (a filer with only one half tagged genuinely
    hasn't reported its total tax provision that way, unlike LongTermDebtCurrent's "0 if
    absent" convention - a missing current-or-deferred component is not safely assumed to be
    zero the way an untagged current-debt-maturity often genuinely is). Mutates rows in
    place and always strips both raw keys.
    """
    for row in rows:
        current = row.pop("current_income_tax_expense_benefit", None)
        deferred = row.pop("deferred_income_tax_expense_benefit", None)
        if row.get("income_tax_expense") is not None or current is None or deferred is None:
            continue
        row["income_tax_expense"] = current + deferred


def _fill_pretax_income_from_results_of_operations_when_validated(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: pretax_income from "ResultsOfOperationsIncomeBeforeIncomeTaxes", but ONLY
    when it exactly matches the independently-known net_income + income_tax_expense identity
    for that same fiscal year.

    This concept is genuinely ambiguous per-filer - live-confirmed CNX Resources tags it as an
    ASC 932 oil-and-gas-producing-activities supplementary disclosure (NOT consolidated pretax
    income), while RRC (Range Resources, same SIC 1311 E&P classification) tags the identical
    concept name as its REAL consolidated pretax income. Rather than guessing which meaning a
    given filer uses, cross-validate the filer's OWN tagged value against its own already-known
    net_income/income_tax_expense for that year - only promote it when they agree exactly (both
    values, being independently-sourced real SEC facts, should match to the dollar when the
    concept really is consolidated pretax income; a supplementary sub-figure like CNX's won't).
    Never overwrites a real "pretax_income" value already resolved from the primary concepts
    above. Mutates rows in place and always strips the raw candidate key.
    """
    for row in rows:
        candidate = row.pop("results_of_operations_income_before_income_taxes", None)
        if row.get("pretax_income") is not None or candidate is None:
            continue
        net_income = row.get("net_income_loss")
        tax = row.get("income_tax_expense")
        if net_income is None or tax is None:
            continue
        if candidate == net_income + tax:
            row["pretax_income"] = candidate


def _fill_pretax_income_from_domestic_foreign_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: pretax_income = IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic
    + ...Foreign, validated against the independently-known net_income + income_tax_expense
    identity for that same fiscal year before being trusted - same validation discipline as
    _fill_pretax_income_from_results_of_operations_when_validated above.

    ADDED 2026-09-06 (goal session: tie-out-checker follow-up on the pretax_to_net_income
    magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/tie_out.py's Round 2
    docstring). Live-confirmed via real SEC companyfacts JSON: ORCL/MCD/PYPL/PSX all tag a
    real Domestic/Foreign pretax-income split (ASC 740-10-50-11's required disclosure) but
    either stopped tagging the combined "...MinorityInterestAnd..."/"...ExtraordinaryItems..."
    total this file's concepts list otherwise relies on (ORCL/MCD - zero entries for the
    combined concept in recent years), or simply have no populated recent entry for it (PYPL/
    PSX - the concept exists in their taxonomy but carries no values for the years checked).
    Domestic alone (this file used to map it straight to "pretax_income" via
    load_financial_statements.py's field_mapping, unconditionally, with no validation at all)
    silently understated these global companies' real pretax income by their entire
    foreign-sourced share: ORCL FY2025 Domestic=$4.376B/Foreign=$9.784B, sum=$14.160B exactly
    equals net_income($12.443B)+income_tax_expense($1.717B) - the stale Domestic-only value
    ($4.376B) was less than a third of the real total. PYPL FY2024 Domestic=$946M/
    Foreign=$4.383B, sum=$5.329B exactly equals net_income($4.147B)+income_tax_expense($1.182B).

    Deliberately validated (not a blind sum) so a filer whose Domestic concept means something
    narrower than ASC 740's standard split - the same genuine per-filer-ambiguity risk
    _fill_pretax_income_from_results_of_operations_when_validated's own docstring documents for
    ResultsOfOperationsIncomeBeforeIncomeTaxes - isn't trusted on the strength of a
    plausible-looking sum alone. A domestic-only filer with no real Foreign concept at all
    (CNX/RRC - genuinely US-only E&P operations) still validates correctly: `foreign` is None,
    defaults to 0, and Domestic alone already matches net_income+income_tax_expense exactly (see
    get_income_statement()'s own concept-list comment on IncomeLossFromContinuingOperations
    BeforeIncomeTaxesDomestic for the live-verified CNX figures) - no regression for that
    population. Never overwrites a real "pretax_income" value already resolved from the primary
    concepts above. Mutates rows in place; always strips both raw keys (even on a rejected
    match) so a domestic-only filer doesn't leak an unmapped-field warning downstream, and so a
    filer whose domestic+foreign sum does NOT validate gets pretax_income left NULL rather than
    silently keeping the old unconditionally-trusted Domestic-only value - the same
    "don't guess when unvalidated" outcome CNX's own sibling concept
    (ResultsOfOperationsIncomeBeforeIncomeTaxes) already gets above.
    """
    for row in rows:
        domestic = row.pop("income_loss_from_continuing_operations_before_income_taxes_domestic", None)
        foreign = row.pop("income_loss_from_continuing_operations_before_income_taxes_foreign", None)
        if row.get("pretax_income") is not None or domestic is None:
            continue
        net_income = row.get("net_income_loss")
        # "income_tax_expense" (the combined-key _fill_income_tax_expense_from_current_
        # deferred_split above writes) only exists at this pre-transform() stage for a filer
        # that tags BOTH CurrentIncomeTaxExpenseBenefit and DeferredIncomeTaxExpenseBenefit -
        # PSX (one of the 4 live-confirmed symbols this function targets) tags neither, only
        # the plain "IncomeTaxExpenseBenefit" total (raw key "income_tax_expense_benefit",
        # not yet merged into "income_tax_expense" - that merge is field_mapping's job,
        # downstream in load_financial_statements.py's transform(), too late for this
        # validation). Falling back to the raw key here is safe: it's the same real SEC total
        # either way, just read before vs. after the eventual DB-column merge.
        tax = row.get("income_tax_expense")
        if tax is None:
            tax = row.get("income_tax_expense_benefit")
        if net_income is None or tax is None:
            continue
        candidate = domestic + (foreign or 0)
        if candidate == net_income + tax:
            row["pretax_income"] = candidate


def _fill_operating_income_from_revenue_minus_costs_and_expenses(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: operating_income = Revenues - CostsAndExpenses, for single-step-format
    filers that report both totals but never tag OperatingIncomeLoss at all.

    Live-confirmed via real SEC companyfacts JSON: RRC (Range Resources, CIK 0000315852) and
    ARDT (CIK 0001756655) both report a real "Revenues" and a real "CostsAndExpenses" total
    every fiscal year but tag zero OperatingIncomeLoss facts anywhere in their filing history -
    a single-step income statement format (revenue, one combined costs-and-expenses line, then
    straight to pretax income) rather than the more common multi-step format this loader's
    other concepts assume. See get_income_statement()'s "CostsAndExpenses" concept comment for
    the live values.

    Writes to "operating_income_loss" (the same raw key the plain OperatingIncomeLoss concept
    populates, already mapped to the "operating_income" column in
    load_financial_statements.py's _INCOME_FIELD_MAPPING) rather than a bare "operating_income"
    key - see income_tax_expense_pretax_income_wiring_gap_fixed_20260905 in memory for why a
    fallback that invents its own bare final-column key instead of reusing an already-mapped
    one silently never reaches the database. Only fires when "Revenues" specifically (RRC/ARDT's
    own primary revenue concept) is present - deliberately narrow rather than trying to
    reconstruct a fully-resolved "revenue" figure from every possible revenue concept alias at
    this pre-transform() aggregation stage, where that resolution hasn't happened yet. Never
    overwrites a real operating_income_loss value. Mutates rows in place and always strips the
    raw costs_and_expenses key.
    """
    for row in rows:
        costs_and_expenses = row.pop("costs_and_expenses", None)
        if row.get("operating_income_loss") is not None or costs_and_expenses is None:
            continue
        revenue = row.get("revenues")
        if revenue is None:
            continue
        row["operating_income_loss"] = revenue - costs_and_expenses


def _nullify_gross_profit_when_cost_of_revenue_mismatches(rows: list[dict[str, Any]]) -> None:
    """Validation fallback: nullify a tagged gross_profit that violates the revenue/COGS identity.

    Root-cause investigation of ABBV/GILD/AMGN pharma gross_profit understatement (CRITICAL,
    2026-09-06): live DB check found ABBV FY2025 revenue=$61.16B, cost_of_revenue=$18.20B
    (implying a real ~70.2% gross margin, consistent with branded pharma economics and stable
    across ABBV's own FY2021-2025 history), but the tagged gross_profit=$12.07B implies only a
    19.7% margin - off by $30.89B (~50% of revenue). cost_of_revenue is the reliable figure here
    (consistent scale year over year, consistent with the sector); the tagged gross_profit
    concept is the one extracted from a segment-specific or otherwise partial XBRL context.
    Confirmed same pattern on AMGN FY2019/2020.

    So this nullifies gross_profit (not cost_of_revenue) when the identity is violated, on the
    theory that cost_of_revenue is the trustworthy operand to keep. Downstream consumers (e.g.
    vqg_quality.py's gross-margin calc) already fall back to `revenue - cost_of_revenue` whenever
    gross_profit is None, so nulling it here lets that reconstruction take over rather than using
    the corrupted tagged value it currently prefers.

    Only fires when revenue, cost_of_revenue, AND gross_profit all exist; never overwrites an
    already-NULL gross_profit; only mutates when the mismatch is material (>2% of revenue).
    Mutates rows in place.
    """
    for row in rows:
        revenue = row.get("revenues")
        cogs = row.get("cost_of_revenue")
        gp = row.get("gross_profit")
        if revenue is None or cogs is None or gp is None:
            continue
        if revenue <= 0:
            continue
        implied_gp = revenue - cogs
        mismatch_pct = abs(implied_gp - gp) / revenue * 100
        if mismatch_pct > 2.0:
            logger.warning(
                f"[GROSS_PROFIT_IDENTITY] Symbol FY{row.get('fiscal_year')}: "
                f"revenue={revenue:,.0f}, cost_of_revenue={cogs:,.0f}, "
                f"stored_gp={gp:,.0f}, implied_gp={implied_gp:,.0f}, "
                f"mismatch={mismatch_pct:.1f}% of revenue - tagged gross_profit appears extracted "
                f"from segment/partial context, nullifying so revenue-cost_of_revenue reconstruction "
                f"takes over downstream"
            )
            row["gross_profit"] = None
