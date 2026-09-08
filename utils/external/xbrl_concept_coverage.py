#!/usr/bin/env python3
"""Shared logic for finding us-gaap/dei/ifrs-full XBRL concepts our SEC loaders never fetch.

Extracted from scripts/xbrl_concept_coverage_scan.py (2026-09-07, goal session: "is there a
better way to deal with XBRL validation than checking every symbol by hand") so the same
concept-gap-detection logic can be reused both as a manually-run CLI tool (the script) and as
an automated DataPatrol check (algo/monitoring/data_patrol/checks/xbrl_new_concepts.py) that
runs on every scheduled pipeline pass instead of only when a human remembers to invoke the
script. See that checker's module docstring for why: this is the "future filings" gap - a
newly-adopted taxonomy tag previously sat invisible until someone thought to re-run the script
or a tie-out check happened to catch a downstream symptom.
"""

from __future__ import annotations

import datetime
import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Persistent triage state - see scripts/xbrl_concept_coverage_scan.py's original comment for the
# full rationale. Checked into git, shared across both the manual script and the automated check.
DISMISSED_FILE = REPO_ROOT / "scripts" / "xbrl_concept_coverage_dismissed.json"

# Separate triage log for find_continuity_gaps() below - a different failure mode from the
# above (a concept we've never fetched at all) so it gets its own dismiss log rather than
# overloading DISMISSED_FILE's "namespace:Concept" keys with a second, incompatible key shape
# ("CIK:Concept", since a continuity gap is filer-specific, not concept-wide).
CONTINUITY_DISMISSED_FILE = REPO_ROOT / "scripts" / "xbrl_concept_continuity_dismissed.json"

# Concepts virtually every operating 10-K filer tags every single fiscal year, regardless of
# industry (financials/REITs/insurers included) - deliberately a short, conservative list.
# Anything broader (e.g. a specific debt or lease concept) legitimately appears/disappears
# for ordinary business reasons (a company pays off its only debt, adopts a new accounting
# standard, etc.) and would make this check noisy rather than high-signal. These three are the
# closest thing to "if this stops being tagged, something is wrong" for any going concern -
# either the filer switched to a synonym/renamed taxonomy tag (the actual "taxonomy migration"
# case this check exists for) or a real discontinuation (bankruptcy, going-private, final 10-K).
CORE_CONTINUITY_CONCEPTS = ["Assets", "Liabilities", "NetIncomeLoss"]

# Known synonym tags our own extraction pipeline already treats as equivalent to a
# CORE_CONTINUITY_CONCEPTS entry (see loaders/helpers/financial_statements_income_config.py's
# _INCOME_FIELD_MAPPING, where "net_income_loss"/"profit_loss"/the continuing-ops-incl-NCI key
# all map to the same "net_income" column, and sec_income_statement.py's _INCOME_CONCEPTS
# fallback chain, which already tries ProfitLoss/IncomeLossFromContinuingOperationsIncluding...
# whenever NetIncomeLoss itself is absent). Without this, the continuity checker false-positives
# on every filer whose real bottom-line tag has always been one of these synonyms (live-
# confirmed 2026-09-08 via Ford Motor Co's real FY2025 10-K, filed 2026-02-11: Assets/Liabilities
# both tagged for 2025-12-31 as expected, but the income statement's net income - a real $8.162B
# loss - is tagged solely as "ProfitLoss" that year, not "NetIncomeLoss"; Primerica's PRI is the
# same already-documented case per sec_income_statement.py's own 2026-08-17 fix comment). The
# actual extracted/scored net_income value is unaffected by this switch - it is exactly the kind
# of "filer switched to a synonym tag" case this checker's own docstring says needs no fix, only
# a dismissal - so treat these synonyms as satisfying continuity instead of manually dismissing
# every such filer one CIK at a time.
CONTINUITY_CONCEPT_SYNONYMS: dict[str, list[str]] = {
    "NetIncomeLoss": [
        "ProfitLoss",
        "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
    ],
}

