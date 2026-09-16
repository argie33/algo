#!/usr/bin/env python3
"""Detects the exact blind spot confirmed live on NVDA (2026-09-16 investigation): the EPS/
book-value split-discontinuity guard in loaders/helpers/vqg_growth.py
(is_split_or_share_count_scale_error, wired through GrowthMetricsMixin._compute_period_growth)
only scans ADJACENT fiscal years that both have usable shares_outstanding data
(shares_by_year is built by skipping any year where diluted AND basic are both NULL/<=0 and
no company_info_sec fallback applies). When shares_outstanding_diluted/basic are NULL for one
or more intervening fiscal years, the guard silently compares across the gap instead of the
true adjacent years - which dilutes a real split's ratio below its detection tolerance.

Live-confirmed root cause: NVDA's real 10:1 split lands between FY2022 and FY2023 (shares
2.535B -> 25.07B, ratio 9.89, only 1.10% off the clean 10x multiple - well inside the
production guard's EPS_SPLIT_GUARD_CLEAN_TOLERANCE of 1.5%, would have been caught cleanly).
But annual_income_statement.shares_outstanding_diluted/basic are NULL for both FY2023 and
FY2024 in the real DB, so the guard's adjacent-pair scan is forced to jump straight from
FY2022 to FY2025 (2.535B -> 24.8B, ratio 9.78, 2.16% off 10x) - just outside tolerance. The
data gap, not a real change in capital structure, is what lets the split slip through.

This is DETECTION only, not a fix to the production guard itself - see this check's own
`_LIVE_BYPASS_NOTE` below and the goal-session writeup for why the two are being kept
separate (root-cause fix needs careful tolerance design against legitimate multi-year
buyback/dilution drift; this check is safe and additive, surfacing candidates into the
existing human-reviewed queue rather than silently shipping a corrupted growth number).
Deliberately WARN, not ERROR/CRIT: a nearby clean-multiple ratio across a data gap is a
plausible-split CANDIDATE for review, not proof - same discipline as
reverse_merger_shell.py's "go look at this."
"""

import logging
from itertools import pairwise
from typing import Any

from loaders.helpers.vqg_growth import is_split_or_share_count_scale_error
from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

from ..base import BaseCheck, CheckResult
from ..config import INFO, WARN

logger = logging.getLogger(__name__)

# Wider than the production guard's EPS_SPLIT_GUARD_CLEAN_TOLERANCE (1.5%) on purpose: this
# check exists precisely because a genuine gap-diluted split ratio (NVDA: 2.16% off 10x)
# falls just outside that tight production tolerance. This is a WARN-only detection surface,
# not a value-blocking guard, so casting a wider net to catch that class of near-miss is the
# whole point - false positives cost a human a look at the review queue, not a wrong number.
_GAP_DETECTION_TOLERANCE = 0.05
# Below the smallest real clean multiple (1.5x) with margin - excludes ordinary multi-year
# dilution/buyback drift (see the production guard's own 2026-08-31 false-positive fix,
# TRNO/RCMT/LOPE/ARW, ~60% cumulative drift over 5 years with no single-year jump) from ever
# reaching the clean-multiple check at all.
_MIN_RATIO_OF_INTEREST = 1.4
_MAX_REPORTED = 30


class GrowthShareCountGapSplitRiskChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_share_count_gap_masks_split(cur)
        return self.results

    def check_share_count_gap_masks_split(self, cur: Any) -> None:
        try:
            cur.execute("""
                SELECT ais.symbol, ais.fiscal_year, ais.shares_outstanding_diluted, ais.shares_outstanding_basic,
                       gm.eps_growth_1y, gm.eps_growth_1y_unavailable_reason,
                       gm.eps_growth_3y, gm.eps_growth_3y_unavailable_reason,
                       gm.eps_growth_5y, gm.eps_growth_5y_unavailable_reason,
                       gm.book_value_growth, gm.book_value_growth_unavailable_reason
                FROM annual_income_statement ais
                JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
                LEFT JOIN growth_metrics gm ON gm.symbol = ais.symbol
                WHERE ais.data_unavailable = FALSE
                ORDER BY ais.symbol, ais.fiscal_year
            """)
            rows = cur.fetchall()

            # (fiscal_year, shares) per symbol, restricted to years with usable shares data -
            # same "diluted preferred, fallback basic" convention as GrowthMetricsMixin's own
            # shares_by_year construction (company_info_sec's single-snapshot fallback is
            # deliberately NOT reproduced here: it can only ever mask this exact gap further,
            # never reveal one, so skipping it makes this check strictly more sensitive, not
            # less, than the production guard it's auditing).
            shares_by_symbol: dict[str, list[tuple[int, float]]] = {}
            growth_row_by_symbol: dict[str, Any] = {}
            for row in rows:
                symbol = row["symbol"]
                growth_row_by_symbol.setdefault(symbol, row)
                fiscal_year = row["fiscal_year"]
                shares = row["shares_outstanding_diluted"] or row["shares_outstanding_basic"]
                if fiscal_year is None or shares is None or shares <= 0:
                    continue
                shares_by_symbol.setdefault(symbol, []).append((int(fiscal_year), float(shares)))

            clean_multiples = ValueQualityGrowthMetricsLoader.EPS_SPLIT_GUARD_CLEAN_MULTIPLES

            flagged: list[dict[str, Any]] = []
            for symbol, years in shares_by_symbol.items():
                years.sort()
                for (fy_a, shares_a), (fy_b, shares_b) in pairwise(years):
                    gap = fy_b - fy_a
                    if gap < 2:
                        # Genuinely adjacent years - the production guard already scans this
                        # pair directly, nothing hidden by a gap here.
                        continue
                    ratio = max(shares_a, shares_b) / min(shares_a, shares_b)
                    if ratio < _MIN_RATIO_OF_INTEREST:
                        continue
                    if not is_split_or_share_count_scale_error(ratio, clean_multiples, _GAP_DETECTION_TOLERANCE):
                        continue

                    growth_row = growth_row_by_symbol.get(symbol, {})
                    # If any growth field spanning this gap currently reports a real (non-null)
                    # value, the production guard has ALREADY been bypassed for this symbol -
                    # not just a latent risk. This is the highest-priority subset to review
                    # first (mirrors the live-confirmed NVDA case exactly).
                    live_bypassed_fields = [
                        field
                        for field in ("eps_growth_1y", "eps_growth_3y", "eps_growth_5y", "book_value_growth")
                        if growth_row.get(field) is not None
                    ]
                    flagged.append(
                        {
                            "symbol": symbol,
                            "fiscal_year_before_gap": fy_a,
                            "fiscal_year_after_gap": fy_b,
                            "gap_years": gap,
                            "shares_before": shares_a,
                            "shares_after": shares_b,
                            "ratio": round(ratio, 3),
                            "currently_bypassed_fields": live_bypassed_fields,
                        }
                    )

            if not flagged:
                self.log(
                    "growth_share_count_gap_split_risk",
                    INFO,
                    "annual_income_statement",
                    "no share-count data gaps masking a near-clean-multiple split ratio detected",
                )
                return

            # Symbols with a currently-live bypassed growth field first (real, shipping bug
            # right now) then by ratio's closeness to a clean multiple.
            flagged.sort(key=lambda r: (not r["currently_bypassed_fields"], -r["ratio"]))
            live_count = sum(1 for r in flagged if r["currently_bypassed_fields"])
            self.log(
                "growth_share_count_gap_split_risk",
                WARN,
                "annual_income_statement",
                f"{len(flagged)} symbol(s) have a >=2-year gap in shares_outstanding_diluted/basic "
                f"spanning a near-clean-multiple share-count ratio - the EPS/book-value split-guard "
                f"(loaders/helpers/vqg_growth.py) only scans adjacent years WITH data, so a gap can "
                f"dilute a real split ratio below its detection tolerance (see NVDA, this check's own "
                f"motivating discovery: 2022->2023 true split ratio 9.89 was cleanly detectable, but "
                f"the FY2023/FY2024 data gap forced the guard to compare 2022->2025 instead, 9.78, "
                f"just outside tolerance). {live_count} of these already have a non-null growth field "
                f"spanning the gap RIGHT NOW (currently_bypassed_fields) - review those first. Needs "
                f"individual filing review before treating as a confirmed split, not an automatic fix.",
                {"count": len(flagged), "currently_bypassed_count": live_count, "examples": flagged[:_MAX_REPORTED]},
            )
        except Exception as e:
            logger.error(
                f"[GrowthShareCountGapSplitRiskChecker] check_share_count_gap_masks_split failed: {e}",
                exc_info=True,
            )
            self.log(
                "growth_share_count_gap_split_risk",
                WARN,
                "annual_income_statement",
                f"Check execution failed (not a data finding): {e}",
            )
