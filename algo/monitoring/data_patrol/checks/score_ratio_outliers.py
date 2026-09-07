#!/usr/bin/env python3
"""Cross-sectional outlier detection for the percentile-ranked Value/Quality ratio inputs
(pe_ratio, pb_ratio, ps_ratio, fcf_yield, roe, roce_pct).

Added 2026-09-07 (goal session: "automate the XBRL stuff for the future, identify and address
gaps as needed" - direct follow-up to a live "huge scoring bug" audit that found SOAR/LX/ROC/
ALTG/ECOR/MSB each independently topping a Value or Quality leaderboard off a single extreme,
statistically-implausible ratio - see MIN_PLAUSIBLE_PE_RATIO/MAX_PLAUSIBLE_FCF_YIELD_PCT in
loaders/load_sec_valuations.py and loaders/helpers/sec_valuations_yield_dcf.py, and the ROE
sign-flip guard in loaders/load_value_quality_growth_metrics.py's update_quality_roe_roce_
percentiles - for the specific fixes that session produced by hand).

Every one of those was found by a human eyeballing a leaderboard and asking "why is this
obscure/distressed name #1" - the exact "reactive, one bug at a time" pattern
xbrl_new_concepts.py and statistical_anomaly.py were already built to get away from for raw
XBRL facts. This is the same philosophy applied one layer up, to the DERIVED ratios that feed
percentile-rank scoring: `_percent_rank_cheap_high`/`_percent_rank_higher_is_better` are pure
ORDER-based ranks, so a single most-extreme raw value - genuine or not - always wins percentile
100 outright, and a fixed MIN/MAX_PLAUSIBLE_* bound only protects the specific field/threshold a
human has already investigated. A NEW pathological case in a field or magnitude nobody has
looked at yet (the next MSB, in a metric this session didn't touch) would otherwise sit
undetected until someone happens to notice it on a leaderboard again.

Deliberately WARN, not ERROR/CRIT, and deliberately a REVIEW QUEUE, not an auto-reject: unlike
xbrl_new_concepts.py's allowlist-membership check (binary, no judgment call) or tie_out.py's
arithmetic identities (definitionally wrong by construction), "is this ratio's magnitude real or
an artifact" needs the same investigation this session did by hand for SOAR/LX/ROC (checking
SEC XBRL facts, comparing to real peers) - a magnitude threshold alone can't tell a genuine
deep-value/distress case (real, if extreme) from an extraction/scale bug. This surfaces
candidates; a human (or a future automated follow-up) still has to look, exactly like
statistical_anomaly.py's own revenue/total_assets YoY checks.

Thresholds are dynamic (5x the population's own 95th-percentile-from-the-tail reference point),
not hardcoded absolute numbers, matching statistical_anomaly.py's own "calibrated against the
live distribution, not guessed" convention - a ratio's normal range can shift over
years/market regimes, and a fixed absolute number would either go stale or need re-tuning by
hand every time someone re-derives it, the same maintenance burden this whole check exists to
avoid.
"""

import logging
from typing import Any

from ..base import BaseCheck, CheckResult
from ..config import ERROR, WARN

logger = logging.getLogger(__name__)

_MAX_REPORTED_PER_CHECK = 20
_OUTLIER_MULTIPLE = 5.0

# (table, field, direction, percentile_rank_reference) - direction "low" means the ranking
# convention rewards the SMALLEST raw value (cheap-is-good: PE/PB/PS), "high" means it rewards
# the LARGEST raw value (FCF yield/ROE/ROCE/dividend_yield). percentile_rank_reference is which
# tail percentile anchors the "normal extreme" the outlier multiple is measured against - p05
# for "low" fields (the already-cheap tail), p95 for "high" fields (the already-rich tail).
_RATIO_FIELDS: list[tuple[str, str, str]] = [
    ("value_metrics", "pe_ratio", "low"),
    ("value_metrics", "pb_ratio", "low"),
    ("value_metrics", "ps_ratio", "low"),
    ("value_metrics", "fcf_yield", "high"),
    ("quality_metrics", "roe", "high"),
    ("quality_metrics", "roce_pct", "high"),
]


class ScoreRatioOutlierChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        self.results = []
        for table, field, direction in _RATIO_FIELDS:
            self._check_ratio_outliers(cur, table, field, direction)
        return self.results

    def _check_ratio_outliers(self, cur: Any, table: str, field: str, direction: str) -> None:
        check_name = f"{field}_cross_sectional_outlier"
        try:
            cur.execute(
                f"""
                SELECT symbol, {field} AS val
                FROM {table}
                WHERE {field} IS NOT NULL AND COALESCE(data_unavailable, false) = false
                """
            )
            rows = [(r["symbol"], float(r["val"])) for r in cur.fetchall()]
            if len(rows) < 100:
                # Too small a population for a percentile reference point to be meaningful -
                # same "needs a real sample" guard as the Value pillar's own sector-relative
                # percentile ranking (_MIN_SECTOR_SLICE).
                return

            values = sorted(v for _, v in rows)
            n = len(values)
            if direction == "low":
                # Reference: p05 (the already-cheap tail). Flag anything cheaper than
                # reference/_OUTLIER_MULTIPLE - i.e. 5x cheaper than what's already an extreme
                # value in this universe. Only positive values are ranked "cheap is good" here
                # (a negative ratio means something else entirely, e.g. negative book value) -
                # exclude non-positive values from both the reference calc and the flagged set.
                positive_values = [v for v in values if v > 0]
                if len(positive_values) < 100:
                    return
                reference = positive_values[max(0, int(len(positive_values) * 0.05) - 1)]
                if reference <= 0:
                    return
                bound = reference / _OUTLIER_MULTIPLE
                flagged = [(s, v) for s, v in rows if 0 < v < bound]
                flagged.sort(key=lambda sv: sv[1])
            else:
                reference = values[min(n - 1, int(n * 0.95))]
                if reference <= 0:
                    return
                bound = reference * _OUTLIER_MULTIPLE
                flagged = [(s, v) for s, v in rows if v > bound]
                flagged.sort(key=lambda sv: sv[1], reverse=True)

            if not flagged:
                return

            examples = [
                {"symbol": s, "value": v, "reference_p05_or_p95": round(reference, 4)}
                for s, v in flagged[:_MAX_REPORTED_PER_CHECK]
            ]
            self.log(
                check_name,
                WARN,
                table,
                f"{len(flagged)} symbol(s) have a {field} more than {_OUTLIER_MULTIPLE:.0f}x "
                f"{'below' if direction == 'low' else 'above'} the universe's own "
                f"{'p05' if direction == 'low' else 'p95'} ({reference:.4f}) - review queue, not a "
                "confirmed bug: a single most-extreme raw value always wins percentile-rank 100 "
                "outright regardless of whether it's genuine (real deep-value/distress) or an "
                "extraction/scale artifact - see this check's own module docstring for the "
                "SOAR/LX/ROC/MSB precedent that motivated it",
                {"count": len(flagged), "examples": examples},
            )
        except Exception as e:
            logger.error(f"[ScoreRatioOutlierChecker] {check_name} failed: {e}", exc_info=True)
            self.log(check_name, ERROR, table, f"{check_name} failed: {e}")