# Every place a real (non-test, non-fallback-table) concept list lives today.
CONCEPT_SOURCE_FILES = [
    "utils/external/sec_income_statement.py",
    "utils/external/sec_income_statement_fallbacks.py",
    "utils/external/sec_balance_sheet.py",
    "utils/external/sec_cash_flow.py",
    "utils/external/sec_custom_xbrl_concepts.py",
    "utils/external/sec_xbrl_segments.py",
    "utils/external/sec_xbrl_segment_revenue.py",
    "utils/external/sec_xbrl_segment_revenue_2.py",
    "utils/external/sec_statements.py",
    "utils/external/sec_statements_aggregate.py",
    "utils/external/sec_statements_entry_resolution.py",
    "utils/external/sec_statements_shared.py",
    "utils/external/sec_statements_unit_context.py",
    "loaders/helpers/sec_dual_class_eps.py",
    "loaders/helpers/sec_segment_debt.py",
    "loaders/helpers/sec_valuations_dcf.py",
    "loaders/helpers/sec_valuations_income_context.py",
    "loaders/helpers/sec_valuations_ratios.py",
    "loaders/helpers/sec_valuations_shares.py",
    "loaders/helpers/sec_valuations_yield_dcf.py",
    "loaders/load_sec_segment_info.py",
    "loaders/load_sec_segment_metrics.py",
]

# A real us-gaap/dei/ifrs-full concept name is PascalCase, letters+digits only, at least ~5
# characters. Matches some non-concept PascalCase identifiers too, but those simply never
# appear in real companyfacts data and get filtered out at diff time.
#
# FIXED 2026-09-07 (goal session: "make sure the list/checks are right" audit): the {4,90}
# upper bound silently excluded any ALREADY-fetched concept whose literal is over 90 chars
# from load_known_concepts()'s output - live-confirmed 9 real concepts we do fetch exceed 90
# chars (up to 110, e.g. sec_income_statement.py's "IncomeLossFromContinuingOperationsBefore
# IncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", sec_cash_flow.py's two
# Cash...RestrictedCash...PeriodIncreaseDecrease variants). Each falsely reappeared as an
# "undismissed gap" in xbrl_concept_coverage_scan.py output despite being fully wired up - a
# false positive in the checker itself, not a real gap. Raised to 160 (headroom above the
# longest real concept literal found, 110 chars) rather than removing the cap entirely, so a
# truly malformed/non-concept PascalCase run-on string still gets excluded.
_CONCEPT_LITERAL_RE = re.compile(r'"([A-Z][A-Za-z0-9]{4,160})"')

