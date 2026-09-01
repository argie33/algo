-- Migration 1254: Null out GRAL's stale cost_of_revenue values (sourced from a since-removed
-- CostsAndExpenses concept mapping) - real-money-readiness goal session, 2026-08-31.
--
-- Root cause: annual_income_statement.cost_of_revenue for GRAL (GRAIL, Inc., CIK 1699031)
-- currently holds $1,608,487,000 (FY2023) / $2,314,753,000 (FY2024) / $709,335,000 (FY2025) -
-- values that exactly match GRAL's real SEC XBRL "CostsAndExpenses" concept (TOTAL operating
-- costs and expenses: COGS + R&D + SG&A + everything), not a cost-of-revenue/COGS figure.
-- Live-confirmed via direct SEC companyfacts API fetch (CIK 1699031) - CostsAndExpenses is the
-- ONLY concept anywhere in GRAL's real filings with these exact values; no concept named
-- CostOfRevenue/CostOfSales/CostOfGoodsAndServicesSold/CostOfGoodsAndServiceExcluding...
-- exists for this filer at all. Result: GRAL's stored "cost of revenue" was 5-17x its real
-- revenue ($93.1M/$125.6M/$147.2M for the same years) - impossible for a real operating
-- company and an artifact of a stale write, not a real number.
--
-- Confirmed the CURRENT extraction code (utils/external/sec_statements.py) does NOT map
-- CostsAndExpenses to cost_of_revenue anywhere in its active concept list, and a live call to
-- get_income_statement(client, 'GRAL', period='annual') today returns no cost_of_revenue /
-- cost_of_goods_and_services_sold field for any fiscal year - the current code correctly
-- produces no value for this filer (GRAL simply doesn't tag a genuine COGS-style concept).
-- git log -S "CostsAndExpenses" over sec_statements.py/load_financial_statements.py found no
-- trace of it ever being wired to the cost_of_revenue target column in this repo's visible
-- history (likely predates it, or was introduced/removed within a single squash-merge - see
-- [[worktree_growth_multi_input_blend_12_fixes_recovered_to_main_20260831]]'s documented
-- --is-ancestor/squash-merge blind spot for why git history can miss this).
--
-- Why the DB never self-corrected: load_financial_statements.py's preserve_on_missing_fields
-- COALESCEs a missing fresh value against whatever already exists on ON CONFLICT DO UPDATE
-- (deliberate, for the legitimate "this run's fetch simply didn't produce a value for this
-- optional concept" case) - it cannot distinguish that from "this column's source concept was
-- REMOVED from the fetch list entirely and will never be repopulated again". Same bug class as
-- the BMA/ARS-currency stale-stockholders_equity fix landed the same day (see
-- load_financial_statements.py's fetch_incremental() 2026-08-31 comment), just for a removed
-- concept mapping instead of a currency-rejection guard.
--
-- Scope: cost_of_revenue ONLY. revenue/net_income/operating_income/EPS/shares for GRAL were
-- independently live-verified against real SEC data and are correct (operating_income_loss
-- -$1,515,382,000/-$2,189,158,000/-$562,163,000 for FY2023-2025 match exactly) - not touched
-- here. gross_profit is already NULL for GRAL (never computed, since cost_of_revenue was never
-- validly available) - unaffected. Deliberately NOT setting data_unavailable/reason at the
-- row level, matching migration 1225's precedent: these rows carry other real, required data
-- (revenue, net_income), so a row-level "unavailable" flag would incorrectly hide that.
--
-- This is a narrowly-scoped, single-symbol fix. A broader DB scan
-- (`cost_of_revenue > revenue * 5`) found 504 rows across many symbols with extreme
-- cost_of_revenue/revenue ratios, but manual spot-checking showed this mixes AT LEAST 2-3
-- distinct root causes (this CostsAndExpenses conflation; a separate revenue-mis-scaling
-- pattern visible in ANDE/EXC/KT/LSTR-shaped rows where revenue itself looks wrong by orders
-- of magnitude, not cost_of_revenue; and REIT-specific reporting quirks) - NOT bulk-fixed here,
-- left as an explicitly flagged open item needing its own dedicated per-pattern investigation
-- before any wider migration, per this codebase's established discipline against blind bulk
-- edits (see migration 1252's KT carve-out for the same reasoning).

BEGIN;

UPDATE annual_income_statement
   SET cost_of_revenue = NULL
 WHERE symbol = 'GRAL'
   AND fiscal_year IN (2023, 2024, 2025)
   AND cost_of_revenue IN (1608487000, 2314753000, 709335000);

COMMIT;
