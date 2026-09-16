#!/usr/bin/env python3
"""Detects when GrowthMetricsMixin.shares_by_year (loaders/helpers/vqg_growth.py) resolves a
fiscal year's share count via the company_info_sec fallback (a single CURRENT snapshot applied
to every year lacking real annual_income_statement shares) or leaves a true gap (no fallback
available either), and that resolution puts an adjacent-year ratio close to a clean split
multiple but just outside the production guard's tight EPS_SPLIT_GUARD_CLEAN_TOLERANCE. Only
scans each symbol's most recent _MAX_OFFSET_YEARS fiscal years (the widest window any real
growth-field CAGR uses) - unrestricted, a symbol's full history against the fallback constant
produces mostly coincidental old-history noise unrelated to any live computation (cut real
flagged-symbol count from 694 to 281 against the live DB when added; see _MAX_OFFSET_YEARS'
own comment).

Live-confirmed on NVDA (2026-09-16): FY2023/FY2024 shares_outstanding_diluted/basic are NULL,
resolved via company_info_sec's CURRENT 24.1B-share snapshot (not NVDA's true FY2023 restated
count). FY2022's real 2.535B vs that fallback gives ratio 9.507 - 4.93% off the real 10:1
split's clean 10x multiple, outside the 1.5% production tolerance. Verified by running
ValueQualityGrowthMetricsLoader._compute_growth_metrics against real NVDA rows: eps_growth_5y
returns 22.88 (the known pre/post-split-blended wrong value) right now, in production, today.

WARN-only detection, not a fix to the guard itself - the fallback exists to avoid blocking
book_value_growth entirely for thin-shares-data symbols, and tightening it needs care against
that tradeoff. See reverse_merger_shell.py for the same "surface it, needs a human" discipline.
"""

import logging
from itertools import pairwise
from typing import Any

from loaders.helpers.vqg_growth import is_split_or_share_count_scale_error
from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

from ..base import BaseCheck, CheckResult
from ..config import INFO, WARN

logger = logging.getLogger(__name__)

# Wider than production's EPS_SPLIT_GUARD_CLEAN_TOLERANCE (1.5%) on purpose - this check exists
# because NVDA's real fallback-driven ratio (4.93% off 10x) falls just outside it. WARN-only, so
# casting a wider net costs a review-queue look, not a wrong number.
_GAP_DETECTION_TOLERANCE = 0.05
_MIN_RATIO_OF_INTEREST = 1.4  # below the smallest real clean multiple (1.5x), with margin
_MAX_REPORTED = 30
# Production's split-guard only ever scans within a growth field's own CAGR window
# (target_year..latest_year, offset<=5 for eps_growth_5y/eps_growth_trend_5y - the widest offset
# any field uses), not a symbol's full multi-decade history. Unrestricted, a symbol's old,
# otherwise-irrelevant history routinely lands a coincidental near-clean-multiple ratio against
# the company_info_sec fallback constant (live-caught: NVDA's own 2019->2020 boundary, ratio
# 9.75, 7 years before its latest fiscal year and never used by any real CAGR computation) - pure
# noise that drowned the real, in-window 2022->2023 finding among ~650 others before this bound.
_MAX_OFFSET_YEARS = 5


class GrowthShareCountGapSplitRiskChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_share_count_gap_masks_split(cur)
        return self.results

    def check_share_count_gap_masks_split(self, cur: Any) -> None:
        try:
            cur.execute("""
                SELECT ais.symbol, ais.fiscal_year, ais.shares_outstanding_diluted, ais.shares_outstanding_basic,
                       gm.eps_growth_1y, gm.eps_growth_3y, gm.eps_growth_5y, gm.book_value_growth
                FROM annual_income_statement ais
                JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
                LEFT JOIN growth_metrics gm ON gm.symbol = ais.symbol
                WHERE ais.data_unavailable = FALSE
                ORDER BY ais.symbol, ais.fiscal_year
            """)
            rows = cur.fetchall()

            cur.execute("""
                SELECT symbol, shares_outstanding FROM company_info_sec
                WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
            """)
            fallback_by_symbol = {r["symbol"]: float(r["shares_outstanding"]) for r in cur.fetchall()}

            # (fiscal_year, resolved_shares, source) per symbol - reproduces
            # GrowthMetricsMixin's own real/fallback resolution exactly, so adjacent-pair ratios
            # here match what the production guard actually compares, not a simplified model.
            resolved_by_symbol: dict[str, list[tuple[int, float, str]]] = {}
            growth_row_by_symbol: dict[str, Any] = {}
            latest_fiscal_year_by_symbol: dict[str, int] = {}
            for row in rows:
                symbol = row["symbol"]
                growth_row_by_symbol.setdefault(symbol, row)
                fiscal_year = row["fiscal_year"]
                if fiscal_year is None:
                    continue
                fiscal_year = int(fiscal_year)
                latest_fiscal_year_by_symbol[symbol] = max(
                    latest_fiscal_year_by_symbol.get(symbol, fiscal_year), fiscal_year
                )
                real_shares = row["shares_outstanding_diluted"] or row["shares_outstanding_basic"]
                if real_shares is not None and real_shares > 0:
                    resolved_by_symbol.setdefault(symbol, []).append((fiscal_year, float(real_shares), "real"))
                    continue
                fallback = fallback_by_symbol.get(symbol)
                if fallback is not None:
                    resolved_by_symbol.setdefault(symbol, []).append((fiscal_year, fallback, "fallback"))

            clean_multiples = ValueQualityGrowthMetricsLoader.EPS_SPLIT_GUARD_CLEAN_MULTIPLES
            tight_tolerance = ValueQualityGrowthMetricsLoader.EPS_SPLIT_GUARD_CLEAN_TOLERANCE

            flagged: list[dict[str, Any]] = []
            for symbol, years in resolved_by_symbol.items():
                latest_fiscal_year = latest_fiscal_year_by_symbol.get(symbol)
                if latest_fiscal_year is None:
                    continue
                window_floor = latest_fiscal_year - _MAX_OFFSET_YEARS
                years = sorted((fy, shares, src) for fy, shares, src in years if fy >= window_floor)
                for (fy_a, shares_a, src_a), (fy_b, shares_b, src_b) in pairwise(years):
                    ratio = max(shares_a, shares_b) / min(shares_a, shares_b)
                    if ratio < _MIN_RATIO_OF_INTEREST:
                        continue
                    if is_split_or_share_count_scale_error(ratio, clean_multiples, tight_tolerance):
                        # Production's own tight tolerance already catches this pair - not a
                        # blind spot this check needs to surface.
                        continue
                    if not is_split_or_share_count_scale_error(ratio, clean_multiples, _GAP_DETECTION_TOLERANCE):
                        continue

                    gap_years = fy_b - fy_a
                    if gap_years >= 2:
                        mask_reason = "data_gap"
                    elif src_a == "fallback" or src_b == "fallback":
                        mask_reason = "fallback_substituted"
                    else:
                        # Two genuinely adjacent real-data years, near but not within the tight
                        # tolerance - a tolerance-calibration question, not a gap/fallback
                        # masking one, so out of this check's scope.
                        continue

                    growth_row = growth_row_by_symbol.get(symbol, {})
                    live_bypassed_fields = [
                        field
                        for field in ("eps_growth_1y", "eps_growth_3y", "eps_growth_5y", "book_value_growth")
                        if growth_row.get(field) is not None
                    ]
                    flagged.append(
                        {
                            "symbol": symbol,
                            "fiscal_year_before": fy_a,
                            "fiscal_year_after": fy_b,
                            "mask_reason": mask_reason,
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
                    "no share-count gap/fallback resolution masking a near-clean-multiple split ratio detected",
                )
                return

            flagged.sort(key=lambda r: (not r["currently_bypassed_fields"], -r["ratio"]))
            live_count = sum(1 for r in flagged if r["currently_bypassed_fields"])
            self.log(
                "growth_share_count_gap_split_risk",
                WARN,
                "annual_income_statement",
                f"{len(flagged)} symbol(s) have a share-count data gap or company_info_sec fallback "
                f"substitution producing a near-clean-multiple ratio the production split-guard's tight "
                f"tolerance misses (see NVDA, this check's own motivating discovery - loaders/helpers/"
                f"vqg_growth.py). {live_count} already have a non-null growth field spanning it RIGHT NOW "
                f"(currently_bypassed_fields) - review those first. Needs individual filing review, not "
                f"an automatic fix.",
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