# Concept-name substrings that are almost always footnote/disclosure detail rather than a
# statement-level number we'd ever score - see scripts/xbrl_concept_coverage_scan.py's
# original comment for detail on each category.
NOISE_SUBSTRINGS = [
    "TaxRateReconciliation",
    "PaymentsDue",
    "WeightedAverageNumberOf",
    "AntidilutiveSecurities",
    "RelatedParty",
    "SegmentReportingInformation",
    "ScheduleOf",
    "RangeMin",
    "RangeMax",
    "ShareBasedCompensationArrangementByShareBasedPaymentAward",
    "BusinessCombination",
    "IncomeLossFromDiscontinuedOperations",
    "AssetImpairmentCharges",
    "GuaranteeObligations",
    "DerivativeInstrument",
    "FairValue",
    # Added 2026-09-07 (goal session: comprehensive tie-out/XBRL coverage audit) after
    # reviewing the top ~250 undismissed gaps by company count and finding every single one
    # fell into one of these same already-established categories (deferred-tax schedule detail,
    # tax-reconciliation footnote lines, equity/APIC rollforward detail, debt-maturity/lease
    # schedules, cash-flow footnote detail already reflected net at the aggregate level this
    # schema tracks, etc) - see scripts/xbrl_concept_coverage_dismissed.json for the individual
    # per-concept precedents each pattern generalizes (e.g. "DeferredTaxAssetsNet" already
    # dismissed as "Deferred-tax footnote schedule component" - every DeferredTax* sibling is
    # the same class of footnote breakdown, not worth re-litigating one at a time).
    "DeferredTax",
    "IncomeTaxReconciliation",
    "UnrecognizedTaxBenefit",
    "IncomeTaxPaid",  # jurisdiction/refund-split variants of the already-dismissed IncomeTaxesPaidNet
    "TreasuryStock",
    "AdjustmentsToAdditionalPaidInCapital",
    "AdditionalPaidInCapital",
    "StockIssuedDuringPeriod",
    "StockRepurchase",
    "LongTermDebtMaturitiesRepaymentsOfPrincipal",
    "FiniteLivedIntangibleAssetsAmortizationExpense",
    "FiniteLivedIntangibleAssets",
    "FinanceLease",
    "OperatingLease",
    "ClassOfWarrantOrRight",
    "RestrictedCash",
    "DefinedContributionPlan",
    "DefinedBenefitPlan",
    "AvailableForSale",
    "ContractWithCustomerLiability",
    # Cash-flow-statement working-capital/investing/financing footnote detail already
    # reflected net in this schema's operating_cash_flow/investing_cash_flow/
    # financing_cash_flow totals - same rationale as the already-dismissed
    # IncreaseDecreaseInAccountsReceivable/PaymentsToAcquireBusinessesNetOfCashAcquired.
    "IncreaseDecreaseIn",
    "ProceedsFrom",
    "PaymentsFor",
    "PaymentsTo",
    "RepaymentsOf",
    # Added 2026-09-08 (goal session: "keep working through XBRL stuff") after a min-companies
    # 50 scan surfaced 776 undismissed concepts, hand-reviewed by category. Every one below is
    # bank/insurance regulatory schedule detail, business-combination purchase-price-allocation
    # detail, or lease/receivable maturity-schedule footnote breakdown - never a statement-level
    # figure this schema scores. Verified none of these substrings collide with any concept
    # literal we already fetch (utils/external/xbrl_concept_coverage.py's load_known_concepts()
    # checked directly before adding). Same "generalize the established per-concept precedent
    # instead of re-litigating one at a time" rationale as the DeferredTax/BusinessCombination
    # additions above.
    "BusinessAcquisition",  # purchase-price-allocation/pro-forma detail, distinct literal prefix from the already-noise "BusinessCombination"
    "FutureMinimumPayments",  # capital/sales-type lease receivable maturity schedules (CapitalLeasesFutureMinimumPaymentsReceivable*)
    "AllowanceForLoanAndLeaseLosses",  # bank ALLL rollforward detail (period increase/decrease, provision, adjustments)
    "LossContingency",  # litigation schedule detail (range of loss, claims dismissed/settled counts, accrual rollforward)
    "FinancingReceivable",  # bank financing-receivable schedule/aging/modification detail
    "CertainLoansAcquiredInTransfer",  # purchased-credit-impaired loan schedule detail
    "InterestBearingDomesticDeposit",  # bank deposit-mix schedule (checking/savings/money-market/CD breakdown)
    "InterestBearingDepositLiabilities",  # sibling of the deposit-mix schedule above
    "AccrualForEnvironmentalLossContingencies",  # environmental-remediation accrual rollforward
    "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpense",  # insurance claims-reserve rollforward (current/prior year paid/incurred)
    "MarketLease",  # above/below-market lease intangible amortization schedule
    "BankingRegulation",  # regulatory capital-ratio disclosure (Tier 1, well-capitalized minimums)
    "LineOfCreditFacility",  # credit-facility footnote detail (periodic payment, additional borrowings) - distinct from the single fair-value concept we already fetch
    "InterestExpenseFederal",  # bank funding-cost breakdown (fed funds purchased/FHLB advances)
    "InterestExpenseJunior",  # junior subordinated debenture interest detail
    "InterestExpenseLessee",  # capital-lease interest sub-component, already reflected in aggregate interest_expense
    "InterestExpenseSavingsDeposits",  # bank deposit-cost breakdown sibling of InterestBearingDomesticDeposit above
    "InterestExpenseSecuritiesSoldUnderAgreementsToRepurchase",  # repo funding-cost detail
    "InterestExpenseTimeDeposits",  # CD funding-cost detail
    "InterestIncomeFederalFundsSold",  # bank interest-income breakdown sibling of InterestExpenseFederal above
    "CededPremiumsWritten",  # reinsurance premium-ceding schedule
    "AssumedPremiumsWritten",  # reinsurance premium-assumption schedule
    "LoansAndLeasesReceivable",  # bank loan-portfolio-mix schedule (commercial/related-party/etc breakdown)
    "LoansReceivable",  # sibling loan-type breakdown (commercial real estate, fixed-rate, etc)
    "LoansHeldForSale",  # loan-type breakdown of held-for-sale mortgages
    "AssetRetirementObligation",  # ARO rollforward detail (cash settled, FX translation, period change)
    "IncomeTaxExamination",  # tax-audit contingency detail (estimate of loss, interest/penalties accrued)
    "IndefiniteLivedIntangibleAssets",  # intangible-asset rollforward detail, distinct from the amortizable-intangible noise already covered by "FiniteLivedIntangibleAssets"
    "MultiemployerPlan",  # multiemployer pension-plan disclosure detail
    "SelfInsuranceReserve",  # self-insurance reserve rollforward
    # Added 2026-09-08 (goal session: "is the coverage scan catching everything it should"
    # audit, ifrs-full now scanned for the first time - see xbrl_concept_coverage_scan.py's
    # namespace default fix same commit). Hand-reviewed the top ~110 ifrs-full concepts by
    # company count (50-250+ filers each: Agnico Eagle, Bank of Nova Scotia, Unilever, Sony,
    # PLDT, Barclays, Scully Royalty). These are IFRS's own footnote/reconciliation naming
    # idioms ("AdjustmentsFor...", "IncreaseDecreaseThrough...", cash-flow-statement
    # indirect-method reconciliation lines, share-option/actuarial/employee-benefit schedule
    # detail, business-combination and tax-rate-reconciliation detail) that don't share
    # literal substrings with the existing us-gaap-oriented patterns above despite being the
    # same class of non-statement-level disclosure. Deliberately did NOT dismiss items that
    # look like they could be real statement-level balance-sheet/income-statement lines this
    # schema might actually want (OtherCurrentAssets/OtherNoncurrentAssets/OtherPayables/
    # TradeReceivables/Prepayments/CurrentInvestments/CashEquivalents/CashOnHand/ContractAssets/
    # NetDebt/RawMaterials/CapitalCommitments/DividendsPaidOrdinaryShares/etc.) - those need a
    # deliberate per-concept review (cross-check against this schema's existing IFRS aliases in
    # sec_balance_sheet.py/sec_income_statement.py/sec_cash_flow.py) before either fetching or
    # dismissing, not a blanket substring generalization; left undismissed on purpose so they
    # keep surfacing for that follow-up instead of silently disappearing.
    "AdjustmentsFor",  # cash-flow indirect-method reconciliation lines (interest/tax/FX/disposal add-backs)
    "IncreaseDecreaseThrough",  # rollforward/reconciliation detail (FX, ownership changes, conversions)
    "ShareOption",  # share-option scheme detail (exercise price, expiry, forfeiture counts)
    "SharebasedPaymentArrangement",  # sibling of the above, IFRS 2 disclosure schedule
    "ExercisePriceShareOptionsGranted",  # share-option pricing detail
    "WeightedAverageExercisePriceOfShareOptions",  # sibling share-option pricing detail
    "WeightedAverageSharePriceShareOptionsGranted",  # sibling share-option pricing detail
    "NumberOfShareOptions",  # share-option count rollforward
    "DescriptionOf",  # narrative/assumption-description text tags (volatility, risk-free rate, etc.)
    "ActuarialAssumption",  # pension actuarial-assumption disclosure detail
    "DefinedBenefitObligation",  # pension obligation rollforward, sibling of us-gaap DefinedBenefitPlan noise
    "NetDefinedBenefitLiabilityAsset",  # pension service-cost/interest-expense sub-component detail
    "KeyManagementPersonnelCompensation",  # executive-comp disclosure detail
    "DirectorsRemuneration",  # director-comp disclosure detail
    "TaxRateEffectFrom",  # tax-rate-reconciliation footnote line, sibling of us-gaap TaxRateReconciliation
    "IncomeTaxRelatingTo",  # OCI tax-effect breakdown detail
    "TemporaryDifferencesAssociatedWith",  # deferred-tax footnote detail, IFRS sibling of us-gaap DeferredTax noise
    "IdentifiableAssetsAcquiredLiabilitiesAssumed",  # business-combination PPA detail, IFRS sibling of us-gaap BusinessCombination noise
    "ConsiderationPaidReceived",  # business-combination consideration detail
    "PercentageOf",  # ownership/revenue-concentration percentage disclosure tags, not a statement figure
    "ClosingForeignExchangeRate",  # FX-translation footnote rate disclosure, not a statement figure
    "SocialSecurityContributions",  # payroll-tax footnote detail
    "ShorttermEmployeeBenefitsAccruals",  # employee-benefit accrual detail
    "ShorttermEmployeeBenefitsExpense",  # sibling employee-benefit expense detail
    "CapitalCommitments",  # capital-commitment footnote disclosure, not a recognized statement balance
    "ContractualCapitalCommitments",  # sibling of the above
    # Added 2026-09-08 (goal: continue the ifrs-full backlog from the batch above). A
    # --min-companies 100 scan still showed 206 undismissed concepts, ~all ifrs-full. Spot-
    # checked 2-3 concepts per category directly in the on-disk companyfacts cache (Agnico
    # Eagle, Bank of Nova Scotia, Barclays, Scully Royalty) - every one confirmed to be
    # footnote/reconciliation-schedule detail (a tax-reconciliation percentage or dollar
    # sub-line, a per-share/count disclosure tag, a lease/provision/business-combination
    # movement-schedule line), never the statement-level headline figure. Deliberately scoped
    # to NOT catch the bare headline concepts a separate live task is mapping as real aliases:
    # CurrentTaxLiabilities/CurrentTaxAssets (only the duplicate-suffixed *Current variant is
    # noise), OtherComprehensiveIncome bare, RightofuseAssets/CurrentLeaseLiabilities/
    # NoncurrentLeaseLiabilities bare, Provisions/OtherProvisions/CurrentProvisions/
    # NoncurrentProvisions bare (only the *UsedOtherProvisions/*ProvisionsOtherProvisions
    # rollforward lines are noise).
    #
    # Tax-rate reconciliation detail (spot-checked ApplicableTaxRate=0.26 (a rate, not a
    # dollar amount) and TaxExpenseIncomeAtApplicableTaxRate on AGNICO EAGLE MINES LIMITED's
    # 2017 40-F, TaxEffectOfForeignTaxRates=-9,370,000 same filing - all reconciliation-table
    # sub-lines that foot into the single effective-tax-rate/tax-expense figures this schema
    # already scores).
    "ApplicableTaxRate",  # also catches TaxExpenseIncomeAtApplicableTaxRate
    "AverageEffectiveTaxRate",
    "TaxEffectOf",  # TaxEffectOfForeignTaxRates/ExpenseNotDeductible.../TaxLosses/RevenuesExemptFromTaxation2011
    "TaxEffectFromChangeInTaxRate",
    "TaxEffectsForReconciliation",  # OtherTaxEffectsForReconciliationBetweenAccountingProfitAndTaxExpenseIncome
    "CurrentTaxLiabilitiesCurrent",  # duplicate-suffixed dimensional variant of the real CurrentTaxLiabilities concept
    "CurrentTaxAssetsCurrent",  # sibling of the above
    # OCI net-of-tax component breakdowns (spot-checked OtherComprehensiveIncomeNetOfTax
    # ExchangeDifferencesOnTranslation=396,000,000 on BANK OF NOVA SCOTIA's 2018 40-F and
    # ReserveOfExchangeDifferencesOnTranslation=3,054,000,000 on BARCLAYS PLC's 2019 20-F -
    # both are the per-component breakdown of the single OtherComprehensiveIncome total this
    # schema already scores, not a new headline figure).
    "OtherComprehensiveIncomeNetOfTax",  # bare OtherComprehensiveIncome (the headline total) is unaffected
    "ReclassifiedToProfitOrLossNetOfTax",  # ThatWillBeReclassified.../ThatWillNotBeReclassified... variants
    "GainsLossesOnExchangeDifferencesOnTranslation",
    "ReserveOfExchangeDifferencesOnTranslation",
    "ReserveOfSharebasedPayments",
    # IFRS-16 lease footnote/disclosure detail (movement schedule and rate disclosure, not the
    # headline RightofuseAssets/CurrentLeaseLiabilities/NoncurrentLeaseLiabilities balances,
    # which stay undismissed for the parallel live-alias-mapping task). Spot-checked
    # PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities=3,382,000 and
    # InterestExpenseOnLeaseLiabilities=1,909,000 on AGNICO EAGLE MINES LIMITED's 40-Fs -
    # both are cash-flow-statement/interest sub-components of the aggregate figures this
    # schema tracks net.
    "PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities",
    "InterestExpenseOnLeaseLiabilities",
    "AdditionsToRightofuseAssets",
    "DepreciationRightofuseAssets",
    "CashOutflowForLeases",
    "ExpenseRelatingTo",  # ShorttermLeases/VariableLeasePayments/LeasesOfLowvalueAssets exemption-disclosure lines
    "WeightedAverageLesseesIncrementalBorrowingRateAppliedToLeaseLiabilities",  # rate disclosure, not a $ line item
    # Share-issuance/equity mechanics disclosure (spot-checked IssueOfEquity=215,000,000 (a
    # roll-forward addition, not a balance) and NumberOfSharesIssued=225,465,654 (a share
    # count, not a dollar figure) on AGNICO EAGLE MINES LIMITED's 40-Fs).
    "IssueOfEquity",
    "NumberOfSharesIssued",  # also catches the NumberOfSharesIssuedAndFullyPaid variant
    "NumberOfSharesAuthorised",
    "ParValuePerShare",  # spot-checked val=0 on AGNICO EAGLE - per-share, not a $ line item
    "ShareIssueRelatedCost",
    "DividendsPaidOrdinaryShares",  # also catches the DividendsPaidOrdinarySharesPerShare variant
    "BasicAndDilutedEarningsLossPerShare",  # spot-checked val=-3.81 on Scully Royalty - per-share, not $
    # JV/associates equity-method detail (spot-checked ShareOfProfitLossOfAssociatesAnd
    # JointVenturesAccountedForUsingEquityMethod=414,000,000 and InvestmentAccountedForUsing
    # EquityMethod=4,586,000,000 on BANK OF NOVA SCOTIA's 40-F - equity-method sub-line
    # breakdowns, not statement-level totals this schema scores).
    "ShareOfProfitLossOfAssociates",  # also catches the ...AndJointVenturesAccountedForUsingEquityMethod variant
    "InvestmentAccountedForUsingEquityMethod",
    "InvestmentsInSubsidiariesJointVenturesAndAssociates",
    # Provision movement-schedule detail (opening/closing/used/reversed roll-forward, not the
    # balance itself - bare Provisions/OtherProvisions/CurrentProvisions/NoncurrentProvisions
    # stay undismissed). Spot-checked ProvisionUsedOtherProvisions=212,000,000 and
    # AdditionalProvisionsOtherProvisions=27,000,000 on BANK OF NOVA SCOTIA's 40-F - both are
    # roll-forward movement lines, not the provision balance.
    "ProvisionUsedOtherProvisions",
    "AdditionalProvisionsOtherProvisions",
    "UnusedProvisionReversedOtherProvisions",
    # Business-combination/disposal-group detail (spot-checked CashFlowsUsedInObtainingControl
    # OfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities=12,434,000 on AGNICO EAGLE
    # and LiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale=29,897,000 on Scully
    # Royalty - PPA/disposal-group footnote sub-lines, not statement-level totals).
    "ObtainingControlOfSubsidiariesOrOtherBusinesses",  # CashFlowsUsedIn... investing-activities line
    "LosingControlOfSubsidiariesOrOtherBusinesses",  # CashFlowsFrom... sibling
    "LiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale",
    # Bank/derivative notional & rate disclosure - this schema doesn't score bank-specific
    # derivative books. Spot-checked NotionalAmount=4,547,246,000,000 (a derivative-book
    # notional, not a recognized balance) and BorrowingsInterestRate=0.0465 (a rate, not a $
    # figure) on BANK OF NOVA SCOTIA's 40-F.
    "NotionalAmount",
    "BorrowingsInterestRate",
    "AllowanceAccountForCreditLossesOfFinancialAssets",
]


