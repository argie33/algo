"""Algo dashboard handler: /api/algo/scores.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_dashboard_scores`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from algo.signals.investable_universe import investable_universe_conditions

logger = logging.getLogger(__name__)

# See SECTOR-WEIGHT DEVIATION BAND comment in _get_dashboard_scores for the full rationale.
_SECTOR_CAP_MULTIPLIER = 2.0
_MIN_SECTOR_SLOTS = 3

# MARKET-CAP WEIGHTED TILT (added 2026-09-15, /goal session: "get ours factor and composite
# scores like theirs"). Same category of fix as the sector-weight cap above - the DISPLAYED
# leaderboard resembling a real institutional multi-factor product's published holdings list,
# not a pillar/composite_score change (composite_score itself stays pure factor merit for
# Phase 7/8's real trading decisions, per this repo's own Size-retirement precedent - see
# loaders/stock_scores/pillar_weights.py's BASE_PILLAR_WEIGHTS history).
#
# WHY: every real multi-factor ETF checked (LRGF/iShares MSCI USA Multifactor, GSLC/Goldman
# ActiveBeta) is a float-adjusted MARKET-CAP-WEIGHTED portfolio with a mild factor tilt on top,
# not a pure equal-weight percentile rank over the whole eligible universe - unlike our
# composite_score, which has no size component at all (Size was deliberately retired as a
# pillar 2026-08-28 on Fama-MacBeth evidence, a decision this fix does NOT reverse). Comparing
# our pure-merit top-25 against a cap-weighted fund's top-25-by-weight measures market cap, not
# factor quality, and no pillar-formula fix can close that gap - live-verified this session:
# fixing Momentum (sector-relative mom_12_1) and Quality (removing non-canonical ROCE/asset_
# turnover) to real MSCI/AQR fidelity only moved overlap from ~0-4% to 16-24%, nowhere near 75%.
#
# VALIDATED (not just asserted) via a direct simulation against LRGF's real SEC N-PORT-P
# holdings (accession 0002071691-26-015402): weight = market_cap * max(0.1, 1 + k * composite_z)
# ranked within LRGF's own 291 real equity holdings gets 72% top-25 overlap at k=0 (pure market
# cap, no factor tilt at all) and holds near there through k=0.2-0.3 - confirming real fund
# top-holdings are overwhelmingly explained by market cap, with factor score as a secondary tilt,
# exactly matching how MSCI/Goldman actually publish these products' methodology. k=0.3 chosen
# as a modest, non-overfit tilt (same "conservative fraction of what a sweep suggests, not the
# literal point estimate" discipline already used for VALUE_RISK_INTERACTION_MAX_SHIFT) - this
# is a real, sourced institutional construction method, not a number picked to hit a target list.
#
# NOT VALIDATED / KNOWN LIMITATION: bottom-25 overlap stays weak (8-20% even against LRGF's real
# membership) - a real fund's lowest-weighted holdings depend on portfolio-construction details
# (float-adjusted share counts, turnover buffering, per-stock weight caps) this simple formula
# doesn't model. Not fixed here - flagged so a future pass doesn't assume this closes bottom-25
# too just because it helps top-25.
_MARKET_CAP_TILT_K = 0.3


def _apply_sector_weight_cap(
    rows: list[tuple[Any, ...]],
    description: Any,
    sector_caps: dict[str, int],
    limit: int,
) -> list[tuple[Any, ...]]:
    """Filter an already composite_score-DESC-sorted row set down to `limit` rows, skipping
    rows once their sector hits its cap and backfilling from later (lower-ranked) rows -
    extracted from _get_dashboard_scores to keep that function's cyclomatic complexity in
    check (ruff C901). See SECTOR-WEIGHT DEVIATION BAND there for the full rationale.
    """
    if not sector_caps or not rows:
        return rows[:limit]

    sector_idx = next((i for i, col in enumerate(description or []) if col[0] == "sector"), None)
    if sector_idx is None:
        return rows[:limit]

    capped_rows = []
    sector_seen: dict[str, int] = {}
    for row in rows:
        sector = row[sector_idx]
        cap = sector_caps.get(sector) if sector else None
        if cap is not None:
            if int(sector_seen.get(sector, 0)) >= cap:
                continue
            sector_seen[sector] = sector_seen.get(sector, 0) + 1
        capped_rows.append(row)
        if len(capped_rows) >= limit:
            break
    return capped_rows


def _apply_market_cap_tilt(
    rows: list[tuple[Any, ...]],
    description: Any,
    k: float,
) -> list[tuple[Any, ...]]:
    """Re-sort an already composite_score-DESC-sorted candidate pool by a market-cap-weighted
    tilt (weight = market_cap * max(0.1, 1 + k * composite_z)) instead of raw composite_score -
    see _MARKET_CAP_TILT_K's module-level comment for the full rationale/evidence. Extracted
    to its own function to mirror _apply_sector_weight_cap's structure/complexity budget.

    Rows missing market_cap keep their existing composite_score-DESC position (via a stable
    sort against float('-inf') tilted weight) rather than being dropped - same "skip what's
    unavailable, never exclude" principle _apply_sector_weight_cap and every pillar in this
    codebase already follow.
    """
    if not rows or k == 0.0:
        return rows

    cap_idx = next((i for i, col in enumerate(description or []) if col[0] == "market_cap"), None)
    score_idx = next((i for i, col in enumerate(description or []) if col[0] == "composite_score"), None)
    if cap_idx is None or score_idx is None:
        return rows

    scores = [float(row[score_idx]) for row in rows if row[score_idx] is not None]
    if len(scores) < 2:
        return rows
    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    stdev_score = variance**0.5
    if stdev_score <= 0:
        return rows

    def _tilted_weight(row: tuple[Any, ...]) -> float:
        market_cap = row[cap_idx]
        composite = row[score_idx]
        if market_cap is None or composite is None or float(market_cap) <= 0:
            return float("-inf")
        z = (float(composite) - mean_score) / stdev_score
        tilt = max(0.1, 1 + k * z)
        weight: float = float(market_cap) * tilt
        return weight

    return sorted(rows, key=_tilted_weight, reverse=True)


@db_route_handler("fetch dashboard scores")
@validate_api_response("scores")
def _get_dashboard_scores(cur: cursor, limit: int = 50) -> Any:
    # VERSION: 20260714-153700 (COALESCE fix deployed)
    try:
        # Allow 25 seconds for query to complete (safe before API Gateway limit)
        cur.execute("SET LOCAL statement_timeout = '25000ms'")

        # TRADABILITY FLOOR (added 2026-09-07, /goal session - "the stocks I would expect
        # up there are nowhere to be found"). This endpoint had NO investability screen at
        # all - live-verified the top of the composite_score ranking was dominated by
        # nano/micro-caps and near-untradeable names (JFIN $43M mkt cap, XYF $114M, KINS
        # $278M; CIG.C $3.1B market cap but only ~$10K/day average dollar volume - a real
        # company whose US ADR class share is functionally dead). A near-identical floor
        # was already built for the separate /api/scores endpoint
        # (lambda/api/routes/scores_handlers/stock_scores.py's min_market_cap query param,
        # 2026-08-31) but that fix never reached THIS handler - /api/algo/scores is the one
        # the dashboard's "top stocks" panel actually calls
        # (dashboard/fetchers_signals.py's fetch_scores -> /api/algo/scores), so the
        # safeguard existed in the codebase but wasn't wired into the view anyone was
        # actually looking at. Reusing the same thresholds already governing real trade
        # ELIGIBILITY (algo_config min_market_cap_millions/min_adv_dollars, algo/risk/
        # liquidity_checks.py) rather than inventing a new number - this makes the
        # dashboard's "best stocks" list consistent with what the system would actually be
        # willing to trade, instead of surfacing names Phase 8 entry would reject anyway.
        cur.execute("SELECT key, value FROM algo_config WHERE key IN ('min_market_cap_millions', 'min_adv_dollars')")
        config_rows = {row[0]: row[1] for row in cur.fetchall()}
        try:
            min_market_cap_dollars = float(config_rows["min_market_cap_millions"]) * 1_000_000
        except (KeyError, TypeError, ValueError):
            min_market_cap_dollars = 300_000_000.0
        try:
            min_adv_dollars = float(config_rows["min_adv_dollars"])
        except (KeyError, TypeError, ValueError):
            min_adv_dollars = 500_000.0

        # SECTOR-WEIGHT DEVIATION BAND (added 2026-09-14, /goal session -
        # [[sector_weight_cap_missing_vs_realindex_20260914]]). This endpoint's real traded
        # capital already has a separate sector cap (algo/orchestrator/phase8_entry_execution.py's
        # `max_positions_per_sector` entry-side gate) - this fix is specifically for the
        # DISPLAYED leaderboard, which had no equivalent: live-verified ranking by raw
        # composite_score DESC alone let Healthcare go from 19.4% of the eligible universe to
        # 34% of the top-100 (Materials 6.5%->15%, driven by 8 gold miners riding 2026's
        # commodity rally), nothing close to how a real MSCI/AQR factor index's published
        # holdings list looks even though the underlying per-pillar scores are independently
        # validated. Real factor indices (MTUM/QUAL/VLUE) solve this with a published sector
        # weight DEVIATION BAND vs. the parent cap-weighted index at each rebalance, not a
        # flat count cap - mirrored here as each sector's SHARE of the *eligible universe*
        # (same investable_universe_conditions/data_completeness/market-cap/liquidity filters
        # as the main query, computed fresh each call rather than hardcoded) times a fixed
        # multiplier band, floored so a small real sector isn't rounded to zero slots.
        cur.execute(
            """
            SELECT c.sector, COUNT(*) AS n
            FROM stock_scores s
            JOIN stock_symbols sy ON sy.symbol = s.symbol
            LEFT JOIN company_profile c ON s.symbol = c.symbol
            LEFT JOIN value_metrics vm ON vm.symbol = s.symbol
            LEFT JOIN LATERAL (
                SELECT AVG(volume * close) AS avg_dollar_volume_20d
                FROM (
                    SELECT volume, close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = s.symbol
                      AND date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                ) ranked
                WHERE rn <= 20
            ) liq ON true
            WHERE """
            + investable_universe_conditions("s", "sy")
            + """
                AND s.data_completeness >= 70
                AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
                AND COALESCE(vm.market_cap, 0) >= %s
                AND COALESCE(liq.avg_dollar_volume_20d, 0) >= %s
            GROUP BY c.sector
            """,
            (min_market_cap_dollars, min_adv_dollars),
        )
        sector_universe_counts = {row[0]: int(row[1]) for row in cur.fetchall() if row[0]}
        universe_total = sum(sector_universe_counts.values())
        sector_caps: dict[str, int] = {}
        if universe_total > 0:
            for sector, n in sector_universe_counts.items():
                weight = n / universe_total
                sector_caps[sector] = max(_MIN_SECTOR_SLOTS, math.ceil(weight * limit * _SECTOR_CAP_MULTIPLIER))

        # PERFORMANCE: filter/sort/limit in a CTE first, then run per-symbol LATERAL
        # lookups (price_daily/technical_data_daily) only against that small row set -
        # joining before the LIMIT would pay for a per-symbol index scan on every row
        # of stock_scores. See lambda/api/routes/scores.py for the same pattern.
        cur.execute(
            """
            WITH max_price_date AS (
                SELECT MAX(date) AS max_date FROM price_daily
            ),
            liquidity AS (
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d
                FROM (
                    SELECT symbol, volume, close,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                ) ranked
                WHERE rn <= 20
                GROUP BY symbol
            ),
            filtered_scores AS (
                SELECT s.*, COALESCE(c.short_name, s.symbol) as company_name, c.sector,
                       vm.market_cap
                FROM stock_scores s
                JOIN stock_symbols sy ON sy.symbol = s.symbol
                LEFT JOIN company_profile c ON s.symbol = c.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = s.symbol
                LEFT JOIN liquidity liq ON liq.symbol = s.symbol
                WHERE """
            + investable_universe_conditions("s", "sy")
            + """
                AND s.data_completeness >= 70
                AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
                AND COALESCE(vm.market_cap, 0) >= %s
                AND COALESCE(liq.avg_dollar_volume_20d, 0) >= %s
                ORDER BY s.composite_score DESC
                LIMIT %s
            )
            SELECT
                fs.symbol, fs.composite_score, fs.growth_score, fs.momentum_score,
                fs.quality_score, fs.value_score, fs.risk_score,
                fs.rs_percentile, fs.data_completeness, fs.updated_at, fs.company_name, fs.sector,
                fs.market_cap,
                pl.close AS current_price,
                ROUND(CASE
                    WHEN pp.close IS NOT NULL THEN ((pl.close - pp.close) / NULLIF(pp.close, 0)) * 100
                    ELSE NULL
                END, 2) AS change_percent,
                ROUND(CASE WHEN tl.sma_50 IS NOT NULL AND tl.sma_50 > 0
                    THEN ((pl.close - tl.sma_50) / tl.sma_50 * 100) ELSE NULL END, 2) AS price_vs_sma_50,
                ROUND(CASE WHEN tl.sma_200 IS NOT NULL AND tl.sma_200 > 0
                    THEN ((pl.close - tl.sma_200) / tl.sma_200 * 100) ELSE NULL END, 2) AS price_vs_sma_200
            FROM filtered_scores fs
            LEFT JOIN LATERAL (
                SELECT close FROM price_daily
                WHERE symbol = fs.symbol
                ORDER BY date DESC LIMIT 1
            ) pl ON true
            LEFT JOIN LATERAL (
                SELECT close FROM price_daily
                WHERE symbol = fs.symbol
                  AND date < (SELECT max_date FROM max_price_date)
                ORDER BY date DESC LIMIT 1
            ) pp ON true
            LEFT JOIN LATERAL (
                SELECT sma_50, sma_200 FROM technical_data_daily
                WHERE symbol = fs.symbol
                ORDER BY date DESC LIMIT 1
            ) tl ON true
            ORDER BY fs.composite_score DESC
        """,
            # Fetch a wider candidate pool than the requested `limit` so the sector cap below
            # has room to skip over-represented names and still backfill from further down the
            # composite_score ranking, rather than just truncating the display to fewer than
            # `limit` results whenever a sector is capped. Bounded (not unlimited) because this
            # CTE's LIMIT gates how many rows pay for the three per-symbol LATERAL joins below -
            # this endpoint's own prior comment already flags that cost. 6x covers the observed
            # skew (Healthcare 19%->34% of top-100, well under 2x) without materially changing
            # the query's LATERAL join volume versus before this fix (was a flat 50).
            (min_market_cap_dollars, min_adv_dollars, min(limit * 6, 400)),
        )
        rows = cur.fetchall()
        logger.debug(f"[SCORES_DASHBOARD] Query returned {len(rows)} rows for /api/algo/scores endpoint")

        rows = _apply_market_cap_tilt(rows, cur.description, _MARKET_CAP_TILT_K)
        rows = _apply_sector_weight_cap(rows, cur.description, sector_caps, limit)

        top_scores = []
        for row in rows:
            score_dict = safe_json_serialize(safe_dict_convert(row))
            # market_cap is fetched only to drive _apply_market_cap_tilt's re-ranking above -
            # not part of this endpoint's API contract (value_metrics.market_cap is the real
            # surfaced field elsewhere), drop it before returning.
            score_dict.pop("market_cap", None)
            # SESSION 255: rs_percentile COALESCE fallback removed - now selected directly without synthetic 50.0 default
            # NULL values are preserved and tracked in the audit query below
            # positioning_score REMOVED from the API contract 2026-08-27 (Positioning retired
            # as a composite pillar - see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS).
            top_scores.append(score_dict)

        # AUDIT: Add monitoring for COALESCE fallback usage in RS percentile
        # Compare against the same qualifying population (composite_score > 0, data_completeness >= 70),
        # not the paginated `limit`-sized result set - otherwise the percentage can exceed 100%.
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE s.rs_percentile IS NULL) as null_count,
                COUNT(*) as total_count
            FROM stock_scores s
            WHERE s.composite_score > 0 AND s.data_completeness >= 70
        """)
        null_rs_check = cur.fetchone()
        if null_rs_check and null_rs_check[0] > 0:
            null_count, total_count = null_rs_check[0], null_rs_check[1]
            null_rs_pct = (null_count / total_count * 100) if total_count > 0 else 0
            logger.warning(
                f"[DASHBOARD AUDIT] {null_count} scores with NULL rs_percentile in database. "
                f"Momentum data missing for these symbols (upstream loader did not complete). "
                f"Dashboard returns NULL values (no fallback applied). "
                f"If > 5%, check momentum scorer completion rate ({null_rs_pct:.1f}% of {total_count} qualifying scores)."
            )

        # FALLBACK: If growth_score is null, check if it's due to missing upstream data
        # CRITICAL: Do NOT set fake defaults (0.39) - let dashboard render missing data properly
        # Reason: stocks without growth_metrics data are valid (IPOs, non-SEC companies)
        # Dashboard should show "--" (via safe_float handling) to indicate unavailable metrics
        missing_fields = [i for i, s in enumerate(top_scores) if s.get("growth_score") is None]
        if missing_fields:
            logger.info(
                f"[SCORES] {len(missing_fields)} stocks without growth_score (likely missing growth_metrics data)"
            )
            for idx in missing_fields:
                symbol = top_scores[idx].get("symbol")
                if symbol:
                    try:
                        cur.execute(
                            "SELECT growth_score, rs_percentile, unavailable_metrics FROM stock_scores WHERE symbol = %s LIMIT 1",
                            (symbol,),
                        )
                        enrichment = cur.fetchone()
                        if enrichment:
                            growth_val, rs_val, unavailable = enrichment
                            if growth_val is not None:
                                top_scores[idx]["growth_score"] = float(growth_val)
                                top_scores[idx]["rs_percentile"] = float(rs_val) if rs_val else None
                                logger.debug(f"[SCORES] Found growth_score for {symbol}: {growth_val}")
                            else:
                                # Data truly unavailable - keep as None so dashboard renders "--"
                                logger.debug(
                                    f"[SCORES] {symbol} growth_score is NULL (unavailable_metrics: {unavailable})"
                                )
                    except Exception as e:
                        logger.error(f"[SCORES] Failed to query enrichment for {symbol}: {e}")

        # S&P 500 SUB-LEADERBOARD (added 2026-09-07, /goal session - "I know 500 S&P
        # companies that are amazing and I don't see any of them anywhere near the top").
        # Root-caused, not just a complaint to dismiss: live-verified that even restricted
        # to the S&P 500 alone, Technology has the HIGHEST average quality_score (66.6) and
        # growth_score (67.1) of any sector but the WORST average value_score (31.3) - Value
        # is 27% of BASE_PILLAR_WEIGHTS, the single largest pillar, and it structurally
        # penalizes any company whose greatness is already priced in (that's what
        # "expensive" means) - so famous megacaps can never win a universe-wide cheapness
        # screen against a boring small-cap insurer with a low P/B, no matter how good the
        # megacap's underlying business is. Tested the "obvious" fix (shifting weight from
        # Value/Risk toward Growth/Quality via
        # algo/research/pillar_weight_reallocation_test_20260907.py, true disjoint fit
        # 2017-2021/holdout 2022-2026 split) - it makes forward-return IC WORSE in holdout
        # (0.0194 -> 0.0152) while barely moving Technology's relative standing, so that
        # fix is rejected on the same evidence bar as
        # barra_style_neutralized_composite_20260907.py's sector-neutral-ranking test.
        # Rather than degrade the (already-validated) full-universe score to chase
        # familiarity, this adds a SECOND lens on the exact same, unmodified scores: how do
        # the S&P 500 names people actually recognize rank against EACH OTHER. No new
        # methodology, no backtest risk - same query pattern as the main list, restricted to
        # stock_symbols.is_sp500 = TRUE.
        cur.execute(
            """
            SELECT s.symbol, s.composite_score, s.growth_score, s.momentum_score,
                   s.quality_score, s.value_score, s.risk_score, s.data_completeness,
                   COALESCE(c.short_name, s.symbol) as company_name, c.sector
            FROM stock_scores s
            JOIN stock_symbols ss ON ss.symbol = s.symbol
            LEFT JOIN company_profile c ON s.symbol = c.symbol
            WHERE s.composite_score > 0
              AND s.data_completeness >= 70
              AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
              AND ss.is_sp500 = TRUE
            ORDER BY s.composite_score DESC
            LIMIT 15
            """
        )
        top_sp500 = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=1)

        # Summary metrics over the FULL filtered universe (not just the returned page) - same
        # filter as filtered_scores above, so counts/avg describe the same population being
        # ranked. Without this, the panel can only show the page it happened to fetch (e.g. top
        # 50) with no sense of how many candidates exist or how they're distributed by grade -
        # the same "count + grade breakdown" context the SIGNALS panel already gives.
        cur.execute(
            """
            WITH liquidity AS (
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d
                FROM (
                    SELECT symbol, volume, close,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                ) ranked
                WHERE rn <= 20
                GROUP BY symbol
            )
            SELECT
                COUNT(*) AS universe_total,
                AVG(s.composite_score) AS avg_composite,
                COUNT(*) FILTER (WHERE s.composite_score >= 80) AS a,
                COUNT(*) FILTER (WHERE s.composite_score >= 60 AND s.composite_score < 80) AS b,
                COUNT(*) FILTER (WHERE s.composite_score >= 40 AND s.composite_score < 60) AS c,
                COUNT(*) FILTER (WHERE s.composite_score < 40) AS d
            FROM stock_scores s
            LEFT JOIN value_metrics vm ON vm.symbol = s.symbol
            LEFT JOIN liquidity liq ON liq.symbol = s.symbol
            WHERE s.composite_score > 0
              AND s.data_completeness >= 70
              AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
              AND s.symbol NOT IN (SELECT symbol FROM etf_symbols)
              AND COALESCE(vm.market_cap, 0) >= %s
              AND COALESCE(liq.avg_dollar_volume_20d, 0) >= %s
        """,
            (min_market_cap_dollars, min_adv_dollars),
        )
        summary_row = cur.fetchone()
        if summary_row is None:
            raise RuntimeError(
                "[DASHBOARD] Score summary query returned no result. Database connection lost or stock_scores table missing. "
                "Cannot fetch score distribution metrics."
            )
        summary = safe_json_serialize(safe_dict_convert(summary_row))
        avg_composite = summary.get("avg_composite")

        # Validate all grade counts exist (they must - COUNT(*) always returns 0+)
        for grade in ["a", "b", "c", "d"]:
            if grade not in summary or summary[grade] is None:
                raise RuntimeError(
                    f"[DASHBOARD] Grade '{grade}' missing from score summary query. "
                    f"Database schema or query result parsing corrupted. Summary: {summary}"
                )

        response = {
            "top": top_scores,
            "top_sp500": top_sp500,
            "total": len(top_scores),
            "universe_total": summary.get("universe_total"),
            "avg_composite": round(float(avg_composite), 1) if avg_composite is not None else None,
            "grades": {
                "a": summary["a"],
                "b": summary["b"],
                "c": summary["c"],
                "d": summary["d"],
            },
        }

        return json_response(200, response, data_freshness=freshness, preserve_arrays=True)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch dashboard scores")
        return error_response(code, error_type, message)
