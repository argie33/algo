-- Migration 1261: Null out orphaned, unconverted-local-currency long_term_debt values for
-- SKM (SK Telecom, Korea/KRW), BGDE, and AM (Antero Midstream).
-- Date: 2026-09-06 (goal session: "SEC/XBRL missing data to zero" / implausible-values audit)

-- ROOT CAUSE: same "once real, always real" preserve_on_missing_fields protection already
-- documented in migration 1250 (currency-guard-gap) and migration 1255 (never-tagged
-- concept) - just a third variant, this time on annual_balance_sheet.long_term_debt.
-- Live-confirmed via a direct call to utils/external/sec_statements.get_balance_sheet()
-- (current code, not historical): SKM's fresh extraction returns NO "long_term_debt" key
-- for ANY fiscal year (SK Telecom reports under the ifrs-full taxonomy with no matching
-- debt concept this pipeline's aliases currently resolve, distinct from migration 1255's
-- KT cost_of_revenue case - a different field, same filer family). BGDE/AM's fresh
-- extraction DOES correctly return sane long_term_debt for their current fiscal years
-- (BGDE FY2023/2024: ~$19-21M; AM FY2022-2024: ~$3.1-3.4B) - only their older, no-longer-
-- current rows (BGDE FY2022, AM FY2019) carry the orphaned stale value, matching migration
-- 1250's "self-heals for later years once a real concept starts resolving" shape exactly.
--
-- Live-verified stored (broken) vs. real-magnitude cross-check:
--   - SKM FY2022/2023/2024: long_term_debt stored as 7.19/7.42/6.57 TRILLION - the raw KRW
--     magnitude of SK Telecom's real ~$4.8-5.4B USD debt (at ~1,350-1,450 KRW/USD), never
--     divided down. total_liabilities on the SAME rows is correctly USD-scale (~$12.7-
--     15.2B), confirming this is an isolated single-field corruption, not a whole-row
--     currency failure - annual_income_statement.revenue for the same fiscal years is also
--     correctly USD-converted ($12.16-13.73B, matching SK Telecom's real revenue).
--   - BGDE FY2022: long_term_debt stored as 28.12 TRILLION vs FY2023/2024's real ~$19-21M -
--     a >1,000,000x jump only explicable as the same orphaned-raw-currency artifact.
--   - AM FY2019: long_term_debt stored as 2.89 TRILLION vs FY2022-2024's real ~$3.1-3.4B -
--     same shape.
--
-- Downstream impact before this fix (SecValuationsLoader.fetch_incremental, live-verified):
-- SKM enterprise_value $6.58 TRILLION / ev_ebitda 5740.37 / ev_revenue 541.02 on a real
-- $14.86B market cap - after nulling, enterprise_value $14.66B / ev_ebitda 12.79 /
-- ev_revenue 1.21, all now plausible for a real telecom.
--
-- SKM's is the only one of these three affecting LIVE scoring today (its most recent 3
-- fiscal years are ALL bad, so any anchor-year selection hits one) - BGDE/AM's bad years
-- are already older than their current anchor year and don't feed live valuations, fixed
-- here anyway for correctness/consistency with the 1250/1255 precedent of cleaning up the
-- full orphaned population rather than only the currently-load-bearing rows.
--
-- Only long_term_debt is touched - total_liabilities, total_assets, stockholders_equity,
-- and every other field on these rows are correctly extracted and current (verified via a
-- live get_balance_sheet() call for each symbol before writing this migration), so
-- data_unavailable/reason are deliberately left alone, same discipline as migration 1255.

BEGIN;

UPDATE annual_balance_sheet
   SET long_term_debt = NULL
 WHERE (
         (symbol = 'SKM' AND fiscal_year IN (2022, 2023, 2024))
         OR (symbol = 'BGDE' AND fiscal_year = 2022)
         OR (symbol = 'AM' AND fiscal_year = 2019)
       )
   AND long_term_debt IS NOT NULL;

COMMIT;
