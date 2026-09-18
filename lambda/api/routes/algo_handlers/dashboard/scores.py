"""Algo dashboard handler: /api/algo/scores.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_dashboard_scores`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
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
from algo.signals.market_cap_tilt import compute_tilted_weights

logger = logging.getLogger(__name__)

# SECTOR-WEIGHT DEVIATION BAND REMOVED 2026-09-16 (user directive: "we not doing the scores
# like the industry guys we have extra slop"). _apply_sector_weight_cap (added 2026-09-14)
# was homegrown, uncited machinery - a 2.0x-of-eligible-universe-share multiplier and a
# 3-slot floor invented for this repo, never checked against any real published index
# provider's actual sector-deviation-band formula (unlike composite_tilted_weight just below,
# which WAS live-verified against real LRGF/GSLC holdings overlap before being kept). It was
# also the exact bug class migration 1294 exists to prevent: added only to THIS endpoint,
# never ported to lambda/api/routes/scores_handlers/stock_scores.py, so the two endpoints
# silently disagreed on which stocks appear in the leaderboard. Removed rather than fixed by
# porting - "we have extra slop" was about this filter's existence, not just its uneven
# rollout. Both endpoints now order by composite_tilted_weight alone, with zero endpoint-
# specific display machinery layered on top of the one shared, already-validated column.

# MARKET-CAP WEIGHTED TILT - THIS ENDPOINT'S DEFAULT SORT KEY (added 2026-09-15, moved into a
# stored column same day; briefly changed to raw composite_score 2026-09-16, REVERTED BACK
# the same day - see "DEFAULT SORT ORDER" note below for why). Formula REPLACED 2026-09-16 -
# see loaders/stock_scores/market_cap_tilt.py's own module comment for the switch from a
# fitted k=0.2 damping constant to MSCI's real, published Momentum Tilt Index formula. Not a
# pillar/composite_score change (composite_score itself stays pure factor merit for Phase 7/8's
# real trading decisions, per this repo's own Size-retirement precedent - see
# loaders/stock_scores/pillar_weights.py's BASE_PILLAR_WEIGHTS history) - purely a DISPLAY
# ordering choice for this "top stocks" leaderboard.
#
# DEFAULT SORT ORDER (final, 2026-09-16, user: "we don't make shit up, we do what the industry
# does only"). This endpoint briefly defaulted to raw composite_score DESC earlier the same day
# (to match a UI-consistency fix already made in the webapp's Rankings tab - see git history)
# - REVERTED after live-verified evidence that raw ranking is not what real factor-index
# products actually publish: top 50 by raw composite_score was 29/50 Financial Services
# micro/small-cap banks and thrifts, essentially none of them recognizable, because this
# system's composite has no Size dimension at all (Size was retired as a pillar - see
# BASE_PILLAR_WEIGHTS history) and an unweighted factor score mechanically favors small caps'
# more extreme ratios. Checked MSCI's own primary-source methodology directly
# (MSCI_Enhanced_Value_Index_Meth_Aug14.pdf, Section 2.4 "Weighting Scheme") rather than
# guessing: "The securities selected... are assigned weights in the proportion of market cap
# weight * Final Value Score." Real MSCI/iShares factor index holdings tables are published
# ordered by that resulting WEIGHT, never by the raw factor score alone - this is not a style
# preference, it is the actual, stated construction of the real products this system is
# modeling itself on. composite_tilted_weight is therefore the industry-correct default
# ordering for a "top stocks" leaderboard, not raw composite_score - the earlier "sorted
# highest to lowest by the visible badge" UX concern doesn't apply here the same way it does
# in a React page with an interactive toggle (this is a fixed TUI panel), and in any case
# matches how real fund fact sheets already work: holdings ordered by weight, with the
# underlying factor exposure shown as a separate, non-ordering column.
#
# COMPUTED AT REQUEST TIME AGAIN 2026-09-17 (migration 1308 dropped the stored
# composite_tilted_weight column migration 1294 added 2026-09-15 - see
# algo/signals/market_cap_tilt.py's module docstring for the full rationale). The original
# 2026-09-15 move to a stored column existed to fix a real "one endpoint got the tilt fix,
# the other didn't" bug from request-time computation duplicated ad hoc in two places -
# that risk is addressed differently now: compute_tilted_weights() is the ONE shared
# implementation both this endpoint and lambda/api/routes/scores_handlers/stock_scores.py
# import and call, so there is still exactly one formula, it's just not persisted as a
# column read like a duplicate/parallel score next to the real pillar scores.


@db_route_handler("fetch dashboard scores")
@validate_api_response("scores")
def _get_dashboard_scores(cur: cursor, limit: int = 50) -> Any:
    # VERSION: 20260714-153700 (COALESCE fix deployed)
    try:
        # Allow 25 seconds for query to complete (safe before API Gateway limit)
        cur.execute("SET LOCAL statement_timeout = '25000ms'")

        # TRADABILITY FLOOR: IBD-STYLE LIQUIDITY SCREEN (originally added 2026-09-07 as a
        # market-cap floor; REPLACED 2026-09-16, same "filtering in place in python
        # dashboard.py scores" sweep that removed the homegrown sector-weight cap above -
        # live-caught divergence: this endpoint (what the TUI dashboard's scores panel
        # calls) kept a $300M min_market_cap_millions floor as its default investability
        # screen, while lambda/api/routes/scores_handlers/stock_scores.py (what the webapp's
        # /app/scores page actually calls) had that SAME floor deliberately REMOVED
        # 2026-09-15 on live-verified evidence that real IBD screens (IBD 50) have no
        # market-cap floor at all - only a minimum share price (~$10) and minimum average
        # dollar volume, spanning small/mid/large-cap by design (see that file's own
        # "IBD-STYLE LIQUIDITY SCREEN" comment for the full citation). That fix never
        # reached THIS handler, so the two UIs were silently screening different
        # populations and showing different top-N stocks for the identical scores table -
        # the exact "one path got the fix, another didn't" bug class already flagged for the
        # sector-cap and tilt-weight issues elsewhere in this file, just a third instance of
        # it. Reuses the identical algo_config keys/thresholds/query shape as
        # stock_scores.py's default screen (min_stock_price, min_adv_dollars) rather than
        # inventing a parallel implementation, so the two endpoints can't drift again.
        cur.execute("SELECT key, value FROM algo_config WHERE key IN ('min_stock_price', 'min_adv_dollars')")
        config_rows = {row[0]: row[1] for row in cur.fetchall()}
        try:
            min_stock_price = float(config_rows["min_stock_price"])
        except (KeyError, TypeError, ValueError):
            min_stock_price = 5.0
        try:
            min_adv_dollars = float(config_rows["min_adv_dollars"])
        except (KeyError, TypeError, ValueError):
            min_adv_dollars = 500_000.0

        # TILT WEIGHT IS NOW COMPUTED HERE, NOT READ FROM A STORED COLUMN (2026-09-17,
        # migration 1308 dropped stock_scores.composite_tilted_weight - see
        # algo/signals/market_cap_tilt.py's module docstring for the full rationale/formula).
        # Fetch the full eligible population's (symbol, composite_score, market_cap) first -
        # tilt weight is a function of the WHOLE population's mean/stdev, so it can't be
        # computed per-row inside a LIMIT'd query - then rank/limit in Python before running
        # the existing per-symbol LATERAL enrichment query only against that small top-N set
        # (same "filter/sort/limit first, enrich after" performance pattern as before).
        cur.execute(
            """
            WITH liquidity AS (
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d,
                       (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                FROM (
                    SELECT symbol, volume, close, date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                ) ranked
                WHERE rn <= 20
                GROUP BY symbol
            )
            SELECT s.symbol, s.composite_score, vm.market_cap
            FROM stock_scores s
            JOIN stock_symbols sy ON sy.symbol = s.symbol
            LEFT JOIN value_metrics vm ON vm.symbol = s.symbol
            LEFT JOIN liquidity liq ON liq.symbol = s.symbol
            WHERE """
            + investable_universe_conditions("s", "sy")
            + """
                AND s.data_completeness >= 70
                AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
                AND COALESCE(liq.latest_close, 0) >= %s
                AND COALESCE(liq.avg_dollar_volume_20d, 0) >= %s
            """,
            (min_stock_price, min_adv_dollars),
        )
        population_rows = cur.fetchall()
        score_by_symbol = {r[0]: float(r[1]) for r in population_rows if r[1] is not None}
        market_cap_by_symbol = {r[0]: float(r[2]) for r in population_rows if r[2] is not None}
        tilted_weight_by_symbol = compute_tilted_weights(score_by_symbol, market_cap_by_symbol)

        ranked_symbols = sorted(
            score_by_symbol.keys(),
            key=lambda sym: (tilted_weight_by_symbol.get(sym, -1.0), score_by_symbol[sym]),
            reverse=True,
        )[:limit]

        if not ranked_symbols:
            rows: list[Any] = []
        else:
            cur.execute(
                """
                WITH max_price_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                ),
                filtered_scores AS (
                    SELECT s.*, COALESCE(c.short_name, s.symbol) as company_name, c.sector
                    FROM stock_scores s
                    LEFT JOIN company_profile c ON s.symbol = c.symbol
                    WHERE s.symbol = ANY(%s)
                )
                SELECT
                    fs.symbol, fs.composite_score, fs.growth_score, fs.momentum_score,
                    fs.quality_score, fs.value_score, fs.risk_score,
                    fs.rs_percentile, fs.data_completeness, fs.updated_at, fs.company_name, fs.sector,
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
            """,
                (ranked_symbols,),
            )
            rows_by_symbol = {row[0]: row for row in cur.fetchall()}
            rows = [rows_by_symbol[sym] for sym in ranked_symbols if sym in rows_by_symbol]
            logger.debug(f"[SCORES_DASHBOARD] Query returned {len(rows)} rows for /api/algo/scores endpoint")

        top_scores: list[Any] = []
        for row in rows:
            score_dict = safe_json_serialize(safe_dict_convert(row))
            row_symbol = score_dict.get("symbol")
            score_dict["composite_tilted_weight"] = tilted_weight_by_symbol.get(row_symbol) if row_symbol else None
            # SESSION 255: rs_percentile COALESCE fallback removed - now selected directly without synthetic 50.0 default
            # NULL values are preserved and tracked in the audit query below
            # positioning_score REMOVED from the API contract 2026-08-27 (Positioning retired

        top_scores = []
        for row in rows:
            score_dict = safe_json_serialize(safe_dict_convert(row))
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
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d,
                       (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                FROM (
                    SELECT symbol, volume, close, date,
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
            LEFT JOIN liquidity liq ON liq.symbol = s.symbol
            WHERE s.composite_score > 0
              AND s.data_completeness >= 70
              AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
              AND s.symbol NOT IN (SELECT symbol FROM etf_symbols)
              AND COALESCE(liq.latest_close, 0) >= %s
              AND COALESCE(liq.avg_dollar_volume_20d, 0) >= %s
        """,
            (min_stock_price, min_adv_dollars),
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
