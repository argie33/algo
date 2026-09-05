-- Migration 1256: Add period_end date column to quarterly_income_statement
-- Date: 2026-09-05 (goal session: "SEC/XBRL missing data + implausible values" sweep)

-- ROOT CAUSE: quarterly_income_statement.fiscal_year is assigned as the CALENDAR year of
-- each fact's real period-end date (see sec_statements.py's _aggregate_concepts_resolve_
-- entry_period, "Use period end year as the fiscal year key, not SEC's fy field" - a
-- deliberate, correct choice for separating current-year data from multi-year comparison
-- columns). For a non-December-fiscal-year-end filer (e.g. AAPL, fiscal year end in
-- September), this scatters a single real fiscal cycle's 4 quarters across TWO different
-- calendar-year "fiscal_year" values: AAPL's Q1 (Oct-Dec) ends in December, landing in the
-- SAME OR AN EARLIER calendar year than its own Q2-Q4 (which end the following Mar/Jun/Sep).
-- Live-confirmed via real DB query: AAPL's real Oct-Dec 2025 quarter (its largest, the
-- holiday quarter, EPS $2.85) is stored as fiscal_year=2025/fiscal_quarter=1, while the
-- FOLLOWING two quarters (Jan-Mar 2026, Apr-Jun 2026) are stored as fiscal_year=2026/
-- fiscal_quarter=2,3 - so `ORDER BY fiscal_year DESC, fiscal_quarter DESC` places the real,
-- most-recent quarter FIFTH in the sort, behind three chronologically OLDER quarters that
-- happen to share fiscal_year=2025 with it.
--
-- IMPACT: loaders/load_earnings_metrics.py and loaders/load_value_quality_growth_metrics.py's
-- _compute_quarterly_metrics both do `... ORDER BY fiscal_year DESC, fiscal_quarter DESC
-- LIMIT N` and treat the result as "the last N quarters in chronological order" - for AAPL
-- right now this silently excludes its real most recent quarter from every trailing-quarter
-- metric (earnings_metrics consistency/quality score, consecutive_positive_quarters,
-- quarterly_growth_momentum, earnings_growth_4q_avg, eps_growth_stability,
-- earnings_surprise_avg, earnings_beat_rate) for any non-December-FYE filer where this
-- adjacency occurs - a wrong-but-plausible-looking value, not a NULL, so it doesn't surface
-- via any existing missing-data/implausible-value reason code.
--
-- FIX: store the fact's own real period-end date (already read from the raw SEC XBRL
-- entry's "end" field in sec_statements.py, just never persisted) so consumers can
-- `ORDER BY period_end DESC` directly instead of reconstructing chronological order from
-- fiscal_year/fiscal_quarter labels. Purely additive - nullable column, no existing row
-- touched, no existing consumer's fiscal_year/fiscal_quarter columns changed. Old rows keep
-- period_end NULL until their next refresh (loaders COALESCE-order by fiscal_year/quarter
-- for those, identical to today's behavior - no regression), new/refreshed rows get the
-- real date and sort correctly.

BEGIN;

ALTER TABLE quarterly_income_statement
ADD COLUMN IF NOT EXISTS period_end DATE;

COMMENT ON COLUMN quarterly_income_statement.period_end IS
    'Real fiscal-period end date from the SEC XBRL fact (entry["end"]). NULL for rows written '
    'before migration 1256 until their next refresh. Use for chronological ordering instead of '
    '(fiscal_year, fiscal_quarter) - see migration 1256 header for why those two columns do not '
    'reliably sort in true chronological order for non-December-fiscal-year-end filers.';

COMMIT;
