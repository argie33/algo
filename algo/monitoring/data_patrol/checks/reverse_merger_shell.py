#!/usr/bin/env python3
"""Detects a business-identity discontinuity hiding inside one continuous-looking row of
annual financial history: a filer with an SEC-recorded name change (formerNames in its
submissions.json) whose reported revenue jumps by an extreme multiple across the fiscal
year straddling that rename - the "reverse-merger shell" pattern already found live during
the 2026-09-13 reverse-merger-shell prevalence sweep (COPR/ELOX/MYSZ, and AXIL Brands, Inc.
- CIK 0001718500's own submissions.json shows it was "Reviv3 Procare Co", a haircare/
cosmetics filer, until 2024-02-13, then became "Axil Brands, Inc." - a hearing-protection
company - with annual revenue jumping ~10x from FY2022's $2.34M to FY2023's $23.5M, right at
that boundary). Growth/trend/momentum metrics computed from this symbol's own multi-year
annual_income_statement history silently treat the pre- and post-merger businesses as one
continuous company.

Deliberately WARN, not ERROR/CRIT: an ordinary corporate rename (2,765 cached filers have a
formerNames entry - Alcoa->Arconic->Howmet, AIG's own capitalization change, etc.) never
shows this signature since the operating business is unchanged, but a genuine hypergrowth
company coinciding with an unrelated rename is not ruled out by this heuristic alone - this
needs a human to actually read the two 10-Ks before quarantining, same discipline as
xbrl_concept_continuity.py's "go look at this," not proof of a live bug. Reads ONLY the
already-on-disk submissions cache (populated by normal loader runs) plus the local
symbol->CIK ticker cache file - no new network calls, no live SEC fetches, so a full active-
universe pass is cheap enough to run every time (no rotating sample needed).
"""

import json
import logging
import tempfile
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import INFO, WARN

logger = logging.getLogger(__name__)

_SUBMISSIONS_CACHE_DIR = Path(tempfile.gettempdir()) / "algo-sec-edgar-cache" / "submissions"
_TICKER_CACHE_FILE = Path(tempfile.gettempdir()) / "sec_ticker_cache.json"
_REVENUE_JUMP_RATIO = 5.0
_MIN_REVENUE_FLOOR = 100_000.0
_MAX_REPORTED = 20
# A reverse merger's operating-business change (and the resulting revenue discontinuity)
# routinely PRECEDES the formal SEC name-change filing by a fiscal year or more - the deal
# closes and the new business consolidates before the rename paperwork is effective (live-
# confirmed: AXIL Brands/Reviv3 Procare Co's own real revenue jump was FY2022->FY2023, but
# its SEC-recorded rename effective date is 2024-02-13, which would anchor a naive exact-year
# boundary one fiscal year too late and miss the real discontinuity entirely). Scanning every
# adjacent fiscal-year pair in a window around the rename, not just the exact boundary year,
# catches this without weakening precision - it's still WARN-only, human-reviewed.
_WINDOW_YEARS_BEFORE = 2
_WINDOW_YEARS_AFTER = 1


def _load_symbol_to_cik() -> dict[str, str]:
    try:
        with open(_TICKER_CACHE_FILE) as f:
            return dict(json.load(f).get("mapping") or {})
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.debug(f"[ReverseMergerShellChecker] could not load ticker cache: {e}")
        return {}


def _latest_rename_year(cik_padded: str) -> int | None:
    """Most recent formerNames->to date's calendar year, or None if never renamed/no cache."""
    path = _SUBMISSIONS_CACHE_DIR / f"{cik_padded}.json"
    try:
        with open(path) as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    data = payload.get("data", payload)
    former_names = data.get("formerNames") or []
    if not former_names:
        return None
    to_dates = [fn.get("to") for fn in former_names if fn.get("to")]
    if not to_dates:
        return None
    return max(int(d[:4]) for d in to_dates)


class ReverseMergerShellChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_reverse_merger_revenue_discontinuity(cur)
        return self.results

    def check_reverse_merger_revenue_discontinuity(self, cur: Any) -> None:
        try:
            symbol_to_cik = _load_symbol_to_cik()
            if not symbol_to_cik:
                # No local ticker cache yet (fresh host before any loader run) - nothing to
                # cross-reference, not a data-integrity finding.
                self.log(
                    "reverse_merger_shell_revenue_discontinuity",
                    INFO,
                    "sec_edgar_submissions_cache",
                    "no local ticker cache available yet - skipping",
                )
                return

            cur.execute("""
                SELECT a.symbol, a.fiscal_year, a.revenue
                FROM annual_income_statement a
                JOIN stock_symbols s ON s.symbol = a.symbol AND s.active = true
                WHERE a.data_unavailable = FALSE AND a.revenue IS NOT NULL
                ORDER BY a.symbol, a.fiscal_year
            """)
            revenue_by_symbol: dict[str, list[tuple[int, float]]] = {}
            for row in cur.fetchall():
                revenue_by_symbol.setdefault(row["symbol"], []).append((int(row["fiscal_year"]), float(row["revenue"])))

            flagged: list[dict[str, Any]] = []
            for symbol, years in revenue_by_symbol.items():
                cik = symbol_to_cik.get(symbol.upper())
                if not cik:
                    continue
                rename_year = _latest_rename_year(cik)
                if rename_year is None:
                    continue
                years.sort()
                window = [
                    (fy, rev)
                    for fy, rev in years
                    if rename_year - _WINDOW_YEARS_BEFORE <= fy <= rename_year + _WINDOW_YEARS_AFTER
                ]
                best: dict[str, Any] | None = None
                for (fy_a, rev_a), (fy_b, rev_b) in pairwise(window):
                    if abs(rev_a) < _MIN_REVENUE_FLOOR or abs(rev_b) < _MIN_REVENUE_FLOOR:
                        continue
                    if min(rev_a, rev_b) <= 0:
                        continue
                    ratio = max(rev_a, rev_b) / min(rev_a, rev_b)
                    if ratio >= _REVENUE_JUMP_RATIO and (best is None or ratio > best["ratio"]):
                        best = {
                            "symbol": symbol,
                            "rename_year": rename_year,
                            "fiscal_year_before": fy_a,
                            "fiscal_year_after": fy_b,
                            "revenue_before": rev_a,
                            "revenue_after": rev_b,
                            "ratio": round(ratio, 1),
                        }
                if best is not None:
                    flagged.append(best)

            if not flagged:
                self.log(
                    "reverse_merger_shell_revenue_discontinuity",
                    INFO,
                    "annual_income_statement",
                    "no rename-boundary revenue discontinuities detected",
                )
                return

            flagged.sort(key=lambda r: r["ratio"], reverse=True)
            self.log(
                "reverse_merger_shell_revenue_discontinuity",
                WARN,
                "annual_income_statement",
                f"{len(flagged)} symbol(s) show a >={_REVENUE_JUMP_RATIO:.0f}x revenue jump "
                "across an SEC-recorded company-name-change boundary - possible reverse-merger "
                "shell splicing two unrelated businesses' financials under one CIK (see AXIL "
                "Brands/Reviv3 Procare Co, this check's own motivating discovery). Needs "
                "individual 10-K review before quarantining, not an automatic finding.",
                {"count": len(flagged), "examples": flagged[:_MAX_REPORTED]},
            )
        except Exception as e:
            logger.error(
                f"[ReverseMergerShellChecker] check_reverse_merger_revenue_discontinuity failed: {e}",
                exc_info=True,
            )
            self.log(
                "reverse_merger_shell_revenue_discontinuity",
                WARN,
                "annual_income_statement",
                f"Check execution failed (not a data finding): {e}",
            )
