#!/usr/bin/env python3
"""Consolidated Sector + Industry Performance & Rankings Loader.

CONSOLIDATION: Merges 2 separate sector loaders into one:
  - load_sector_performance.py (BaseLoader legacy, daily % returns)
  - load_sector_rankings.py (OptimalLoader modern, rankings + momentum)

Into unified OptimalLoader framework:
  - Computes: daily sector/industry performance (% return, weighted by market cap)
  - Computes: sector/industry rankings (average score, momentum vs 1w/4w/12w ago)
  - Outputs: sector_performance + sector_ranking + industry_ranking (3 tables)
  - Framework: Modern OptimalLoader (consistent with rest of pipeline)

Benefits:
  - Unified OptimalLoader framework (consistency)
  - 1 ECS task instead of 2 (saves ~$0.01-0.02/run + 5-10 min runtime)
  - Single transaction for atomic updates to all 3 tables
  - Easier maintenance (one framework, one error handler)
  - Better integration with pipeline infrastructure

Run: python3 loaders/load_sector_industry_daily.py
"""

import logging
import sys
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from algo.infrastructure.market_calendar import MarketCalendar
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SectorIndustryDailyLoader(OptimalLoader):
    """Consolidated sector + industry daily loader: performance + rankings.

    Market-wide loader (pseudo-symbol "market"). Computes:
    1. Sector/industry performance (daily % return from price changes)
    2. Sector/industry rankings (average score + momentum history)
    """

    table_name = "sector_performance"  # Primary table for watermarking
    primary_key = ("sector", "date")
    watermark_field = "date"
    is_symbol_based = False
    output_tables = ["sector_performance", "sector_ranking", "industry_ranking"]  # All tables written by this loader

    def load_global(self) -> int:
        """Override load_global() to return row count directly (side-effect loader)."""
        import os

        from utils.db.dynamo_lock import DynamoDBLockManager
        from utils.db.local_file_lock import FileLockManager, get_lock_manager
        from utils.db.rds_lock import RDSLockManager

        # get_lock_manager() returns FileLockManager when LOCAL_MODE=true (all local dev runs
        # take this path - see utils/db/local_file_lock.py), else DynamoDBLockManager with
        # RDSLockManager fallback. All three duck-type the same acquire/release/
        # lock_duration_seconds interface used below. The RuntimeError handler further down
        # only fires when BOTH DynamoDB and RDS are unavailable in non-LOCAL_MODE (production)
        # runs - it does not apply to FileLockManager, which was already fixed for its former
        # Windows race condition (Session 281: atomic O_CREAT|O_EXCL file creation).
        lock_manager: FileLockManager | DynamoDBLockManager | RDSLockManager | None = None
        try:
            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
            )
            lock_ttl = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))
            try:
                lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
            except RuntimeError as ddb_err:
                # CRITICAL (Session 282): DynamoDB unavailable in a non-LOCAL_MODE (production)
                # run, and RDS fallback also failed - fail fast rather than proceed unlocked.
                # (LOCAL_MODE=true never reaches this branch: get_lock_manager() returns
                # FileLockManager directly without raising.)
                logger.critical(
                    f"[{self.table_name}] DynamoDB lock unavailable: {ddb_err}. "
                    f"Cannot proceed without distributed locking. Fix DynamoDB access or AWS credentials."
                )
                from algo.exceptions import LockAcquisitionError

                raise LockAcquisitionError(
                    lock_key=self.table_name,
                    reason=f"DynamoDB lock manager unavailable: {ddb_err}",
                    context={"table_name": self.table_name},
                ) from ddb_err

            # get_lock_manager() either returns a real lock manager or raises RuntimeError
            # above (caught and re-raised as LockAcquisitionError) - it never returns None.
            # Narrows the type for mypy without weakening lock_manager's declared type,
            # which must stay Optional for the `if lock_manager:` release check in finally.
            assert lock_manager is not None
            if not lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5):
                logger.error(f"[{self.table_name}] Could not acquire lock")
                return 0

            # Execute the fetch_incremental which does all the work via side effects
            rows = self.fetch_incremental("market", None)
            # For side-effect loaders, rows is the count or data dict
            return sum(rows.values()) if isinstance(rows, dict) and rows else (len(rows) if rows else 1)
        finally:
            if lock_manager:
                lock_manager.release(lock_key=self.table_name)

    def run(
        self, symbols: Iterable[str] | None = None, parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to use market-wide pseudo-symbol.

        This loader is is_symbol_based=False (global), so it always processes market-wide
        metrics using the pseudo-symbol "market". Any passed symbols are ignored.
        """
        # Global-mode loaders always use pseudo-symbol "market", ignoring any passed symbol list
        return super().run(symbols=["market"], parallelism=parallelism, backfill_days=backfill_days)

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Compute sector/industry metrics globally (market-wide).

        This is the fetch_global() entry point for OptimalLoader's load_global() pattern.
        Computes sector/industry rankings and performance for all securities.

        Returns:
            Empty list (all writes handled via side effects)
        """
        return self.fetch_incremental("market", since)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute sector/industry metrics for today.

        Args:
            symbol: Pseudo-symbol "market" (ignored)
            since: Optional backfill start date

        Returns:
            Empty list - this is a side-effect-only loader (writes directly to DB).
            Rows are inserted via SQL within this method, not returned for framework insertion.
        """
        if symbol != "market":
            # No work to do: this loader only processes market-wide metrics, not individual symbols
            return []

        row_counts = {"sector_performance": 0, "sector_ranking": 0, "industry_ranking": 0}
        try:
            target_date = date.today()
            # BUG FOUND 2026-08-10 (live-reproduced, 11-day real gap): this loader is
            # scheduled in the "morning" PIPELINES list (scripts/local_loader_scheduler.py) -
            # i.e. it's meant to run BEFORE market close, same as trend_analysis/technical -
            # but target_date=today() only has real EOD price_daily coverage AFTER today's
            # close has loaded. Confirmed live: price_daily had exactly 1 row for today vs
            # ~4900 for a normal trading day, so the sector_performance INNER JOIN below
            # (pd_today.date = target_date) matched almost nothing - "Inserted 1 sector
            # performance row" instead of ~11 (one per sector), with no exception (the
            # Session 290/291 zero-rows fail-fast a few lines below only fires when ALL
            # THREE tables are empty; sector_ranking/industry_ranking are computed from
            # stock_scores, not today's price_daily, so they kept succeeding normally and
            # masked this). sector_performance sat frozen at MAX(date)=2026-07-30 (11 real
            # days stale) while sector_ranking correctly showed 2026-08-08. Falls back to the
            # latest date price_daily actually has adequate coverage for, same behavior every
            # other "morning" loader in this codebase already has (report on the last
            # completed trading day, not literal today) - instead of silently computing a
            # near-empty "success" for a date that hasn't closed yet.
            min_expected_symbols = 500
            with DatabaseContext("read") as cur:
                cur.execute("SELECT COUNT(*) FROM price_daily WHERE date = %s", (target_date,))
                today_count = (cur.fetchone() or [0])[0]
            if today_count < min_expected_symbols:
                fallback_date = MarketCalendar.get_previous_trading_day(target_date - timedelta(days=1))
                if fallback_date is None:
                    raise RuntimeError(
                        f"[{self.table_name}] CRITICAL: price_daily has only {today_count} rows "
                        f"for {target_date} (today's EOD close not loaded yet) and "
                        f"MarketCalendar.get_previous_trading_day() returned None for a fallback. "
                        f"Cannot compute sector performance without a usable target date."
                    )
                logger.warning(
                    f"[SECTOR_INDUSTRY] price_daily only has {today_count} rows for "
                    f"{target_date} (today's close not loaded yet) - using latest completed "
                    f"trading day {fallback_date} instead."
                )
                target_date = fallback_date
            # Previous TRADING day, not literal calendar day-1: a naive timedelta(days=1)
            # resolves to a weekend/holiday whenever target_date is a Monday (or the day
            # after a market holiday), and price_daily has zero rows for a day the market
            # never opened. The INNER JOIN below then matches nothing for any symbol.
            # CRITICAL FIX (Session 291): FAIL-FAST when previous trading day unavailable.
            # Before: silently fell back to target_date - timedelta(days=1) (which could be
            # a non-trading day), causing INNER JOIN to return 0 rows silently.
            # This masked the real error (MarketCalendar unable to find previous trading day)
            # and stalled sector_performance updates (confirmed live: "0 rows inserted" every
            # run from 2026-07-10 onward until Session 290 when the fallback was noticed).
            # Solution: Raise explicit error if previous trading day cannot be determined.
            prev_trading_day = MarketCalendar.get_previous_trading_day(target_date - timedelta(days=1))
            if prev_trading_day is None:
                raise RuntimeError(
                    f"[{self.table_name}] CRITICAL: Cannot determine previous trading day before {target_date}. "
                    f"MarketCalendar.get_previous_trading_day() returned None. "
                    f"Sector performance calculations require a valid previous trading day for day-over-day price changes. "
                    f"Cannot proceed with silent fallback to calendar date (would cause INNER JOIN to return 0 rows). "
                    f"Check: (1) Market calendar data is loaded, (2) We're not at start of historical data"
                )
            prev_date = prev_trading_day

            with DatabaseContext("write") as cur:
                # ===== SECTOR PERFORMANCE =====
                # Calculate daily % return per sector (weighted by price as market cap proxy)
                # FIXED (Session 279): Use company_info_sec.sic_description (SEC data) instead of
                # broken company_profile.sector (76% "Unknown" due to deprecated yfinance loader)
                cur.execute(
                    """
                    WITH daily_changes AS (
                        SELECT
                            COALESCE(c.sic_description, 'Unknown') as sector,
                            pd_today.symbol,
                            (pd_today.close - pd_prev.close) / NULLIF(pd_prev.close, 0) as daily_return,
                            pd_today.close as market_cap_proxy
                        FROM price_daily pd_today
                        INNER JOIN price_daily pd_prev
                            ON pd_today.symbol = pd_prev.symbol
                            AND pd_prev.date = %s
                        LEFT JOIN company_info_sec c ON pd_today.symbol = c.symbol
                        WHERE pd_today.date = %s
                    ),
                    sector_weighted_avg AS (
                        SELECT
                            sector,
                            SUM(daily_return * market_cap_proxy) / NULLIF(SUM(market_cap_proxy), 0) as return_pct,
                            COUNT(DISTINCT symbol) as stock_count
                        FROM daily_changes
                        WHERE sector != ''
                        GROUP BY sector
                    ),
                    -- Whole-universe cap-weighted return for the same date, used as the
                    -- relative_strength benchmark below. Deliberately the full daily_changes
                    -- set (all sectors combined), not a single ticker like SPY, so the
                    -- benchmark stays available even on days a benchmark symbol is missing.
                    market_weighted_avg AS (
                        SELECT
                            SUM(daily_return * market_cap_proxy) / NULLIF(SUM(market_cap_proxy), 0) as return_pct
                        FROM daily_changes
                    )
                    INSERT INTO sector_performance (sector, date, return_pct, relative_strength, stock_count, created_at, updated_at)
                    SELECT
                        s.sector,
                        %s as date,
                        s.return_pct,
                        -- Relative strength = sector's daily return vs the whole-universe
                        -- benchmark return that same day: (1+sector_return)/(1+market_return).
                        -- >1.0 = sector outperformed the broad market that day, <1.0 = underperformed.
                        -- Previously hardcoded to the literal 1.0 for every sector/day (never a
                        -- real calculation) - confirmed live-served via /sectors/{name}/trend.
                        (1 + s.return_pct) / NULLIF(1 + m.return_pct, 0) as relative_strength,
                        s.stock_count,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM sector_weighted_avg s
                    CROSS JOIN market_weighted_avg m
                    WHERE s.return_pct IS NOT NULL
                    ON CONFLICT (sector, date) DO UPDATE SET
                        return_pct = EXCLUDED.return_pct,
                        relative_strength = EXCLUDED.relative_strength,
                        stock_count = EXCLUDED.stock_count,
                        updated_at = NOW()
                    """,
                    (prev_date, target_date, target_date),
                )
                perf_count = cur.rowcount
                row_counts["sector_performance"] = perf_count
                logger.info(f"[SECTOR_INDUSTRY] Inserted {perf_count} sector performance rows using SEC SIC data")

                # ===== SECTOR RANKINGS =====
                # Rank sectors by average composite score + compute momentum
                # GOVERNANCE FIX: Removed COALESCE(ss.composite_score, 50) - no fabricated scores
                # Only include sectors with stocks that have real scores
                # Deliberately NOT the Session 279 SIC-description switch used by sector_performance
                # above: algo/signals/sector_rotation.py hardcodes DEFENSIVE_SECTORS/CYCLICAL_SECTORS
                # against the broad GICS-style categories ("Utilities", "Technology", "Healthcare", ...)
                # that only company_profile.sector uses - company_info_sec.sic_description's granular
                # per-company names (e.g. "Adhesives & Sealants") never match that list, so switching
                # sector_ranking to SIC data silently broke sector rotation for every run since Session
                # 279 (confirmed live 2026-07-20: 0/8 required sectors found, every recompute failed).
                # company_profile.sector is still 76% "Unknown" overall, but restricted to symbols with
                # a real composite_score (the actual ranking universe) all 8 required sectors have
                # 100+ stocks - real, non-fabricated coverage, just narrower than the full symbol list.
                cur.execute(
                    """
                    WITH sector_stats AS (
                        SELECT
                            COALESCE(cp.sector, 'Unknown') AS sector_name,
                            COUNT(DISTINCT ss.symbol) AS stock_count,
                            AVG(ss.composite_score) AS avg_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC) AS current_rank
                        FROM stock_scores ss
                        LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
                        WHERE ss.composite_score IS NOT NULL
                        GROUP BY COALESCE(cp.sector, 'Unknown')
                    )
                    INSERT INTO sector_ranking
                      (sector_name, date, current_rank, momentum_score, data_source,
                       rank_1w_ago, rank_4w_ago, rank_12w_ago, stock_count, avg_score)
                    SELECT
                        ss.sector_name,
                        NOW()::date,
                        ss.current_rank,
                        -- Sign convention: positive = improving (rank number went DOWN, e.g.
                        -- 5 -> 2 means climbing toward #1). This previously computed
                        -- current_rank - old_rank (the opposite sign: improving showed
                        -- NEGATIVE), inconsistent with every consumer of rank history in this
                        -- codebase - algo/signals/sector_rotation.py independently computes its
                        -- own rank_improvement_1w/4w/12w = old_rank - current_rank (positive =
                        -- improving) from the same r1w/r4w/r12w columns, and that's what
                        -- actually drives defensive_lead_score/rotation-signal decisions. This
                        -- momentum_score column wasn't used for any of those decisions, but IS
                        -- displayed directly to operators (dashboard/panels/sectors.py:
                        -- "mom:{value}"), where the sign-inverted value reads backwards -
                        -- negative looks like decline when it's actually improvement.
                        COALESCE(r1.rank, ss.current_rank) - ss.current_rank,
                        'price_daily_aggregated' as data_source,
                        COALESCE(r1.rank, ss.current_rank),
                        COALESCE(r4.rank, ss.current_rank),
                        COALESCE(r12.rank, ss.current_rank),
                        ss.stock_count,
                        ss.avg_score
                    FROM sector_stats ss
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '7 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r1 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '28 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r4 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '84 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r12 ON TRUE
                    ON CONFLICT (sector_name, date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        data_source = EXCLUDED.data_source,
                        stock_count = EXCLUDED.stock_count,
                        avg_score = EXCLUDED.avg_score,
                        updated_at = NOW()
                    """,
                )
                rank_count = cur.rowcount
                row_counts["sector_ranking"] = rank_count
                logger.info(f"[SECTOR_INDUSTRY] Inserted {rank_count} sector ranking rows")

                # ===== INDUSTRY RANKINGS =====
                # Same ranking logic but for industries
                # GOVERNANCE FIX: Removed COALESCE(ss.composite_score, 50) - no fabricated scores
                cur.execute(
                    """
                    WITH industry_stats AS (
                        SELECT
                            cp.industry AS industry_name,
                            COUNT(DISTINCT ss.symbol) AS stock_count,
                            AVG(ss.composite_score) AS avg_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC) AS current_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
                        WHERE cp.industry IS NOT NULL
                          AND cp.industry != ''
                          AND ss.composite_score IS NOT NULL
                        GROUP BY cp.industry
                    )
                    INSERT INTO industry_ranking
                      (industry, date_recorded, current_rank, momentum_score, data_source,
                       rank_1w_ago, rank_4w_ago, rank_12w_ago, stock_count, avg_score)
                    SELECT
                        i_stats.industry_name,
                        NOW()::date,
                        i_stats.current_rank,
                        -- Sign convention: positive = improving (rank went DOWN), matching the
                        -- sector_ranking fix above and sector_rotation.py's own
                        -- old_rank - current_rank convention. Previously computed
                        -- current_rank - old_rank here (the inverted sign the sector_ranking
                        -- comment above documents as wrong) - this value is returned directly
                        -- as "momentum_score" by lambda/api/routes/industries.py to the
                        -- Industries dashboard page, where the sign-inverted value read backwards.
                        COALESCE(r1.rank, i_stats.current_rank) - i_stats.current_rank,
                        'price_daily_aggregated' as data_source,
                        COALESCE(r1.rank, i_stats.current_rank),
                        COALESCE(r4.rank, i_stats.current_rank),
                        COALESCE(r12.rank, i_stats.current_rank),
                        i_stats.stock_count,
                        i_stats.avg_score
                    FROM industry_stats i_stats
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '7 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r1 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '28 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r4 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '84 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r12 ON TRUE
                    ON CONFLICT (industry, date_recorded) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        data_source = EXCLUDED.data_source,
                        stock_count = EXCLUDED.stock_count,
                        avg_score = EXCLUDED.avg_score,
                        updated_at = NOW()
                    """,
                )
                ind_count = cur.rowcount
                row_counts["industry_ranking"] = ind_count
                logger.info(f"[SECTOR_INDUSTRY] Inserted {ind_count} industry ranking rows")

                # Delete stale data (keep 90 days)
                cur.execute("DELETE FROM sector_performance WHERE date < NOW()::date - INTERVAL '90 days'")
                cur.execute("DELETE FROM sector_ranking WHERE date < NOW()::date - INTERVAL '90 days'")
                cur.execute("DELETE FROM industry_ranking WHERE date_recorded < NOW()::date - INTERVAL '90 days'")

        except Exception as e:
            logger.error(f"[SECTOR_INDUSTRY] Computation failed: {e}", exc_info=True)
            raise

        # Return empty list - this is a side-effect loader that writes directly to DB
        # The OptimalLoader framework expects rows to validate/insert, but we already did the
        # writes ourselves via SQL statements. Returning empty list signals success (rows were
        # already inserted via side effects), not failure.
        total_rows = sum(row_counts.values())
        logger.info(
            f"[SECTOR_INDUSTRY] Total rows updated: {total_rows} (perf={row_counts['sector_performance']}, rank={row_counts['sector_ranking']}, ind={row_counts['industry_ranking']})"
        )
        # BUG FOUND 2026-08-10: returning [] unconditionally regardless of total_rows meant a
        # day where all 3 INSERT...SELECT statements matched 0 rows (e.g. stock_scores.
        # composite_score entirely NULL that day, breaking both sector_ranking and
        # industry_ranking's source CTEs) still reported success - no exception, no failed
        # status. sector_ranking is one of only 15 tables in utils/loader_priority.py's
        # critical-loader list gating Phase 1, so a silent 0-row day here would have looked
        # identical to a healthy run to every downstream consumer. Fail fast here for the same
        # reason the prev_trading_day check above does (Session 291) - only when ALL THREE
        # tables got zero rows, since each has an independent, legitimately-partial source
        # query and a single table being empty isn't necessarily this loader's fault.
        if total_rows == 0:
            raise RuntimeError(
                f"[{self.table_name}] CRITICAL: All 3 INSERT statements matched 0 rows "
                f"(sector_performance={row_counts['sector_performance']}, "
                f"sector_ranking={row_counts['sector_ranking']}, "
                f"industry_ranking={row_counts['industry_ranking']}) for {target_date}. "
                f"This would otherwise silently report success. Check: (1) price_daily has "
                f"rows for {target_date}/{prev_date}, (2) stock_scores.composite_score is "
                f"populated, (3) company_info_sec/company_profile joins are matching."
            )
        return []


if __name__ == "__main__":
    sys.exit(
        run_loader(
            SectorIndustryDailyLoader,
            description="Consolidated sector + industry daily (performance + rankings)",
            global_mode=True,
        )
    )
