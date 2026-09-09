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

        # FIXED 2026-09-07 (goal session: scores-review, CWEN live-confirmed): the "never
        # overwrite a real value" guard above left a pre-existing shares_diluted value alone
        # even when that value came from a BARE (non-dimensional) tag belonging to a
        # different class/context than the one just dimensionally resolved for shares_basic -
        # live-confirmed via CWEN's real companyfacts: bare WeightedAverageNumberOfDiluted
        # SharesOutstanding=35,000,000 identical for FY2023/2024/2025 (a real per-class
        # diluted count tracking a growing company should move, not freeze for 3 straight
        # years), while the dimensionally-resolved Class C shares_basic correctly varies and
        # is much larger (84,000,000 for FY2025) - diluted < basic is a hard accounting
        # impossibility (shares_outstanding_diluted must be >= shares_outstanding_basic,
        # already enforced by tie_out.py's check_diluted_ge_basic_shares), proving the bare
        # tag is the wrong class's figure, not a real number for the class this row now
        # represents. Only fires when accepting it would create that impossibility - a bare
        # diluted value that's merely close to (or above) basic is left untouched, since nothing
        # then proves it's wrong.
        basic_key = "weighted_average_number_of_shares_outstanding_basic"
        diluted_key = "weighted_average_number_of_diluted_shares_outstanding"
        if (
            diluted_key not in filled
            and "shares_diluted" in result
            and row.get(basic_key) is not None
            and row.get(diluted_key) is not None
            and row[diluted_key] < row[basic_key]
        ):
            logger.info(
                f"[DUAL_CLASS_EPS] {symbol} FY{row['fiscal_year']}: replacing implausible bare "
                f"{diluted_key}={row[diluted_key]} (< basic {row[basic_key]}, wrong class/context) "
                f"with class '{class_letter}' dimensional match {result['shares_diluted']}"
            )
            row[diluted_key] = result["shares_diluted"]
            filled.append(diluted_key)

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


