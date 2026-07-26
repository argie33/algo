#!/usr/bin/env python3
"""Recreate views after quantity column migration."""

import logging

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def recreate_views():
    """Recreate views that were dropped during migration."""

    view_definitions = {
        "open_positions": """
            CREATE VIEW open_positions AS
            SELECT ap.position_id, ap.symbol, ap.quantity, ap.current_price,
                   ap.position_value, ap.current_stop_price, ap.status,
                   ap.entry_date, at.trade_id
            FROM algo_positions ap
            LEFT JOIN algo_trades at ON ap.trade_ids_arr @> ARRAY[at.trade_id]::text[]
            WHERE ap.status = 'open'
        """,
        "positions_using_stale_fallback": """
            CREATE VIEW positions_using_stale_fallback AS
            SELECT ap.position_id, ap.symbol, ap.quantity, ap.status
            FROM algo_positions ap
            WHERE ap.use_stale_fallback_price = true
        """,
    }

    matview_definitions = {
        "circuit_breaker_metrics": """
            CREATE MATERIALIZED VIEW circuit_breaker_metrics AS
            WITH latest_snap AS (
                SELECT total_portfolio_value, daily_return_pct
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC
                LIMIT 1
            ),
            peak_value AS (
                SELECT MAX(total_portfolio_value) AS peak
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= (NOW() - '30 days'::interval)
            ),
            trough_value AS (
                SELECT MIN(total_portfolio_value) AS trough
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= (NOW() - '30 days'::interval)
            )
            SELECT
                (SELECT total_portfolio_value FROM latest_snap) AS current_portfolio_value,
                (SELECT daily_return_pct FROM latest_snap) AS daily_return_pct,
                (SELECT peak FROM peak_value) AS peak_30d,
                (SELECT trough FROM trough_value) AS trough_30d,
                CASE
                    WHEN (SELECT peak FROM peak_value) IS NOT NULL
                    THEN ((SELECT total_portfolio_value FROM latest_snap) / (SELECT peak FROM peak_value) - 1) * 100
                    ELSE NULL
                END AS drawdown_pct
        """,
        "algo_positions_with_risk": """
            CREATE MATERIALIZED VIEW algo_positions_with_risk AS
            SELECT ap.position_id, ap.symbol, ap.quantity, ap.entry_price,
                   ap.current_price, ap.current_stop_price, ap.status,
                   (ap.quantity * ap.current_price) AS position_value,
                   ((ap.current_price - ap.entry_price) / ap.entry_price * 100) AS unrealized_pct,
                   ((ap.entry_price - ap.current_stop_price) * ap.quantity) AS risk_dollars
            FROM algo_positions ap
            WHERE ap.status = 'open'
        """,
        "mv_latest_prices": """
            CREATE MATERIALIZED VIEW mv_latest_prices AS
            SELECT DISTINCT ON (symbol) symbol, close AS price, timestamp AS price_date
            FROM price_daily
            ORDER BY symbol, timestamp DESC
        """,
        "mv_stock_scores_full": """
            CREATE MATERIALIZED VIEW mv_stock_scores_full AS
            SELECT ss.symbol, ss.composite_score, ss.momentum_score, ss.quality_score,
                   ss.value_score, ss.growth_score, ss.positioning_score,
                   ss.stability_score, ss.completeness_score
            FROM stock_scores ss
        """,
    }

    try:
        with DatabaseContext("write") as cur:
            logger.info("Recreating regular views...")

            for view_name, definition in view_definitions.items():
                try:
                    cur.execute(definition)
                    logger.info(f"  ✓ Created view: {view_name}")
                except Exception as e:
                    logger.warning(f"  ! Could not create view {view_name}: {e}")

            logger.info("\nRecreating materialized views...")

            for mview_name, definition in matview_definitions.items():
                try:
                    cur.execute(definition)
                    logger.info(f"  ✓ Created materialized view: {mview_name}")
                except Exception as e:
                    logger.warning(f"  ! Could not create materialized view {mview_name}: {e}")

            logger.info("\nView recreation complete!")

    except Exception as e:
        logger.error(f"View recreation failed: {e}")
        raise


if __name__ == "__main__":
    recreate_views()
