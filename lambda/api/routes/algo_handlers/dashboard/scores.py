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

logger = logging.getLogger(__name__)

# RAW, UNFILTERED, RANKED BY REAL composite_score (2026-09-18 user directive: "it should not
# filter it should show the raw results from the table" - reapplied after a concurrent-session
# git operation reverted this endpoint back to a pre-directive state that both defaulted to
# ranking by composite_tilted_weight (a request-time-computed, whole-composite market-cap tilt
# - a DIFFERENT, older concept than the per-pillar momentum/quality/value/growth/risk_tilted_
# weight columns discussed in loaders/stock_scores/market_cap_tilt.py's docstring; this file's
# history below predates and is unrelated to that per-pillar mechanism) and applied a default
# investable-universe/data-completeness/liquidity screen. Both are gone: this endpoint now
# returns every stock_scores row, ranked by the same real composite_score column Phase 7/8
# trading decisions use and that scores_handlers/stock_scores.py's default view also ranks by
# - one number, one ranking, no hidden filter, matching that endpoint so dashboard.py TUI and
# the React scores page can no longer silently disagree about which stocks even appear. See
# git history on this file for the composite_tilted_weight-based design this replaces if that
# context is ever needed again - not reproduced here since it's no longer live behavior.


@db_route_handler("fetch dashboard scores")
@validate_api_response("scores")
def _get_dashboard_scores(cur: cursor, limit: int = 50) -> Any:
    # VERSION: 20260714-153700 (COALESCE fix deployed)
    try:
        # Allow 25 seconds for query to complete (safe before API Gateway limit)
        cur.execute("SET LOCAL statement_timeout = '25000ms'")

        # RAW, UNFILTERED, RANKED BY composite_score (see module docstring above) - no
        # investable-universe/data-completeness/liquidity screen, no tilt-weight computation
        # or re-ranking. Straight SQL ORDER BY on the real, stored column, same "filter/sort/
        # limit first, enrich after" performance pattern as before (LATERAL price/technical
        # lookups only run against the already-limited page).
        cur.execute(
            """
            WITH max_price_date AS (
                SELECT MAX(date) AS max_date FROM price_daily
            ),
            filtered_scores AS (
                SELECT s.*, COALESCE(c.short_name, s.symbol) as company_name, c.sector
                FROM stock_scores s
                JOIN stock_symbols sy ON sy.symbol = s.symbol
                LEFT JOIN company_profile c ON s.symbol = c.symbol
                ORDER BY s.composite_score DESC NULLS LAST
                LIMIT %s
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
            ORDER BY fs.composite_score DESC NULLS LAST
        """,
            (limit,),
        )
        rows = cur.fetchall()
        logger.debug(f"[SCORES_DASHBOARD] Query returned {len(rows)} rows for /api/algo/scores endpoint")

        top_scores: list[Any] = []
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
        # RAW, UNFILTERED (2026-09-18, same directive as the main list above) - is_sp500 =
        # TRUE is the one deliberate, explicit lens this sub-list exists for, not a
        # data-quality filter.
        cur.execute(
            """
            SELECT s.symbol, s.composite_score, s.growth_score, s.momentum_score,
                   s.quality_score, s.value_score, s.risk_score, s.data_completeness,
                   COALESCE(c.short_name, s.symbol) as company_name, c.sector
            FROM stock_scores s
            JOIN stock_symbols ss ON ss.symbol = s.symbol
            LEFT JOIN company_profile c ON s.symbol = c.symbol
            WHERE ss.is_sp500 = TRUE
            ORDER BY s.composite_score DESC NULLS LAST
            LIMIT 15
            """
        )
        top_sp500 = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=1)

        # Summary metrics over the FULL, RAW stock_scores table (not just the returned page) -
        # same "no default filter" contract as the main list above, so this summary line
        # describes the same population the list is actually drawn from. COUNT/AVG/FILTER
        # already ignore NULL composite_score rows on their own, so no explicit NULL handling
        # needed.
        cur.execute(
            """
            SELECT
                COUNT(*) AS universe_total,
                AVG(s.composite_score) AS avg_composite,
                COUNT(*) FILTER (WHERE s.composite_score >= 80) AS a,
                COUNT(*) FILTER (WHERE s.composite_score >= 60 AND s.composite_score < 80) AS b,
                COUNT(*) FILTER (WHERE s.composite_score >= 40 AND s.composite_score < 60) AS c,
                COUNT(*) FILTER (WHERE s.composite_score < 40) AS d
            FROM stock_scores s
        """
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
