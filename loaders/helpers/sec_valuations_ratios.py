"""Core per-share valuation ratios (PE/PB/PS/PEG) for SecValuationsLoader._compute_valuations,
extracted from load_sec_valuations.py (2026-09-05, file-size ratchet: that file is one of the
Tier-1 bloaters flagged for decomposition, see MEMORY.md's bloater_decomposition_strategy_20260905).
Each method is verbatim (only the `result["x_ratio"] = ...` assignment became a `return`, and
the "leave it None" branches became `return None`) - mixed into SecValuationsLoader, which still
defines every MIN_PLAUSIBLE_PE_RATIO/MIN_PLAUSIBLE_PB_RATIO/MIN_PLAUSIBLE_PS_RATIO class constant
this file reads via `self`, so behavior is unchanged - only the code moved file and got wrapped
in a `return` instead of a dict assignment.
"""

import logging

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SecValuationRatiosMixin:
    """PE/PB/PS/PEG ratio computation methods for SecValuationsLoader. Not usable standalone -
    relies on class constants defined on SecValuationsLoader itself.
    """

    # Type-only declarations (no values) so mypy resolves the `self.X` reads below - the real
    # values are class constants defined on SecValuationsLoader, the only class this mixin is
    # ever combined with.
    MIN_PLAUSIBLE_PE_RATIO: float
    MIN_PLAUSIBLE_PB_RATIO: float
    MIN_PLAUSIBLE_PS_RATIO: float

    def _compute_pe_ratio(self, symbol: str, current_price: float, ttm_eps: float | None) -> float | None:
        """PE Ratio = Price ÷ TTM EPS (bound to MIN_PLAUSIBLE_PE_RATIO..10000 - see
        MIN_PLAUSIBLE_PB_RATIO's docstring for the VCIG-driven lower-bound addition)

        ADDED same day (goal session: "implausible values" sweep, follow-up): the 10000
        ceiling doesn't catch every near-zero-EPS blowup - ICUI live-confirmed (FY2025
        annual EPS $0.03, TTM-from-4-real-quarters EPS ~$1.20): pe_ratio=5586 (current_
        price $167.58 / $0.03) sails under the 10000 ceiling and both the ratio-only sanity
        check (_sanity_check_pe_ratio) and this bound accepted it as "plausible", yet the
        true trailing-4-quarter PE is ~140 - the exact same "measurement-window mismatch,
        not a scale bug" case that check's own quarterly-EPS rescue already handles for the
        DIFFERENT failure mode (ratio disagreement with yfinance), just never wired here for
        this one (yfinance had no PE coverage for ICUI, so that check never even ran). A
        near-zero EPS base is unreliable regardless of what magnitude PE it happens to
        produce - same $0.10-floor convention as growth_metrics' own realized eps_growth_1y
        and the same-day forward_eps_growth immaterial-base fix (migration 1259).
        """
        if ttm_eps and ttm_eps > 0:
            pe = current_price / ttm_eps
            if pe <= 10000 and pe >= self.MIN_PLAUSIBLE_PE_RATIO and ttm_eps >= 0.10:
                if self._pe_earnings_too_volatile(symbol):
                    logger.warning(
                        f"[{symbol}] PE ratio {pe:.2f} computed off a single profitable year "
                        "immediately following 2+ net-loss years - excluding from Value scoring "
                        "as an earnings-stability-driven distortion, not a genuine bargain "
                        "(see _pe_earnings_too_volatile)."
                    )
                    return None
                if self._pe_earnings_tax_benefit_inflated(symbol):
                    logger.warning(
                        f"[{symbol}] PE ratio {pe:.2f} computed off net income inflated by a "
                        "large one-off tax benefit relative to pretax income - excluding from "
                        "Value scoring as a tax-driven distortion, not a genuine bargain "
                        "(see _pe_earnings_tax_benefit_inflated)."
                    )
                    return None
                return round(pe, 2)
            elif pe > 10000 or ttm_eps < 0.10:
                # FIXED 2026-09-05 (goal session: "implausible values" sweep) - same
                # missing-cross-year-fallback gap as ps_ratio just above and fcf_margin
                # (loaders/helpers/vqg_quality.py): the anchor year's ttm_eps can be a real but
                # near-zero extraction/reporting artifact even though an older fiscal year has a
                # real, representative EPS that would produce a plausible pe_ratio against the
                # same current_price.
                fallback_pe = None
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT earnings_per_share FROM annual_income_statement
                        WHERE symbol = %s AND earnings_per_share IS NOT NULL
                          AND earnings_per_share > 0 AND data_unavailable IS NOT TRUE
                        ORDER BY fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    older_eps_rows = cur.fetchall()
                for (older_eps,) in older_eps_rows:
                    older_eps_f = float(older_eps)
                    # Require the fallback year's own EPS to clear the same immaterial-base
                    # floor - the query above includes the anchor year itself (fiscal_year
                    # DESC, no offset), so without this an immaterial anchor EPS would just
                    # re-select itself on the first loop iteration.
                    if older_eps_f < 0.10:
                        continue
                    candidate_pe = current_price / older_eps_f
                    if self.MIN_PLAUSIBLE_PE_RATIO <= candidate_pe <= 10000:
                        fallback_pe = candidate_pe
                        break
                if fallback_pe is not None:
                    return round(fallback_pe, 2)
                else:
                    logger.warning(f"[{symbol}] PE ratio out of bounds ({pe:.0f}), marking as NULL")
                    return None
            else:
                logger.warning(
                    f"[{symbol}] PE ratio implausibly low ({pe:.4f} < {self.MIN_PLAUSIBLE_PE_RATIO}), "
                    "excluding from Value scoring rather than letting a single extreme value rank #1."
                )
                return None
        elif ttm_eps == 0:
            # Company is unprofitable this TTM
            return None
        else:
            logger.warning(f"[{symbol}] TTM EPS missing or invalid, PE ratio unavailable")
            return None

    @staticmethod
    def _pe_earnings_too_volatile(symbol: str) -> bool:
        """True when 2+ of the last 3 reported fiscal years' net_income were losses.

        ADDED 2026-09-07 (goal: "digging into scores" audit - "why are distressed companies
        topping the Value leaderboard"). A single profitable year immediately after a run of
        losses can produce a mathematically valid but statistically meaningless "cheap" PE -
        live-confirmed RILY (B. Riley Financial): FY2025 net_income +$307.4M/EPS $9.80 right
        after FY2024 -$764.3M, FY2023 -$99.9M, FY2022 -$159.8M, computing pe_ratio=0.72 and
        ranking #3 on the entire Value factor leaderboard - a company whose earnings swing by
        $1B+ year to year has no business looking "cheap for good reason" off one quarter's
        (Q1 FY2026 alone was $213M of that $307.4M) worth of what reads like a non-recurring
        gain, not durable earnings power. Universe-wide: 82 symbols show this exact "2+
        consecutive loss years then a profit year, now showing a suspiciously cheap PE" shape
        (live query, not assumed).

        Deliberately does NOT try to match the exact fiscal year that produced `ttm_eps` (which
        this class's other same-file fallbacks track carefully via income_rows indices) -
        checking the last 3 REPORTED fiscal years' net_income sign, independent of which one
        backs ttm_eps, is a simpler and more robust earnings-stability signal that only ever
        makes this guard MORE conservative (exclude more), never fabricates a wrong number, in
        the rare case ttm_eps came from an older/substituted row.

        Same "exclude rather than fabricate" convention as MIN_PLAUSIBLE_PE_RATIO/
        GROWTH_INPUT_IMPLAUSIBLE_PCT elsewhere in this codebase (see growth_scoring.py's
        GROWTH_INPUT_IMPLAUSIBLE_PCT docstring for the sibling Growth-pillar version of this
        same principle) - an unstable-earnings PE isn't wrong data, it's just not a reliable
        value signal, so it's excluded from ranking rather than clipped or smoothed.

        Requires 3 real (non-NULL) fiscal years on file - a symbol with less history returns
        False (doesn't block a genuinely short-lived filer's PE on incomplete grounds).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT net_income FROM annual_income_statement
                WHERE symbol = %s AND net_income IS NOT NULL AND data_unavailable IS NOT TRUE
                ORDER BY fiscal_year DESC LIMIT 3
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        if len(rows) < 3:
            return False
        negative_years = sum(1 for (net_income,) in rows if net_income < 0)
        return negative_years >= 2

    @staticmethod
    def _pe_earnings_tax_benefit_inflated(symbol: str) -> bool:
        """True when the latest fiscal year's net_income is inflated 30%+ above pretax_income
        by a one-off tax benefit (a negative income_tax_expense), rather than durable operating
        earnings power.

        ADDED 2026-09-07 (goal: "why does LLY score so far below distressed/turnaround
        healthcare peers" audit). LLY's genuinely rich valuation (pe_ratio ~50, PB ~39, EV/EBITDA
        ~36, FCF yield ~0.8%) was being outranked on the Value factor by small-cap biotechs whose
        "cheap" PE was an artifact of a deferred-tax-asset valuation-allowance release, not real
        earnings. Live-confirmed RIGL: FY2025 pretax_income $121.8M but net_income $367.0M off a
        -$245.2M income_tax_expense (effective tax rate -201%) - pretax operating income implies
        a PE in the 8-9x range, not the 2.39 net-income-based figure that was ranking it #1 on
        the Value leaderboard ahead of every real pharma major. Universe-wide, a live query of
        symbols with pretax_income > 0, pe_ratio < 20, and net_income > 1.3x pretax_income found
        ~35 names (ACAD, AUPH, INSP, TDW, AFRM, UBER, PEGA, AGCO, etc.) sharing this exact
        deeply-negative-effective-tax-rate shape - this is not a single-symbol anomaly.

        Distinct from _pe_earnings_too_volatile (which catches "loss years then a profit year"
        via net_income sign): a company can be reporting income growth for 3 straight years
        while still having THIS year's headline net_income skewed well above its pretax/operating
        earnings by a one-off tax item - RIGL is exactly that case (2024 and 2025 were both
        GAAP-profitable, so the loss-years guard doesn't fire).

        30% threshold: an ordinary R&D-credit-driven negative effective tax rate is typically a
        single-digit-to-teens percentage; a rate more negative than -30% (net_income > 1.3x
        pretax_income) reliably indicates a valuation-allowance release, NOL utilization event,
        or similar one-off rather than a structurally low tax jurisdiction (which shows a low but
        usually POSITIVE rate, not a large tax benefit). Same "exclude rather than fabricate"
        convention as _pe_earnings_too_volatile/MIN_PLAUSIBLE_PE_RATIO.

        Requires the latest fiscal year to have both pretax_income and income_tax_expense on
        file and pretax_income > 0 - a symbol missing either, or with a pretax loss (unprofitable
        already excluded upstream by the ttm_eps > 0 check), returns False.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT pretax_income, income_tax_expense FROM annual_income_statement
                WHERE symbol = %s AND pretax_income IS NOT NULL AND income_tax_expense IS NOT NULL
                  AND data_unavailable IS NOT TRUE
                ORDER BY fiscal_year DESC LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()
        if not row or len(row) != 2:
            return False
        pretax_income, income_tax_expense = row
        if pretax_income is None or pretax_income <= 0:
            return False
        pretax_f = float(pretax_income)
        tax_f = float(income_tax_expense)
        return tax_f < 0 and abs(tax_f) >= 0.30 * pretax_f

    def _compute_pb_ratio(
        self, symbol: str, current_price: float, book_value: float | None, shares_out: float
    ) -> float | None:
        """PB Ratio = Price ÷ Book Value Per Share (bound to MIN_PLAUSIBLE_PB_RATIO..1000 -
        see that constant's docstring for the VCIG-driven lower-bound addition)
        ADDED same day (goal session: "implausible values" sweep, follow-up to the pe_ratio
        immaterial-EPS fix - see test_sec_valuations_pe_pb_ratio_implausible_anchor_cross_
        year_fallback_20260905.py's ICUI case for the full mechanism): a live DB scan found
        67 universe symbols with a real but near-zero book-value-per-share (< $0.10) driving
        a pb_ratio technically under the 1000 ceiling but practically meaningless, same class
        as pe_ratio's 143-symbol population.
        """
        if book_value and book_value > 0:
            bvps = book_value / shares_out
            if bvps > 0:
                pb = current_price / bvps
                if pb <= 1000 and pb >= self.MIN_PLAUSIBLE_PB_RATIO and bvps >= 0.10:
                    return round(pb, 2)
                elif pb > 1000 or bvps < 0.10:
                    # FIXED 2026-09-05 (goal session: "implausible values" sweep) - same
                    # missing-cross-year-fallback gap as pe_ratio/ps_ratio just above and
                    # fcf_margin (loaders/helpers/vqg_quality.py): the anchor year's book_value
                    # can be a real but near-zero extraction/reporting artifact even though an
                    # older fiscal year has a real, representative stockholders_equity that
                    # would produce a plausible pb_ratio against the same current_price/
                    # shares_out (shares_out is a current-snapshot value, not fiscal-year-scoped,
                    # same reasoning as the ps_ratio fix above).
                    fallback_pb = None
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT stockholders_equity FROM annual_balance_sheet
                            WHERE symbol = %s AND stockholders_equity IS NOT NULL
                              AND stockholders_equity > 0 AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        older_equity_rows = cur.fetchall()
                    for (older_equity,) in older_equity_rows:
                        older_bvps = float(older_equity) / shares_out
                        # Same anchor-year-included-in-query guard as pe_ratio's fallback -
                        # a near-zero anchor bvps must not just re-select itself.
                        if older_bvps < 0.10:
                            continue
                        candidate_pb = current_price / older_bvps
                        if self.MIN_PLAUSIBLE_PB_RATIO <= candidate_pb <= 1000:
                            fallback_pb = candidate_pb
                            break
                    if fallback_pb is not None:
                        return round(fallback_pb, 2)
                    else:
                        logger.warning(f"[{symbol}] PB ratio out of bounds ({pb:.0f}), marking as NULL")
                        return None
                else:
                    logger.warning(
                        f"[{symbol}] PB ratio implausibly low ({pb:.4f} < {self.MIN_PLAUSIBLE_PB_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
                    return None
            return None
        else:
            logger.warning(f"[{symbol}] Book value missing, PB ratio unavailable")
            return None

    def _compute_ps_ratio(
        self, symbol: str, current_price: float, ttm_revenue: float | None, shares_out: float
    ) -> float | None:
        """PS Ratio = Price ÷ Revenue Per Share (bound to MIN_PLAUSIBLE_PS_RATIO..10000 -
        see MIN_PLAUSIBLE_PB_RATIO's docstring for the VCIG-driven lower-bound addition)

        ADDED same day (goal session: "implausible values" sweep, follow-up to the pe_ratio
        immaterial-EPS fix): a live DB scan found 301 universe symbols with a real but
        near-zero revenue-per-share (< $0.10) driving a ps_ratio technically under the 10000
        ceiling but practically meaningless, same class as pe_ratio's 143-symbol population.
        """
        if ttm_revenue and ttm_revenue > 0:
            rps = ttm_revenue / shares_out
            if rps > 0:
                ps = current_price / rps
                if ps <= 10000 and ps >= self.MIN_PLAUSIBLE_PS_RATIO and rps >= 0.10:
                    return round(ps, 2)
                elif ps > 10000 or rps < 0.10:
                    # FIXED 2026-09-05 (goal session: "implausible values" sweep, same gap class
                    # as fcf_margin's cross-year fallback - see
                    # test_fcf_margin_implausible_anchor_cross_year_fallback_20260905.py): the
                    # anchor year's ttm_revenue can be a real but near-zero extraction/reporting
                    # artifact (e.g. a not-yet-fully-tagged interim period) even though an older
                    # fiscal year has a real, representative revenue figure - shares_out/
                    # current_price are current-snapshot values (not fiscal-year-scoped), so
                    # re-pairing them with an older year's revenue is the same "mixed-vintage but
                    # more representative" substitution ttm_revenue's own None-fallback (this
                    # method's caller) already does, just triggered by "implausible" instead of
                    # "missing". _compute_valuations doesn't have the caller's income_rows in
                    # scope, so this queries fresh - only reached on the rare implausible-ratio
                    # path, same "extra query is fine here" discipline as
                    # _find_plausible_cross_year_ratio elsewhere in this codebase.
                    fallback_ps = None
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT revenue FROM annual_income_statement
                            WHERE symbol = %s AND revenue IS NOT NULL AND revenue > 0
                              AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        older_revenue_rows = cur.fetchall()
                    for (older_revenue,) in older_revenue_rows:
                        older_rps = float(older_revenue) / shares_out
                        # Same anchor-year-included-in-query guard as pe_ratio's fallback -
                        # a near-zero anchor rps must not just re-select itself.
                        if older_rps < 0.10:
                            continue
                        candidate_ps = current_price / older_rps
                        if self.MIN_PLAUSIBLE_PS_RATIO <= candidate_ps <= 10000:
                            fallback_ps = candidate_ps
                            break
                    if fallback_ps is not None:
                        return round(fallback_ps, 2)
                    else:
                        logger.warning(f"[{symbol}] PS ratio out of bounds ({ps:.0f}), marking as NULL")
                        return None
                else:
                    logger.warning(
                        f"[{symbol}] PS ratio implausibly low ({ps:.4f} < {self.MIN_PLAUSIBLE_PS_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
                    return None
            return None
        else:
            logger.warning(f"[{symbol}] TTM revenue missing, PS ratio unavailable")
            return None

    def _compute_peg_ratio(
        self,
        symbol: str,
        pe_ratio: float | None,
        prior_year_eps: float | None,
        ttm_eps: float | None,
    ) -> float | None:
        """PEG Ratio = PE ÷ Earnings Growth Rate % (bound to 0..10000)
        Growth rate: (TTM EPS - EPS from prior fiscal year) / EPS from prior fiscal year
        NOTE: Annual (fiscal-year over fiscal-year), not quarterly - full quarterly
        lookback would require quarterly history this loader doesn't fetch.

        ADDED same day (goal session: "implausible values" sweep): a real but anomalously
        LOW prior_year_eps (a one-off trough year, e.g. a litigation/impairment charge) makes
        growth_rate mathematically enormous, which DEFLATES peg_ratio toward zero instead of
        inflating it past the 10000 ceiling - the opposite failure direction from pe/pb/ps
        ratio's immaterial-denominator bugs, so that ceiling never catches it, and a fixed-
        dollar floor (like pe_ratio's $0.10) doesn't either, since the trough EPS isn't
        necessarily tiny in absolute terms. Live-confirmed via GILD: FY2024 EPS=$0.38 (real,
        litigation-charge trough year) vs FY2021-2023's $4.96/$3.66/$4.54 (GILD's real normal
        range) and FY2025's $6.84 recovery - growth_rate=1700%, peg=22.08/1700=0.01, while
        yfinance's own real trailingPegRatio for GILD is 2.03 (live-checked directly, not
        assumed) - confirming this is a genuine bug, not an industry-standard artifact. Same
        pattern independently confirmed for AA/Alcoa (FY2024 EPS=$0.26 vs FY2018-2021's
        $1.34-$2.30 range) via a live DB scan finding 30+ real large/mid-caps with peg_ratio
        exactly 0.01.

        Rather than invent an arbitrary magnitude cutoff (no such threshold is established
        anywhere in this codebase or verifiable against real PEG methodology), this uses the
        company's OWN multi-year EPS history as ground truth: prior_year_eps must be at least
        25% of the median of its other real, positive fiscal years on file (same "genuinely
        anomalous relative to this filer's own history" reasoning as the cross-year fallback
        fixes above, just detecting the inverse problem - an anomalous LOW anchor, not an
        anomalous HIGH one).
        """
        if pe_ratio and prior_year_eps is not None and prior_year_eps > 0 and ttm_eps is not None and ttm_eps > 0:
            growth_rate = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100 if prior_year_eps != 0 else None
            if growth_rate and growth_rate > 0 and pe_ratio > 0:
                # Cheap pre-filter before the extra DB round-trip below: real, organic YoY EPS
                # growth essentially never exceeds a few hundred percent (GILD/AA's trough-year
                # artifacts were 1700%/1592%) - only pay for the history query on the rare
                # symbols with unusually explosive growth, not every symbol with positive
                # growth (same "only reached on the rare implausible path" discipline as the
                # pe/pb/ps cross-year fallback queries above).
                prior_year_eps_is_trough = False
                if growth_rate > 300:
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT earnings_per_share FROM annual_income_statement
                            WHERE symbol = %s AND earnings_per_share IS NOT NULL
                              AND earnings_per_share > 0 AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        other_eps_rows = [float(r[0]) for r in cur.fetchall() if float(r[0]) != prior_year_eps]
                    if len(other_eps_rows) >= 2:
                        sorted_eps = sorted(other_eps_rows)
                        mid = len(sorted_eps) // 2
                        median_eps = (
                            sorted_eps[mid] if len(sorted_eps) % 2 else (sorted_eps[mid - 1] + sorted_eps[mid]) / 2
                        )
                        if median_eps > 0 and prior_year_eps < 0.25 * median_eps:
                            prior_year_eps_is_trough = True
                if prior_year_eps_is_trough:
                    logger.debug(
                        f"[{symbol}] PEG ratio prior_year_eps={prior_year_eps} is a trough year "
                        f"relative to its own EPS history - growth_rate={growth_rate:.0f}% is a "
                        f"low-base artifact, marking peg_ratio as NULL"
                    )
                    return None
                else:
                    peg = pe_ratio / growth_rate
                    if peg <= 10000:  # Reasonable PEG bounds
                        return round(peg, 2)
                    else:
                        logger.debug(f"[{symbol}] PEG ratio out of bounds ({peg:.0f}), marking as NULL")
                        return None
        return None
