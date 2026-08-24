-- Migration 1217: Clean up future-dated rows in sector_ranking / industry_ranking
--
-- ISSUE: loaders/load_sector_industry_daily.py's sector_ranking and industry_ranking
-- INSERTs used NOW()::date directly in SQL instead of the target_date the Python code
-- already computes (via a price_daily-coverage check + MarketCalendar.get_previous_trading_day()
-- fallback - see the loader's "BUG FOUND 2026-08-10" comment). Any run whose wall-clock had
-- already crossed midnight in the database server's timezone while it was still the prior
-- calendar day in US market terms wrote rows dated a day that hadn't even opened for trading
-- yet. Live-confirmed 2026-08-23: 13 sector_ranking rows and 391 industry_ranking rows dated
-- one calendar day ahead of the most recent real trading day, with real (non-fabricated)
-- stock_count/avg_score values computed from that run's stock_scores snapshot - not test/debug
-- junk like migration 1200's cleanup, just filed under the wrong date.
--
-- IMPACT: this is the exact landmine migration 1200 flagged in algo/signals/sector_rotation.py's
-- MAX(date)-based lookup (already scoped to `date <= eval_date` there, so not live-broken today),
-- but a future-dated row is also live-wrong for any caller that queries "the latest date" without
-- an explicit <= today bound - e.g. lambda/api/routes/algo_handlers/market.py's sector-rankings
-- query (`WHERE date = (SELECT MAX(date) FROM sector_ranking)`, no date bound at all) would have
-- silently served a "current" sector ranking dated a day in the future.
--
-- FIX: the loader itself was fixed in the same change (parameterized on target_date, matching
-- sector_performance's existing correct behavior - confirmed live that sector_performance had
-- zero rows with this problem, only sector_ranking/industry_ranking, which never depended on the
-- price_daily fallback check to begin with). This migration removes the corrupted rows so the
-- next real run recomputes them under the correct date instead of leaving a duplicate/orphaned
-- future-dated row sitting alongside it.
--
-- SAFE: deletes only rows strictly after the most recent DISTINCT date that is not itself the
-- max date (i.e. rows dated later than every other row in the table) - equivalent in effect to
-- "delete rows dated after the true latest real trading day" without hardcoding today's date
-- into the migration, since a migration file's "run date" and "the day it happens to be applied"
-- are not the same thing.

DELETE FROM sector_ranking
WHERE date > (SELECT MAX(date) FROM sector_ranking sr2 WHERE sr2.date < (SELECT MAX(date) FROM sector_ranking));

DELETE FROM industry_ranking
WHERE date_recorded > (
    SELECT MAX(date_recorded) FROM industry_ranking ir2
    WHERE ir2.date_recorded < (SELECT MAX(date_recorded) FROM industry_ranking)
);
