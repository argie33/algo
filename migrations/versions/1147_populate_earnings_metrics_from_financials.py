#!/usr/bin/env python3
"""Migration 1147: Populate earnings_metrics from quarterly financial statements.

REWRITTEN (2026-08-09): the original version computed earnings_quality_score and
consistency_score with raw SQL RANDOM() - fake data, not a real signal - and also
referenced columns that don't exist (`q.period_end_date`, `q.eps` - the real table is
`quarterly_income_statement.fiscal_year`/`fiscal_quarter`/`earnings_per_share`), so it
would have crashed even before the RANDOM() problem was noticed.

The originally-envisioned formula (beat/miss percentage vs analyst estimates, revenue
beat rate - see APPROACH below) is NOT possible right now: both tables that would supply
it, analyst_quarterly_estimates (migration 1199) and earnings_history, are fully created
but have ZERO rows - no loader has ever populated either one. Confirmed live 2026-08-09.

Replaced with a simpler, honest, fully real formula computed from
quarterly_income_statement.earnings_per_share, which IS well populated (122,965/147,318
rows, ~83%): profitability consistency over the trailing 4 reported quarters (fraction
of quarters with positive EPS), dampened by relative EPS volatility (coefficient of
variation). This is a legitimate earnings-quality proxy - "how consistently profitable
has this company been lately" - just a much simpler one than the original beat-rate
design, and deterministic (same inputs always produce the same score, unlike RANDOM()).
If a real analyst-estimates loader is ever built for analyst_quarterly_estimates or
earnings_history, revisit this to add a real beat-rate component.

Renamed upgrade()/downgrade() to up()/down() (see migration 1146's fix - every other
.py migration in this repo uses up()/down(), the runner won't apply upgrade()/downgrade())
and changed DatabaseContext("postgres") to DatabaseContext("write") (the "postgres" role
always rolls back on __exit__, so the original version would have silently persisted
nothing even with a real formula - see migration 1146's fix for the same bug, confirmed
live).

CONTEXT:
- earnings_metrics table was created by migration 1146
- Populates it with a real, deterministic earnings-consistency score
- This enables AdvancedFilters._earnings_quality_score() to return real data

ORIGINALLY ENVISIONED APPROACH (not currently possible - see above):
1. For each symbol, get most recent quarterly earnings
2. Calculate earnings quality score based on:
   - Historical EPS accuracy (consistency over past 4 quarters)
   - Beat/miss percentage
   - Revenue beat rate
3. Insert into earnings_metrics
"""

import logging

logger = logging.getLogger(__name__)


def up() -> None:
    """Populate earnings_metrics from real quarterly EPS consistency."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("write") as cur:
        # earnings_quality_score / consistency_score from trailing-4-quarter EPS:
        # consistency_score = % of trailing quarters with positive EPS
        # earnings_quality_score = same, dampened by relative EPS volatility (stdev/|mean|)
        cur.execute("""
            WITH recent AS (
                SELECT symbol, fiscal_year, fiscal_quarter, earnings_per_share,
                       ROW_NUMBER() OVER (
                           PARTITION BY symbol ORDER BY fiscal_year DESC, fiscal_quarter DESC
                       ) AS rn
                FROM quarterly_income_statement
                WHERE earnings_per_share IS NOT NULL
            ),
            trailing4 AS (
                SELECT symbol,
                       COUNT(*) AS n_quarters,
                       COUNT(*) FILTER (WHERE earnings_per_share > 0) AS positive_quarters,
                       AVG(earnings_per_share) AS avg_eps,
                       STDDEV_SAMP(earnings_per_share) AS stdev_eps
                FROM recent
                WHERE rn <= 4
                GROUP BY symbol
                HAVING COUNT(*) >= 2
            )
            INSERT INTO earnings_metrics
            (symbol, report_date, earnings_quality_score, consistency_score, created_at, updated_at)
            SELECT
                symbol,
                CURRENT_DATE,
                ROUND(
                    LEAST(100, GREATEST(0,
                        (positive_quarters::numeric / n_quarters) * 100
                        * (1 - LEAST(1, COALESCE(stdev_eps / NULLIF(ABS(avg_eps), 0), 0) / 2))
                    )), 2
                ),
                ROUND((positive_quarters::numeric / n_quarters) * 100, 2),
                NOW(),
                NOW()
            FROM trailing4
            ON CONFLICT (symbol, report_date) DO NOTHING
        """)
        logger.info("Populated earnings_metrics from real quarterly_income_statement EPS history")

        # Mark symbols without enough quarterly EPS history as unavailable
        cur.execute("""
            INSERT INTO earnings_metrics
            (symbol, report_date, earnings_quality_score, data_unavailable,
             unavailable_reason, created_at, updated_at)
            SELECT
                s.symbol,
                CURRENT_DATE,
                NULL,
                TRUE,
                'insufficient_quarterly_eps_history',
                NOW(),
                NOW()
            FROM stock_symbols s
            WHERE NOT EXISTS (
                SELECT 1 FROM earnings_metrics e WHERE e.symbol = s.symbol
            )
            AND s.active = TRUE
            AND length(s.symbol) <= 10  -- earnings_metrics.symbol is VARCHAR(10); stock_symbols
                                         -- has a handful of longer non-ticker test fixture rows
                                         -- (HEALTH_CHECK_TEST, DB_CONTEXT_TEST, etc.)
            ON CONFLICT (symbol, report_date) DO NOTHING
        """)

        logger.info("Marked symbols without sufficient EPS history as unavailable")
        logger.info("Migration 1147 complete: earnings_metrics populated with real EPS-consistency scores")


def down() -> None:
    """Clear earnings_metrics data."""
    from utils.db.context import DatabaseContext

    with DatabaseContext("write") as cur:
        cur.execute("DELETE FROM earnings_metrics WHERE report_date = CURRENT_DATE")
        logger.info("Migration 1147 downgrade complete: earnings_metrics cleared")


if __name__ == "__main__":
    import sys

    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        up()
    elif action == "downgrade":
        down()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
