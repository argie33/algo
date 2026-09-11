"""Post-transform value-plausibility validation methods (EPS/net_income/gross_profit/
debt/goodwill/revenue) for ConsolidatedFinancialStatementsLoader - sibling half of
loaders/helpers/financial_statements_share_count_validation.py (see that module's docstring for
the full split rationale: both came from one 992-line extraction out of
load_financial_statements.py, split again on a 2026-09-07 new-file-cap failure into two
cohesive-by-sub-topic halves). Pure code motion, no method body changed.

Relies on attributes/methods defined on ConsolidatedFinancialStatementsLoader itself
(self.table_name, self.statement_type, self.period, self._record_explicit_null_rejection) -
not usable standalone, same convention as loaders/helpers/sec_valuations_ratios.py's
SecValuationRatiosMixin.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FinancialStatementsValueValidationMixin:
    """EPS/net_income/gross_profit/debt/goodwill/revenue plausibility checks for
    ConsolidatedFinancialStatementsLoader. Not usable standalone - relies on attributes/methods
    defined on that class.
    """

    # Type-only declarations (no values) so mypy resolves the self.X reads below - the real
    # values/methods are defined on ConsolidatedFinancialStatementsLoader, the only class this
    # mixin is ever combined with.
    table_name: str
    statement_type: str
    period: str

    def _record_explicit_null_rejection(self, row: dict[str, Any], field: str, reason: str) -> None: ...

    def _reject_implausible_eps(self, transformed: list[dict[str, Any]]) -> None:
        """Reject earnings_per_share/diluted_eps values that are confidently wrong due to
        filer-side XBRL tagging errors, not a SEC API normalization issue like the shares
        guard above. Mutates `transformed` in place.

        FOUND 2026-08-23 (goal session: real-money-readiness "why does earnings_per_share
        say -$24,852,333/share" audit): live-confirmed via GIBO's real companyfacts JSON -
        the filer itself tagged EarningsPerShareBasic under the correct "USD/shares" unit
        but with the SAME raw value as that year's NetIncomeLoss (FY2023: both exactly
        -12,117,569; FY2024: both exactly -24,852,333) - i.e. the filer's own XBRL reports
        total net income as if it were per-share, not a unit-parsing bug on our side (no
        currency/unit filter would catch this - the unit tag is correct, the underlying
        number is wrong). Also live-confirmed on BTTC, HQ, GROY, BRUN, and EP's FY2013/2014
        (eps==net_income exactly), plus a related /1000 variant (FLOC: eps=32,729 vs
        net_income=32,729,000 - implied ~1,000 shares). No consumer downstream (growth_metrics'
        eps_growth_*) reliably catches this: the resulting YoY growth RATIO between two
        similarly-corrupted years can look like an ordinary percentage (GIBO's eps_growth_1y
        computed a plausible-looking -100.00), so a wrong-by-millions per-share value was
        reaching stock_scores/growth_metrics undetected. Implied-shares floor deliberately
        low (10,000) - BRK.A (~1.6M real shares) and foreign large-caps reporting in local
        currency (BSAC ~471M CLP shares, EC ~2.06B COP shares) all clear it comfortably;
        only implies-basically-no-real-float cases like the ones above trip it.
        """
        min_plausible_implied_shares = 10_000
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, eps_
        # reconciliation follow-up): the implied-shares floor above only catches the
        # "eps==net_income" extreme (implies basically zero real shares) - it does NOT catch
        # a filer-side decimal/scale error that lands on a still-plausible-looking implied
        # share count. Live-confirmed via NRC (National Research Corporation, CIK 0000070487):
        # FY2025 10-K tags EarningsPerShareDiluted=$50.00 against real NetIncomeLoss=
        # $11,600,000 - implied_shares = 232,000, comfortably above the 10,000 floor (so the
        # check above never fires), but NRC's OWN real weighted-average diluted share count
        # for the SAME row is 22,396,000 - a ~96x gap, and $50/share is obviously wrong for a
        # company whose real diluted EPS is ~$0.52 (a real, filed 10-K/Q shows the correct
        # scale in adjacent periods: FY2024 diluted_eps=$1.04 against 23,743,000 shares, an
        # entirely normal-looking figure). Unlike the shares_outstanding guard above, this
        # row already carries its own real share count from the SAME extraction - a much
        # tighter, symbol-specific cross-check than the earlier absolute floor, so a generous
        # 10x tolerance (well outside any real dilution/NCI/preferred-dividend spread, which
        # tie_out.py's own eps_reconciliation check already tolerates at 15%) still leaves no
        # room for a genuine EPS to trip it while catching this exact scale-error shape.
        eps_shares_field = {
            "earnings_per_share": "shares_outstanding_basic",
            "diluted_eps": "shares_outstanding_diluted",
        }
        max_implied_vs_reported_shares_ratio = 10.0
        # FIXED 2026-09-10 (goal: "SEC/XBRL missing data to zero" sweep, eps_never_tagged_
        # in_filings follow-up): the NRC-shaped ratio guard above assumes the row's OWN
        # reported share count is reliable ground truth, so a big gap must mean EPS is
        # wrong. Live-confirmed via EH (EHang)'s real companyfacts JSON this assumption is
        # backwards for a distinct failure shape: EH tags a real, correct
        # EarningsPerShareBasic/Diluted (FY2024 -$0.23, FY2025 -$0.27) against a real,
        # correct NetIncomeLoss (FY2024 -$31.48M) - implied_shares ~136.9M, a perfectly
        # plausible real public float - but the FILER'S OWN
        # WeightedAverageNumberOfSharesOutstandingBasic/Diluted tag is 134,367 (a ~1,020x
        # scale-tagging error on the SHARES concept itself, not the EPS concept - the filer
        # dropped the trailing "000" a real ADS-equivalent count would carry). Blindly
        # nulling EPS here destroyed EH's genuinely-correct income-statement data. The
        # asymmetry that distinguishes this from NRC: NRC's reported_shares (22,396,000) is
        # itself a perfectly plausible real-company share count, so a gap against implied_
        # shares means implied (i.e. EPS) is wrong; EH's reported_shares (134,367) is itself
        # implausibly small for any real operating company's weighted-average share count,
        # while its implied_shares is not - meaning reported_shares is the corrupted side,
        # not EPS. Checking magnitude plausibility of reported_shares directly (not just the
        # ratio) generalizes this without reopening NRC/GIBO/FLOC/BTTC/HQ/GROY/BRUN/EP - none
        # of those hit this branch anyway (GIBO/FLOC/BTTC/HQ/GROY/BRUN/EP are all caught by
        # the earlier eps==net_income implied-shares floor above and never reach this ratio
        # check at all; NRC's reported_shares comfortably clears this floor so it still
        # falls through to the reject branch below, unchanged).
        min_plausible_reported_shares_for_real_company = 1_000_000
        # BUG FOUND 2026-08-31 (goal session: "let's check the logs" sweep of live loader
        # output): SWK/UAMY quarterly rows hit the raw NUMERIC(12,4) column-overflow guard in
        # sec_base.py instead of this smarter rejection (e.g. "earnings_per_share=150330000")
        # - live-confirmed the reason: this function's implied-shares check requires
        # net_income to be present and non-zero for the SAME row, but a quarterly row can
        # have net_income missing/None while still carrying a garbage per-share value from
        # the identical filer-side mistagging bug this function already exists to catch. The
        # `continue` above skipped the whole row, so the garbage value reached the DB-insert
        # layer's overflow guard instead - which fails safe (data_unavailable) but with a
        # worse error and none of the informative "why" this function provides. Add an
        # absolute-magnitude fallback that doesn't need net_income at all: no real company has
        # ever reported anywhere near $1,000,000/share EPS in a single period (BRK.A's real
        # historical extremes, driven by unrealized investment gains, stay under $200,000/share
        # even in exceptional years - this floor leaves >5x headroom above that).
        max_plausible_abs_eps = 1_000_000
        for row in transformed:
            net_income = row.get("net_income")
            has_net_income = net_income is not None and net_income != 0
            for field in ("earnings_per_share", "diluted_eps"):
                eps = row.get(field)
                if eps is None or eps == 0:
                    continue
                if has_net_income:
                    assert net_income is not None  # narrows for mypy; has_net_income already guarantees this
                    implied_shares = abs(float(net_income) / float(eps))
                    if implied_shares < min_plausible_implied_shares:
                        logger.warning(
                            f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                            f"{field}={eps} implies only {implied_shares:,.0f} shares outstanding "
                            f"against net_income={net_income:,.0f} - implausibly low for any real "
                            "public float. Filer-side XBRL tagging error (raw net income reported "
                            "as per-share), not a currency/scale issue. Rejecting rather than "
                            "storing a confidently-wrong per-share value."
                        )
                        row[field] = None
                        self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                        continue
                    reported_shares = row.get(eps_shares_field[field])
                    if reported_shares is not None and float(reported_shares) > 0:
                        shares_ratio = max(implied_shares, float(reported_shares)) / min(
                            implied_shares, float(reported_shares)
                        )
                        if (
                            shares_ratio > max_implied_vs_reported_shares_ratio
                            and float(reported_shares) < min_plausible_reported_shares_for_real_company
                            and implied_shares >= min_plausible_reported_shares_for_real_company
                        ):
                            logger.info(
                                f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                                f"{field}={eps} implies {implied_shares:,.0f} shares (plausible) against "
                                f"net_income={net_income:,.0f}, but this row's own "
                                f"{eps_shares_field[field]}={float(reported_shares):,.0f} is itself "
                                f"implausibly small ({shares_ratio:,.0f}x gap) - EH-shaped: the "
                                "reported share count is the filer-side scale-tagging error, not "
                                "the EPS. Keeping the real, correctly-tagged EPS value rather than "
                                "nulling it over a corrupted sibling field."
                            )
                            continue
                        if shares_ratio > max_implied_vs_reported_shares_ratio:
                            logger.warning(
                                f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                                f"{field}={eps} implies {implied_shares:,.0f} shares against "
                                f"net_income={net_income:,.0f}, but this row's own "
                                f"{eps_shares_field[field]}={float(reported_shares):,.0f} - a "
                                f"{shares_ratio:,.0f}x gap. Filer-side decimal/scale tagging error "
                                "(NRC-shaped: a plausible-looking implied share count that still "
                                "disagrees with this row's own real share count), not a currency/"
                                "scale issue. Rejecting rather than storing a confidently-wrong "
                                "per-share value."
                            )
                            row[field] = None
                            self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                            continue
                if abs(float(eps)) > max_plausible_abs_eps:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={eps} exceeds ${max_plausible_abs_eps:,}/share - implausible for "
                        "any real filer regardless of net_income availability (net_income was "
                        f"{'unavailable/zero' if not has_net_income else f'{net_income:,.0f}'} for "
                        "this row, so the implied-shares cross-check above couldn't run). Same "
                        "filer-side XBRL tagging error class, caught via absolute magnitude "
                        "instead. Rejecting rather than storing a confidently-wrong per-share "
                        "value or letting it hit the raw column-overflow guard downstream."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")

    def _reject_scale_mismatched_net_income(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `net_income` when it's a clean 1,000x or 1,000,000x-too-small multiple of
        (pretax_income - income_tax_expense) - the same filer-side "reported in thousands/
        millions under a whole-dollar concept" scale error `_reject_implausible_eps`'s own
        docstring already names (the FLOC case: eps=32,729 vs net_income=32,729,000), just
        caught here from the other side of that same identity, for rows where pretax_income/
        income_tax_expense happen to carry the correct scale while net_income itself doesn't.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, pretax_to_
        net_income follow-up - this identity's own 593-symbol tie-out failure count hadn't
        moved all session despite several sibling fixes landing). Live-confirmed via 3 of
        this check's own top offenders: MVBF (pretax=$36,850,000, tax=$9,928,000,
        net_income=$26,922 - pretax-tax=$26,922,000, an EXACT 1,000x match), KWY
        (pretax=-$14,004,000, tax=-$3,752,000, net_income=-$10,252 - pretax-tax=-$10,252,000,
        exact match), NXPL (pretax=-$10,463,000, tax=$0, net_income=-$10,463 - exact match).
        Unlike `_reject_implausible_eps`'s fp=None non-integer detector (which catches this
        exact bug shape but only for EPS, and only for proxy-statement-sourced facts), this
        targets net_income directly, regardless of source form, since a clean multiplicative
        match against this row's own pretax_income/income_tax_expense is precise enough on
        its own - no reliance on the fact's form/fp (already gone by the time `transformed`
        rows reach this stage).

        Deliberately does NOT attempt to "fix" the value by multiplying it back up: with
        `pretax_income - income_tax_expense` itself sometimes wrong instead (ambiguous from
        magnitude alone, same as `_reject_implausible_eps`'s MVBF/TE-shaped mirror case),
        nulling is the same "honest NULL over a confidently-wrong number" choice made
        throughout this file - either value being wrong corrupts the same downstream ratios
        (ROE, net_margin, ...) equally, so which one gets nulled doesn't change the outcome.
        Tolerance (20% of the scaled comparison, not tie_out.py's tighter 10%/$500K) is
        deliberately loose: this only needs to recognize "unmistakably the same multiplicative
        family", not reconcile the identity precisely - genuine NCI/discontinued-operations
        noise this file's own pretax_to_net_income WARN check already tolerates can push a
        real match a few points off 1,000x/1,000,000x without this guard losing confidence
        that it's still the same scale-error shape.
        """
        min_plausible_abs_expected = 100_000.0
        scale_tolerance_pct = 0.20
        for row in transformed:
            net_income = row.get("net_income")
            pretax_income = row.get("pretax_income")
            income_tax_expense = row.get("income_tax_expense")
            if net_income is None or net_income == 0 or pretax_income is None or income_tax_expense is None:
                continue
            expected = float(pretax_income) - float(income_tax_expense)
            if abs(expected) < min_plausible_abs_expected:
                continue
            for scale in (1_000, 1_000_000):
                scaled_net_income = float(net_income) * scale
                relative_error = abs(scaled_net_income - expected) / abs(expected)
                if relative_error <= scale_tolerance_pct:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"net_income={net_income:,.0f} is a {scale:,}x-too-small match against "
                        f"pretax_income({pretax_income:,.0f}) - income_tax_expense("
                        f"{income_tax_expense:,.0f}) = {expected:,.0f} (net_income*{scale:,} = "
                        f"{scaled_net_income:,.0f}, {relative_error:.1%} residual). Filer-side "
                        "scale tagging error (reported in thousands/millions under a whole-"
                        "dollar concept), not a currency issue. Rejecting rather than storing a "
                        "confidently-wrong net_income."
                    )
                    row["net_income"] = None
                    self._record_explicit_null_rejection(row, "net_income", "net_income_scale_error")
                    break

    def _reject_implausible_gross_profit(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `gross_profit` when it exceeds revenue by more than 3x while cost_of_revenue
        is a real, positive figure - not a tolerance/measurement-noise check like
        algo/monitoring/data_patrol/checks/tie_out.py's own gross_profit_identity WARN (2%
        tolerance, still exploratory per that file's own docstring), but a hard mathematical
        impossibility check: gross_profit = revenue - cost_of_revenue, so with a real positive
        cost_of_revenue on the same row, gross_profit can never legitimately exceed revenue at
        all, let alone by 3x+.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
        identity follow-up). Live-confirmed via HCTI: FY2025 10-K/A tags GrossProfit=
        $1,235,000,000 against real revenue=$13,891,000 and cost_of_revenue=$12,001,000 (real
        FY2025 gross profit is ~$1.89M - HCTI's own Q2 2026 10-Q shows a comparable-scale
        $4.459M half-year gross profit, confirming the real business is nowhere near
        $1.235B) - an ~89x overstatement, a filer/filing-agent tagging error in the amendment
        itself. Not a clean round-multiple scale error (unlike `_reject_scale_mismatched_
        net_income` above) - no single scale factor to detect, so this uses the simpler
        "impossible under the definitional identity" signal instead. 3x threshold (not 1x)
        deliberately leaves room for a company reporting an adjusted/non-strictly-definitional
        gross profit figure that legitimately differs somewhat from the raw subtraction -
        only rejects an extreme, order-of-magnitude-style violation.
        """
        max_plausible_gross_profit_to_revenue_ratio = 3.0
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or revenue <= 0 or cost_of_revenue is None or cost_of_revenue <= 0:
                continue
            if gross_profit is None:
                continue
            if float(gross_profit) > float(revenue) * max_plausible_gross_profit_to_revenue_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"gross_profit={gross_profit:,.0f} exceeds {max_plausible_gross_profit_to_revenue_ratio:.0f}x "
                    f"revenue({revenue:,.0f}) while cost_of_revenue({cost_of_revenue:,.0f}) is a real positive "
                    "figure - mathematically impossible under gross_profit = revenue - cost_of_revenue. "
                    "Filer-side tagging error, not a currency/scale issue with a clean multiple. Rejecting "
                    "rather than storing a confidently-wrong gross_profit."
                )
                row["gross_profit"] = None
                self._record_explicit_null_rejection(row, "gross_profit", "implausible_gross_profit_scale_error")

    def _reject_stale_gross_profit_without_fresh_concept(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null a stale `gross_profit` value for any (symbol, fiscal_year) where this
        run's fresh SEC extraction has both revenue and cost_of_revenue but no fresh
        gross_profit fact of its own. Mutates nothing in `transformed` directly - records the
        rejection so post_run() force-nulls the DB column, bypassing preserve_on_missing_
        fields' COALESCE (see the 2026-08-23 fix comment in __init__ for why that's necessary
        for a deliberate rejection, as opposed to a transient fetch gap).

        ADDED 2026-09-06 (goal session: tie-out-checker follow-up on the gross_profit_identity
        magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/tie_out.py's Round 2
        docstring). Live-confirmed via real SEC companyfacts JSON: ABBV/GILD/AMGN/ABT's only
        "GrossProfit" XBRL facts are a supplementary Q4-only quarterly-data-table stub (e.g.
        ABBV FY2024: start=2024-10-01/end=2024-12-31, a 91-day span) - correctly rejected by
        the annual span_days<330 check in sec_statements_entry_resolution.py, so the CURRENT
        extraction code produces no gross_profit value for these filers at all (confirmed via a
        direct get_income_statement() call: fresh rows have revenue/cost_of_revenue populated,
        no "gross_profit" key). The non-NULL gross_profit already stored for these rows
        (ABBV FY2025: $12.066B, live-identified by the tie-out checker as failing revenue
        ($61.16B) - cost_of_revenue($18.204B) ~= gross_profit by a ~3.6x margin - the real
        implied figure is ~$42.96B) is a leftover from BEFORE that span check existed, silently
        protected ever since by preserve_on_missing_fields' COALESCE. fetch_incremental()
        always refetches a symbol's FULL XBRL history in one company-facts API call (no
        incremental date cutoff), so this run's absence of a gross_profit fact for a fiscal
        year that DOES have fresh revenue/cost_of_revenue is not the kind of transient gap
        preserve_on_missing_fields exists to protect - the concept genuinely produces no usable
        annual value for this filer/year under the current, correct code, so any stored value
        must be stale. Same force-null-bypasses-COALESCE mechanism as
        _reject_implausible_eps/_reject_implausible_shares_outstanding above; post_run()'s
        UPDATE is a no-op for a row where gross_profit is already NULL, so this is safe to run
        unconditionally for every annual income-statement row with fresh revenue and
        cost_of_revenue, not just the 4 symbols found so far. Annual-only (self.period ==
        "annual") - quarterly's own real Q4 GrossProfit fact legitimately has this same ~90-day
        span, so quarterly extraction isn't affected by (or exposed to) this bug.
        """
        if self.period != "annual":
            return
        for row in transformed:
            if row.get("revenue") is None or row.get("cost_of_revenue") is None or row.get("gross_profit") is not None:
                continue
            self._record_explicit_null_rejection(row, "gross_profit", "gross_profit_stale_no_fresh_annual_concept")

    def _reject_implausible_debt_field(self, transformed: list[dict[str, Any]], field: str) -> None:
        """Reject `field` (long_term_debt or short_term_debt) when it exceeds total_assets by
        more than 20x, on the same row - not a tolerance/measurement-noise check like
        algo/monitoring/data_patrol/checks/tie_out.py's own check_long_term_debt_le_total_
        liabilities WARN, but a hard sanity floor: no real operating company carries debt more
        than 20x its own total assets.

        FOUND 2026-09-07 (goal session: live tie-out run against production DB surfaced 62
        annual long_term_debt_le_total_liabilities violations; digging into the worst ones
        found this instead). Live-confirmed via real SEC companyfacts JSON: VGAS (Verde Clean
        Fuels) FY2023 tags us-gaap:ConvertibleDebt=$40,963,000,000 as of 2023-03-31 in a Q1
        2024 10-Q's prior-period comparative column - VGAS's own real total_assets that year
        is ~$31.9M (10-K FY2023, filed 2024-03-28), a company with zero plausible path to
        $40.96B in convertible debt. A DB-wide sweep found 61 similar symbol-years (BGDE:
        $28.1 TRILLION vs $133M assets; AM: $2.89 TRILLION vs $6.28B assets; CTGO: $44.68B vs
        $58.6M assets) - all fallback-only concepts (ConvertibleDebt/OtherLongTermDebt/
        SecuredLongTermDebt/etc., see sec_balance_sheet.py's concept list), all a filer/filing-
        agent XBRL tagging error, not a clean round-multiple scale error (unlike
        `_reject_scale_mismatched_net_income`) - same "impossible under a hard sanity bound"
        signal as `_reject_implausible_gross_profit` above, just for debt-vs-assets instead of
        gross-profit-vs-revenue. NOTE: BGDE/AM were previously one-off DB-patched (memory:
        skm_bgde_am_orphaned_ltd, 2026-09-06) but had already recurred by this session - a
        one-time DB UPDATE doesn't survive the next incremental re-fetch of the same bad SEC
        source fact, so this needs a persistent extraction-time guard, not just another patch.
        20x deliberately leaves room for genuinely highly-levered financials/BDCs/REITs (which
        legitimately run high debt-to-assets) while still rejecting order-of-magnitude filer
        errors.
        """
        if self.statement_type != "balance":
            return
        max_plausible_debt_to_assets_ratio = 20.0
        for row in transformed:
            total_assets = row.get("total_assets")
            value = row.get(field)
            if total_assets is None or total_assets <= 0 or value is None:
                continue
            if float(value) > float(total_assets) * max_plausible_debt_to_assets_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"{field}={value:,.0f} exceeds {max_plausible_debt_to_assets_ratio:.0f}x "
                    f"total_assets({total_assets:,.0f}) - filer-side XBRL tagging error, not a "
                    "real debt figure. Rejecting rather than storing a confidently-wrong value."
                )
                row[field] = None
                self._record_explicit_null_rejection(row, field, "implausible_debt_vs_total_assets_scale_error")

    def _reject_implausible_goodwill(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `goodwill` when it exceeds `total_assets` on the same row - not a
        tolerance/measurement-noise check like algo/monitoring/data_patrol/checks/tie_out.py's
        own goodwill_le_total_assets WARN, but a hard mathematical impossibility: goodwill is
        one of the line items summed INTO total_assets on a balance sheet, so it can never
        legitimately exceed total_assets, not even slightly - unlike
        `_reject_implausible_debt_field`'s 20x tolerance (real companies can carry debt many
        times their asset base), there is no legitimate multiple here at all.

        FOUND 2026-09-07 (goal session: tie-out score-sanity audit, goodwill_le_total_assets
        live triage). Live-confirmed via real SEC companyfacts JSON, all from the filer's OWN
        real, primary-form (10-K/20-F) filing, not a comparative echo or wrong-period bug in
        this pipeline's extraction: ILLR FY2024 tags Goodwill=$1,005,778,000 against its own
        same-filing Assets=$50,578,000 (a ~20x overstatement); BTCT (foreign private issuer,
        20-F) FY2022 tags Goodwill=$192,962,000 against Assets that never exceed ~$40M in any
        surrounding period; MTC (20-F) tags the identical Goodwill=$108,218,586 across THREE
        straight fiscal years (2023/2024/2025) while Assets is only ~$18.4M - the frozen,
        unchanging-for-3-years figure is itself a signature of a stale/comparative value the
        filer's own XBRL never actually updated. Small tolerance (1.05x) rather than an exact
        0x to allow trivial same-period rounding noise between the two facts' filing contexts,
        not because a real excess is ever legitimate.
        """
        if self.statement_type != "balance":
            return
        max_plausible_goodwill_to_assets_ratio = 1.05
        for row in transformed:
            total_assets = row.get("total_assets")
            goodwill = row.get("goodwill")
            if total_assets is None or total_assets <= 0 or goodwill is None:
                continue
            if float(goodwill) > float(total_assets) * max_plausible_goodwill_to_assets_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"goodwill={goodwill:,.0f} exceeds total_assets({total_assets:,.0f}) - "
                    "mathematically impossible (goodwill is one of the line items summed into "
                    "total_assets). Filer-side tagging error or stale comparative, not a real "
                    "figure. Rejecting rather than storing a confidently-wrong value."
                )
                row["goodwill"] = None
                self._record_explicit_null_rejection(row, "goodwill", "implausible_goodwill_exceeds_total_assets")

    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
    # identity follow-up to the ABBV/GILD/AMGN/ABT stale-stub fix above): live-confirmed via
    # real SEC companyfacts JSON that Centene (CNC) and Elevance Health (ELV) - both managed-
    # care health insurers, SIC "Hospital & Medical Service Plans" - tag their OWN "GrossProfit"/
    # "CostOfGoodsAndServicesSold" XBRL concepts to a narrow, real sub-calculation (their non-
    # premium service-fee segments only, ~$2.7-21B) that EXCLUDES their dominant cost line -
    # medical claims/benefits expense, tagged separately as PolicyholderBenefitsAndClaims
    # IncurredHealthCare/BenefitsLossesAndExpenses (CNC FY2023 $118.9B, ELV H1'26-annualized
    # ~$193B) - which this pipeline never maps to cost_of_revenue at all. Unlike HCTI's
    # gross_profit bug above (a filing-agent tagging ERROR, not a real number at all), CNC's/
    # ELV's $2.67B/$21.2B "GrossProfit"/"CostOfGoodsAndServicesSold" figures ARE real, filer-
    # reported facts - just not economically comparable to a retailer's gross margin, since they
    # cover only a small slice of the filer's true cost structure. Live-cross-checked their real
    # peers to confirm this is NOT a blanket "insurers are all wrong" issue: MOH/HUM (no
    # GrossProfit tag at all, correctly NULL already) and UNH/CI/CVS (real, meaningful
    # CostOfGoodsAndServicesSold figures for their own genuine PBM/retail-pharmacy product
    # segments, ~50-55% of revenue - a real, comparable cost ratio, not this bug) are unaffected
    # and must NOT be touched by this fix. A curated, individually-verified rejection (same
    # discipline as this file's other symbol-specific overrides) rather than a SIC-wide null,
    # which would incorrectly also blank UNH/CI/CVS's real PBM segment cost data.
    _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS = frozenset({"CNC", "ELV"})

    def _reject_partial_segment_gross_profit_for_managed_care_insurers(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null gross_profit/cost_of_revenue for the curated managed-care symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS:
                continue
            for field in ("gross_profit", "cost_of_revenue"):
                if row.get(field) is None:
                    continue
                row[field] = None
                self._record_explicit_null_rejection(row, field, "managed_care_partial_segment_cost_not_total")

    # ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI sweep,
    # gross_profit_identity live re-check after the CNC/ELV/TYGO fixes): live-confirmed via
    # real SEC companyfacts JSON that Altria (MO) is the MIRROR IMAGE of CNC/ELV's bug - here
    # `GrossProfit` is the real, complete, filer-tagged total (matches Revenue exactly minus
    # Altria's true cost of sales), but `CostOfGoodsAndServicesSold` is the PARTIAL concept:
    # every single fiscal year 2016-2025 (`data.sec.gov/api/xbrl/companyconcept/
    # CIK0000764180/us-gaap/CostOfGoodsAndServicesSold.json` vs `.../GrossProfit.json` vs
    # `.../RevenueFromContractWithCustomerExcludingAssessedTax.json`), Revenue - COGS !=
    # GrossProfit by a large, growing margin (FY2025: $23.279B - $5.597B = $17.682B tagged-
    # COGS-implied gross profit vs. the real, filer-tagged GrossProfit of only $14.542B - a
    # $3.14B gap, this pipeline's own `gross_profit_identity` tie-out check's residual).
    # Peer-checked to confirm this is Altria-specific, NOT a tobacco/excise-tax-industry-wide
    # pattern: Philip Morris International (PM, CIK 0001413329) reconciles EXACTLY for the
    # same FY2025 period ($40.648B revenue - $13.366B COGS = $27.282B GrossProfit, to the
    # dollar) - a real, comparable filer in the same industry with the identical excise-tax-
    # exclusion revenue concept shows no such gap, ruling out an industry-wide accounting
    # convention as the explanation. Curated single-symbol rejection (same discipline as
    # _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS above) - only cost_of_revenue is
    # nulled here, NOT gross_profit, since GrossProfit is the reliable, complete figure in
    # this case (opposite of CNC/ELV, where GrossProfit itself was the partial concept).
    #
    # ADDED 2026-09-07 (same goal session, gross_profit_identity live triage continuation,
    # batch 21-45 by residual): ZIM Integrated Shipping (ZIM, CIK 0001654126, a container-
    # shipping line filing 20-F under IFRS) - live-confirmed via real SEC companyfacts JSON:
    # ifrs-full "RevenueFromContractsWithCustomers" ($6.9042B FY2025) - "CostOfSales"
    # ($4.4608B) implies a $2.4434B gross profit (35.4% margin), but the real, filer-tagged
    # "GrossProfit" is only $1.3209B (19.1% margin) - a $1.1225B gap, exactly this pipeline's
    # own gross_profit_identity residual. Unlike TTEK/TAP (a single missing additive concept
    # that reconciles the gap exactly - see _fill_cost_of_revenue_from_other_operating_cost()),
    # an exhaustive scan of every ifrs-full concept for this exact fiscal-year period found NO
    # single concept matching the $1.1225B gap (TransportationExpense $2.1021B and FuelExpense
    # $1.1467B are both real, large, separately-tagged shipping-specific cost lines, but neither
    # alone nor their sum closes the gap exactly) - ruling out the clean-sum pattern. The lower,
    # real GrossProfit figure is corroborated as the reliable one: GrossProfit ($1.3209B) -
    # ProfitLossFromOperatingActivities ($1.016B) = $304.9M, a plausible SG&A-scale residual,
    # while CostOfSales's implied 35.4% gross margin is implausibly high for bulk container
    # shipping's well-known thin-margin economics. No good SEC-registered direct peer exists
    # (most major container lines - Maersk, COSCO, CMA CGM, Hapag-Lloyd - aren't SEC-listed) so
    # this is verified via internal consistency (the operating-income cross-check above) rather
    # than a peer comparison, same as this constant's original MO entry when it predated the PM
    # peer-check precedent.
    _PARTIAL_COST_OF_REVENUE_SYMBOLS = frozenset({"MO", "ZIM"})

    def _reject_partial_cost_of_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null cost_of_revenue (keeping gross_profit) for the curated symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_COST_OF_REVENUE_SYMBOLS:
                continue
            if row.get("cost_of_revenue") is None:
                continue
            row["cost_of_revenue"] = None
            self._record_explicit_null_rejection(row, "cost_of_revenue", "cost_of_revenue_partial_concept_not_total")

    def _reject_scale_mismatched_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `revenue` when it's a clean power-of-10 multiple (100x/1000x/10000x, within
        1%) of (cost_of_revenue + gross_profit) - the same magic-ratio detection already
        proven safe in sec_statements_entry_resolution.py's frame_magnitude_scale_guard (the
        IPAR fix), applied to this pipeline's own concept-priority chain instead of SEC's
        frame-preference tiebreak.

        FOUND 2026-09-06 (goal: score/tie-out sanity audit, gross_profit_identity's current
        top-flagged-by-magnitude non-CNC/ELV offender). Live-confirmed via TYGO's (Tigo
        Energy) real SEC companyfacts JSON: the filer's OWN XBRL genuinely mistags
        RevenueFromContractWithCustomerExcludingAssessedTax at exactly 1000x the correct value
        for every single fiscal year on record (2022: $81.323B tagged vs. $81.323M real;
        2023/2024/2025 same shape) - NOT an extraction-side wrong-context bug like the tie-out
        checker's other gross_profit_identity leads (CNC/ELV, ABBV/GILD/AMGN/ABT): TYGO's own
        "Revenues" concept for the identical periods is correctly tagged every time, and
        _INCOME_FIELD_MAPPING's documented "ExcludingAssessedTax must win when both are
        present" priority (correct for the overwhelming majority of filers, where
        ExcludingAssessedTax is the more precise net-revenue figure) picks the corrupted one
        for this filer specifically. cost_of_revenue/gross_profit are unaffected (both come
        from separate, correctly-tagged concepts), so their sum is the independent, trustworthy
        anchor to validate revenue against - exactly the same role gross_profit_identity's
        `implied_gross_profit` plays in algo/monitoring/data_patrol/checks/tie_out.py, just run
        pre-storage instead of as a post-hoc read-only WARN. DB-wide live scan confirmed this
        exact 1000x pattern currently affects only TYGO (4 rows total, all its own fiscal
        years) - not a systemic bug, so this guard is expected to fire rarely; a legitimate
        filer's revenue vs. cost_of_revenue+gross_profit will essentially never land within 1%
        of an exact power of 10 by chance.
        """
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or cost_of_revenue is None or gross_profit is None:
                continue
            implied_revenue = float(cost_of_revenue) + float(gross_profit)
            if implied_revenue == 0 or revenue == 0:
                continue
            ratio = abs(float(revenue)) / abs(implied_revenue)
            if ratio < 1:
                ratio = 1 / ratio
            if any(abs(ratio - power) / power < 0.01 for power in (100, 1000, 10000)):
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"revenue={revenue:,.0f} is a {ratio:.0f}x-scaled outlier vs. "
                    f"cost_of_revenue+gross_profit={implied_revenue:,.0f} - likely a filer-side "
                    "XBRL tagging error on the higher-priority revenue concept, not a real "
                    "business figure. Rejecting rather than storing a confidently-wrong value."
                )
                row["revenue"] = None
                self._record_explicit_null_rejection(row, "revenue", "revenue_scale_mismatch_vs_cogs_plus_gp")

    def _fill_operating_income_from_revenue_cost_and_opex(self, transformed: list[dict[str, Any]]) -> None:
        """Fallback-only: operating_income = revenue - cost_of_revenue - operating_expenses,
        for filers whose final, fully-mapped row has all three real values but no
        OperatingIncomeLoss/CostsAndExpenses concept anywhere in their filing history.

        ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 300" push, operating_income_
        not_itemized re-investigation continuation). utils/external/sec_income_statement_
        fallbacks.py already covers two narrower shapes at the raw-concept-name stage (before
        _INCOME_FIELD_MAPPING consolidates a filer's specific tagged concepts into the
        canonical "revenue"/"cost_of_revenue"/"operating_expenses" columns): the CASY-style
        D&A-split COGS pair, and the KRC/BEEP no-COGS-at-all case. Live-confirmed via CPT
        (Camden Property Trust, apartment REIT) and CRVL (CorVel Corp): both tag a real
        single, unsplit COGS-family concept under a filer-specific raw key that only becomes
        "cost_of_revenue" after this pipeline's later field-mapping stage - by the time either
        raw-stage fallback above runs, the row doesn't have a plain "revenue"/"cost_of_revenue"/
        "operating_expenses" key to match on at all (CPT's real revenue sits under
        "operating_lease_lease_income" pre-mapping, a REIT-exclusive field; an earlier attempt
        to add this derivation inside get_income_statement() itself was live-tested against
        real SEC data and found to be dead code for exactly this reason). Running here
        instead, after super().transform() has already resolved every filer's own concept
        naming into the three canonical columns, means one general check covers any filer
        shape rather than needing a new raw-concept-name fallback per taxonomy variant. CPT
        FY2025: revenue=$1,573,544,000 - cost_of_revenue=$566,710,000 -
        operating_expenses=$79,344,000 = $927,490,000 (59% margin before depreciation,
        plausible for a REIT).

        Runs after _reject_scale_mismatched_revenue/_reject_partial_cost_of_revenue above so
        a since-nulled implausible revenue/cost_of_revenue can never feed a derived value.
        Deliberately requires all three real values - same "no partial, systematically-wrong
        value" discipline as every sibling fallback in this pipeline. Never overwrites a real
        operating_income already on the row (from a directly-tagged OperatingIncomeLoss
        concept, or an earlier fallback in sec_income_statement_fallbacks.py).
        """
        for row in transformed:
            if row.get("operating_income") is not None:
                continue
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            operating_expenses = row.get("operating_expenses")
            if revenue is None or cost_of_revenue is None or operating_expenses is None:
                continue
            row["operating_income"] = float(revenue) - float(cost_of_revenue) - float(operating_expenses)
