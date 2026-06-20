#!/usr/bin/env python3

"""
Sector Rotation Detector — defensive leadership early warning

Mansfield RS rotation research and IBD's leadership-rotation studies show
that defensive sectors (Utilities, Consumer Staples, Healthcare) typically
begin outperforming SPY 1-3 months BEFORE major market tops, while the
cyclical "risk-on" sectors (Technology, Consumer Discretionary,
Communication, Industrials) start lagging.

This module:
  1. Computes sector RS vs SPY over 4w/12w windows
  2. Identifies if defensive leadership is taking hold
  3. Returns severity score (0-100) for orchestrator/exposure to consume
  4. Persists to sector_rotation_signal table

When defensive_lead_score >= 60, the market exposure model reduces the
composite score by 5-10 points (handled in algo_market_exposure.py).
"""

import json
import logging
from datetime import date as _date

from utils.db import DatabaseContext


logger = logging.getLogger(__name__)

DEFENSIVE_SECTORS = ["Utilities", "Consumer Defensive", "Healthcare"]
CYCLICAL_SECTORS = [
    "Technology",
    "Consumer Cyclical",
    "Communication Services",
    "Industrials",
    "Financial Services",
]

SECTOR_ETF = {
    "Utilities": "XLU",
    "Consumer Defensive": "XLP",
    "Healthcare": "XLV",
    "Technology": "XLK",
    "Consumer Cyclical": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
}


