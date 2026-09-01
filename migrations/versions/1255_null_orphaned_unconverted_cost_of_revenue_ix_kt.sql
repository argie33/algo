-- Migration 1255: Null out orphaned, unconverted-local-currency cost_of_revenue/
-- gross_profit values for IX (Orix Corp, Japan/JPY) and KT (KT Corp, Korea/KRW).
-- Date: 2026-08-31 (goal session: "get all the data we need" full-coverage audit)

-- ROOT CAUSE: unlike migration 1250's poisoned symbols, IX/KT's "revenue" IS correctly
-- FX-converted (both JPY and KRW are whitelisted in MAJOR_CURRENCIES) - this is not the
-- same currency-guard-gap bug class. Live-confirmed via real SEC companyfacts JSON: KT
-- (CIK 892450) tags ZERO cost-of-sales/COGS-related XBRL concepts under either us-gaap or
-- ifrs-full (checked all concepts containing "cost" + "sale"/"revenue"/"good"/"service" -
-- only unrelated pension-cost concepts exist). IX's own get_income_statement() extraction
-- for FY2023 likewise returns no cost_of_revenue-mapped key at all. The trillion-scale
-- values stored for these rows (KT: ~9.4-9.7 trillion KRW-equivalent; IX: ~0.84-2.9
-- trillion JPY-equivalent) cannot be reproduced by any current extraction path - they are
-- orphaned leftovers from an earlier, no-longer-existing extraction mechanism (predating
-- this pipeline's per-concept currency guard, same "once real, always real"
-- preserve_on_missing_fields protection migration 1250 already documents, just for a
-- concept this filer never actually reports rather than a currency-guard rejection).
--
-- migration 1250's own header explicitly (and, per this session's live re-verification,
-- WRONGLY) assumed KT "self-heals via the existing already_available rescue on next
-- loader run - only a single stale FY2015 raw-value row remains there, low-priority/old".
-- That assumption only holds if a real concept exists to eventually re-fetch; since KT
-- reports no COGS concept AT ALL, a fresh extraction can never overwrite the stale value
-- with a corrected one - "self-heal" was never going to happen for this specific field,
-- and it has since grown to affect FY2022-2024 (gross_profit too), not just FY2015.
--
-- IX was not mentioned in migration 1250 at all - a new finding this session. IX shows an
-- unusual alternating pattern (FY2017-2020 have real, plausible cost_of_revenue in the
-- $4-4.5B range; FY2008-2016 and FY2021-2026 are the trillion-scale orphaned values) -
-- this migration's magnitude-ratio filter (cost_of_revenue > revenue * 50) naturally
-- targets only the genuinely-implausible years and leaves the correctly-populated
-- FY2017-2020 rows untouched, without needing to hardcode a year list.
--
-- Only cost_of_revenue/gross_profit are touched - revenue, net_income, and every other
-- field on these rows are correctly extracted and current, so data_unavailable/reason are
-- deliberately left alone (the row as a whole is NOT unavailable, just these two specific
-- fields, and this table has no per-field reason column to record a narrower marker).
-- Scoped to annual_income_statement only - quarterly_income_statement has zero matching
-- rows for these two symbols (checked live before writing this migration).

BEGIN;

UPDATE annual_income_statement
   SET cost_of_revenue = NULL, gross_profit = NULL
 WHERE symbol IN ('IX', 'KT')
   AND revenue > 0
   AND cost_of_revenue > revenue * 50
   AND (cost_of_revenue IS NOT NULL OR gross_profit IS NOT NULL);

COMMIT;