def _fill_operating_income_from_revenue_minus_cogs_and_opex(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: operating_income = Revenues - (COGS ex-D&A) - (COGS D&A) -
    OperatingExpenses, for single-step-format filers that split cost of revenue into two
    separate D&A/ex-D&A concepts and report a real OperatingExpenses total, but never tag
    OperatingIncomeLoss or CostsAndExpenses at all.

    Live-confirmed via real SEC companyfacts JSON: Casey's General Stores (CASY, CIK
    0000726958, $17.5B FY2026 revenue convenience-store/gas retailer) reports real "Revenues"
    ($17,561,101,000 FY2026), real "CostOfGoodsAndServiceExcludingDepreciationDepletionAnd
    Amortization" ($13,240,060,000), real "CostOfGoodsAndServicesSoldDepreciationAnd
    Amortization" ($449,958,000), and real "OperatingExpenses" ($2,837,426,000) but tags NO
    OperatingIncomeLoss/CostsAndExpenses concept anywhere in its filing history. Subtracting
    all three cost terms from revenue yields $1,033,657,000 - a 5.9% operating margin,
    plausible for a low-margin convenience/fuel retailer (vs. an implausible ~84% if
    OperatingExpenses alone were treated as total costs, which is exactly why this concept
    was correctly left unmapped on its own for so long - see get_income_statement()'s
    "OperatingExpenses" concept comment).

    Deliberately requires ALL FOUR real values (revenue + both COGS components +
    OperatingExpenses) - a filer missing any one of them gets no derived value rather than a
    partial, systematically-understated one. Reads (does not pop) the ex-D&A COGS key so
    load_financial_statements.py's normal field_mapping still maps it to "cost_of_revenue" for
    every filer, including ones this function doesn't fire for. Writes to
    "operating_income_loss" (the same raw key the plain OperatingIncomeLoss concept
    populates - see the sibling function above for why). Never overwrites a real
    operating_income_loss value (including one this function or the sibling above already
    filled - whichever runs first wins, and CostsAndExpenges-based derivation runs first).
    Mutates rows in place and always strips the two raw keys unique to this function.
    """
    ex_dda_keys = (
        "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization",
        "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization",
    )
    for row in rows:
        operating_expenses = row.pop("operating_expenses", None)
        cogs_dda = row.pop("cost_of_goods_and_services_sold_depreciation_and_amortization", None)
        if "operating_income_loss" in row and row["operating_income_loss"] is not None:
            continue
        if operating_expenses is None or cogs_dda is None:
            continue
        cogs_ex_dda = None
        for key in ex_dda_keys:
            if key in row and row[key] is not None:
                cogs_ex_dda = row[key]
                break
        if "revenues" not in row or row["revenues"] is None or cogs_ex_dda is None:
            continue
        row["operating_income_loss"] = row["revenues"] - cogs_ex_dda - cogs_dda - operating_expenses


def _fill_cost_of_revenue_from_other_operating_cost(rows: list[dict[str, Any]]) -> None:
    """Add OtherCostOfOperatingRevenue and/or ExciseAndSalesTaxes into
    cost_of_goods_and_services_sold - see each concept's own comment in
    get_income_statement() (TTEK/TAP live-verification detail respectively).

    Only fires when a filer tags BOTH a real cost_of_goods_and_services_sold AND at least one
    of these extra concepts (verified live: each is additive real cost, not a replacement -
    most filers never tag either concept, and this function is a no-op for them). Mutates
    "cost_of_goods_and_services_sold" in place so load_financial_statements.py's ordinary
    field_mapping still maps the corrected total to "cost_of_revenue" for every filer, same
    technique as the CASY D&A fallback above. Always strips both raw keys (never mapped to a
    DB column on their own) whether or not either fired.

    FIXED 2026-09-07 (goal session: gross_profit_identity live tie-out run, PM live-confirmed):
    the addition used to be unconditional whenever both concepts were tagged - correct for TAP
    (Molson Coors: revenue is reported ex-excise-tax, and the filer's OWN tagged GrossProfit
    only reconciles once ExciseAndSalesTaxes is added to COGS - $4.2746B, exact match), but
    live-confirmed WRONG for PM (Philip Morris) FY2025: revenue ($40.648B) is ALSO reported
    ex-excise-tax (RevenueFromContractWithCustomerExcludingAssessedTax), but PM's own tagged
    GrossProfit ($27.282B) ALREADY reconciles with COGS alone ($13.366B, no excise addition
    needed) - adding ExciseAndSalesTaxes ($53.211B) on top produced cost_of_revenue=$66.577B,
    exceeding revenue entirely and breaking gross_profit_identity. Same raw concepts, opposite
    correct treatment per filer - there is no single unconditional rule. Now validated against
    the filer's own tagged "gross_profit" (when present) the same way _fill_pretax_income_
    from_domestic_foreign_split validates against net_income+tax above: only add extra when
    doing so makes cost_of_revenue reconcile BETTER with the filer's own tagged gross_profit
    than leaving it alone would. A filer with no tagged gross_profit at all (the original
    TTEK/SAM-without-GrossProfit case) still gets the addition unconditionally, unchanged from
    before - this only tightens the TAP-vs-PM ambiguous case.
    """
    for row in rows:
        other_cost = row.pop("other_cost_of_operating_revenue", None)
        excise_tax = row.pop("excise_and_sales_taxes", None)
        extra = sum(v for v in (other_cost, excise_tax) if v is not None)
        if extra == 0:
            continue
        cogs = row.get("cost_of_goods_and_services_sold")
        if cogs is None:
            continue
        tagged_gross_profit = row.get("gross_profit")
        revenue = None
        for revenue_key in (
            "revenues",
            "revenue_from_contract_with_customer_excluding_assessed_tax",
            "revenue_from_contract_with_customer_including_assessed_tax",
        ):
            if row.get(revenue_key) is not None:
                revenue = row[revenue_key]
                break
        if tagged_gross_profit is not None and revenue is not None:
            error_without_extra = abs((revenue - cogs) - tagged_gross_profit)
            error_with_extra = abs((revenue - cogs - extra) - tagged_gross_profit)
            if error_without_extra <= error_with_extra:
                continue  # Filer's own tagged gross_profit already reconciles without the addition
        row["cost_of_goods_and_services_sold"] = cogs + extra


_SELLING_TYPE_GATE_KEYS = (
    "selling_expense",
    "selling_and_marketing_expense",
    "sales_and_marketing_expense",
    "marketing_expense",
    "distribution_costs",
)


def _fill_sga_from_general_and_administrative_when_no_selling_component(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: promotes us-gaap/ifrs-full "GeneralAndAdministrativeExpense" into
    "selling_general_and_administrative_expense" (-> operating_expenses column via
    load_financial_statements.py's _INCOME_FIELD_MAPPING) ONLY for filers where G&A genuinely
    functions as their complete SG&A-equivalent expense line.

    ADDED 2026-09-09 (goal: XBRL coverage-scan comment-leak follow-up - see
    get_income_statement()'s "GeneralAndAdministrativeExpense" concept comment for the full
    live-evidence writeup: 2,231 us-gaap + 276 ifrs-full real filers on the local companyfacts
    cache tag this concept). A plain unconditional alias (the same technique used for the
    "AdministrativeExpense" IFRS fallback above) would be WRONG here: a systematic check across
    the whole population (not just a handful of spot checks) found 1,115 of the 2,231 us-gaap
    filers (~50%) and 191 of the 276 ifrs-full filers (~69%) ALSO separately tag a selling/
    marketing/distribution-type expense (SellingExpense/SellingAndMarketingExpense/
    SalesAndMarketingExpense/MarketingExpense/DistributionCosts) or, for ifrs-full, the sibling
    "AdministrativeExpense" concept, for the SAME fiscal year that G&A is tagged with no combined
    SG&A total - live-confirmed e.g. Arts Way Manufacturing (CIK 0000007623) FY2025:
    GeneralAndAdministrativeExpense=$4,193,753 AND SellingExpense=$1,439,529 tagged separately.
    For those filers, G&A alone is only the administrative PORTION of SG&A - aliasing it
    directly would silently and systematically UNDERSTATE the combined total by omitting the
    selling/marketing/distribution component entirely, the exact failure mode the coverage-scan
    task this fix comes from explicitly warned against.

    Only fires when (a) no combined SG&A/AdministrativeExpense-derived value is already present
    for that fiscal year (checked via "selling_general_and_administrative_expense", the raw key
    both SellingGeneralAndAdministrativeExpense and the AdministrativeExpense IFRS alias already
    populate during _aggregate_concepts) AND (b) none of the 5 selling-type "gate" concepts is
    present for that same row. Live-confirmed safe (G&A functions as the complete SG&A-
    equivalent, no separate selling/marketing/distribution tag at all) for 10 real filers: us-
    gaap - Boeing, MasTec, Wendy's, Federal Realty, CTO Realty Growth; ifrs-full - Pan American
    Silver, Teck Resources, DRDGold, WPP plc, Woori Financial Group.

    Mutates rows in place. Always strips "general_and_administrative_expense" and all 5 gate
    keys (never mapped to a DB column on their own - see get_income_statement()'s comment on
    why they're deliberately absent from _INCOME_FIELD_MAPPING) whether or not the fallback
    fires for that row. Never overwrites a real "selling_general_and_administrative_expense"
    value.
    """
    for row in rows:
        general_and_administrative = row.pop("general_and_administrative_expense", None)
        # NOTE: pop every gate key unconditionally (not inside any()'s generator, which would
        # short-circuit on the first truthy pop and leave the remaining gate keys stranded in
        # the row dict) - each key is unmapped in _INCOME_FIELD_MAPPING and must never survive
        # into a persisted row regardless of which branch below fires.
        selling_component_values = [row.pop(key, None) for key in _SELLING_TYPE_GATE_KEYS]
        has_selling_component = any(v is not None for v in selling_component_values)
        if row.get("selling_general_and_administrative_expense") is not None:
            continue
        if general_and_administrative is None or has_selling_component:
            continue
        row["selling_general_and_administrative_expense"] = general_and_administrative