class SectorRotationDetector:
    """Detect defensive sector leadership patterns."""

    def __init__(self, config=None):
        if config is not None and not isinstance(config, dict):
            raise TypeError(f"config must be a dict, got {type(config).__name__}")
        self.config = config

    def compute(self, eval_date=None):
        """Run sector rotation analysis for the eval_date.

        Uses sector_ranking table (we don't have sector ETF price history).
        Lower rank = stronger sector. We measure: how have defensive sectors'
        ranks improved vs cyclicals' over 4 weeks.
        """
        if eval_date is None:
            eval_date = _date.today()

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT sector_name, current_rank, momentum_score,
                           rank_1w_ago, rank_4w_ago, rank_12w_ago
                    FROM sector_ranking
                    WHERE date = (
                        SELECT MAX(date) FROM sector_ranking
                        WHERE date <= %s
                    )
                    AND sector_name <> '' AND sector_name IS NOT NULL
                    AND sector_name <> 'Benchmark'
                    """,
                    (eval_date,),
                )
                rows = cur.fetchall()

            sector_data = {}
            for sector_name, rank, momentum, r1w, r4w, r12w in rows:
                if rank is None:
                    continue
                rank = int(rank)

                # Fail-fast: missing historical ranks means incomplete data for rotation analysis
                if r1w is None:
                    logger.warning(f"[SECTOR ROTATION] {sector_name}: missing 1w rank data for {eval_date}")
                    raise ValueError(
                        f"Sector {sector_name} missing rank_1w_ago for {eval_date} — "
                        "incomplete sector_ranking data; cannot compute rotation signal"
                    )
                if r4w is None:
                    logger.warning(f"[SECTOR ROTATION] {sector_name}: missing 4w rank data for {eval_date}")
                    raise ValueError(
                        f"Sector {sector_name} missing rank_4w_ago for {eval_date} — "
                        "incomplete sector_ranking data; cannot compute rotation signal"
                    )
                if r12w is None:
                    logger.warning(f"[SECTOR ROTATION] {sector_name}: missing 12w rank data for {eval_date}")
                    raise ValueError(
                        f"Sector {sector_name} missing rank_12w_ago for {eval_date} — "
                        "incomplete sector_ranking data; cannot compute rotation signal"
                    )

                imp_4w = int(r4w) - rank
                imp_12w = int(r12w) - rank
                imp_1w = int(r1w) - rank

                # Fail-fast: missing momentum data indicates incomplete calculation
                if momentum is None:
                    logger.warning(f"[SECTOR ROTATION] {sector_name}: missing momentum_score for {eval_date}")
                    raise ValueError(
                        f"Sector {sector_name} missing momentum_score for {eval_date} — "
                        "incomplete sector_ranking data"
                    )

                sector_data[sector_name] = {
                    "rank": rank,
                    "momentum": float(momentum),
                    "rank_improvement_1w": imp_1w,
                    "rank_improvement_4w": imp_4w,
                    "rank_improvement_12w": imp_12w,
                    "is_defensive": sector_name in DEFENSIVE_SECTORS,
                    "is_cyclical": sector_name in CYCLICAL_SECTORS,
                }

            defensive = [d for d in sector_data.values() if d["is_defensive"]]
            cyclical = [d for d in sector_data.values() if d["is_cyclical"]]

            if not sector_data:
                raise ValueError(
                    f"No sector ranking data found for {eval_date} — sector_ranking table may be empty"
                )
            if not defensive or not cyclical:
                missing_defensive = [s for s in DEFENSIVE_SECTORS if s not in sector_data]
                missing_cyclical = [s for s in CYCLICAL_SECTORS if s not in sector_data]
                raise ValueError(
                    f"Incomplete sector data for {eval_date}: "
                    f"missing defensive={missing_defensive}, missing cyclical={missing_cyclical}"
                )

            def_imp_4w = sum(d["rank_improvement_4w"] for d in defensive) / len(
                defensive
            )
            cyc_imp_4w = sum(d["rank_improvement_4w"] for d in cyclical) / len(cyclical)
            spread = def_imp_4w - cyc_imp_4w

            def_avg_momentum = sum(d["momentum"] for d in defensive) / len(defensive)
            cyc_avg_momentum = sum(d["momentum"] for d in cyclical) / len(cyclical)
            momentum_spread = def_avg_momentum - cyc_avg_momentum

            defensive_lead_score = max(0, min(100, spread * 15 + 50))

            cyclical_weak_score = max(0, min(100, -cyc_imp_4w * 15 + 50))

            weeks_persistent = sum(
                [
                    (
                        1
                        if (
                            sum(d["rank_improvement_1w"] for d in defensive)
                            / len(defensive)
                        )
                        > (
                            sum(d["rank_improvement_1w"] for d in cyclical)
                            / len(cyclical)
                        )
                        else 0
                    ),
                    1 if def_imp_4w > cyc_imp_4w else 0,
                    (
                        1
                        if (
                            sum(d["rank_improvement_12w"] for d in defensive)
                            / len(defensive)
                        )
                        > (
                            sum(d["rank_improvement_12w"] for d in cyclical)
                            / len(cyclical)
                        )
                        else 0
                    ),
                ]
            )

            if defensive_lead_score >= 75 and weeks_persistent >= 3:
                signal = "severe_defensive_rotation"
            elif defensive_lead_score >= 60 and weeks_persistent >= 2:
                signal = "defensive_rotation_warning"
            elif defensive_lead_score >= 50:
                signal = "mild_defensive_lead"
            elif def_imp_4w < cyc_imp_4w - 3:
                signal = "risk_on_confirmed"
            else:
                signal = "neutral"

            result = {
                "eval_date": str(eval_date),
                "signal": signal,
                "defensive_lead_score": round(defensive_lead_score, 1),
                "cyclical_weak_score": round(cyclical_weak_score, 1),
                "defensive_rank_improvement_4w": round(def_imp_4w, 2),
                "cyclical_rank_improvement_4w": round(cyc_imp_4w, 2),
                "spread_4w": round(spread, 2),
                "momentum_spread": round(momentum_spread, 2),
                "weeks_persistent": weeks_persistent,
                "sector_data": sector_data,
                "reduce_exposure_pts": self._exposure_penalty(
                    defensive_lead_score, weeks_persistent
                ),
            }
            self._persist(eval_date, result)
            return result
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _exposure_penalty(self, lead_score, weeks):
        """Recommend market exposure reduction in pts based on signal severity."""
        if lead_score >= 75 and weeks >= 3:
            return 10
        if lead_score >= 60 and weeks >= 2:
            return 5
        if lead_score >= 50:
            return 2
        return 0

    def _persist(self, eval_date, result):
        try:
            details_dict = {
                "defensive_lead_score": result.get("defensive_lead_score"),
                "cyclical_weak_score": result.get("cyclical_weak_score"),
                "defensive_rank_improvement_4w": result.get(
                    "defensive_rank_improvement_4w"
                ),
                "cyclical_rank_improvement_4w": result.get(
                    "cyclical_rank_improvement_4w"
                ),
                "spread_4w": result.get("spread_4w"),
                "weeks_persistent": result.get("weeks_persistent"),
                "reduce_exposure_pts": result.get("reduce_exposure_pts"),
                "sector_data": result.get("sector_data", {}),
            }

            details_json = json.dumps(details_dict)

            # Validate the JSON can be parsed back (catch bad data before DB insert)
            try:
                json.loads(details_json)
            except (json.JSONDecodeError, ValueError) as je:
                logger.error(
                    f"Invalid JSON generated for sector_rotation {eval_date}: {je}",
                    exc_info=True,
                )
                details_json = json.dumps(
                    {"error": "JSON serialization failed", "timestamp": str(eval_date)}
                )

            with DatabaseContext("write") as cur:
                cur.execute(
                    """INSERT INTO sector_rotation_signal
                       (date, sector, signal, strength, rank, details)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (date, sector) DO UPDATE SET
                           signal = EXCLUDED.signal,
                           strength = EXCLUDED.strength,
                           rank = EXCLUDED.rank,
                           details = EXCLUDED.details""",
                    (
                        eval_date,
                        "market_rotation",
                        result["signal"],
                        round(result.get("defensive_lead_score", 0) / 100.0, 4),
                        1,
                        details_json,
                    ),
                )
        except Exception as e:
            logger.error(
                f"persist sector_rotation failed for {eval_date}: {e}", exc_info=True
            )


if __name__ == "__main__":
    d = SectorRotationDetector()
    result = d.compute(_date(2026, 4, 24))
    if result:
        logger.info(f"SECTOR ROTATION — {result['eval_date']}")
        logger.info(f"Signal: {result['signal']}")
        logger.info(f"Defensive lead score: {result['defensive_lead_score']}/100")
        logger.info(f"Cyclical weak score: {result['cyclical_weak_score']}/100")
        logger.info(
            f"Defensive rank improvement 4w: {result['defensive_rank_improvement_4w']}"
        )
        logger.info(
            f"Cyclical rank improvement 4w: {result['cyclical_rank_improvement_4w']}"
        )
        logger.info(f"Spread: {result['spread_4w']}")
        logger.info(f"Weeks persistent: {result['weeks_persistent']}/4")
        logger.info(f"Recommended exp drop: {result['reduce_exposure_pts']} pts")
        logger.info("Per-sector ranks:")
        for sec, d in sorted(
            result["sector_data"].items(),
            key=lambda x: x[1]["rank_improvement_4w"],
            reverse=True,
        ):
            tag = (
                "[DEF]"
                if d["is_defensive"]
                else "[CYC]" if d["is_cyclical"] else "[   ]"
            )
            logger.info(
                f"  {tag} {sec:25s}  rank={d['rank']}  imp_4w={d['rank_improvement_4w']:+.0f}  imp_12w={d['rank_improvement_12w']:+.0f}"
            )