def load_dismissed() -> dict[str, str]:
    if not DISMISSED_FILE.exists():
        # Not an error - no dismissals have been recorded yet, not that data is missing.
        return {}
    try:
        return cast(dict[str, str], json.loads(DISMISSED_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def save_dismissed(dismissed: dict[str, str]) -> None:
    DISMISSED_FILE.write_text(json.dumps(dict(sorted(dismissed.items())), indent=2) + "\n", encoding="utf-8")


def load_known_concepts() -> set[str]:
    known: set[str] = set()
    for rel in CONCEPT_SOURCE_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        known.update(_CONCEPT_LITERAL_RE.findall(text))
    return known


def iter_companyfacts_cache() -> list[Path]:
    cache_dir = Path(tempfile.gettempdir()) / "algo-sec-edgar-cache" / "companyfacts"
    if not cache_dir.exists():
        # Not an error - not yet initialized by a loader run. Callers that need to
        # distinguish this from "scanned and found nothing" check this function themselves.
        return []
    return sorted(cache_dir.glob("*.json"))


def load_continuity_dismissed() -> dict[str, str]:
    if not CONTINUITY_DISMISSED_FILE.exists():
        return {}
    try:
        return cast(dict[str, str], json.loads(CONTINUITY_DISMISSED_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def save_continuity_dismissed(dismissed: dict[str, str]) -> None:
    CONTINUITY_DISMISSED_FILE.write_text(json.dumps(dict(sorted(dismissed.items())), indent=2) + "\n", encoding="utf-8")


# FIXED 2026-09-08 (goal: "is the XBRL data going down" sweep): find_continuity_gaps() below
# used to require an EXACT string match between a concept's own annual end-dates and the
# filer's cross-concept "anchor" end-date. Live-confirmed BT BRANDS, INC. (CIK 0001718224)
# false-positived on this: its FY2024 10-K (accn 0001477932-25-002248) tags Assets/Liabilities
# with end="2024-12-31" (balance-sheet instant context) but NetIncomeLoss with end="2024-12-29"
# (income-statement duration context, the filer's REAL 52/53-week fiscal year-end) - the exact
# same filing, same fiscal year, just a 2-day skew between an instant and a duration XBRL
# context that SEC EDGAR's own renderer doesn't reconcile. NetIncomeLoss WAS genuinely present
# and unchanged; the checker just never matched its "2024-12-29" against the anchor's
# "2024-12-31". A small tolerance window (same-fact reporting-date skew is always a few days,
# never close to a real fiscal year's ~365-day gap) fixes this without risking a false
# negative - two genuinely different fiscal years can never collide within this window.
_CONTINUITY_DATE_TOLERANCE_DAYS = 7


def _dates_close(a: str, b: str, tolerance_days: int = _CONTINUITY_DATE_TOLERANCE_DAYS) -> bool:
    try:
        da = datetime.date.fromisoformat(a)
        db = datetime.date.fromisoformat(b)
    except ValueError:
        return a == b
    return abs((da - db).days) <= tolerance_days


def _has_close_match(target: str, candidates: set[str]) -> bool:
    return any(_dates_close(target, c) for c in candidates)


def _annual_end_dates(fact_entries: list[dict[str, object]]) -> set[str]:
    """Distinct fiscal-period-end dates ('end') this concept has an annual (10-K/10-K/A) fact
    for, in ANY unit (USD covers the three CORE_CONTINUITY_CONCEPTS; a filer using a non-USD
    reporting currency still tags Assets/Liabilities/NetIncomeLoss, just under a different unit
    key, so this checks every unit rather than assuming "USD").
    """
    ends: set[str] = set()
    for entry in fact_entries:
        form = cast(str, entry.get("form") or "")
        end = entry.get("end")
        if form.startswith("10-K") and isinstance(end, str):
            ends.add(end)
    return ends


def find_continuity_gaps(min_prior_years: int = 3) -> list[dict[str, object]]:
    """Find filers where a CORE_CONTINUITY_CONCEPTS concept was tagged every year for at least
    `min_prior_years` straight prior annual filings but is absent from the most recent one -
    the "taxonomy migration" / "filer switched tags" gap that find_gaps() above cannot see
    (find_gaps() only catches a concept appearing for the FIRST time anywhere in the universe;
    this catches one disappearing for a SPECIFIC filer that used to report it every year).

    A concept that was never tagged by a filer at all is not a continuity gap (that is either
    a genuine business difference - e.g. a REIT with no NetIncomeLoss concept some year - or
    the plain coverage gap find_gaps() already handles) - only "had it consistently, then
    suddenly didn't" counts here.

    Uses each filer's OWN reporting history as the anchor timeline (the union of annual end-
    dates across all three core concepts), not a global fiscal calendar - avoids false positives
    for non-calendar fiscal years and filers that report late/early relative to peers.
    """
    files = iter_companyfacts_cache()
    if not files:
        # No on-disk companyfacts cache yet (e.g. a fresh host before any loader has run this
        # cycle) - nothing to process, not a data-loss condition. Mirrors the caller's own
        # identical check (XbrlConceptContinuityChecker.check_concept_continuity), which
        # already treats an empty cache as "nothing to scan yet," not a finding.
        return []
    dismissed = load_continuity_dismissed()

    gaps: list[dict[str, object]] = []
    for fp in files:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data") or {}
        entity_name = data.get("entityName", fp.stem)
        usgaap = (data.get("facts") or {}).get("us-gaap") or {}

        per_concept_ends: dict[str, set[str]] = {}
        anchor_ends: set[str] = set()
        for concept in CORE_CONTINUITY_CONCEPTS:
            ends: set[str] = set()
            for tag in (concept, *CONTINUITY_CONCEPT_SYNONYMS.get(concept, [])):
                concept_data = usgaap.get(tag)
                if not concept_data:
                    continue
                entries: list[dict[str, object]] = []
                for unit_entries in (concept_data.get("units") or {}).values():
                    entries.extend(unit_entries)
                ends.update(_annual_end_dates(entries))
            per_concept_ends[concept] = ends
            anchor_ends.update(ends)

        if len(anchor_ends) < min_prior_years + 1:
            continue  # Not enough of this filer's own history to judge "used to report every year"

        sorted_ends = sorted(anchor_ends, reverse=True)
        latest = sorted_ends[0]
        prior_window = sorted_ends[1 : min_prior_years + 1]

        for concept in CORE_CONTINUITY_CONCEPTS:
            own_ends = per_concept_ends[concept]
            if not own_ends:
                continue  # Never tagged at all - a coverage gap, not a continuity regression
            if _has_close_match(latest, own_ends):
                continue  # Still present this year (within the instant/duration skew tolerance) - no gap
            if not all(_has_close_match(p, own_ends) for p in prior_window):
                continue  # Wasn't consistently present before either - not a new regression
            key = f"{fp.stem}:{concept}"
            if key in dismissed:
                continue
            gaps.append(
                {
                    "cik": fp.stem,
                    "entity_name": entity_name,
                    "concept": f"us-gaap:{concept}",
                    "latest_expected_end": latest,
                    "prior_years_present": prior_window,
                }
            )
    gaps.sort(key=lambda g: (cast(str, g["concept"]), cast(str, g["entity_name"])))
    return gaps


def scan_cache(namespaces: list[str]) -> tuple[Counter[str], dict[str, str]]:
    """Return (concept -> #companies tagging it, one example entityName per concept)."""
    files = iter_companyfacts_cache()
    if not files:
        return Counter(), {}

    company_count: Counter[str] = Counter()
    example: dict[str, str] = {}
    for fp in files:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data") or {}
        entity_name = data.get("entityName", fp.stem)
        facts = data.get("facts") or {}
        seen_this_company: set[str] = set()
        for ns in namespaces:
            for concept in (facts.get(ns) or {}).keys():
                key = f"{ns}:{concept}"
                if key in seen_this_company:
                    continue
                seen_this_company.add(key)
                company_count[key] += 1
                example.setdefault(key, entity_name)
    return company_count, example


def find_gaps(
    namespaces: list[str],
    min_companies: int = 1,
    exclude_noise: bool = False,
    include_dismissed: bool = False,
) -> list[tuple[int, str, str]]:
    """Return (company_count, "namespace:Concept", example_filer) tuples, sorted descending.

    Empty list also means "no cached companyfacts data available" - callers that need to
    distinguish that from "scanned and found nothing" should check iter_companyfacts_cache()
    themselves first.
    """
    known = load_known_concepts()
    dismissed = load_dismissed()
    counts, examples = scan_cache(namespaces)

    gaps = []
    for key, n in counts.items():
        _ns, concept = key.split(":", 1)
        if concept in known:
            continue
        if n < min_companies:
            continue
        if exclude_noise and any(noise in concept for noise in NOISE_SUBSTRINGS):
            continue
        if key in dismissed and not include_dismissed:
            continue
        gaps.append((n, key, examples[key]))
    gaps.sort(reverse=True)
    return gaps
