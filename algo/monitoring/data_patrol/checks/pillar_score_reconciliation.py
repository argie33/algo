#!/usr/bin/env python3
"""Verifies stock_scores pillar columns reconcile to their own authoritative source tables.

Added 2026-09-08 (goal: score sanity audit, follow-up to composite_score_reconciliation.py).
That module closed the gap between composite_score and its 5 stored pillar inputs, but nothing
verified the pillar layer ITSELF against the table each pillar is actually computed from and
copied out of. For Quality specifically: quality_metrics.quality_score is the sole authoritative
value (see loaders/stock_scores/quality_scoring.py's _score_quality - "Uses only pre-computed
quality_score... No fallback computation"), and stock_scores.quality_score is a straight copy of
it (loaders/load_stock_scores.py's batch load path). A stale stock_scores row - built before a
quality_metrics rewrite/backfill/reload, or a copy bug - would silently diverge with nothing in
CI to catch it. This is exactly the failure mode live-observed in this same session: a landed-
but-not-yet-reloaded quality_metrics fix (broker-dealer fcf_margin exclusion) leaves stock_scores
holding stale GS/MS quality_score values with no automated signal that a reload is needed.

Deliberately does NOT re-derive quality_score from raw ratio columns (roe/roa/roce_pct/
fcf_margin/debt_to_equity/margin_volatility/asset_turnover/gross_profitability) via the
sector-neutral z-score formula itself - that formula lives in
loaders/helpers/vqg_quality_batch.py's update_quality_sector_neutral_scores() and is under
active concurrent development in this session (broker-dealer exclusion set, D2E/ROA/ROCE peer-
group refinement). Duplicating that logic here would (a) violate reuse-over-reimplementation for
a formula still in flux, and (b) risk flagging every symbol as a false positive the moment a
legitimate methodology change lands in one copy but not the other. update_quality_sector_neutral_
scores() already self-heals quality_metrics.quality_score against the raw ratios on every batch
run (it's a pure overwrite, not additive-delta) - the real, previously-uncovered gap is one layer
up: does stock_scores actually hold what quality_metrics currently says. That's what this checks.

Given its own new module for the same file-size-ratchet reason composite_score_reconciliation.py
was: tie_out.py is already past its size-ratchet ceiling.
"""

import logging
from typing import Any

from utils.loaders.helpers import _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)

_MAX_REPORTED_PER_CHECK = 20
_WARN_ABS = 0.01  # float/rounding noise budget - both columns store the same numeric(5,2) shape
_ERROR_ABS = 1.0  # beyond this is not explainable by rounding - a stale copy or a real bug


class PillarScoreReconciliationChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        self.check_quality_score_reconciliation(cur)
        return self.results

    def check_quality_score_reconciliation(self, cur: Any) -> None:
        try:
            # FIXED 2026-09-08 (goal session: scores-reload due-diligence audit): excludes
            # closed-end funds/investment trusts (company_info_sec.entity_type='other' AND
            # sic_code IS NULL - same shape utils/loaders/helpers.py's fundamentals-universe
            # query already uses to keep them out of stock_scores entirely) and BDCs
            # (_KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS - SEC classifies these entity_type=
            # 'operating' despite sic_code=NULL, so the CEF shape alone misses them). Both
            # populations are DELIBERATELY excluded from load_stock_scores.py's own universe
            # query (they file N-CSR/N-2, not a 10-K, so there's nothing for it to recompute),
            # so their stock_scores row is permanently frozen at whatever date they last had
            # one while quality_metrics.quality_score can still move (fed by a different,
            # broader universe query) - a structural mismatch, not a stale-copy bug. Live-
            # confirmed: of 143 active symbols with no stock_scores row at all for a fresh
            # reload date, 87 matched the CEF entity_type/sic_code shape and the rest were
            # BDCs on this list (MAIN/TSLX/BBDC/LIEN spot-checked directly).
            #
            # FIXED 2026-09-08 (same audit, second pass): also requires stock_symbols.active -
            # the CEF/BDC exclusions above dropped the count from 125 to 19, but 8 of those 19
            # were INACTIVE symbols (delisted/liquidated SPAC shells - Iron Horse Acquisitions,
            # Churchill Capital XII, Social Commerce Partners, TRG Latin America, SilverBox Corp
            # V, KPET Ultra Paceline, Dynamix Corp, National Storage Affiliates - live-confirmed
            # via stock_symbols.active=false for all 8), which load_stock_scores.py's own
            # universe query already excludes via `WHERE s.active = true` - comparing a
            # never-scored, delisted symbol's frozen stock_scores row against a quality_metrics
            # row some other, less-selective process may still be touching is the same class of
            # false positive as the CEF/BDC case, just a different exclusion reason.
            #
            # FIXED 2026-09-09 (goal session: xbrl-scan/tie-out exhaustiveness audit): also
            # requires stock_symbols.data_unavailable IS NOT TRUE. Live-confirmed via SBEV/NCL
            # (both flagged ERROR here, divergence 1.04/0.40, unchanged after a fresh --now
            # signals --loaders scores reload): utils/loaders/helpers.py's fundamentals-universe
            # query (used by load_stock_scores.py) filters `s.data_unavailable IS NOT TRUE`, so
            # once yfinance stops returning price data for a symbol for 30 days
            # (_mark_symbol_permanently_unavailable in loaders/load_prices.py sets stock_symbols.
            # data_unavailable=true, active stays true) that symbol drops out of stock_scores
            # entirely - ALL pillars freeze, not just the price-dependent ones - while
            # load_value_quality_growth_metrics.py's quality_metrics universe query has no such
            # filter (fundamentals data is orthogonal to price-feed health) and keeps recomputing
            # quality_score every run. Same "frozen copy vs moving source" structural mismatch as
            # the CEF/BDC/inactive exclusions above, just gated on a different column - not a
            # stale-row-awaiting-reload bug, and no reload can ever close it while the symbol stays
            # data_unavailable.
            cur.execute(
                """
                SELECT ss.symbol, ss.date, ss.quality_score AS stock_scores_quality_score,
                       qm.quality_score AS quality_metrics_quality_score
                FROM (
                    SELECT DISTINCT ON (symbol) symbol, date, quality_score
                    FROM stock_scores
                    WHERE quality_score IS NOT NULL
                    ORDER BY symbol, date DESC
                ) ss
                JOIN quality_metrics qm ON qm.symbol = ss.symbol
                JOIN stock_symbols sym ON sym.symbol = ss.symbol AND sym.active = true
                    AND sym.data_unavailable IS NOT TRUE
                LEFT JOIN company_info_sec c ON c.symbol = ss.symbol
                WHERE qm.quality_score IS NOT NULL
                  AND COALESCE(qm.data_unavailable, false) = false
                  AND NOT (c.entity_type = 'other' AND c.sic_code IS NULL)
                  AND ss.symbol != ALL(%(bdc_symbols)s)
                """,
                {"bdc_symbols": sorted(_KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS)},
            )
            flagged = []
            for row in cur.fetchall():
                stored = float(row["stock_scores_quality_score"])
                source = float(row["quality_metrics_quality_score"])
                divergence = abs(stored - source)
                if divergence > _WARN_ABS:
                    flagged.append(
                        {
                            "symbol": row["symbol"],
                            "date": str(row["date"]),
                            "stock_scores_quality_score": stored,
                            "quality_metrics_quality_score": source,
                            "divergence": round(divergence, 4),
                        }
                    )
            if flagged:
                flagged.sort(key=lambda r: r["divergence"], reverse=True)
                severity = ERROR if flagged[0]["divergence"] > _ERROR_ABS else WARN
                self.log(
                    "pillar_score_reconciliation",
                    severity,
                    "stock_scores",
                    f"{len(flagged)} symbol(s) have a stock_scores.quality_score that doesn't "
                    f"match its own authoritative source (quality_metrics.quality_score) beyond "
                    f"a {_WARN_ABS}-point rounding budget (max divergence "
                    f"{flagged[0]['divergence']:.4f}) - likely a stale stock_scores row awaiting "
                    f"reload after a quality_metrics recompute/backfill",
                    {"count": len(flagged), "examples": flagged[:_MAX_REPORTED_PER_CHECK]},
                )
            else:
                # Always log even when clean (FIXED 2026-09-10, goal: institution-grade
                # data-quality architecture): PatrolLogger.log_results only supersedes a
                # (check_name, target_table)'s prior 'open' row when this check fires AGAIN -
                # a check that silently returns on a clean pass can never resolve its own
                # earlier flagged finding, leaving a stale phantom ERROR/WARN open in
                # data_patrol_log forever after the underlying issue is actually fixed. Live-
                # hit this exact case the same session: a rescore fixed a real 2603-symbol
                # divergence to 0, but the ERROR row stayed 'open' with nothing to close it.
                self.log(
                    "pillar_score_reconciliation",
                    INFO,
                    "stock_scores",
                    "quality_score reconciles cleanly between stock_scores and quality_metrics",
                )
        except Exception as e:
            logger.error(
                f"[PillarScoreReconciliationChecker] check_quality_score_reconciliation failed: {e}", exc_info=True
            )
            self.log(
                "pillar_score_reconciliation",
                ERROR,
                "stock_scores",
                f"Check execution failed (likely schema drift, not a data finding): {e}",
            )
